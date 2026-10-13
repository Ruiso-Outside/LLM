"use strict";
// Agentes e grupos: editor, seletor no modo 👥 Agentes e execução dos grupos.
// Carregado antes do app.js; as funções só usam S/app.js quando são chamadas.

const AG = { doc: { agents: [], groups: [] }, edit: null, draft: null };
const AGENT_COLORS = ["#7c6cf2", "#4fc3f7", "#3ecf8e", "#f2b84b", "#f2686a", "#e07cf2", "#9aa0b4"];
const AGENT_ICONS = ["🤖", "🧮", "✏️", "✅", "🔎", "📝", "🧐", "💻", "🗺️", "🔍", "🎨", "📊", "🧠", "💬", "📚", "⚖️", "🛡️", "🌐"];
const agentById = id => AG.doc.agents.find(a => a.id === id);
const groupById = id => AG.doc.groups.find(g => g.id === id);
const clone = o => JSON.parse(JSON.stringify(o));
const modelNameOf = path => (S.status?.models.find(m => m.path === path) || {}).name || (path ? path.split("/").pop().replace(/\.gguf$/i, "") : "");
const agentModelName = a => a.model ? (modelNameOf(a.model) + (S.status?.models.some(m => m.path === a.model) ? "" : " (não encontrado)")) : "modelo principal";
function modelOptions(sel) {
  const models = S.status?.models || [];
  return '<option value="">Modelo principal (o carregado no topo)</option>' + models.map(m =>
    `<option value="${esc(m.path)}" ${m.path === sel ? "selected" : ""}>${esc(m.name)} ${capIcons(m.info)} (${fmtSize(m.size)})</option>`).join("") +
    (sel && !models.some(m => m.path === sel) ? `<option value="${esc(sel)}" selected>⚠ ${esc(modelNameOf(sel))} (não encontrado)</option>` : "");
}

async function loadAgents() {
  try { AG.doc = await api("/api/agents"); } catch { return; }
  renderAgentSelect();
  if ($("#agentsModal").classList.contains("open")) renderAgentsModal();
}
async function saveAgentsDoc(msg) {
  AG.doc = await api("/api/agents", { method: "PUT", body: AG.doc });
  renderAgentSelect(); renderAgentsModal();
  if (msg) toast(msg);
}

// ------------------------------------------------------------------ seletor do compositor
function renderAgentSelect() {
  const sel = $("#agentSelect"); const cur = ls("agentSel", "");
  const g = AG.doc.groups.map(x => `<option value="g:${x.id}">${esc(x.icon)} ${esc(x.name)} · ${x.steps.length} agentes</option>`).join("");
  const a = AG.doc.agents.map(x => `<option value="a:${x.id}">${esc(x.icon)} ${esc(x.name)}</option>`).join("");
  const html = (g ? `<optgroup label="Grupos">${g}</optgroup>` : "") + (a ? `<optgroup label="Agentes sozinhos">${a}</optgroup>` : "")
    || '<option value="">Nenhum agente: clique em ⚙️</option>';
  if (sel.dataset.sig !== html) { sel.innerHTML = html; sel.dataset.sig = html; }
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}
$("#agentSelect").onchange = e => { lsSet("agentSel", e.target.value); updateHint(); };
function currentAgentSel() {
  const [t, id] = ($("#agentSelect").value || "").split(":");
  return t === "g" ? { group: groupById(id) } : t === "a" ? { agent: agentById(id) } : {};
}
function agentsHint() {
  const s = currentAgentSel();
  if (s.group) return `👥 ${s.group.name}: ` + s.group.steps.map(st => { const a = agentById(st.agent); return a ? `${a.icon} ${a.name}${st.role === "validator" ? " (valida)" : ""}` : ""; }).join(" → ");
  if (s.agent) return `${s.agent.icon} Conversando com o agente ${s.agent.name}.`;
  return "Crie um agente ou grupo no ⚙️ ao lado (ou na barra lateral, em Agentes).";
}

