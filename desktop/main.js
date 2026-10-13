// LLM Local - app desktop.
// Roda o servidor Python escondido, fica na bandeja do sistema e abre a
// "pergunta rapida" por um atalho global.
const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, nativeImage, screen, shell, dialog, Notification } = require("electron");
const path = require("path");
const fs = require("fs");
const http = require("http");
const { spawn, spawnSync } = require("child_process");

const PORT = 8765;
const BASE = `http://127.0.0.1:${PORT}`;
const PY_APP = app.isPackaged ? path.join(process.resourcesPath, "app") : path.join(__dirname, "..", "app");
const ICON = path.join(__dirname, "icon.png");
const TRAY_ICON = path.join(__dirname, "icon-tray.png");
const CONFIG_FILE = path.join(app.getPath("userData"), "config.json");
const LOG_FILE = path.join(app.getPath("userData"), "server.log");
const QUICK_W = 720;

let mainWin = null, quickWin = null, tray = null, server = null;
let quitting = false, quickPinned = false, quickHiddenAt = 0, trayHintShown = false;
let config = { homeDir: "", hotkey: "Ctrl+Shift+Space", autoStart: true, quickHideOnBlur: true };

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) app.quit();
app.on("second-instance", (_e, argv) => argv.includes("--quick") ? showQuick() : showMain());
app.setAppUserModelId("studio.piphin.llmlocal");

// ------------------------------------------------------------------ config
function loadConfig() {
  try { config = { ...config, ...JSON.parse(fs.readFileSync(CONFIG_FILE, "utf8").replace(/^\uFEFF/, "")) }; } catch {}
}
function saveConfig() {
  fs.mkdirSync(path.dirname(CONFIG_FILE), { recursive: true });
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2));
}

async function askHomeDir(firstRun) {
  const def = path.join(app.getPath("home"), "LLM Local");
  if (firstRun) {
    const r = await dialog.showMessageBox({
      type: "question", title: "LLM Local", icon: nativeImage.createFromPath(ICON),
      message: "Onde guardar os modelos, o motor e as conversas?",
      detail: `Os modelos costumam ter de 3 a 20 GB cada, então prefira um disco com bastante espaço.\n\nPasta padrão: ${def}`,
      buttons: ["Usar a pasta padrão", "Escolher outra pasta..."], defaultId: 0, cancelId: 0, noLink: true,
    });
    if (r.response === 0) return def;
  }
  const r = await dialog.showOpenDialog({ title: "Pasta de dados do LLM Local", properties: ["openDirectory", "createDirectory"],
    defaultPath: config.homeDir || def });
  return r.canceled ? (firstRun ? def : null) : r.filePaths[0];
}

// ------------------------------------------------------------------ servidor Python
function findPython() {
  const cands = [["python", []], ["py", ["-3"]], ["python3", []]];
  for (const [cmd, args] of cands) {
    try {
      const r = spawnSync(cmd, [...args, "-c", "import sys;print(sys.version_info>=(3,9))"], { windowsHide: true, encoding: "utf8", timeout: 15000 });
      if (r.status === 0 && r.stdout.trim() === "True") return [cmd, args];
    } catch {}
  }
  return null;
}

function ping(urlPath = "/api/status", timeout = 1500) {
  return new Promise(resolve => {
    const req = http.get(BASE + urlPath, { timeout }, res => {
      let body = ""; res.on("data", d => body += d); res.on("end", () => resolve(res.statusCode === 200 ? body : null));
    });
    req.on("error", () => resolve(null)); req.on("timeout", () => { req.destroy(); resolve(null); });
  });
}

async function startServer() {
  if (await ping()) return true; // ja tem um servidor rodando
  const py = findPython();
  if (!py) {
    const r = await dialog.showMessageBox({ type: "error", title: "LLM Local",
      message: "Python não encontrado",
      detail: "O LLM Local precisa do Python 3.9 ou mais novo.\nInstale em python.org marcando a opção \"Add python.exe to PATH\" e abra o app de novo.",
      buttons: ["Abrir python.org", "Fechar"] });
    if (r.response === 0) shell.openExternal("https://www.python.org/downloads/");
    return false;
  }
  fs.mkdirSync(config.homeDir, { recursive: true });
  const log = fs.createWriteStream(LOG_FILE, { flags: "w" });
  server = spawn(py[0], [...py[1], path.join(PY_APP, "server.py")], {
    cwd: PY_APP, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, LLM_HOME: config.homeDir, LLM_PORT: String(PORT), LLM_PARENT_PID: String(process.pid),
           PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1" },
  });
  server.stdout.pipe(log); server.stderr.pipe(log);
  server.on("exit", code => {
    server = null;
    if (!quitting) dialog.showErrorBox("LLM Local", `O servidor interno parou (código ${code}).\nVeja o log em:\n${LOG_FILE}`);
  });
  for (let i = 0; i < 60; i++) {
    if (await ping()) return true;
    await new Promise(r => setTimeout(r, 300));
  }
  dialog.showErrorBox("LLM Local", `O servidor interno não respondeu.\nVeja o log em:\n${LOG_FILE}`);
  return false;
}

