// LLM Local - app desktop.
// Roda o servidor Python escondido, fica na bandeja do sistema e abre a
// "pergunta rapida" por um atalho global.
const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, nativeImage, screen, shell, dialog, Notification, session, desktopCapturer, clipboard } = require("electron");
const path = require("path");
const fs = require("fs");
const http = require("http");
const { spawn, spawnSync } = require("child_process");

const PORT = Number(process.env.LLM_PORT) || 8765; // LLM_PORT: porta alternativa (desenvolvimento)
const BASE = `http://127.0.0.1:${PORT}`;
const PY_APP = app.isPackaged ? path.join(process.resourcesPath, "server") : path.join(__dirname, "..", "app");
const ICON = path.join(__dirname, "icon.png");
const TRAY_ICON = path.join(__dirname, "icon-tray.png");
const CONFIG_FILE = path.join(app.getPath("userData"), "config.json");
const LOG_FILE = path.join(app.getPath("userData"), "server.log");
const QUICK_W = 720;

let mainWin = null, quickWin = null, tray = null, server = null;

// ------------------------------------------------------------------ idioma (bandeja, avisos e janelas do sistema)
// O idioma vem das Configurações do app (settings.language); antes do servidor subir, usa o do Windows.
const MAIN_I18N = {
  "A janela do LLM Local parou de responder.": ["The LLM Local window stopped responding.", "La ventana de LLM Local dejó de responder."],
  "Isso costuma acontecer quando a memória da placa de vídeo enche ou uma resposta muito longa está sendo desenhada. O ocorrido foi salvo no relatório de diagnóstico.": ["This usually happens when the graphics card memory is full or a very long answer is being drawn. It was saved in the diagnostic report.", "Esto suele pasar cuando la memoria de la tarjeta gráfica se llena o se está dibujando una respuesta muy larga. Se guardó en el informe de diagnóstico."],
  "Recarregar a janela": ["Reload the window", "Recargar la ventana"],
  "Esperar": ["Wait", "Esperar"],
  "Fechar o LLM Local": ["Close LLM Local", "Cerrar LLM Local"],
  "Abrir relatório de diagnóstico": ["Open diagnostic report", "Abrir informe de diagnóstico"],
  "Abrir LLM Local": ["Open LLM Local", "Abrir LLM Local"],
  "Pergunta rápida": ["Quick ask", "Pregunta rápida"],
  "Descarregar modelos (liberar GPU)": ["Unload models (free the GPU)", "Descargar modelos (liberar la GPU)"],
  "Carregar último modelo": ["Load last model", "Cargar último modelo"],
  "Iniciar com o Windows": ["Start with Windows", "Iniciar con Windows"],
  "Abrir pasta de dados": ["Open data folder", "Abrir carpeta de datos"],
  "Criar atalhos (Menu Iniciar e Área de Trabalho)": ["Create shortcuts (Start Menu and Desktop)", "Crear accesos directos (Menú Inicio y Escritorio)"],
  "Atalhos criados.": ["Shortcuts created.", "Accesos directos creados."],
  "Reiniciar e atualizar para {v}": ["Restart and update to {v}", "Reiniciar y actualizar a {v}"],
  "Baixar o pacote da versão {v}": ["Download the package for version {v}", "Descargar el paquete de la versión {v}"],
  "Baixando atualização {v} ({p}%)": ["Downloading update {v} ({p}%)", "Descargando actualización {v} ({p}%)"],
  "Verificar atualizações (versão {v})": ["Check for updates (version {v})", "Buscar actualizaciones (versión {v})"],
  "Sair": ["Quit", "Salir"],
  "Carregando {name}...": ["Loading {name}...", "Cargando {name}..."],
  "Nenhum modelo carregado": ["No model loaded", "Ningún modelo cargado"],
  "Erro no motor": ["Engine error", "Error del motor"],
  "Servidor offline": ["Server offline", "Servidor desconectado"],
  "LLM Local continua rodando": ["LLM Local is still running", "LLM Local sigue en ejecución"],
  "Use {k} para uma pergunta rápida. Para sair, clique com o botão direito no ícone perto do relógio.": ["Use {k} for a quick question. To quit, right-click the icon next to the clock.", "Usa {k} para una pregunta rápida. Para salir, haz clic derecho en el ícono junto al reloj."],
  "Atualização do LLM Local": ["LLM Local update", "Actualización de LLM Local"],
  "A versão {v} precisa do pacote completo. Abra Configurações → App desktop.": ["Version {v} needs the full package. Open Settings → Desktop app.", "La versión {v} necesita el paquete completo. Abre Configuración → App de escritorio."],
  "Baixando a versão {v} em segundo plano...": ["Downloading version {v} in the background...", "Descargando la versión {v} en segundo plano..."],
  "A versão {v} do LLM Local está pronta.": ["LLM Local version {v} is ready.", "La versión {v} de LLM Local está lista."],
  "Reinicie para atualizar agora. Se preferir, a atualização será aplicada quando você fechar o app.": ["Restart to update now. Or the update will be applied when you close the app.", "Reinicia para actualizar ahora. Si prefieres, la actualización se aplicará al cerrar la app."],
  "Reiniciar e atualizar": ["Restart and update", "Reiniciar y actualizar"],
  "Depois": ["Later", "Después"],
  "Criar atalhos do LLM Local?": ["Create LLM Local shortcuts?", "¿Crear accesos directos de LLM Local?"],
  "No Menu Iniciar e na Área de Trabalho, apontando para:\n{p}\n\nDeixe a pasta do app onde ela está (se mover, crie os atalhos de novo pelo menu do ícone perto do relógio).": ["In the Start Menu and on the Desktop, pointing to:\n{p}\n\nKeep the app folder where it is (if you move it, create the shortcuts again from the menu of the icon next to the clock).", "En el Menú Inicio y en el Escritorio, apuntando a:\n{p}\n\nDeja la carpeta de la app donde está (si la mueves, vuelve a crear los accesos desde el menú del ícono junto al reloj)."],
  "Criar atalhos": ["Create shortcuts", "Crear accesos directos"],
  "Agora não": ["Not now", "Ahora no"],
  "Não foi possível criar os atalhos.": ["Couldn't create the shortcuts.", "No se pudieron crear los accesos directos."],
  "Salvar arquivo": ["Save file", "Guardar archivo"],
  "Escolha uma pasta para o Codex trabalhar": ["Choose a folder for Codex to work in", "Elige una carpeta para que Codex trabaje"],
  "Onde guardar os modelos, o motor e as conversas?": ["Where should models, the engine and chats be stored?", "¿Dónde guardar los modelos, el motor y las conversaciones?"],
  "Os modelos costumam ter de 3 a 20 GB cada, então prefira um disco com bastante espaço.\n\nPasta padrão: {d}": ["Models are usually 3 to 20 GB each, so prefer a drive with plenty of space.\n\nDefault folder: {d}", "Los modelos suelen tener de 3 a 20 GB cada uno, así que prefiere un disco con bastante espacio.\n\nCarpeta predeterminada: {d}"],
  "Usar a pasta padrão": ["Use the default folder", "Usar la carpeta predeterminada"],
  "Escolher outra pasta...": ["Choose another folder...", "Elegir otra carpeta..."],
  "Pasta de dados do LLM Local": ["LLM Local data folder", "Carpeta de datos de LLM Local"],
  "O atalho {k} já está em uso por outro programa.": ["The shortcut {k} is already used by another program.", "El atajo {k} ya lo usa otro programa."],
  "Escolha outro em Configurações → App desktop.": ["Choose another one in Settings → Desktop app.", "Elige otro en Configuración → App de escritorio."],
};
let uiLang = null;
const curLang = () => {
  if (uiLang) return uiLang;
  const l = (app.getLocale() || "").toLowerCase();
  return l.startsWith("pt") ? "pt-BR" : l.startsWith("es") ? "es" : "en";
};
function tm(key, vars) {
  const lang = curLang();
  let s = lang === "pt-BR" ? key : (MAIN_I18N[key]?.[lang === "en" ? 0 : 1] ?? key);
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => vars[k] ?? m);
  return s;
}
let quitting = false, quickPinned = false, quickHiddenAt = 0, trayHintShown = false;
let config = { homeDir: "", hotkey: "Ctrl+Shift+Space", voiceHotkey: "Ctrl+Alt+Space", screenHotkey: "Ctrl+Alt+S", autoStart: true, quickHideOnBlur: true };

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
      message: tm("Onde guardar os modelos, o motor e as conversas?"),
      detail: tm("Os modelos costumam ter de 3 a 20 GB cada, então prefira um disco com bastante espaço.\n\nPasta padrão: {d}", { d: def }),
      buttons: [tm("Usar a pasta padrão"), tm("Escolher outra pasta...")], defaultId: 0, cancelId: 0, noLink: true,
    });
    if (r.response === 0) return def;
  }
  const r = await dialog.showOpenDialog({ title: tm("Pasta de dados do LLM Local"), properties: ["openDirectory", "createDirectory"],
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

// ------------------------------------------------------------------ diagnóstico e "salva-vidas"
// Registra travamentos da janela, quedas de processos e eventos do servidor em diagnostico.log
// (pasta %APPDATA%\LLM Local). Se a janela parar de responder, oferece recarregar ou fechar.
const DIAG_FILE = () => path.join(app.getPath("userData"), "diagnostico.log");
function diag(msg) {
  try {
    const f = DIAG_FILE();
    if (fs.existsSync(f) && fs.statSync(f).size > 1024 * 1024) fs.renameSync(f, f + ".old"); // guarda só ~1 MB recente
    fs.appendFile(f, `${new Date().toISOString()} ${msg}\n`, () => {});
  } catch {}
}
async function serverSnapshot() {
  try {
    const st = await new Promise((res, rej) => {
      const r = http.get(BASE + "/api/diag", { timeout: 3000 }, x => { let d = ""; x.on("data", c => d += c); x.on("end", () => res(d)); });
      r.on("timeout", () => r.destroy(new Error("timeout"))); r.on("error", rej);
    });
    return st.slice(0, 2000);
  } catch (e) { return `servidor sem resposta (${e.message})`; }
}
function watchWindow(win, name) {
  let timer = null, asked = false;
  win.webContents.on("unresponsive", async () => {
    diag(`[${name}] janela parou de responder | ${await serverSnapshot()}`);
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (asked || win.isDestroyed()) return;
      asked = true;
      const { response } = await dialog.showMessageBox({ type: "warning", title: "LLM Local", noLink: true, defaultId: 0, cancelId: 1,
        message: tm("A janela do LLM Local parou de responder."),
        detail: tm("Isso costuma acontecer quando a memória da placa de vídeo enche ou uma resposta muito longa está sendo desenhada. O ocorrido foi salvo no relatório de diagnóstico."),
        buttons: [tm("Recarregar a janela"), tm("Esperar"), tm("Fechar o LLM Local")] });
      asked = false;
      if (win.isDestroyed()) return;
      if (response === 0) { diag(`[${name}] recarregada pelo usuário`); win.webContents.forcefullyCrashRenderer(); win.webContents.reload(); }
      if (response === 2) { diag(`[${name}] app fechado pelo usuário após travar`); forceQuit(); }
    }, 7000);
  });
  win.webContents.on("responsive", () => { clearTimeout(timer); diag(`[${name}] voltou a responder`); });
  win.webContents.on("render-process-gone", (_e, d) => {
    diag(`[${name}] processo da janela caiu: ${d.reason} (código ${d.exitCode})`);
    if (!win.isDestroyed() && d.reason !== "clean-exit") setTimeout(() => !win.isDestroyed() && win.webContents.reload(), 1000);
  });
}
app.on("child-process-gone", (_e, d) => diag(`processo ${d.type} caiu: ${d.reason} (código ${d.exitCode})${d.type === "GPU" ? " | possível falta de memória de vídeo" : ""}`));
// sair de qualquer jeito: encerra o servidor e os motores e fecha o app sem esperar as janelas
function forceQuit() {
  quitting = true;
  try { if (server?.pid) spawnSync("taskkill", ["/pid", String(server.pid), "/T", "/F"], { windowsHide: true }); } catch {}
  app.exit(0);
}
ipcMain.on("diag", (_e, msg) => diag(`[janela] ${String(msg).slice(0, 500)}`));
ipcMain.handle("open-diag", () => { const f = DIAG_FILE(); if (!fs.existsSync(f)) fs.writeFileSync(f, ""); shell.showItemInFolder(f); });