// ------------------------------------------------------------------ janela de edição
function renderAgentsModal() {
  const ed = AG.edit;
  $("#agentList").innerHTML = AG.doc.agents.map(a => `<div class="item clickable ${ed?.type === "agent" && ed.id === a.id ? "sel" : ""}" data-edit="agent:${a.id}">
      <span class="ag-dot" style="--c:${esc(a.color)}">${esc(a.icon)}</span><div class="name-col"><span class="name">${esc(a.name)}</span><small class="muted ag-model">${esc(agentModelName(a))}</small></div>${a.web ? '<span title="Pode pesquisar na web">🌐</span>' : ""}</div>`).join("")
    || '<p class="muted small-note">Nenhum agente ainda.</p>';
  $("#groupList").innerHTML = AG.doc.groups.map(g => `<div class="item clickable ${ed?.type === "group" && ed.id === g.id ? "sel" : ""}" data-edit="group:${g.id}">
      <span class="ag-dot" style="--c:#4a4d60">${esc(g.icon)}</span><span class="name">${esc(g.name)}</span><span class="meta">${g.steps.length}</span></div>`).join("")
    || '<p class="muted small-note">Nenhum grupo ainda.</p>';
  renderAgentEditor();
}

function renderAgentEditor() {
  const box = $("#agentEditor"); const d = AG.draft;
  if (!d) {
    box.innerHTML = `<div class="ag-intro"><h3>Como funciona</h3>
      <p><b>🤖 Agente</b>: um assistente com uma <b>função</b> (instruções) só dele. Ex.: "crie um problema de matemática".</p>
      <p><b>👥 Grupo</b>: uma sequência de agentes. Cada um recebe o seu pedido <b>e o trabalho dos anteriores</b>.</p>
      <p><b>✅ Validador</b>: marque um agente do grupo como validador. Se ele <b>reprovar</b>, o agente anterior refaz com o feedback e o validador confere de novo.</p>
      <p>Para usar, escolha o modo <b>👥 Agentes</b> na caixa de mensagem e selecione o grupo ou agente.</p>
      <p class="muted">Comece por um modelo pronto ao lado (ex.: 🧮 Matemática) e edite como quiser.</p></div>`;
    return;
  }
  if (AG.edit.type === "agent") {
    box.innerHTML = `<h3>${AG.edit.isNew ? "Novo agente" : "Editar agente"}</h3>
      <div class="ag-form">
        <div class="row"><label class="grow">Nome <input class="input" id="agName" value="${esc(d.name)}" maxlength="60" placeholder="Ex.: Resolvedor"></label></div>
        <label>Ícone <div class="icon-pick">${AGENT_ICONS.map(i => `<button type="button" class="${i === d.icon ? "on" : ""}" data-icon="${i}">${i}</button>`).join("")}
          <input class="input icon-input" id="agIcon" value="${esc(d.icon)}" maxlength="8" title="Ou digite/cole outro emoji"></div></label>
        <label>Cor <div class="color-pick">${AGENT_COLORS.map(c => `<button type="button" class="${c === d.color ? "on" : ""}" data-color="${c}" style="--c:${c}"></button>`).join("")}</div></label>
        <label>Modelo
          <select class="input" id="agModel">${modelOptions(d.model)}</select>
          <small class="muted">Cada agente pode usar um modelo diferente (ex.: um leve e rápido para criar, um mais forte para validar). Modelos diferentes do principal são carregados juntos, se couberem na GPU.</small></label>
        <label>Função do agente (instruções)
          <textarea class="input" id="agInstr" rows="9" placeholder="Descreva o que este agente faz, como deve responder e o que NÃO deve fazer.&#10;Ex.: Você resolve o problema do agente anterior mostrando o passo a passo e destaca a resposta final.">${esc(d.instructions)}</textarea></label>
        <div class="grid">
          <label class="check"><input type="checkbox" id="agTempOn" ${d.temperature !== null && d.temperature !== undefined ? "checked" : ""}> Temperatura própria</label>
          <label>Criatividade: <span id="agTempVal">${(d.temperature ?? 0.7).toFixed(2)}</span>
            <input type="range" class="range" id="agTemp" min="0" max="1.5" step="0.05" value="${d.temperature ?? 0.7}" ${d.temperature === null || d.temperature === undefined ? "disabled" : ""}>
            <small class="muted">Baixa = preciso e consistente (bom para validar e calcular). Alta = criativo.</small></label>
          <label class="check full"><input type="checkbox" id="agWeb" ${d.web ? "checked" : ""}> 🌐 Pode pesquisar na web antes de responder</label>
        </div>
        <div class="row end">
          ${AG.edit.isNew ? "" : '<button type="button" class="btn danger" data-ag="delete">Excluir</button><button type="button" class="btn" data-ag="chat">Conversar com ele</button>'}
          <button type="button" class="btn primary" data-ag="save">Salvar agente</button>
        </div>
      </div>`;
    return;
  }
  const opts = sel => AG.doc.agents.map(a => `<option value="${a.id}" ${a.id === sel ? "selected" : ""}>${esc(a.icon)} ${esc(a.name)} · ${esc(agentModelName(a))}</option>`).join("");
  box.innerHTML = `<h3>${AG.edit.isNew ? "Novo grupo" : "Editar grupo"}</h3>
    <div class="ag-form">
      <div class="row"><label style="width:90px">Ícone <input class="input icon-input" id="grIcon" value="${esc(d.icon)}" maxlength="8"></label>
        <label class="grow">Nome <input class="input" id="grName" value="${esc(d.name)}" maxlength="60" placeholder="Ex.: Matemática"></label></div>
      <label>Objetivo do grupo <input class="input" id="grDesc" value="${esc(d.description)}" placeholder="Ex.: Cria um cálculo, resolve e valida"></label>
      <div><b>Etapas</b> <small class="muted">(executadas em ordem; cada agente vê o trabalho dos anteriores)</small></div>
      <div class="steps-edit">${d.steps.map((s, i) => `<div class="step-row" data-i="${i}">
          <span class="step-n">${i + 1}</span>
          <select class="input" data-step-agent>${AG.doc.agents.length ? opts(s.agent) : "<option>Crie agentes primeiro</option>"}</select>
          <select class="input small-input" data-step-role><option value="agent" ${s.role !== "validator" ? "selected" : ""}>Agente</option><option value="validator" ${s.role === "validator" ? "selected" : ""}>✅ Validador</option></select>
          <button type="button" class="icon-btn" data-step="up" title="Subir">▲</button><button type="button" class="icon-btn" data-step="down" title="Descer">▼</button><button type="button" class="icon-btn" data-step="del" title="Remover">✕</button>
        </div>`).join("") || '<p class="muted small-note">Nenhuma etapa. Adicione agentes abaixo.</p>'}</div>
      <div class="row"><button type="button" class="btn small" data-ag="add-step" ${AG.doc.agents.length ? "" : "disabled"}>+ Adicionar etapa</button>
        ${AG.doc.agents.length ? "" : '<small class="muted">Crie agentes primeiro.</small>'}</div>
      <label style="max-width:320px">Tentativas extras quando o validador reprovar <input class="input" type="number" id="grRetries" min="0" max="5" value="${d.max_retries}"></label>
      <div class="row end">
        ${AG.edit.isNew ? "" : '<button type="button" class="btn danger" data-ag="delete">Excluir</button><button type="button" class="btn" data-ag="chat">Usar no chat</button>'}
        <button type="button" class="btn primary" data-ag="save">Salvar grupo</button>
      </div>
    </div>`;
}

