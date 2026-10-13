// Expoe para as paginas apenas as funcoes do app desktop que elas precisam.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("llmDesktop", {
  getConfig: () => ipcRenderer.invoke("get-config"),
  setHotkey: k => ipcRenderer.invoke("set-hotkey", k),
  setOption: (key, value) => ipcRenderer.invoke("set-option", key, value),
  chooseHomeDir: () => ipcRenderer.invoke("choose-home"),
  chooseFolder: () => ipcRenderer.invoke("choose-folder"),
  openPath: p => ipcRenderer.invoke("open-path", p),
  showItem: p => ipcRenderer.invoke("show-item", p),
  openMain: chatId => ipcRenderer.send("open-main", chatId),
  hideQuick: () => ipcRenderer.send("hide-quick"),
  setQuickPinned: v => ipcRenderer.send("quick-pinned", v),
  resizeQuick: h => ipcRenderer.send("resize-quick", h),
  onQuickShow: cb => ipcRenderer.on("quick-show", (_e, data) => cb(data)),
  updateInfo: () => ipcRenderer.invoke("update-info"),
  checkUpdates: () => ipcRenderer.invoke("update-check"),
  installUpdate: () => ipcRenderer.invoke("update-install"),
  onUpdateState: cb => ipcRenderer.on("update-state", (_e, s) => cb(s)),
});