function createMain(show) {
  mainWin = new BrowserWindow({ width: 1240, height: 820, minWidth: 720, minHeight: 500, show: false, title: "LLM Local",
    icon: ICON, backgroundColor: "#0f1014", autoHideMenuBar: true, webPreferences: prefs });
  mainWin.removeMenu();
  guardLinks(mainWin);
  mainWin.loadURL(BASE + "/");
  watchWindow(mainWin, "principal");
  if (show) mainWin.once("ready-to-show", () => { mainWin.show(); if (mainWin.isMinimized()) mainWin.restore(); mainWin.focus(); });
  mainWin.on("close", e => {
    if (quitting) return;
    e.preventDefault(); mainWin.hide();
    if (!trayHintShown && Notification.isSupported()) {
      trayHintShown = true;
      new Notification({ title: tm("LLM Local continua rodando"), icon: ICON,
        body: tm("Use {k} para uma pergunta rápida. Para sair, clique com o botão direito no ícone perto do relógio.", { k: prettyKey(config.hotkey) }) }).show();
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
  watchWindow(quickWin, "pergunta rápida");
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
function registerHotkey(k, fn = toggleQuick) {
  try { return globalShortcut.register(toAccelerator(k), fn); } catch { return false; }
}
// atalho de voz: abre a pergunta rápida e começa a gravar; apertar de novo envia
function voiceShortcut() {
  if (!quickWin?.isVisible()) showQuick();
  quickWin.webContents.send("quick-voice");
}

// contexto da tela: captura o monitor onde está o mouse (sem a janela da pergunta rápida)
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function captureScreen() {
  const wasVisible = quickWin?.isVisible();
  if (wasVisible) { quickWin.setOpacity(0); quickWin.hide(); await sleep(250); }
  try {
    const disp = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
    const w = Math.round(disp.size.width * disp.scaleFactor), h = Math.round(disp.size.height * disp.scaleFactor);
    const sources = await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: w, height: h } });
    const src = sources.find(s => s.display_id === String(disp.id)) || sources[0];
    if (!src || src.thumbnail.isEmpty()) return null;
    let img = src.thumbnail;
    if (img.getSize().width > 1920) img = img.resize({ width: 1920, quality: "best" }); // o modelo de visão não precisa de mais
    return img.toJPEG(88);
  } finally {
    if (wasVisible) { quickWin.show(); quickWin.setOpacity(1); quickWin.focus(); }
  }
}
// atalho de tela: captura primeiro e depois abre a pergunta rápida com o print anexado
async function screenShortcut() {
  const visible = quickWin?.isVisible();
  let jpg = null;
  try { jpg = await captureScreen(); } catch {}
  if (!visible) showQuick();
  if (jpg) quickWin.webContents.send("quick-context", { kind: "screen", data: jpg });
}
ipcMain.handle("capture-screen", async () => { try { return await captureScreen(); } catch { return null; } });
ipcMain.handle("read-clipboard", () => {
  const img = clipboard.readImage();
  return { text: clipboard.readText(), image: img.isEmpty() ? null : img.toPNG() };
});
ipcMain.handle("set-screen-hotkey", (_e, k) => {
  if (!k || k === config.screenHotkey) return { ok: true, hotkey: config.screenHotkey };
  try { globalShortcut.unregister(toAccelerator(config.screenHotkey)); } catch {}
  if (registerHotkey(k, screenShortcut)) { config.screenHotkey = k; saveConfig(); return { ok: true, hotkey: k }; }
  registerHotkey(config.screenHotkey, screenShortcut);
  return { ok: false, hotkey: config.screenHotkey };
});

// ------------------------------------------------------------------ bandeja
let lastTrayState = "";
async function updateTray() {
  if (!tray) return;
  let st = null;
  try { st = JSON.parse(await ping("/api/status") || "null"); } catch {}
  const e = st?.engine || { state: "offline" };
  const name = st ? ((st.models.find(m => m.path === e.model) || {}).name || e.model) : "";
  if (st?.settings) uiLang = st.settings.language || uiLang;
  const label = { ready: `● ${name}`, loading: tm("Carregando {name}...", { name }), stopped: tm("Nenhum modelo carregado"), error: tm("Erro no motor"), offline: tm("Servidor offline") }[e.state];
  const sig = [label, config.autoStart, config.hotkey, updateState.status, updateState.percent, curLang()].join("|");
  if (sig === lastTrayState) return;
  lastTrayState = sig;
  tray.setToolTip("LLM Local - " + label);
  const lastModel = st?.settings?.last_model;
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: tm("Abrir LLM Local"), click: () => showMain() },
    { label: `${tm("Pergunta rápida")}\t${prettyKey(config.hotkey)}`, click: showQuick },
    { type: "separator" },
    { label, enabled: false },
    e.state === "ready" || e.state === "loading"
      ? { label: tm("Descarregar modelos (liberar GPU)"), click: () => post("/api/unload", { all: true }) }
      : { label: tm("Carregar último modelo"), enabled: !!lastModel, click: () => post("/api/load", { model: lastModel }) },
    { type: "separator" },
    { label: tm("Iniciar com o Windows"), type: "checkbox", checked: config.autoStart, click: i => setOption("autoStart", i.checked) },
    { label: tm("Abrir pasta de dados"), click: () => shell.openPath(config.homeDir) },
    { label: tm("Criar atalhos (Menu Iniciar e Área de Trabalho)"), visible: app.isPackaged, click: () => { if (createShortcuts()) new Notification({ title: "LLM Local", body: tm("Atalhos criados."), icon: ICON }).show(); } },
    updateState.status === "ready"
      ? { label: tm("Reiniciar e atualizar para {v}", { v: updateState.version }), click: installUpdate }
      : updateState.status === "manual"
        ? { label: tm("Baixar o pacote da versão {v}", { v: updateState.version }), click: installUpdate }
      : updateState.status === "downloading"
        ? { label: tm("Baixando atualização {v} ({p}%)", { v: updateState.version, p: updateState.percent }), enabled: false }
        : { label: tm("Verificar atualizações (versão {v})", { v: app.getVersion() }), click: checkForUpdates },
    { type: "separator" },
    { label: tm("Recarregar a janela"), click: () => { if (mainWin && !mainWin.isDestroyed()) { mainWin.webContents.forcefullyCrashRenderer(); mainWin.webContents.reload(); showMain(); } } },
    { label: tm("Abrir relatório de diagnóstico"), click: () => { const f = DIAG_FILE(); if (!fs.existsSync(f)) fs.writeFileSync(f, ""); shell.showItemInFolder(f); } },
    { label: tm("Sair"), click: () => { quitting = true; app.quit(); setTimeout(forceQuit, 5000); } },
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
  try { globalShortcut.unregister(toAccelerator(config.hotkey)); } catch {}
  if (registerHotkey(k)) { config.hotkey = k; saveConfig(); lastTrayState = ""; updateTray(); return { ok: true, hotkey: k }; }
  registerHotkey(config.hotkey);
  return { ok: false, hotkey: config.hotkey };
});
ipcMain.handle("set-voice-hotkey", (_e, k) => {
  if (!k || k === config.voiceHotkey) return { ok: true, hotkey: config.voiceHotkey };
  try { globalShortcut.unregister(toAccelerator(config.voiceHotkey)); } catch {}
  if (registerHotkey(k, voiceShortcut)) { config.voiceHotkey = k; saveConfig(); return { ok: true, hotkey: k }; }
  registerHotkey(config.voiceHotkey, voiceShortcut);
  return { ok: false, hotkey: config.voiceHotkey };
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
ipcMain.handle("choose-folder", async () => {
  const r = await dialog.showOpenDialog(mainWin, { title: tm("Escolha uma pasta para o Codex trabalhar"), properties: ["openDirectory", "createDirectory"] });
  return r.canceled ? null : r.filePaths[0];
});
// so abre PASTAS (nunca executa arquivos)
ipcMain.handle("open-path", (_e, p) => typeof p === "string" && fs.existsSync(p) && fs.statSync(p).isDirectory() ? shell.openPath(p) : "pasta inexistente");
ipcMain.handle("show-item", (_e, p) => { if (typeof p === "string" && fs.existsSync(p)) shell.showItemInFolder(p); });
ipcMain.on("open-main", (_e, chatId) => { hideQuick(); showMain(chatId); });
ipcMain.on("hide-quick", hideQuick);
ipcMain.on("quick-pinned", (_e, v) => { quickPinned = !!v; });
ipcMain.on("resize-quick", (_e, h) => {
  if (!quickWin) return;
  const height = Math.max(70, Math.min(760, Math.round(h)));
  const b = quickWin.getBounds();
  if (b.height !== height) quickWin.setBounds({ ...b, width: QUICK_W, height });
});

// ------------------------------------------------------------------ atualizacao automatica (GitHub Releases)
// Ao abrir (e a cada 6 h) le o patch.json do ultimo Release de github.com/Ruiso-Outside/LLM.
// Atualizacao normal: baixa app-patch-X.zip (so JavaScript, HTML e Python), confere o SHA-512
// e troca resources/app e resources/server ao reiniciar. O .exe (Electron oficial, sem
// modificacoes) nunca muda, entao o Controle Inteligente de Aplicativos do Windows nao bloqueia.
// Se a versao do Electron mudar, e preciso o instalador completo: o app avisa e abre a pagina.
const crypto = require("crypto");
const RELEASES = "https://github.com/Ruiso-Outside/LLM/releases";
const RES = process.resourcesPath;
let updateState = { status: "idle", version: "", percent: 0, error: "" };
let updatePromptShown = false;
let patchReady = null; // { version, staging }
let applyingPatch = false;

function sendUpdateState(patch) {
  updateState = { ...updateState, ...patch };
  for (const w of [mainWin, quickWin]) if (w && !w.isDestroyed()) w.webContents.send("update-state", updateState);
  lastTrayState = ""; updateTray();
}

const cmpVer = (a, b) => {
  const pa = String(a).split(".").map(Number), pb = String(b).split(".").map(Number);
  for (let i = 0; i < 3; i++) if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) - (pb[i] || 0);
  return 0;
};
const errText = err => String(err?.message || err).split("\n")[0];

// LLM_UPDATE_URL: pasta local de testes com patch.json e o zip; sem ela, usa os Releases do GitHub
const feedUrl = (file, version) => process.env.LLM_UPDATE_URL ? process.env.LLM_UPDATE_URL.replace(/\/?$/, "/") + file
  : version ? `${RELEASES}/download/v${version}/${file}` : `${RELEASES}/latest/download/${file}`;

function cleanupOldUpdates() {
  if (!app.isPackaged) return;
  try {
    for (const n of fs.readdirSync(RES)) if (/^_(old|update)_/.test(n)) fs.rmSync(path.join(RES, n), { recursive: true, force: true });
  } catch {}
}

function initUpdater() {
  if (!app.isPackaged) return; // em desenvolvimento nao atualiza
  cleanupOldUpdates();
  setTimeout(checkForUpdates, 8000);
  setInterval(checkForUpdates, 6 * 60 * 60 * 1000);
}

async function checkForUpdates() {
  if (!app.isPackaged) return sendUpdateState({ status: "dev" });
  if (["checking", "downloading", "ready"].includes(updateState.status)) return;
  sendUpdateState({ status: "checking", error: "" });
  try {
    const r = await fetch(feedUrl("patch.json") + "?t=" + Date.now(), { redirect: "follow", cache: "no-store" });
    if (r.status === 404) return sendUpdateState({ status: "latest" }); // Release sem patch (versao antiga)
    if (!r.ok) throw new Error(`GitHub respondeu HTTP ${r.status}`);
    const m = await r.json();
    if (cmpVer(m.version, app.getVersion()) <= 0) return sendUpdateState({ status: "latest" });
    if (m.electron !== process.versions.electron) {
      // a versao nova troca o Electron: precisa do instalador completo
      sendUpdateState({ status: "manual", version: m.version });
      if (Notification.isSupported())
        new Notification({ title: tm("Atualização do LLM Local"), icon: ICON, body: tm("A versão {v} precisa do pacote completo. Abra Configurações → App desktop.", { v: m.version }) }).show();
      return;
    }
    await downloadPatch(m);
  } catch (err) {
    sendUpdateState({ status: "error", error: errText(err) });
  }
}

async function downloadPatch(m) {
  sendUpdateState({ status: "downloading", version: m.version, percent: 0 });
  if (Notification.isSupported())
    new Notification({ title: tm("Atualização do LLM Local"), icon: ICON, body: tm("Baixando a versão {v} em segundo plano...", { v: m.version }) }).show();
  const staging = path.join(RES, `_update_${m.version}`);
  fs.rmSync(staging, { recursive: true, force: true });
  fs.mkdirSync(staging, { recursive: true }); // falha aqui se a pasta do app nao permitir escrita
  const zip = path.join(staging, m.file);
  const r = await fetch(feedUrl(m.file, m.version), { redirect: "follow" });
  if (!r.ok) throw new Error(`não foi possível baixar ${m.file} (HTTP ${r.status})`);
  const total = Number(r.headers.get("content-length")) || m.size || 0;
  const hash = crypto.createHash("sha512");
  const out = fs.createWriteStream(zip);
  let got = 0, lastPct = -1;
  for await (const chunk of r.body) {
    hash.update(chunk); got += chunk.length;
    if (!out.write(chunk)) await new Promise(res => out.once("drain", res));
    const pct = total ? Math.floor(got / total * 100) : 0;
    if (pct !== lastPct) { lastPct = pct; sendUpdateState({ percent: pct }); }
  }
  await new Promise((res, rej) => out.end(err => err ? rej(err) : res()));
  if (hash.digest("base64") !== m.sha512) throw new Error("o arquivo baixado está corrompido (SHA-512 diferente). Tente de novo.");
  // tar.exe vem com o Windows 10/11 e extrai .zip
  const tarExe = path.join(process.env.SystemRoot || "C:\\Windows", "System32", "tar.exe"); // nao depende do PATH
  const x = spawnSync(tarExe, ["-xf", zip, "-C", staging], { windowsHide: true, encoding: "utf8" });
  if (x.status !== 0) throw new Error("falha ao extrair a atualização: " + (x.stderr || "").trim().split("\n")[0]);
  fs.rmSync(zip, { force: true });
  const pkg = JSON.parse(fs.readFileSync(path.join(staging, "app", "package.json"), "utf8"));
  if (pkg.version !== m.version || !fs.existsSync(path.join(staging, "app", "main.js")) || !fs.existsSync(path.join(staging, "server", "server.py")))
    throw new Error("o pacote da atualização está incompleto.");
  patchReady = { version: m.version, staging };
  sendUpdateState({ status: "ready", version: m.version, percent: 100 });
  if (updatePromptShown) return;
  updatePromptShown = true;
  const res = await dialog.showMessageBox({
    type: "info", title: "LLM Local", icon: nativeImage.createFromPath(ICON),
    message: tm("A versão {v} do LLM Local está pronta.", { v: m.version }),
    detail: tm("Reinicie para atualizar agora. Se preferir, a atualização será aplicada quando você fechar o app."),
    buttons: [tm("Reiniciar e atualizar"), tm("Depois")], defaultId: 0, cancelId: 1, noLink: true,
  });
  if (res.response === 0) installUpdate();
}

// troca as pastas do app pela versao nova; se algo falhar, volta a versao anterior
function applyPatch() {
  if (!patchReady || applyingPatch) return false;
  applyingPatch = true;
  stopServer();
  const done = [];
  try {
    for (const d of ["app", "server"]) {
      const cur = path.join(RES, d), old = path.join(RES, `_old_${d}`), next = path.join(patchReady.staging, d);
      fs.rmSync(old, { recursive: true, force: true });
      renameRetry(cur, old); done.push([d, "old"]);
      renameRetry(next, cur); done.push([d, "new"]);
    }
    return true;
  } catch (err) {
    for (const [d, step] of done.reverse()) {
      try {
        if (step === "new") fs.renameSync(path.join(RES, d), path.join(patchReady.staging, d));
        else fs.renameSync(path.join(RES, `_old_${d}`), path.join(RES, d));
      } catch {}
    }
    dialog.showErrorBox("LLM Local", "Não foi possível aplicar a atualização; o app continua na versão atual.\n\n" + errText(err));
    return false;
  } finally {
    patchReady = null;
  }
}

function renameRetry(from, to) {
  // o Windows pode segurar a pasta por alguns instantes depois que o servidor fecha
  for (let i = 0; ; i++) {
    try { return fs.renameSync(from, to); } catch (err) {
      if (i >= 20 || !["EPERM", "EBUSY", "EACCES"].includes(err.code)) throw err;
      spawnSync("cmd", ["/c", "ping -n 2 127.0.0.1 >nul"], { windowsHide: true }); // espera ~1 s
    }
  }
}

function installUpdate() {
  if (updateState.status === "manual") return shell.openExternal(`${RELEASES}/latest`);
  if (!patchReady) return;
  quitting = true;
  globalShortcut.unregisterAll();
  if (applyPatch()) { app.relaunch(); app.exit(0); }
  else quitting = false;
}

ipcMain.handle("update-info", () => ({ ...updateState, current: app.getVersion() }));
ipcMain.handle("update-check", () => { checkForUpdates(); return { ...updateState, current: app.getVersion() }; });
ipcMain.handle("update-install", () => { if (["ready", "manual"].includes(updateState.status)) installUpdate(); });

// ------------------------------------------------------------------ atalhos (versao portatil)
// O app e distribuido como .zip (o instalador NSIS e bloqueado pelo Controle Inteligente de
// Aplicativos). Na primeira execucao, oferece criar os atalhos que um instalador criaria.
const START_MENU_LNK = () => path.join(app.getPath("appData"), "Microsoft", "Windows", "Start Menu", "Programs", "LLM Local.lnk");
const DESKTOP_LNK = () => path.join(app.getPath("desktop"), "LLM Local.lnk");

function createShortcuts() {
  const opts = { target: process.execPath, icon: path.join(__dirname, "icon.ico"), iconIndex: 0, description: "LLM Local", appUserModelId: "studio.piphin.llmlocal" };
  let ok = true;
  for (const lnk of [START_MENU_LNK(), DESKTOP_LNK()]) ok = shell.writeShortcutLink(lnk, fs.existsSync(lnk) ? "replace" : "create", opts) && ok;
  return ok;
}

async function offerShortcuts() {
  if (!app.isPackaged || config.shortcutsOffered) return;
  config.shortcutsOffered = true; saveConfig();
  if (fs.existsSync(START_MENU_LNK()) || fs.existsSync(DESKTOP_LNK())) return; // ja tem atalhos (instalacao antiga)
  const r = await dialog.showMessageBox({
    type: "question", title: "LLM Local", icon: nativeImage.createFromPath(ICON),
    message: tm("Criar atalhos do LLM Local?"),
    detail: tm("No Menu Iniciar e na Área de Trabalho, apontando para:\n{p}\n\nDeixe a pasta do app onde ela está (se mover, crie os atalhos de novo pelo menu do ícone perto do relógio).", { p: process.execPath }),
    buttons: [tm("Criar atalhos"), tm("Agora não")], defaultId: 0, cancelId: 1, noLink: true,
  });
  if (r.response === 0 && !createShortcuts()) dialog.showErrorBox("LLM Local", tm("Não foi possível criar os atalhos."));
}

// ------------------------------------------------------------------ inicio
app.whenReady().then(async () => {
  if (!gotLock) return;
  loadConfig();
  const firstRun = !config.homeDir;
  if (firstRun) { config.homeDir = await askHomeDir(true); saveConfig(); applyAutoStart(); }
  if (!(await startServer())) { quitting = true; return app.quit(); }

  // downloads (backup, imagens): sempre pergunta onde salvar, comecando em Documentos
  session.defaultSession.setPermissionRequestHandler((wc, permission, cb) => {
    cb(permission === "media" ? wc.getURL().startsWith(BASE) : true);
  });
  session.defaultSession.on("will-download", (_e, item) => {
    item.setSaveDialogOptions({ title: tm("Salvar arquivo"), defaultPath: path.join(app.getPath("documents"), item.getFilename()) });
  });

  tray = new Tray(nativeImage.createFromPath(TRAY_ICON));
  tray.on("click", () => showMain());
  updateTray(); setInterval(updateTray, 4000);

  if (!registerHotkey(config.hotkey)) {
    dialog.showMessageBox({ type: "warning", title: "LLM Local", message: tm("O atalho {k} já está em uso por outro programa.", { k: prettyKey(config.hotkey) }),
      detail: tm("Escolha outro em Configurações → App desktop.") });
  }
  registerHotkey(config.voiceHotkey, voiceShortcut);
  registerHotkey(config.screenHotkey, screenShortcut);
  diag(`app iniciado (versão ${app.getVersion()})`);
  createQuick();
  initUpdater();
  setTimeout(offerShortcuts, 2500);
  const hidden = process.argv.includes("--hidden");
  createMain(!hidden);
  if (process.argv.includes("--quick")) showQuick();
});

app.on("window-all-closed", e => e.preventDefault?.()); // continua na bandeja
app.on("before-quit", () => { quitting = true; });
app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  if (patchReady) applyPatch(); // "Depois": aplica a atualizacao ao fechar
  stopServer();
});