// lê o formulário para o rascunho (antes de redesenhar ou salvar)
function syncDraft() {
  const d = AG.draft; if (!d) return;
  if (AG.edit.type === "agent") {
    d.name = $("#agName").value.trim(); d.icon = $("#agIcon").value.trim() || "🤖"; d.instructions = $("#agInstr").value;
    d.temperature = $("#agTempOn").checked ? +$("#agTemp").value : null; d.web = $("#agWeb").checked; d.model = $("#agModel").value;
  } else {
    d.name = $("#grName").value.trim(); d.icon = $("#grIcon").value.trim() || "👥"; d.description = $("#grDesc").value.trim();
    d.max_retries = Math.max(0, Math.min(5, +$("#grRetries").value || 0));
    $$("#agentEditor .step-row").forEach(r => { const s = d.steps[+r.dataset.i]; s.agent = r.querySelector("[data-step-agent]").value; s.role = r.querySelector("[data-step-role]").value; });
  }
}

function editItem(type, id) {
  const src = type === "agent" ? agentById(id) : groupById(id);
  AG.edit = { type, id, isNew: !src };
  AG.draft = src ? clone(src) : type === "agent"
    ? { id: uid(), name: "", icon: "🤖", color: AGENT_COLORS[AG.doc.agents.length % AGENT_COLORS.length], instructions: "", temperature: null, web: false, model: "" }
    : { id: uid(), name: "", icon: "👥", description: "", steps: [], max_retries: 2 };
  renderAgentsModal();
  (type === "agent" ? $("#agName") : $("#grName"))?.focus();
}