function stopServer() {
  if (!server) return;
  const pid = server.pid; server = null;
  // encerra a arvore toda (python + llama-server)
  try { spawnSync("taskkill", ["/pid", String(pid), "/T", "/F"], { windowsHide: true }); } catch {}
}

// ------------------------------------------------------------------ janelas
const prefs = { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: true };

function guardLinks(win) {
  // links externos abrem no navegador padrao, nunca dentro do app
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url) && !url.startsWith(BASE)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith(BASE)) { e.preventDefault(); if (/^https?:\/\//.test(url)) shell.openExternal(url); }
  });
}

function createMain(show) {
  mainWin = new BrowserWindow({ width: 1240, height: 820, minWidth: 720, minHeight: 500, show: false, title: "LLM Local",
    icon: ICON, backgroundColor: "#0f1014", autoHideMenuBar: true, webPreferences: prefs });
  mainWin.removeMenu();
  guardLinks(mainWin);
  mainWin.loadURL(BASE + "/");
  if (show) mainWin.once("ready-to-show", () => { mainWin.show(); if (mainWin.isMinimized()) mainWin.restore(); mainWin.focus(); });
  mainWin.on("close", e => {
    if (quitting) return;
    e.preventDefault(); mainWin.hide();
    if (!trayHintShown && Notification.isSupported()) {
      trayHintShown = true;
      new Notification({ title: "LLM Local continua rodando", icon: ICON,
        body: `Use ${prettyKey(config.hotkey)} para uma pergunta rápida. Para sair, clique com o botão direito no ícone perto do relógio.` }).show();
    }
  });
}

function showMain(chatId) {
  if (!mainWin) createMain(false);
  if (chatId && /^[\w-]+$/.test(chatId)) mainWin.webContents.executeJavaScript(`location.hash = "chat=${chatId}"`).catch(() => {});
  if (mainWin.isMinimized()) mainWin.restore();
  mainWin.show(); mainWin.focus();
}

function createQuick() {
  quickWin = new BrowserWindow({ width: QUICK_W, height: 96, show: false, frame: false, transparent: true, resizable: false,
    alwaysOnTop: true, skipTaskbar: true, fullscreenable: false, maximizable: false, minimizable: false,
    hasShadow: false, title: "Pergunta rápida", icon: ICON, webPreferences: prefs });
  quickWin.setAlwaysOnTop(true, "floating");
  guardLinks(quickWin);
  quickWin.loadURL(BASE + "/quick.html");
  quickWin.on("blur", () => { if (config.quickHideOnBlur && !quickPinned) hideQuick(); });
}

function showQuick() {
  if (!quickWin) createQuick();
  const d = screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea;
  const [, h] = quickWin.getSize();
  quickWin.setBounds({ x: Math.round(d.x + (d.width - QUICK_W) / 2), y: Math.round(d.y + d.height * 0.16), width: QUICK_W, height: h });
  quickWin.show(); quickWin.focus();
  quickWin.webContents.send("quick-show", { hiddenFor: quickHiddenAt ? Date.now() - quickHiddenAt : 0 });
}

function hideQuick() {
  if (quickWin?.isVisible()) { quickWin.hide(); quickHiddenAt = Date.now(); }
}

function toggleQuick() {
  if (quickWin?.isVisible() && quickWin.isFocused()) hideQuick(); else showQuick();
}

// ------------------------------------------------------------------ atalho global
const prettyKey = k => k.replace(/Space/g, "Espaço").replace(/CommandOrControl|Control/g, "Ctrl");
function toAccelerator(k) {
  return k.replace(/\bArrow(Up|Down|Left|Right)\b/g, "$1").replace(/\bEscape\b/g, "Esc");
}
function registerHotkey(k) {
  try { return globalShortcut.register(toAccelerator(k), toggleQuick); } catch { return false; }
}

