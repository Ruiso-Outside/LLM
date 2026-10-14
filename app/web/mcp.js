"use strict";
// Ferramentas MCP: lista de servidores (Configurações), seleção no Codex e nos agentes.
// Carregado antes do app.js; só usa S/app.js quando as funções são chamadas.

const MCP = { list: [], roblox: false, busy: {} };
const mcpEnabled = () => MCP.list.filter(s => s.enabled);
const mcpName = id => (MCP.list.find(s => s.id === id) || {}).name || id;

async function loadMcp() {
  try { const r = await api("/api/mcp"); MCP.list = r.servers; MCP.roblox = r.roblox_detected; } catch { return; }
  renderMcpList();
  if (typeof renderModeBars === "function") renderModeBars();
}
async function saveMcp(list) {
  try { const r = await api("/api/mcp", { method: "PUT", body: { servers: list } }); MCP.list = r.servers; }
  catch (e) { toast(trText(e.message), 4000); }
  renderMcpList(); renderModeBars();
}

const mcpOn = s => s.tools.filter(x => x.enabled);
const mcpTokens = s => mcpOn(s).reduce((a, x) => a + (x.tokens || 0), 0);
function mcpToolsHTML(s) {
  if (!s.tools.length) return "";
  const on = mcpOn(s), tk = mcpTokens(s), heavy = tk > 6000;
  return `<details class="mcp-tools" ${MCP.open?.[s.id] ? "open" : ""} data-mcp-tools="${esc(s.id)}"><summary>${t("Ferramentas: {on} de {n} ligadas", { on: on.length, n: s.tools.length })} · <span class="${heavy ? "err-text" : ""}">~${fmtNum(tk)} tokens</span></summary>
    ${heavy ? `<div class="warn-box">${t("Ferramentas demais: elas ocupam ~{n} tokens do contexto em cada pedido. Deixe ligadas só as que vai usar.", { n: fmtNum(tk) })}</div>` : ""}
    <div class="row wrap mcp-tool-btns">${Object.keys(s.profiles || {}).map(k => `<button type="button" class="btn small" data-mcp-sel="${esc(k)}">${esc(t(PROFILE_LABEL[k] || k))}</button>`).join("")}<button type="button" class="btn small" data-mcp-sel="all">${t("Todas")}</button><button type="button" class="btn small" data-mcp-sel="none">${t("Nenhuma")}</button></div>
    <div class="mcp-tool-list">${s.tools.map(x => `<label class="check" title="${esc(x.description)}"><input type="checkbox" data-mcp-tool="${esc(x.name)}" ${x.enabled ? "checked" : ""}> <code>${esc(x.name)}</code>${x.read_only ? ` <small class="muted">${t("(só leitura)")}</small>` : ""} <small class="muted">~${fmtNum(x.tokens || 0)}</small></label>`).join("")}</div></details>`;
}
function setMcpTools(id, names) {
  saveMcp(MCP.list.map(s => s.id !== id ? s : { ...s, allowed: names === null ? null : names }));
}

function mcpStateHTML(s) {
  if (MCP.busy[s.id]) return `<span class="spin"></span> <small class="muted">${t("conectando...")}</small>`;
  if (s.state === "pronto" && s.tools.length) return `<span class="mcp-dot ok"></span><small>${t("{n} ferramentas", { n: s.tools.length })}</small>`;
  if (s.state === "erro" || s.error) return `<span class="mcp-dot bad"></span><small class="err-text">${esc(trText(s.error || t("erro")))}</small>`;
  return `<span class="mcp-dot"></span><small class="muted">${t("conecta quando for usado")}</small>`;
}
function renderMcpList() {
  const box = $("#mcpList"); if (!box) return;
  box.innerHTML = MCP.list.length ? MCP.list.map(s => `<div class="item mcp-item" data-mcp="${esc(s.id)}">
      <div class="mcp-main"><div class="mcp-title"><b>${s.id === "roblox" ? "🟦" : "🔌"} ${esc(s.name)}</b> ${mcpStateHTML(s)}</div>
        <small class="muted mcp-cmd" title="${esc(s.url || s.command_line)}">${esc(s.url || s.command_line)}</small>
        ${mcpToolsHTML(s)}
        <div class="mcp-opts"><label class="check"><input type="checkbox" data-mcp-opt="enabled" ${s.enabled ? "checked" : ""}> ${t("Usar no Codex")}</label>
          <label class="check" title="${esc(t("Sem isso, o app pede sua confirmação antes de cada ação que altera algo (ferramentas só de leitura não pedem)."))}"><input type="checkbox" data-mcp-opt="auto_approve" ${s.auto_approve ? "checked" : ""}> ${t("Não pedir confirmação")}</label></div></div>
      <div class="mcp-btns"><button type="button" class="btn small" data-mcp-act="test">${t("Testar")}</button><button type="button" class="btn small danger" data-mcp-act="del">${t("Remover")}</button></div>
    </div>`).join("") : `<p class="muted small-note">${t("Nenhum servidor MCP.")}</p>`;
  $("#mcpAddRea").hidden = MCP.list.some(s => s.id === "rea");
  const rb = $("#mcpAddRoblox");
  rb.hidden = MCP.list.some(s => s.id === "roblox");
  rb.disabled = !MCP.roblox; rb.title = MCP.roblox ? "" : t("Roblox Studio não encontrado neste PC.");
}