$("#agentList").onclick = $("#groupList").onclick = e => {
  const it = e.target.closest("[data-edit]"); if (!it) return;
  const [type, id] = it.dataset.edit.split(":"); editItem(type, id);
};
$("#newAgent").onclick = () => editItem("agent", null);
$("#newGroup").onclick = () => editItem("group", null);
$$("[data-tpl]").forEach(b => b.onclick = async () => {
  const r = await post("/api/agents/template", { kind: b.dataset.tpl });
  AG.doc = r.doc; renderAgentSelect(); editItem("group", r.group_id); toast("Grupo criado! Edite à vontade ou use no chat.");
});

$("#agentEditor").addEventListener("input", e => {
  if (e.target.id === "agTemp") $("#agTempVal").textContent = (+e.target.value).toFixed(2);
});
$("#agentEditor").addEventListener("change", e => {
  if (e.target.id === "agTempOn") $("#agTemp").disabled = !e.target.checked;
});
$("#agentEditor").addEventListener("click", async e => {
  const d = AG.draft; if (!d) return;
  const ic = e.target.closest("[data-icon]"); if (ic) { syncDraft(); d.icon = ic.dataset.icon; return renderAgentEditor(); }
  const co = e.target.closest("[data-color]"); if (co) { syncDraft(); d.color = co.dataset.color; return renderAgentEditor(); }
  const st = e.target.closest("[data-step]");
  if (st) {
    syncDraft(); const i = +st.closest(".step-row").dataset.i; const s = d.steps;
    if (st.dataset.step === "del") s.splice(i, 1);
    if (st.dataset.step === "up" && i > 0) [s[i - 1], s[i]] = [s[i], s[i - 1]];
    if (st.dataset.step === "down" && i < s.length - 1) [s[i + 1], s[i]] = [s[i], s[i + 1]];
    return renderAgentEditor();
  }
  const act = e.target.closest("[data-ag]")?.dataset.ag; if (!act) return;
  if (act === "add-step") { syncDraft(); d.steps.push({ agent: AG.doc.agents[0].id, role: "agent" }); return renderAgentEditor(); }
  if (act === "save") {
    syncDraft();
    if (!d.name) return toast("Dê um nome.");
    if (AG.edit.type === "agent" && !d.instructions.trim()) return toast("Descreva a função do agente.");
    if (AG.edit.type === "group" && !d.steps.length) return toast("Adicione pelo menos uma etapa.");
    const list = AG.edit.type === "agent" ? AG.doc.agents : AG.doc.groups;
    const i = list.findIndex(x => x.id === d.id); if (i >= 0) list[i] = d; else list.push(d);
    await saveAgentsDoc(AG.edit.type === "agent" ? "Agente salvo" : "Grupo salvo");
    AG.edit.isNew = false; AG.draft = clone((AG.edit.type === "agent" ? agentById : groupById)(d.id) || d);
    return renderAgentsModal();
  }
  if (act === "delete") {
    const inGroups = AG.edit.type === "agent" ? AG.doc.groups.filter(g => g.steps.some(s => s.agent === d.id)).map(g => g.name) : [];
    if (!confirm(`Excluir "${d.name}"?` + (inGroups.length ? `\n\nEle será removido dos grupos: ${inGroups.join(", ")}.` : ""))) return;
    if (AG.edit.type === "agent") { AG.doc.agents = AG.doc.agents.filter(a => a.id !== d.id); AG.doc.groups.forEach(g => g.steps = g.steps.filter(s => s.agent !== d.id)); }
    else AG.doc.groups = AG.doc.groups.filter(g => g.id !== d.id);
    AG.edit = AG.draft = null; return saveAgentsDoc("Excluído");
  }
  if (act === "chat") {
    const v = (AG.edit.type === "agent" ? "a:" : "g:") + d.id;
    lsSet("agentSel", v); renderAgentSelect(); $("#agentSelect").value = v;
    $("#agentsModal").classList.remove("open"); setMode("agents"); newChat();
  }
});

