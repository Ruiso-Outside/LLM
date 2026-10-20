// Dentro do Piphin Hub (módulo): monta a mesma ponte window.llmDesktop do app desktop,
// falando com o motor do módulo (desktop/module/backend.js) por window.piphin.
// No app separado e no navegador este arquivo não faz nada.
(() => {
  if (window.llmDesktop || !window.piphin) return;
  const call = (ch) => async (...args) => {
    const r = await piphin.invoke(ch, ...args);
    if (!r.ok) throw new Error(r.error);
    return r.data;
  };
  const fire = (ch) => (...args) => { piphin.invoke(ch, ...args); };
  // imagens chegam em base64 (o Electron do app separado entregava bytes)
  const bytes = (b64) => (b64 ? Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)) : null);

  window.llmDesktop = {
    inHub: true,
    getConfig: call("get-config"),
    setHotkey: call("set-hotkey"),
    setVoiceHotkey: call("set-voice-hotkey"),
    setScreenHotkey: call("set-screen-hotkey"),
    onQuickVoice: (cb) => piphin.on("quick-voice", () => cb()),
    diag: fire("diag"),
    openDiag: call("open-diag"),
    captureScreen: async () => bytes(await call("capture-screen")()),
    readClipboard: async () => { const r = await call("read-clipboard")(); return { text: r.text, image: bytes(r.image) }; },
    onQuickContext: (cb) => piphin.on("quick-context", (d) => cb({ ...d, data: bytes(d.data) })),
    setOption: call("set-option"),
    chooseHomeDir: call("choose-home"),
    chooseFolder: call("choose-folder"),
    openPath: call("open-path"),
    showItem: call("show-item"),
    openMain: fire("open-main"),
    hideQuick: fire("hide-quick"),
    setQuickPinned: fire("quick-pinned"),
    resizeQuick: fire("resize-quick"),
    onQuickShow: (cb) => piphin.on("quick-show", cb),
    // as atualizações do módulo são do Piphin Hub
    updateInfo: call("update-info"),
    checkUpdates: call("update-check"),
    installUpdate: call("update-install"),
    onUpdateState: (cb) => piphin.on("update-state", cb),
  };
  // "Continuar no app" da pergunta rápida: abre a conversa na janela principal
  piphin.on("open-chat", (id) => { if (id && /^[\w-]+$/.test(id)) location.hash = "chat=" + id; });
})();