$("#mcpList").addEventListener("toggle", e => {
  const d = e.target.closest?.("[data-mcp-tools]"); if (d) (MCP.open ||= {})[d.dataset.mcpTools] = d.open;
}, true);
$("#mcpList").addEventListener("change", e => {
  const tool = e.target.dataset.mcpTool;
  if (tool) {
    const s = MCP.list.find(x => x.id === e.target.closest("[data-mcp]").dataset.mcp);
    const names = new Set(mcpOn(s).map(x => x.name)); e.target.checked ? names.add(tool) : names.delete(tool);
    return setMcpTools(s.id, names.size === s.tools.length ? null : [...names]);
  }
  const opt = e.target.dataset.mcpOpt; if (!opt) return;
  const id = e.target.closest("[data-mcp]").dataset.mcp;
  saveMcp(MCP.list.map(s => s.id === id ? { ...s, [opt]: e.target.checked } : s));
});
$("#mcpList").addEventListener("click", async e => {
  const sel = e.target.closest("[data-mcp-sel]")?.dataset.mcpSel;
  if (sel) {
    const id = e.target.closest("[data-mcp]").dataset.mcp;
    return setMcpTools(id, sel === "all" ? null : sel === "none" ? [] : (MCP.list.find(s => s.id === id)?.profiles?.[sel] || []));
  }
  const act = e.target.closest("[data-mcp-act]")?.dataset.mcpAct; if (!act) return;
  const id = e.target.closest("[data-mcp]").dataset.mcp;
  if (act === "del") {
    if (!confirm(t("Remover \"{name}\"?", { name: mcpName(id) }))) return;
    return saveMcp(MCP.list.filter(s => s.id !== id));
  }
  if (act === "test") {
    MCP.busy[id] = true; renderMcpList();
    try { const r = await post("/api/mcp/test", { id }); MCP.list = r.servers; const s = MCP.list.find(x => x.id === id);
      toast(s?.tools.length ? t("{name}: {n} ferramentas", { name: s.name, n: s.tools.length }) : trText(s?.error || ""), 4000); }
    catch (err) { toast(trText(err.message), 5000); await loadMcp(); }
    delete MCP.busy[id]; renderMcpList();
  }
});
const PROFILE_LABEL = { essentials: "Essenciais", windows: "Windows completo" };
$("#mcpAddRea").onclick = async () => {
  const b = $("#mcpAddRea"); b.disabled = true;
  try {
    const r = await post("/api/mcp/preset", { kind: "rea" }); MCP.list = r.servers; renderMcpList(); renderModeBars();
    toast(t("REA adicionado como servidor MCP (usa a cópia instalada no motor, sem internet)."), 6000);
  } catch (e) { toast(trText(e.message), 6000); }
  b.disabled = false;
};
$("#mcpAddRoblox").onclick = async () => {
  try { const r = await post("/api/mcp/preset", { kind: "roblox" }); MCP.list = r.servers; renderMcpList(); renderModeBars();
    toast(t("Roblox Studio adicionado. Deixe o Studio aberto com um jogo para usar as ferramentas."), 4500); }
  catch (e) { toast(trText(e.message), 4000); }
};
const mcpType = () => $("#mcpType").value;
function mcpFormType() { const http = mcpType() === "http"; $("#mcpCmdRow").hidden = http; $("#mcpEnvRow").hidden = http; $("#mcpUrlRow").hidden = !http; }
$("#mcpType").onchange = mcpFormType;
$("#mcpAddCustom").onclick = () => { $("#mcpForm").hidden = false; ["#mcpName", "#mcpCmd", "#mcpUrl", "#mcpEnv"].forEach(s => $(s).value = ""); mcpFormType(); $("#mcpName").focus(); };
$("#mcpCancel").onclick = () => { $("#mcpForm").hidden = true; };
$("#mcpSave").onclick = async () => {
  const name = $("#mcpName").value.trim(); if (!name) return toast(t("Dê um nome."));
  const s = mcpType() === "http" ? { name, type: "http", url: $("#mcpUrl").value.trim() }
    : { name, type: "stdio", command_line: $("#mcpCmd").value.trim(), env: $("#mcpEnv").value };
  const before = MCP.list.length;
  await saveMcp([...MCP.list, { ...s, enabled: true, auto_approve: false }]);
  if (MCP.list.length > before) { $("#mcpForm").hidden = true; toast(t("Servidor adicionado. Clique em Testar para conectar.")); }
};

// ---- rótulos das ferramentas MCP nas respostas
function mcpToolLabel(name, label) {
  const m = /^mcp__([a-z0-9_]+?)__(.+)$/.exec(name || "");
  if (!m) return null;
  return label || `${mcpName(m[1])} · ${m[2]}`;
}
// corpo do passo: código Luau/JS em destaque, demais argumentos em JSON
function mcpArgsHTML(args) {
  args = args || {}; let h = "";
  const rest = {};
  for (const [k, v] of Object.entries(args)) {
    if (typeof v === "string" && (/^(code|source|script|command|query)$/i.test(k) || v.includes("\n"))) h += codeBlock(/code|source|script/i.test(k) ? "lua" : "", v);
    else rest[k] = v;
  }
  if (Object.keys(rest).length) h = `<pre class="tool-out">${esc(JSON.stringify(rest, null, 2))}</pre>` + h;
  return h;
}