// ------------------------------------------------------------------ execução de um grupo
async function runGroup(group) {
  if (!group) return toast("Grupo não encontrado.");
  const msg = { role: "assistant", mode: "group", model: modelName(), group: { id: group.id, name: group.name, icon: group.icon }, steps: [], content: "" };
  const messages = buildMessages();
  S.chat.messages.push(msg);
  startGenerating();
  let base = 0, lastPred = 0, cur = null;
  try {
    await streamChat({ group_id: group.id, messages, ...sampling() }, S.abort.signal, j => {
      if (j.timings) {
        lastPred = j.timings.predicted_n || 0;
        msg.stats = { tps: j.timings.predicted_per_second || 0, tokens: base + lastPred, lastOut: lastPred, prompt: j.timings.prompt_n || 0, cached: j.timings.cache_n || 0 };
      }
      if (j.llmlocal && cur) cur.web = { ...cur.web, ...j.llmlocal };
      const g = j.group;
      if (g?.type === "loading") msg.loadingModel = { index: g.index, model: g.model };
      if (g?.type === "step_start") { msg.loadingModel = null; base += lastPred; lastPred = 0; cur = { index: g.index, agent: g.agent, role: g.role, attempt: g.attempt, model: g.model, text: "", reasoning: "", status: "running" }; msg.steps.push(cur); }
      else if (g?.type === "delta" && cur) cur.text += g.delta;
      else if (g?.type === "reasoning" && cur) cur.reasoning += g.delta;
      else if (g?.type === "step_end" && cur) { cur.status = "done"; cur.verdict = g.verdict; }
      else if (g?.type === "retry") msg.steps.push({ type: "retry", attempt: g.attempt });
      else if (g?.type === "done") { msg.content = g.final; msg.approved = g.approved; }
      renderLastMessage();
    }, "/api/group/run");
  } catch (e) {
    if (e.name !== "AbortError") msg.error = e.message;
  } finally {
    msg.steps.forEach(s => { if (s.status === "running") s.status = "stopped"; }); delete msg.loadingModel;
    if (!msg.content) msg.content = [...msg.steps].reverse().find(s => s.text && s.role !== "validator")?.text || "";
    await finishGenerating();
  }
}

function groupMsgHTML(msg, idx, isLast, streaming) {
  const live = streaming ? (msg.loadingModel ? `⏳ carregando ${esc(msg.loadingModel.model)}...` : msg.stats?.tokens ? `⚡ ${msg.stats.tps.toFixed(1)} tok/s · ${fmtNum(msg.stats.tokens)} tokens` : "começando...") : "";
  let h = `<div class="msg assistant group-msg ${isLast ? "last" : ""}" data-i="${idx}"><div class="role">👥 ${esc(msg.group.icon)} ${esc(msg.group.name)} · ${esc(msg.model || "")}${live ? `<span class="live">${live}</span>` : ""}</div><div class="g-steps">`;
  for (const s of msg.steps) {
    if (s.type === "retry") { h += `<div class="g-retry">🔁 O validador reprovou: refazendo (tentativa ${s.attempt})</div>`; continue; }
    const verdict = s.verdict === "APROVADO" ? '<span class="verdict ok">✅ Aprovado</span>' : s.verdict === "REPROVADO" ? '<span class="verdict bad">❌ Reprovado</span>' : "";
    const tag = s.role === "validator" ? "validador" : `etapa ${s.index + 1}`;
    h += `<div class="g-step" style="--c:${esc(s.agent.color)}"><div class="g-head"><span class="ag-dot" style="--c:${esc(s.agent.color)}">${esc(s.agent.icon)}</span>
      <b>${esc(s.agent.name)}</b><small class="muted">${tag}${s.attempt > 1 ? ` · tentativa ${s.attempt}` : ""}${s.model ? ` · ${esc(s.model)}` : ""}</small><span class="spacer"></span>${s.status === "running" ? '<span class="spin"></span>' : verdict}</div>`;
    if (s.web) h += webBoxHTML(s.web, s.status === "running");
    if (s.reasoning) h += `<details class="think"><summary>Raciocínio</summary><div class="think-body">${esc(s.reasoning)}</div></details>`;
    const shown = s.role === "validator" ? s.text.replace(/\n?\**\s*VEREDITO\s*[:\-–][^\n]*/gi, "").trim() : s.text;
    h += `<div class="content ${s.status === "running" ? "cursor" : ""}">${linkCitations(md(shown), s.web?.sources)}</div></div>`;
  }
  if (streaming && msg.loadingModel) h += `<div class="g-loading"><span class="spin"></span> Carregando o modelo <b>${esc(msg.loadingModel.model)}</b> para a etapa ${msg.loadingModel.index + 1}...</div>`;
  h += "</div>";
  if (!streaming && msg.approved === false) h += `<div class="err">⚠ O validador não aprovou o resultado, mesmo depois das tentativas extras. Veja o feedback acima.</div>`;
  if (msg.error) h += `<div class="err">${esc(msg.error)}</div>`;
  if (!streaming) h += `<div class="actions"><button data-act="copy">Copiar resultado</button>${isLast ? '<button data-act="regen">Refazer</button>' : ""}<button data-act="del">Excluir</button>${statsHTML(msg.stats)}</div>`;
  return h + "</div>";
}