// ------------------------------------------------------------------ bandeja
let lastTrayState = "";
async function updateTray() {
  if (!tray) return;
  let st = null;
  try { st = JSON.parse(await ping("/api/status") || "null"); } catch {}
  const e = st?.engine || { state: "offline" };
  const name = st ? ((st.models.find(m => m.path === e.model) || {}).name || e.model) : "";
  const label = { ready: `● ${name}`, loading: `Carregando ${name}...`, stopped: "Nenhum modelo carregado", error: "Erro no motor", offline: "Servidor offline" }[e.state];
  const sig = [label, config.autoStart, config.hotkey].join("|");
  if (sig === lastTrayState) return;
  lastTrayState = sig;
  tray.setToolTip("LLM Local - " + label);
  const lastModel = st?.settings?.last_model;
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Abrir LLM Local", click: () => showMain() },
    { label: `Pergunta rápida\t${prettyKey(config.hotkey)}`, click: showQuick },
    { type: "separator" },
    { label, enabled: false },
    e.state === "ready" || e.state === "loading"
      ? { label: "Descarregar modelo (liberar GPU)", click: () => post("/api/unload") }
      : { label: "Carregar último modelo", enabled: !!lastModel, click: () => post("/api/load", { model: lastModel }) },
    { type: "separator" },
    { label: "Iniciar com o Windows", type: "checkbox", checked: config.autoStart, click: i => setOption("autoStart", i.checked) },
    { label: "Abrir pasta de dados", click: () => shell.openPath(config.homeDir) },
    { type: "separator" },
    { label: "Sair", click: () => { quitting = true; app.quit(); } },
  ]));
}

function post(urlPath, body = {}) {
  return new Promise(resolve => {
    const data = JSON.stringify(body);
    const req = http.request(BASE + urlPath, { method: "POST", headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) } },
      res => { res.resume(); res.on("end", () => { lastTrayState = ""; updateTray(); resolve(); }); });
    req.on("error", () => resolve()); req.end(data);
  });
}

// ------------------------------------------------------------------ opcoes
function setOption(key, value) {
  config[key] = value; saveConfig();
  if (key === "autoStart") applyAutoStart();
  lastTrayState = ""; updateTray();
}
function applyAutoStart() {
  if (!app.isPackaged) return; // so no app instalado
  app.setLoginItemSettings({ openAtLogin: config.autoStart, args: ["--hidden"] });
}

ipcMain.handle("get-config", () => ({ ...config, hotkeyLabel: prettyKey(config.hotkey) }));
ipcMain.handle("set-hotkey", (_e, k) => {
  if (!k || k === config.hotkey) return { ok: true, hotkey: config.hotkey };
  globalShortcut.unregisterAll();
  if (registerHotkey(k)) { config.hotkey = k; saveConfig(); lastTrayState = ""; updateTray(); return { ok: true, hotkey: k }; }
  registerHotkey(config.hotkey);
  return { ok: false, hotkey: config.hotkey };
});
ipcMain.handle("set-option", (_e, key, value) => { if (["autoStart", "quickHideOnBlur"].includes(key)) setOption(key, !!value); });
ipcMain.handle("choose-home", async () => {
  const dir = await askHomeDir(false);
  if (!dir || dir === config.homeDir) return null;
  config.homeDir = dir; saveConfig();
  stopServer();
  quitting = true; await new Promise(r => setTimeout(r, 800)); quitting = false;
  if (await startServer()) { mainWin?.reload(); quickWin?.reload(); }
  return dir;
});
ipcMain.on("open-main", (_e, chatId) => { hideQuick(); showMain(chatId); });
ipcMain.on("hide-quick", hideQuick);
ipcMain.on("quick-pinned", (_e, v) => { quickPinned = !!v; });
ipcMain.on("resize-quick", (_e, h) => {
  if (!quickWin) return;
  const height = Math.max(70, Math.min(760, Math.round(h)));
  const b = quickWin.getBounds();
  if (b.height !== height) quickWin.setBounds({ ...b, width: QUICK_W, height });
});

// ------------------------------------------------------------------ inicio
app.whenReady().then(async () => {
  if (!gotLock) return;
  loadConfig();
  const firstRun = !config.homeDir;
  if (firstRun) { config.homeDir = await askHomeDir(true); saveConfig(); applyAutoStart(); }
  if (!(await startServer())) { quitting = true; return app.quit(); }

  tray = new Tray(nativeImage.createFromPath(TRAY_ICON));
  tray.on("click", () => showMain());
  updateTray(); setInterval(updateTray, 4000);

  if (!registerHotkey(config.hotkey)) {
    dialog.showMessageBox({ type: "warning", title: "LLM Local", message: `O atalho ${prettyKey(config.hotkey)} já está em uso por outro programa.`,
      detail: "Escolha outro em Configurações → App desktop." });
  }
  createQuick();
  const hidden = process.argv.includes("--hidden");
  createMain(!hidden);
  if (process.argv.includes("--quick")) showQuick();
});

app.on("window-all-closed", e => e.preventDefault?.()); // continua na bandeja
app.on("before-quit", () => { quitting = true; });
app.on("will-quit", () => { globalShortcut.unregisterAll(); stopServer(); });
