// Piphin LLM como módulo do Piphin Hub: faz o papel do desktop/main.js do app separado.
// Inicia o servidor Python (o mesmo app/ do app separado), cuida da pergunta rápida (janela extra
// do Hub), dos atalhos globais, do print da tela e da área de transferência.
// A configuração e a pasta de dados são as mesmas do app separado (%APPDATA%\LLM Local\config.json).
const fs = require("fs");
const path = require("path");
const http = require("http");
const { spawn, spawnSync } = require("child_process");

const PORT = Number(process.env.LLM_PORT) || 8765;
const BASE = `http://127.0.0.1:${PORT}`;
const QUICK_W = 720;
const CONFIG_FILE = path.join(process.env.APPDATA, "LLM Local", "config.json");

exports.activate = (ctx) => {
  const SERVER_DIR = path.join(ctx.dir, "server");
  const LOG_FILE = path.join(ctx.dataDir, "server.log");
  const DIAG_FILE = path.join(ctx.dataDir, "diagnostico.log");

  let config = { homeDir: "", hotkey: "Ctrl+Shift+Space", voiceHotkey: "Ctrl+Alt+Space", screenHotkey: "Ctrl+Alt+S", quickHideOnBlur: true };
  try { config = { ...config, ...JSON.parse(fs.readFileSync(CONFIG_FILE, "utf8").replace(/^\uFEFF/, "")) }; } catch { /* primeira vez */ }
  const saveConfig = () => { fs.mkdirSync(path.dirname(CONFIG_FILE), { recursive: true }); fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2)); };

  let server = null, serverReady = false, serverError = "", stopping = false, restarts = [];
  let quickPinned = false, quickHiddenAt = 0, quickOpen = false;

  function diag(msg) {
    try {
      if (fs.existsSync(DIAG_FILE) && fs.statSync(DIAG_FILE).size > 1024 * 1024) fs.renameSync(DIAG_FILE, DIAG_FILE + ".old");
      fs.appendFileSync(DIAG_FILE, `${new Date().toISOString()} ${msg}\n`);
    } catch { /* sem disco */ }
  }

  // ---------------------------------------------------------------- servidor Python
  function tryPython(cmd, args) {
    return new Promise((resolve) => {
      let out = "", done = false, p;
      const finish = (ok) => { if (!done) { done = true; clearTimeout(timer); resolve(ok); } };
      try { p = spawn(cmd, [...args, "-c", "import sys;print(sys.version_info>=(3,9))"], { windowsHide: true }); } catch { return resolve(false); }
      const timer = setTimeout(() => { try { p.kill(); } catch { /* já saiu */ } finish(false); }, 10000);
      p.stdout.on("data", (d) => (out += d));
      p.on("error", () => finish(false));
      p.on("exit", (code) => finish(code === 0 && out.trim() === "True"));
    });
  }
  async function findPython() {
    for (const [cmd, args] of [["python", []], ["py", ["-3"]], ["python3", []]]) if (await tryPython(cmd, args)) return [cmd, args];
    return null;
  }
  function ping(urlPath = "/api/status", timeout = 1500) {
    return new Promise((resolve) => {
      const req = http.get(BASE + urlPath, { timeout }, (res) => {
        let body = ""; res.on("data", (d) => (body += d)); res.on("end", () => resolve(res.statusCode === 200 ? body : null));
      });
      req.on("error", () => resolve(null));
      req.on("timeout", () => { req.destroy(); resolve(null); });
    });
  }

  async function startServer() {
    serverError = "";
    if (await ping()) { serverReady = true; return true; } // já há um servidor (ex.: o app separado aberto)
    const py = await findPython();
    if (!py) {
      serverError = "python";
      const r = await ctx.host.messageBox({ type: "error", message: "Python não encontrado",
        detail: "O Piphin LLM precisa do Python 3.9 ou mais novo.\nInstale em python.org marcando a opção \"Add python.exe to PATH\" e abra o módulo de novo.",
        buttons: ["Abrir python.org", "Fechar"] });
      if (r === 0) ctx.emit("open-url", "https://www.python.org/downloads/");
      return false;
    }
    fs.mkdirSync(config.homeDir, { recursive: true });
    const log = fs.createWriteStream(LOG_FILE, { flags: "w" });
    server = spawn(py[0], [...py[1], path.join(SERVER_DIR, "server.py")], {
      cwd: SERVER_DIR, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
      // LLM_PARENT_PID: o servidor se encerra sozinho se este módulo cair
      env: { ...process.env, LLM_HOME: config.homeDir, LLM_PORT: String(PORT), LLM_PARENT_PID: String(process.pid),
        PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1" },
    });
    server.stdout.pipe(log); server.stderr.pipe(log);
    server.on("exit", (code) => {
      server = null; serverReady = false;
      if (stopping) return;
      diag(`servidor interno parou (código ${code})`);
      restartServer(code);
    });
    for (let i = 0; i < 80; i++) {
      if (await ping()) { serverReady = true; return true; }
      await new Promise((r) => setTimeout(r, 300));
    }
    serverError = "timeout";
    diag("servidor interno não respondeu ao iniciar");
    ctx.host.messageBox({ type: "error", message: "O servidor interno não respondeu.", detail: `Veja o log em:\n${LOG_FILE}` }).catch(() => {});
    return false;
  }

  // reinicia o servidor que caiu (até 3 vezes em 5 minutos); as janelas recarregam quando ele volta
  async function restartServer(code) {
    restarts = restarts.filter((t) => Date.now() - t < 5 * 60 * 1000);
    if (restarts.length >= 3) {
      serverError = "crashed";
      diag("servidor caiu 3 vezes em 5 minutos: parei de reiniciar");
      return ctx.host.messageBox({ type: "error", message: "O servidor interno parou várias vezes.", detail: `Veja o log em:\n${LOG_FILE}` }).catch(() => {});
    }
    restarts.push(Date.now());
    ctx.host.notify("Piphin LLM", `O servidor interno parou (código ${code}). Reiniciando...`).catch(() => {});
    await new Promise((r) => setTimeout(r, 1500));
    if (stopping) return;
    if (await startServer()) { diag("servidor reiniciado"); ctx.host.reloadView().catch(() => {}); ctx.host.reloadWindows().catch(() => {}); }
  }

  function stopServer() {
    if (!server) return;
    const pid = server.pid; server = null; serverReady = false;
    // encerra a árvore toda (python + llama-server)
    try { spawnSync("taskkill", ["/pid", String(pid), "/T", "/F"], { windowsHide: true, timeout: 5000 }); } catch { /* já saiu */ }
  }

  // ---------------------------------------------------------------- pergunta rápida
  async function openQuick() {
    if (quickOpen) return;
    await ctx.host.openWindow("quick", { url: BASE + "/quick.html", width: QUICK_W, height: 96, frame: false, transparent: true, resizable: false,
      alwaysOnTop: true, skipTaskbar: true, fullscreenable: false, maximizable: false, minimizable: false, hasShadow: false, title: "Pergunta rápida" });
    quickOpen = true;
  }
  async function showQuick() {
    await openQuick();
    await ctx.host.showWindow("quick", { placement: "cursor-top" });
    ctx.host.sendToWindow("quick", "quick-show", { hiddenFor: quickHiddenAt ? Date.now() - quickHiddenAt : 0 });
  }
  const hideQuick = () => ctx.host.hideWindow("quick");
  async function toggleQuick() {
    const s = await ctx.host.windowState("quick");
    if (s.visible && s.focused) await hideQuick(); else await showQuick();
  }
  async function voiceShortcut() {
    const s = await ctx.host.windowState("quick");
    if (!s.visible) await showQuick();
    ctx.host.sendToWindow("quick", "quick-voice");
  }
  async function screenShortcut() {
    const s = await ctx.host.windowState("quick");
    let jpg = null;
    try { jpg = await ctx.host.captureScreen({ hide: ["quick"] }); } catch { /* sem print */ }
    if (!s.visible) await showQuick();
    if (jpg) ctx.host.sendToWindow("quick", "quick-context", { kind: "screen", data: jpg });
  }

  // ---------------------------------------------------------------- atalhos globais
  const toAccelerator = (k) => String(k || "").replace(/\bArrow(Up|Down|Left|Right)\b/g, "$1").replace(/\bEscape\b/g, "Esc");
  const prettyKey = (k) => String(k || "").replace(/Space/g, "Espaço").replace(/CommandOrControl|Control/g, "Ctrl");
  const actions = { hotkey: toggleQuick, voiceHotkey: voiceShortcut, screenHotkey: screenShortcut };
  const bound = new Map(); // atalho -> ação

  async function bind(key, combo) {
    const acc = toAccelerator(combo);
    if (!acc) return false;
    const ok = await ctx.host.registerHotkey(acc);
    if (ok) bound.set(acc, key);
    return ok;
  }
  async function setHotkey(key, k) {
    if (!k || k === config[key]) return { ok: true, hotkey: config[key] };
    const old = toAccelerator(config[key]);
    await ctx.host.unregisterHotkey(old); bound.delete(old);
    if (await bind(key, k)) { config[key] = k; saveConfig(); return { ok: true, hotkey: k }; }
    await bind(key, config[key]);
    return { ok: false, hotkey: config[key] };
  }
  ctx.host.on("hotkey", (acc) => { const key = bound.get(acc); if (key) actions[key]().catch((e) => ctx.log("atalho", e)); });
  ctx.host.on("window-blur", (name) => { if (name === "quick" && config.quickHideOnBlur && !quickPinned) hideQuick().catch(() => {}); });
  ctx.host.on("window-hide", (name) => { if (name === "quick") quickHiddenAt = Date.now(); });

  // ---------------------------------------------------------------- chamadas das páginas (window.llmDesktop)
  ctx.handle("status", () => ({ ready: serverReady, error: serverError, base: BASE }));
  ctx.handle("retry", async () => { restarts = []; return startServer().then(async (ok) => { if (ok) await afterServer(); return ok; }); });
  ctx.handle("get-config", async () => ({ ...config, autoStart: await ctx.host.getStartWithWindows(), hotkeyLabel: prettyKey(config.hotkey) }));
  ctx.handle("set-hotkey", (k) => setHotkey("hotkey", k));
  ctx.handle("set-voice-hotkey", (k) => setHotkey("voiceHotkey", k));
  ctx.handle("set-screen-hotkey", (k) => setHotkey("screenHotkey", k));
  ctx.handle("set-option", async (key, value) => {
    if (key === "autoStart") return ctx.host.setStartWithWindows(!!value); // no Hub, é o Hub que inicia com o Windows
    if (key === "quickHideOnBlur") { config.quickHideOnBlur = !!value; saveConfig(); }
  });
  ctx.handle("choose-home", async () => {
    const dirs = await ctx.host.openDialog({ title: "Pasta de dados do Piphin LLM", properties: ["openDirectory", "createDirectory"], defaultPath: config.homeDir });
    const dir = dirs && dirs[0];
    if (!dir || dir === config.homeDir) return null;
    config.homeDir = dir; saveConfig();
    stopping = true; stopServer(); await new Promise((r) => setTimeout(r, 800)); stopping = false;
    if (await startServer()) { ctx.host.reloadView().catch(() => {}); ctx.host.reloadWindows().catch(() => {}); }
    return dir;
  });
  ctx.handle("choose-folder", async () => {
    const dirs = await ctx.host.openDialog({ title: "Escolha uma pasta para o Codex trabalhar", properties: ["openDirectory", "createDirectory"] });
    return dirs ? dirs[0] : null;
  });
  ctx.handle("open-path", (p) => ctx.host.openPath(p));
  ctx.handle("show-item", (p) => ctx.host.showItem(p));
  ctx.handle("diag", (msg) => diag(`[janela] ${String(msg).slice(0, 500)}`));
  ctx.handle("open-diag", () => { if (!fs.existsSync(DIAG_FILE)) fs.writeFileSync(DIAG_FILE, ""); return ctx.host.showItem(DIAG_FILE); });
  ctx.handle("capture-screen", () => ctx.host.captureScreen({ hide: ["quick"] }).catch(() => null));
  ctx.handle("read-clipboard", () => ctx.host.readClipboard());
  ctx.handle("open-main", async (chatId) => { await hideQuick(); await ctx.host.focus(); if (chatId) ctx.emit("open-chat", chatId); });
  ctx.handle("hide-quick", () => hideQuick());
  ctx.handle("quick-pinned", (v) => { quickPinned = !!v; });
  ctx.handle("resize-quick", (h) => ctx.host.setWindowBounds("quick", { width: QUICK_W, height: Math.max(70, Math.min(760, Math.round(h))) }));
  // as atualizações do módulo são feitas pelo Piphin Hub
  ctx.handle("update-info", () => ({ status: "idle", version: "", percent: 0, error: "", current: ctx.version }));
  ctx.handle("update-check", () => ({ status: "idle", version: "", percent: 0, error: "", current: ctx.version }));
  ctx.handle("update-install", () => null);

  // ---------------------------------------------------------------- início
  async function afterServer() {
    await openQuick();
    const busy = [];
    for (const key of Object.keys(actions)) if (!(await bind(key, config[key]))) busy.push(prettyKey(config[key]));
    if (busy.length) ctx.host.notify("Piphin LLM", `Atalho já em uso por outro programa: ${busy.join(", ")}. Troque em Configurações → App desktop.`).catch(() => {});
    // a pergunta rápida precisa do Hub rodando: fechar a janela só o esconde
    ctx.host.keepAlive(true, "pergunta rápida do Piphin LLM").catch(() => {});
  }

  (async () => {
    if (!config.homeDir) {
      const def = path.join(process.env.USERPROFILE || process.env.HOME || "C:\\", "LLM Local");
      const r = await ctx.host.messageBox({ type: "question", message: "Onde guardar os modelos, o motor e as conversas?",
        detail: `Os modelos costumam ter de 3 a 20 GB cada, então prefira um disco com bastante espaço.\n\nPasta padrão: ${def}`,
        buttons: ["Usar a pasta padrão", "Escolher outra pasta..."], defaultId: 0, cancelId: 0 });
      let dir = def;
      if (r === 1) {
        const dirs = await ctx.host.openDialog({ title: "Pasta de dados do Piphin LLM", properties: ["openDirectory", "createDirectory"], defaultPath: def });
        if (dirs && dirs[0]) dir = dirs[0];
      }
      config.homeDir = dir; saveConfig();
    }
    diag(`módulo iniciado (versão ${ctx.version})`);
    if (await startServer()) await afterServer();
  })().catch((e) => ctx.log("início", e));

  ctx.onStop(() => { stopping = true; stopServer(); });
};
