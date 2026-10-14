"use strict";
const ls = (k, def) => { try { return localStorage.getItem(k) ?? def; } catch { return def; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch {} };

const S = {
  status: null,
  media: null,         // status do Whisper / gerador de imagem
  chat: null,          // conversa aberta {id, title, created, messages}
  generating: false,
  abort: null,
  selectedRepo: "",
  chatFilter: "",
  web: ls("web", "0") === "1",
  mode: ls("mode", "chat"),          // chat | codex | image
  workspace: ls("workspace", ""),
  attachments: [],     // anexos pendentes no compositor
  wsEdit: [],          // pastas do Codex sendo editadas nas Configurações
  doneTasks: new Set(),
};

// ------------------------------------------------------------------ util
let toastTimer;
function toast(msg, ms = 2600) {
  const el = $("#toast"); el.textContent = trText(msg); el.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), ms);
}
const modelName = () => (S.status.models.find(m => m.path === S.status.engine.model) || {}).name || "";
const extLang = p => ((p || "").split(".").pop() || "").toLowerCase();
const baseName = p => (p || "").split(/[\\/]/).pop();

// ------------------------------------------------------------------ etiquetas dos modelos
function capsHTML(info, compact = false) {
  if (!info) return "";
  const caps = (info.caps || []).map(c => `<span class="cap cap-${c.key}" title="${esc(c.label + ": " + c.tip)}">${c.icon}${compact ? "" : " " + esc(c.label)}</span>`).join("");
  const meta = compact ? "" : [info.params && `<span class="meta-pill" title="Tamanho do modelo em parâmetros. Mais parâmetros = mais inteligente e mais pesado.">🧩 ${esc(info.params)}</span>`,
    info.ctx && `<span class="meta-pill" title="Contexto máximo que o modelo suporta (quanto texto ele consegue considerar de uma vez).">📏 ${esc(info.ctx)}</span>`,
    info.license && `<span class="meta-pill" title="Licença de uso">📜 ${esc(info.license)}</span>`].filter(Boolean).join("");
  return `<span class="caps">${caps}${meta}</span>`;
}
const capIcons = info => (info?.caps || []).filter(c => ["vision", "audio", "tools", "reasoning", "uncensored", "moe"].includes(c.key)).map(c => c.icon).join("");
function starsHTML(q) {
  if (!q?.stars) return "";
  return `<span class="stars" title="${esc(q.tip)}">${"★".repeat(q.stars)}<span class="off">${"★".repeat(5 - q.stars)}</span></span>`;
}
// estimativa de tamanho em Q4_K_M a partir dos parâmetros (≈ 0,6 byte por parâmetro)
const q4Size = info => info?.params_n ? info.params_n * 0.6 : 0;

// ------------------------------------------------------------------ status
async function refreshStatus() {
  try {
    S.status = await api("/api/status");
  } catch { $("#statusPill").textContent = "Servidor offline"; $("#statusPill").className = "pill error"; return; }
  // recarrega o status de mídia quando uma instalação termina
  const finished = S.status.tasks.filter(t => t.status === "done" && !S.doneTasks.has(t.id));
  finished.forEach(t => S.doneTasks.add(t.id));
  if (finished.length) { loadMedia(); loadKbs(); }
  const lang = S.status.settings.language; if (lang && lang !== LANG && !S.generating) return setLanguage(lang);
  renderTopbar(); renderChatList(); renderTasks(); renderStatsBar(); renderModeBars(); renderReaPlaces();
  if ($("#modelsModal").classList.contains("open")) { renderLocalModels(); renderEngine(); }
  if (typeof renderInspector === "function") renderInspector();
}

async function loadMedia() {
  try { S.media = await api("/api/media"); } catch { return; }
  renderModeBars(); renderReaPlaces();
  if ($("#modelsModal").classList.contains("open")) renderEngine();
  if ($("#modelsModal").classList.contains("open")) { renderMedia(); renderLocalModels(); }
}

function renderTopbar() {
  const st = S.status; const e = st.engine;
  const sel = $("#modelSelect"); const prev = sel.value || e.model || st.settings.last_model;
  const opts = st.models.map(m => { const ic = capIcons(m.info).replace("👁", m.mmproj ? "👁" : ""); return `<option value="${esc(m.path)}">${esc(m.name)} ${ic} (${fmtSize(m.size)})</option>`; }).join("");
  if (sel.dataset.sig !== opts) {
    sel.innerHTML = opts || '<option value="">Nenhum modelo baixado</option>';
    sel.dataset.sig = opts;
    if (st.models.some(m => m.path === prev)) sel.value = prev;
  }
  const pill = $("#statusPill"); const btn = $("#loadBtn");
  const name = modelName() || e.model;
  const caps = (e.vision ? " · " + t("👁 visão") : "") + (e.audio ? " · 🎧 " + t("Áudio").toLowerCase() : "");
  const map = { stopped: [t("Nenhum modelo carregado"), ""], loading: [t("Carregando {name}...", { name }), "loading"],
                ready: [(e.mtp_error ? "⚠ " : "") + "● " + name + (e.backend ? ` · ${e.backend.toUpperCase()}` : "") + (e.mtp ? " · ⚡ MTP" : "") + caps, "ready"], error: [t("Erro no motor (clique)"), "error"] };
  const extras = (st.extras || []).filter(x => x.state === "ready" || x.state === "loading");
  pill.textContent = map[e.state][0] + (extras.length ? ` · +${extras.length} extra${extras.length > 1 ? "s" : ""}` : "");
  if (e.state === "stopped" && extras.length) { pill.textContent = t("● {n} modelo(s) extra(s)", { n: extras.length }); pill.className = "pill ready"; }
  else pill.className = "pill " + map[e.state][1];
  pill.title = e.error || (extras.length ? t("Modelos extras (agentes / pergunta rápida):") + "\n" + extras.map(x => `• ${x.name} · ${(x.device || "gpu").toUpperCase()}${x.state === "loading" ? " (carregando)" : ""}`).join("\n") : "");
  const loadedSelected = (e.state === "ready" || e.state === "loading") && sel.value === e.model;
  btn.textContent = loadedSelected ? (e.state === "loading" ? "Cancelar" : "Descarregar") : "Carregar";
  btn.className = "btn " + (loadedSelected ? "" : "primary");
  btn.disabled = !st.models.length;
  updateHint();
}

function updateHint() {
  const st = S.status; if (!st) return;
  let h = "";
  if (S.mode === "image") {
    const im = S.media?.image;
    if (!im?.installed) h = "Para gerar imagens, instale o motor em Modelos → Mídia.";
    else if (!Object.values(im.presets).some(p => p.installed)) h = "Baixe um modelo de imagem em Modelos → Mídia.";
    else h = "🎨 Descreva a imagem. Pode escrever em português.";
  } else if (!Object.keys(st.backends).length) h = "Primeiro passo: abra Modelos → Motor e instale o motor.";
  else if (!st.models.length) h = "Baixe um modelo em Modelos → Baixar modelos.";
  else if (st.engine.state !== "ready") h = st.engine.state === "loading" ? "Carregando modelo na memória..." : "Selecione um modelo e clique em Carregar.";
  else if (S.mode === "agents") h = agentsHint();
  else if (S.mode === "codex" && S.workspace === "__mcp") h = t("🔌 O Codex vai usar só as ferramentas MCP: {names}", { names: mcpEnabled().map(s => s.name).join(", ") });
  else if (S.mode === "codex") h = S.workspace ? t("🛠️ O Codex trabalha somente dentro de {path}", { path: S.workspace }) : t("Escolha ou adicione uma pasta para o Codex trabalhar.");
  else h = S.web ? "🌐 Pesquisa na web ligada: o modelo vai pesquisar antes de cada resposta." : "";
  $("#hint").textContent = h;
}

$("#loadBtn").onclick = async () => {
  const e = S.status.engine; const model = $("#modelSelect").value;
  try {
    if ((e.state === "ready" || e.state === "loading") && model === e.model) await post("/api/unload");
    else { await post("/api/load", { model }); toast("Carregando modelo..."); }
  } catch (err) { toast(err.message, 5000); }
  refreshStatus();
};
$("#modelSelect").onchange = renderTopbar;
$("#statusPill").onclick = () => {
  if (S.status?.engine.state === "error") { openModal("modelsModal"); switchTab("tabEngine"); }
};

// ------------------------------------------------------------------ modos (Chat / Codex / Imagem)
const PLACEHOLDER = {
  chat: "Escreva sua mensagem... (Enter envia, Shift+Enter quebra linha)",
  codex: "Peça ao Codex: ex. “crie um jogo da cobrinha em HTML” ou “corrija o erro no main.py”",
  image: "Descreva a imagem que você quer gerar...",
  agents: "Escreva o pedido para o grupo ou agente selecionado... (ex.: “uma equação do 2º grau de nível médio”)",
};
function setMode(mode) {
  S.mode = mode; lsSet("mode", mode);
  $$("#modes button").forEach(b => b.classList.toggle("on", b.dataset.mode === mode));
  $("#input").placeholder = t(PLACEHOLDER[mode]);
  $("#webBtn").hidden = mode !== "chat";
  if (typeof renderKbSelect === "function") renderKbSelect();
  $("#attachBtn").hidden = mode === "image";
  if (mode === "image" && S.attachments.length) { S.attachments = []; renderAttachTray(); }
  renderModeBars(); updateHint();
  if (typeof renderModeTag === "function") renderModeTag();
}
$("#modes").onclick = e => { const b = e.target.closest("[data-mode]"); if (b && !S.generating) setMode(b.dataset.mode); };

function renderModeBars() {
  $("#codexBar").hidden = S.mode !== "codex";
  $("#imageBar").hidden = S.mode !== "image";
  $("#agentsBar").hidden = S.mode !== "agents";
  if (!S.status) return;
  // pastas do Codex
  const wss = S.status.settings.workspaces || [];
  const hasMcp = mcpEnabled().length > 0;
  if (S.workspace && !wss.includes(S.workspace) && !(S.workspace === "__mcp" && hasMcp)) S.workspace = "";
  if (!S.workspace && wss.length) S.workspace = wss[0];
  const wsOpts = (wss.length ? wss.map(w => `<option value="${esc(w)}" ${w === S.workspace ? "selected" : ""}>📁 ${esc(baseName(w))}</option>`).join("")
    : '<option value="">Nenhuma pasta liberada</option>') +
    (hasMcp ? `<option value="__mcp" ${S.workspace === "__mcp" ? "selected" : ""}>🔌 ${esc(t("Sem pasta: só ferramentas MCP"))}</option>` : "") +
    '<option value="__add">+ Adicionar pasta...</option>';
  const ws = $("#workspaceSelect");
  if (ws.dataset.sig !== wsOpts + S.workspace) { ws.innerHTML = wsOpts; ws.dataset.sig = wsOpts + S.workspace; ws.title = S.workspace; }
  // modelos de imagem
  const presets = S.media?.image?.presets || {};
  const cur = S.status.settings.image_preset;
  const pOpts = Object.entries(presets).map(([k, p]) => `<option value="${k}" ${k === cur ? "selected" : ""} ${p.installed ? "" : "disabled"}>${esc(p.name)}${p.installed ? "" : " " + t("(não baixado)")}</option>`).join("")
    || '<option value="">Sem modelos de imagem</option>';
  const ps = $("#imagePresetSelect");
  if (ps.dataset.sig !== pOpts) { ps.innerHTML = pOpts; ps.dataset.sig = pOpts; }
}
$("#workspaceSelect").onchange = async e => {
  if (e.target.value === "__add") { e.target.value = S.workspace; return addWorkspace(); }
  S.workspace = e.target.value; lsSet("workspace", S.workspace); updateHint();
};
$("#openWorkspace").onclick = () => S.workspace && S.workspace !== "__mcp" ? desktop.openPath(S.workspace) : toast("Nenhuma pasta selecionada.");
$("#imagePresetSelect").onchange = e => api("/api/settings", { method: "PUT", body: { image_preset: e.target.value } }).then(refreshStatus);

async function addWorkspace() {
  const dir = await desktop.chooseFolder();
  if (!dir) return;
  const list = [...new Set([...(S.status.settings.workspaces || []), dir])];
  await api("/api/settings", { method: "PUT", body: { workspaces: list } });
  S.workspace = dir; lsSet("workspace", dir);
  await refreshStatus(); toast("Pasta liberada para o Codex");
}

// ------------------------------------------------------------------ conversas
function renderChatList() {
  if (S.renaming) return;
  const list = S.status.chats.filter(c => !S.chatFilter || (c.title || "").toLowerCase().includes(S.chatFilter));
  const now = new Date(); const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()) / 1000;
  const groups = [["Hoje", c => c.updated >= today], ["Últimos 7 dias", c => c.updated >= today - 6 * 86400],
                  ["Últimos 30 dias", c => c.updated >= today - 29 * 86400], ["Mais antigas", () => true]];
  const used = new Set(); let html = "";
  for (const [label, fn] of groups) {
    const g = list.filter(c => !used.has(c.id) && fn(c)); g.forEach(c => used.add(c.id));
    if (!g.length) continue;
    html += `<div class="chat-group">${label}</div>` + g.map(c =>
      `<div class="chat-item ${S.chat?.id === c.id ? "active" : ""}" data-id="${c.id}" title="Duplo clique para renomear">
        <span class="t">${esc(c.title || "Sem título")}</span><button class="x" title="Excluir">✕</button></div>`).join("");
  }
  if ($("#chatList").dataset.sig !== html) { $("#chatList").innerHTML = html; $("#chatList").dataset.sig = html; }
}

$("#chatList").addEventListener("click", async ev => {
  const item = ev.target.closest(".chat-item"); if (!item) return;
  const id = item.dataset.id;
  if (ev.target.classList.contains("x")) {
    if (!confirm(t("Excluir esta conversa (e os arquivos anexados nela)?"))) return;
    await api("/api/chats/" + id, { method: "DELETE" });
    if (S.chat?.id === id) newChat();
    return refreshStatus();
  }
  if (S.generating) return toast("Aguarde terminar ou clique em Parar.");
  S.chat = await api("/api/chats/" + id);
  renderMessages(); renderChatList();
});
$("#chatList").addEventListener("dblclick", async ev => {
  const item = ev.target.closest(".chat-item"); if (!item) return;
  const c = item.dataset.id === S.chat?.id ? S.chat : await api("/api/chats/" + item.dataset.id);
  const span = item.querySelector(".t");
  const inp = document.createElement("input"); inp.className = "input rename"; inp.value = c.title || "";
  span.replaceWith(inp); inp.focus(); inp.select(); S.renaming = true;
  const finish = async ok => {
    if (!S.renaming) return; S.renaming = false;
    if (ok && inp.value.trim()) { c.title = inp.value.trim(); await saveChat(c); }
    $("#chatList").dataset.sig = ""; refreshStatus();
  };
  inp.onkeydown = e => { if (e.key === "Enter") finish(true); if (e.key === "Escape") { e.stopPropagation(); finish(false); } };
  inp.onblur = () => finish(true);
});
$("#chatSearch").oninput = e => { S.chatFilter = e.target.value.toLowerCase(); renderChatList(); };

function newChat() {
  if (S.generating) return toast("Aguarde terminar ou clique em Parar.");
  S.chat = null; renderMessages(); if (S.status) renderChatList(); $("#input").focus();
}
$("#newChat").onclick = newChat;

async function saveChat(c = S.chat) {
  if (!c) return;
  const r = await api("/api/chats/" + c.id, { method: "PUT", body: c });
  c.updated = r.updated;
}

// ------------------------------------------------------------------ anexos (compositor)
function attachCtx() {
  return { modelHasVision: !!S.status?.engine.vision || !!S.status?.models.find(m => m.path === $("#modelSelect").value)?.mmproj,
           modelHasAudio: !!S.status?.engine.audio, whisperReady: !!(S.media?.whisper?.installed && S.media.whisper.models.length) };
}

function addFiles(files) {
  if (S.mode === "image") setMode("chat");
  for (const file of files) {
    const item = { uid: uid(), name: file.name, kind: attachKind(file), status: "processing", note: t("preparando"), atts: [] };
    if (item.kind === "image") item.preview = URL.createObjectURL(file);
    S.attachments.push(item); renderAttachTray();
    processFile(file, note => { item.note = note; renderAttachTray(); }, attachCtx())
      .then(atts => { item.atts = atts; item.status = "ready"; item.note = describeAtts(atts); })
      .catch(err => { item.status = "error"; item.note = trText(err.message); })
      .finally(renderAttachTray);
  }
}
function describeAtts(atts) {
  const a = atts[0]; if (!a) return "";
  if (a.kind === "text") return t("{n} caracteres", { n: fmtNum(a.text.length) }) + (a.pages ? " · " + t("{n} páginas", { n: a.pages }) : "");
  if (a.kind === "audio") return a.transcript !== undefined ? `${Math.round(a.duration)}s · ${t("transcrito")}` : `${Math.round(a.duration)}s`;
  if (a.kind === "video") return `${Math.round(a.duration)}s · ${t("{n} quadros", { n: a.frames.length })}${a.transcript ? " · " + t("transcrito") : ""}`;
  if (a.kind === "image") return atts.length > 1 ? t("{n} páginas como imagem", { n: atts.length }) : t("imagem");
  return "";
}
function renderAttachTray() {
  $("#attachTray").innerHTML = S.attachments.map(it => `<div class="att-chip ${it.status}" data-uid="${it.uid}" title="${esc(it.note || "")}">
      ${it.preview ? `<img src="${it.preview}">` : `<span class="att-ico">${ATTACH_ICON[it.kind] || "📎"}</span>`}
      <span class="att-txt"><b>${esc(it.name)}</b><small>${it.status === "processing" ? '<span class="spin"></span> ' : it.status === "error" ? "⚠ " : ""}${esc(it.note || "")}</small></span>
      <button class="att-x" title="Remover">✕</button></div>`).join("");
}
$("#attachTray").onclick = e => {
  if (!e.target.classList.contains("att-x")) return;
  const uidv = e.target.closest(".att-chip").dataset.uid;
  S.attachments = S.attachments.filter(a => a.uid !== uidv); renderAttachTray();
};
$("#attachBtn").onclick = () => $("#fileInput").click();
$("#fileInput").onchange = e => { addFiles([...e.target.files]); e.target.value = ""; };
$("#input").addEventListener("paste", e => {
  const files = [...(e.clipboardData?.files || [])];
  if (files.length) { e.preventDefault(); addFiles(files); }
});
let dragDepth = 0;
document.addEventListener("dragenter", e => { if (e.dataTransfer?.types.includes("Files")) { dragDepth++; $("#composer").classList.add("drop"); } });
document.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; $("#composer").classList.remove("drop"); } });
document.addEventListener("dragover", e => e.preventDefault());
document.addEventListener("drop", e => {
  e.preventDefault(); dragDepth = 0; $("#composer").classList.remove("drop");
  if (e.dataTransfer?.files.length && !e.target.closest(".modal")) addFiles([...e.dataTransfer.files]);
});

function attachmentsHTML(atts) {
  if (!atts?.length) return "";
  return `<div class="msg-atts">` + atts.map(a => {
    if (a.kind === "image") return `<img class="att-thumb" src="/api/uploads/${a.id}" title="${esc(a.name)}" data-zoom>`;
    if (a.kind === "audio") return `<div class="att-file"><span>🎵 ${esc(a.name)}</span><audio controls preload="none" src="/api/uploads/${a.id}"></audio>${a.transcript ? `<details><summary>Transcrição</summary><div class="att-transcript">${esc(a.transcript)}</div></details>` : ""}</div>`;
    if (a.kind === "video") return `<div class="att-file"><span>🎬 ${esc(a.name)} <small>(${Math.round(a.duration)}s)</small></span><div class="frames">${(a.frames || []).map(f => `<img src="/api/uploads/${f.id}" title="${Math.round(f.t)}s" data-zoom>`).join("")}</div>${a.transcript ? `<details><summary>Transcrição do áudio</summary><div class="att-transcript">${esc(a.transcript)}</div></details>` : ""}</div>`;
    return `<div class="att-file"><span>📄 ${esc(a.name)} <small>${t("{n} caracteres", { n: fmtNum((a.text || "").length) })}</small></span></div>`;
  }).join("") + `</div>`;
}

// ------------------------------------------------------------------ mensagens
function statsHTML(s) {
  if (!s) return "";
  return `<span class="stats" title="${s.prompt !== undefined ? t("Entrada: {a} tokens ({c} reaproveitados do cache)\nSaída: {b} tokens", { a: s.prompt + (s.cached || 0), c: s.cached || 0, b: s.tokens }) : ""}">${t("{tps} tok/s · {n} tokens gerados", { tps: s.tps.toFixed(1), n: fmtNum(s.tokens) })}${s.prompt !== undefined ? t(" · {n} de entrada", { n: fmtNum(s.prompt + (s.cached || 0)) }) : ""}</span>`;
}

function msgHTML(msg, idx, isLast) {
  const streaming = isLast && S.generating && msg.role === "assistant";
  if (msg.role === "user") {
    return `<div class="msg user ${isLast ? "last" : ""}" data-i="${idx}"><div class="role">Você</div>
      ${attachmentsHTML(msg.attachments)}${msg.content ? `<div class="bubble">${esc(msg.content)}</div>` : ""}
      <div class="actions"><button data-act="copy">Copiar</button><button data-act="edit">Editar</button><button data-act="del">Excluir</button></div></div>`;
  }
  if (msg.mode === "image") return imageMsgHTML(msg, idx, isLast, streaming);
  if (msg.mode === "codex") return codexMsgHTML(msg, idx, isLast, streaming);
  if (msg.mode === "group") return groupMsgHTML(msg, idx, isLast, streaming);
  const { content, reasoning, open } = splitThink(msg);
  const thinking = streaming && (open || (reasoning && !content));
  let live = "";
  if (streaming) {
    if (msg.loadingModel) live = t("⏳ carregando {model}...", { model: esc(msg.loadingModel) });
    else if (msg.web && msg.web.stage !== "done" && msg.web.stage !== "error") live = "";
    else if (msg.stats?.tokens) live = `⚡ ${msg.stats.tps.toFixed(1)} tok/s · ${fmtNum(msg.stats.tokens)} tokens`;
    else live = "processando o prompt...";
  }
  const who = msg.agent ? `<span class="ag-dot" style="--c:${esc(msg.agent.color)}">${esc(msg.agent.icon)}</span> ${esc(msg.agent.name)} <small class="muted">· ${esc(msg.model || "")}</small>` : esc(msg.model || "Assistente");
  let html = `<div class="msg assistant ${isLast ? "last" : ""}" data-i="${idx}"><div class="role">${who}${live ? `<span class="live">${live}</span>` : ""}</div>`;
  if (msg.kb) html += kbBoxHTML(msg.kb, streaming);
  if (msg.web) html += webBoxHTML(msg.web, streaming);
  if (reasoning) html += `<details class="think" ${thinking ? "open" : ""}><summary>${thinking ? "Pensando..." : "Raciocínio"}</summary><div class="think-body">${esc(thinking && reasoning.length > 6000 ? "…" + reasoning.slice(-6000) : reasoning)}</div></details>`;
  html += `<div class="content ${streaming ? "cursor" : ""}">${linkDocCitations(linkCitations(md(content), msg.web?.sources), msg.kb?.sources)}</div>`;
  if (msg.error) html += `<div class="err">${esc(msg.error)}</div>`;
  if (!streaming) html += `<div class="actions"><button data-act="copy">Copiar</button><button data-act="speak" title="Ler em voz alta">🔊</button>${isLast ? '<button data-act="regen">Regenerar</button><button data-act="continue">Continuar</button>' : ""}<button data-act="del">Excluir</button>${statsHTML(msg.stats)}</div>`;
  return html + "</div>";
}

// ---- Codex
const TOOL_LABEL = {
  list_files: a => ["📂", `Listou <code>${esc(a.path || ".")}</code>`],
  read_file: a => ["📄", `Leu <code>${esc(a.path)}</code>${a.start_line ? ` <small>${t("(linhas {a}–{b})", { a: a.start_line, b: a.end_line || t("fim") })}</small>` : ""}`],
  write_file: a => ["✏️", `Escreveu <code>${esc(a.path)}</code> <small>${t("({n} linhas)", { n: (a.content || "").replace(/\n$/, "").split("\n").length })}</small>`],
  edit_file: a => ["🔧", `Editou <code>${esc(a.path)}</code>`],
  search_files: a => ["🔎", `Buscou <code>${esc(a.pattern)}</code>${a.glob ? ` em <code>${esc(a.glob)}</code>` : ""}`],
  delete_path: a => ["🗑️", `Apagar <code>${esc(a.path)}</code>`],
  run_command: a => ["▶️", `<code>${esc(a.command)}</code>`],
  generate_image: a => ["🎨", `Gerar imagem <code>${esc(a.path)}</code>`],
  search_knowledge: a => ["📚", `${t("Buscou na base:")} <code>${esc(a.query || "")}</code>`],
};
function toolBody(step) {
  const a = step.args || {}; let b = "";
  if (mcpToolLabel(step.name)) b += mcpArgsHTML(a);
  if (step.name === "write_file") b += codeBlock(extLang(a.path), a.content || "");
  if (step.name === "edit_file") b += `<div class="diff"><pre class="del">${esc(a.old_text || "")}</pre><pre class="add">${esc(a.new_text || "")}</pre></div>`;
  if (step.name === "generate_image") b += `<div class="tool-prompt">${esc(a.prompt || "")}</div>`;
  if (step.result && (!["write_file", "edit_file"].includes(step.name) || !step.ok)) b += `<pre class="tool-out ${step.ok === false ? "bad" : ""}">${esc(step.result)}</pre>`;
  if (step.image) b += `<img class="tool-img" src="/api/uploads/${step.image}" data-zoom>`;
  return b || '<span class="muted">…</span>';
}
function stepHTML(step, si) {
  if (step.type === "text") return step.text.trim() ? `<div class="content">${md(step.text)}</div>` : "";
  if (step.type === "reasoning") return `<details class="think" data-si="${si}" ${step._open ? "open" : ""}><summary>Raciocínio</summary><div class="think-body">${esc(step.text)}</div></details>`;
  if (step.type === "notice") return `<div class="notice ${step.level === "error" ? "bad" : ""}">${esc(trText(step.text))}</div>`;
  const ml = mcpToolLabel(step.name);
  const [icon, label] = ml ? ["🔌", esc(ml)] : (TOOL_LABEL[step.name] || (() => ["🔧", esc(step.name)]))(step.args || {});
  const mark = { running: '<span class="spin"></span>', approval: "⏸", ok: "✓", error: "✗" }[step.status] || "";
  const open = step.status === "approval" || step._open;
  let h = `<details class="tool ${step.status}" data-si="${si}" ${open ? "open" : ""}><summary><span class="ti">${icon}</span><span class="tl">${label}</span><span class="ts">${mark}</span></summary><div class="tool-body">${toolBody(step)}</div></details>`;
  if (step.status === "approval") {
    const why = ml ? t("A IA quer usar esta ferramenta de {name}.", { name: ml.split(" · ")[0] }) : step.name === "run_command" ? "O Codex quer rodar este comando." : step.name === "delete_path" ? "O Codex quer apagar este item." : "O Codex quer alterar este arquivo.";
    h += `<div class="approval" data-call="${esc(step.id)}"><span>${why}</span><button class="btn small primary" data-approve="once">Permitir</button><button class="btn small" data-approve="always">Sempre nesta conversa</button><button class="btn small danger" data-approve="deny">Negar</button></div>`;
  }
  return h;
}
function codexMsgHTML(msg, idx, isLast, streaming) {
  const live = streaming ? (msg.stats?.tokens ? `⚡ ${msg.stats.tps.toFixed(1)} tok/s · ${fmtNum(msg.stats.tokens)} tokens` : "pensando...") : "";
  let h = `<div class="msg assistant codex ${isLast ? "last" : ""}" data-i="${idx}"><div class="role">🛠️ Codex · ${esc(msg.model || "")} ${msg.workspace === "__mcp" ? '<span class="ws-tag">🔌 MCP</span>' : `<span class="ws-tag" title="${esc(msg.workspace)}">📁 ${esc(baseName(msg.workspace))}</span>`}${live ? `<span class="live">${live}</span>` : ""}</div>`;
  h += `<div class="steps">${(msg.steps || []).map(stepHTML).join("")}${streaming ? '<div class="cursor"></div>' : ""}</div>`;
  if (msg.error) h += `<div class="err">${esc(msg.error)}</div>`;
  if (!streaming) h += checkpointHTML(msg);
  const ck = msg.checkpoint?.changes?.length ? `<button data-act="ck-diff">🔍 Ver alterações</button>${msg.checkpoint.undone ? "" : '<button data-act="ck-undo">↩ Desfazer alterações</button>'}` : "";
  if (!streaming) h += `<div class="actions"><button data-act="copy">Copiar</button>${ck}${msg.workspace === "__mcp" ? "" : '<button data-act="open-ws">Abrir pasta</button>'}${isLast ? '<button data-act="regen">Refazer</button>' : ""}<button data-act="del">Excluir</button>${statsHTML(msg.stats)}</div>`;
  return h + "</div>";
}

// ---- Imagem
function imageMsgHTML(msg, idx, isLast, streaming) {
  const im = msg.image || {};
  let h = `<div class="msg assistant ${isLast ? "last" : ""}" data-i="${idx}"><div class="role">🎨 ${esc(im.presetName || "Imagem")}</div>`;
  if (im.id) {
    h += `<div class="gen-img"><img src="/api/uploads/${im.id}" data-zoom alt="${esc(im.prompt)}"></div>
      <details class="gen-meta"><summary>Seed ${im.seed} · ${im.seconds}s</summary><div><b>Pedido:</b> ${esc(im.prompt)}</div>${im.final_prompt && im.final_prompt !== im.prompt ? `<div><b>Prompt usado:</b> ${esc(im.final_prompt)}</div>` : ""}</details>`;
  } else if (streaming) {
    const label = { enhance: "Melhorando a descrição com o modelo de texto...", unload: "Liberando a GPU...", loading: "Carregando o modelo de imagem...",
                    progress: t("Gerando: passo {a}/{b}", { a: im.step, b: im.total }) + (im.speed ? ` · ${im.speed}` : "") }[im.stage] || t("Preparando...");
    const pct = im.stage === "progress" && im.total ? im.step / im.total * 100 : 0;
    h += `<div class="gen-progress"><div class="row"><span class="spin"></span><span>${label}</span></div><div class="bar"><div style="width:${pct}%"></div></div>
      ${im.prompt && im.prompt !== msg.request ? `<small class="muted">${esc(im.prompt)}</small>` : ""}</div>`;
  }
  if (msg.error) h += `<div class="err">${esc(msg.error)}</div>`;
  if (!streaming) h += `<div class="actions">${isLast && !im.id ? '<button data-act="regen">Tentar de novo</button>' : ""}${im.id ? `<button data-act="img-again">Gerar outra</button><button data-act="img-show">Mostrar na pasta</button><button data-act="img-save">Salvar como...</button><button data-act="img-prompt">Copiar prompt</button>` : ""}<button data-act="del">Excluir</button></div>`;
  return h + "</div>";
}

function renderMessages() {
  const box = $("#messages");
  if (!S.chat || !S.chat.messages.length) {
    const st = S.status;
    const noEngine = st && !Object.keys(st.backends).length; const noModel = st && !st.models.length;
    box.innerHTML = `<div class="empty"><h2>LLM Local</h2><div>Seus modelos, sua máquina. Sem conta, sem limites, sem nada saindo do seu PC.</div>
      ${noEngine || noModel ? `<ol class="steps">
        <li>${noEngine ? "" : "✅ "}Instale o motor em <b>Modelos → Motor</b></li>
        <li>${noModel ? "" : "✅ "}Baixe um modelo em <b>Modelos → Baixar modelos</b></li>
        <li>Selecione o modelo no topo e clique em <b>Carregar</b></li></ol>` : `<div class="mode-cards">
        <div><b>💬 Chat</b><span>Converse, anexe arquivos 📎, imagens, áudios e vídeos.</span></div>
        <div><b>🛠️ Codex</b><span>Crie e edite projetos de software numa pasta que você liberar.</span></div>
        <div><b>🎨 Imagem</b><span>Gere imagens a partir de uma descrição.</span></div></div>`}</div>`;
    return;
  }
  const n = S.chat.messages.length;
  const sum = S.chat.summary;
  box.innerHTML = S.chat.messages.map((m, i) => (sum && i === sum.upto ? summaryDividerHTML(sum) : "") + msgHTML(m, i, i === n - 1)).join("");
  box.scrollTop = box.scrollHeight;
  renderStatsBar();
}

// mantém aberto/fechado o que o usuário expandiu enquanto a resposta é redesenhada
$("#messages").addEventListener("toggle", e => {
  const d = e.target; if (d.dataset?.si === undefined) return;
  const i = +d.closest(".msg")?.dataset.i; const steps = S.chat?.messages[i]?.steps;
  const [a, b] = String(d.dataset.si).split("-"); // "3" (Codex) ou "etapa-parte" (agente com ferramentas)
  const step = b === undefined ? steps?.[+a] : steps?.find(s => s.index === +a && s.parts)?.parts?.[+b];
  if (step) step._open = d.open;
}, true);

// ------------------------------------------------------------------ contador de tokens
function chatTotals(chat) {
  let input = 0, output = 0, ctxUsed = 0;
  for (const m of chat?.messages || []) {
    if (m.role !== "assistant" || !m.stats) continue;
    const inp = (m.stats.prompt || 0) + (m.stats.cached || 0);
    input += inp; output += m.stats.tokens || 0;
    if (m.stats.prompt !== undefined) ctxUsed = inp + (m.stats.lastOut ?? m.stats.tokens ?? 0);
  }
  return { input, output, ctxUsed };
}

function renderStatsBar() {
  const st = S.status; const bar = $("#statsBar"); if (!st) return;
  if (st.engine.state !== "ready" && !S.chat?.messages.length) { bar.innerHTML = ""; return; }
  const tot = chatTotals(S.chat); const g = st.stats || {};
  const nctx = st.engine.n_ctx || st.settings.ctx_size;
  const pct = nctx ? Math.min(100, tot.ctxUsed / nctx * 100) : 0;
  const parts = [];
  if (st.engine.state === "ready")
    parts.push(`<span class="ctx-meter ${pct > 85 ? "high" : pct > 60 ? "mid" : ""}" title="Quanto da memória de contexto do modelo esta conversa já ocupa. Ao chegar em 100%, comece uma nova conversa ou aumente o contexto nas Configurações.">Contexto <span class="track"><div style="width:${pct}%"></div></span><b>${fmtNum(tot.ctxUsed)} / ${fmtNum(nctx)}</b></span>`);
  if (S.chat?.messages.length)
    parts.push(`<span title="Tokens desta conversa: entrada (o que o modelo leu, somando todas as mensagens) e saída (o que ele escreveu)">Conversa: <b>${fmtNum(tot.input + tot.output)}</b> tokens (↑${fmtNum(tot.input)} ↓${fmtNum(tot.output)})</span>`);
  const gTotal = (g.prompt_tokens || 0) + (g.cached_tokens || 0) + (g.completion_tokens || 0);
  parts.push(`<span title="${t("Desde {date}: {a} gerados, {b} de entrada, {c} respostas, {d} pesquisas na web", { date: g.since ? new Date(g.since * 1000).toLocaleDateString(LANG) : t("o início"), a: fmtNum(g.completion_tokens || 0), b: fmtNum((g.prompt_tokens || 0) + (g.cached_tokens || 0)), c: g.requests || 0, d: g.searches || 0 })}">Total geral: <b>${fmtNum(gTotal)}</b> tokens</span>`);
  const html = parts.join("");
  if (bar.dataset.sig !== html) { bar.innerHTML = html; bar.dataset.sig = html; }
}

// redesenho adaptativo: respostas longas custam mais para redesenhar, então o intervalo cresce junto
// (sem isso a janela pode passar 100% do tempo redesenhando e parar de responder)
let rafPending = false, renderCost = 0, lastRender = 0;
function renderLastMessage() {
  if (rafPending) return; rafPending = true;
  const wait = Math.max(0, Math.min(1500, renderCost * 4) - (performance.now() - lastRender));
  setTimeout(() => requestAnimationFrame(() => {
    rafPending = false;
    const t0 = performance.now();
    try { drawLastMessage(); } finally { lastRender = performance.now(); renderCost = lastRender - t0; }
  }), wait);
}
function drawLastMessage() {
  {
    const box = $("#messages"); const n = S.chat.messages.length;
    const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    const el = box.querySelector(`.msg[data-i="${n - 1}"]`);
    const think = el?.querySelector(":scope > details.think");
    const keepOpen = think ? think.open : null;
    const tmp = document.createElement("div"); tmp.innerHTML = msgHTML(S.chat.messages[n - 1], n - 1, true);
    const fresh = tmp.firstElementChild;
    const newThink = fresh.querySelector(":scope > details.think");
    if (newThink && keepOpen !== null && S.generating) newThink.open = keepOpen;
    if (el) el.replaceWith(fresh); else box.appendChild(fresh);
    if (stick) box.scrollTop = box.scrollHeight;
    renderStatsBar();
  }
}

// ---- ações das mensagens
$("#messages").addEventListener("click", async ev => {
  const cb = ev.target.closest(".copy-code");
  if (cb) {
    await navigator.clipboard.writeText(cb.closest(".code").querySelector("code").textContent);
    cb.textContent = "Copiado!"; setTimeout(() => cb.textContent = "Copiar", 1200); return;
  }
  const zoom = ev.target.closest("[data-zoom]");
  if (zoom) return openLightbox(zoom.src);
  const ap = ev.target.closest("[data-approve]");
  if (ap) {
    const id = ap.closest(".approval").dataset.call; const v = ap.dataset.approve;
    const msg = S.chat.messages.at(-1); const step = msg.steps?.find(s => s.id === id) || msg.steps?.flatMap(s => s.parts || []).find(s => s.id === id);
    if (step?.status === "approval") { step.status = v === "deny" ? "error" : "running"; renderLastMessage(); }
    await post("/api/agent/approve", { id, ok: v !== "deny", always: v === "always" });
    return;
  }
  const b = ev.target.closest("[data-act]"); if (!b || S.generating) return;
  const i = +b.closest(".msg").dataset.i; const msg = S.chat.messages[i];
  switch (b.dataset.act) {
    case "copy": await navigator.clipboard.writeText(msg.mode === "codex" ? msg.content : splitThink(msg).content || msg.content); toast("Copiado"); break;
    case "del": S.chat.messages.splice(i, 1); renderMessages(); saveChat(); break;
    case "regen": S.chat.messages.pop(); renderMessages(); dispatch(msg.mode || "chat", { workspace: msg.workspace, prompt: msg.request, group: msg.group?.id, agent: msg.agent?.id }); break;
    case "continue": generate(true, msg.agent ? agentById(msg.agent.id) : null); break;
    case "open-ws": desktop.openPath(msg.workspace); break;
    case "ck-diff": showCodexDiff(msg); break;
    case "ck-undo": undoCodex(msg); break;
    case "speak": speakText(msg.mode === "group" ? msg.content : splitThink(msg).content || msg.content); break;
    case "img-again": genImage(msg.request, { preset: msg.image.preset }); break;
    case "img-show": desktop.showItem(msg.image.path); break;
    case "img-save": { const a = document.createElement("a"); a.href = "/api/uploads/" + msg.image.id; a.download = `imagem-${msg.image.seed}.png`; a.click(); break; }
    case "img-prompt": await navigator.clipboard.writeText(msg.image.final_prompt || msg.image.prompt); toast("Prompt copiado"); break;
    case "edit": {
      const el = b.closest(".msg");
      const bubble = el.querySelector(".bubble");
      const ta = `<textarea class="input edit-area">${esc(msg.content)}</textarea>`;
      if (bubble) bubble.outerHTML = ta; else el.querySelector(".actions").insertAdjacentHTML("beforebegin", ta);
      el.querySelector(".actions").innerHTML = '<button data-act="save-edit">Salvar e reenviar</button><button data-act="cancel-edit">Cancelar</button>';
      el.querySelector("textarea").focus(); break;
    }
    case "cancel-edit": renderMessages(); break;
    case "save-edit": {
      const txt = b.closest(".msg").querySelector("textarea").value.trim(); if (!txt && !msg.attachments?.length) return;
      const next = S.chat.messages[i + 1];
      S.chat.messages.splice(i); S.chat.messages.push({ role: "user", content: txt, attachments: msg.attachments });
      renderMessages(); dispatch(next?.mode || "chat", { workspace: next?.workspace, prompt: txt }); break;
    }
  }
});

function openLightbox(src) {
  const lb = document.createElement("div"); lb.className = "lightbox";
  lb.innerHTML = `<img src="${esc(src)}">`; lb.onclick = () => lb.remove(); document.body.appendChild(lb);
}

// ------------------------------------------------------------------ envio
function buildMessages() {
  const out = []; const sp = S.status.settings.system_prompt; const sum = S.chat.summary;
  const sys = [sp && sp.trim(), sum && "Resumo da parte anterior desta conversa (as mensagens antigas foram resumidas para caber no contexto):\n" + sum.text].filter(Boolean).join("\n\n");
  if (sys) out.push({ role: "system", content: sys });
  for (const m of S.chat.messages.slice(sum ? sum.upto : 0)) {
    if (m.role === "user") out.push({ role: "user", content: m.content, attachments: m.attachments });
    else if (m.mode === "codex") out.push({ role: "assistant", content: m.content, trace: m.trace });
    else if (m.mode === "image") { if (m.image?.id) out.push({ role: "assistant", image: { prompt: m.image.final_prompt || m.image.prompt } }); }
    else { const content = splitThink(m).content; if (content) out.push({ role: "assistant", content }); }
  }
  return out;
}

function sampling() {
  const st = S.status.settings;
  return { temperature: +st.temperature, top_p: +st.top_p, top_k: +st.top_k, min_p: +st.min_p,
           repeat_penalty: +st.repeat_penalty, max_tokens: +st.max_tokens };
}

async function send() {
  const inp = $("#input"); const text = inp.value.trim();
  if (S.generating) return;
  if (S.attachments.some(a => a.status === "processing")) return toast("Aguarde os anexos terminarem de processar.");
  const atts = S.attachments.filter(a => a.status === "ready").flatMap(a => a.atts);
  if (!text && !atts.length) return;
  const mode = S.mode;
  if (mode !== "image" && S.status?.engine.state !== "ready")
    return toast(S.status?.engine.state === "loading" ? "Aguarde o modelo terminar de carregar." : "Carregue um modelo primeiro (botão Carregar no topo).");
  if (mode === "codex" && !S.workspace) return addWorkspace();
  if (mode === "agents" && !currentAgentSel().group && !currentAgentSel().agent) { openModal("agentsModal"); return toast("Crie ou escolha um agente ou grupo."); }
  if (mode === "image") {
    const im = S.media?.image;
    if (!im?.installed || !im.presets[S.status.settings.image_preset]?.installed) { openModal("modelsModal"); switchTab("tabMedia"); return toast("Instale o motor e um modelo de imagem primeiro."); }
  }
  if (!S.chat) S.chat = { id: uid(), title: (mode === "image" ? "🎨 " : mode === "codex" ? "🛠️ " : mode === "agents" ? "👥 " : "") + (text || atts[0]?.name || "Anexo").slice(0, 60).replace(/\s+/g, " "), created: Date.now() / 1000, messages: [] };
  S.chat.messages.push({ role: "user", content: text, ...(atts.length ? { attachments: atts } : {}) });
  inp.value = ""; autoGrow(); S.attachments = []; renderAttachTray();
  renderMessages();
  if (mode !== "image") await maybeSummarize();
  await dispatch(mode, { prompt: text });
}

function dispatch(mode, opts = {}) {
  if (mode === "codex") return runAgent(opts.workspace || S.workspace);
  if (mode === "group") return runGroup(groupById(opts.group) || soloGroup(agentById(String(opts.group || "").replace(/^agent:/, ""))));
  if (mode === "agents") { const s = currentAgentSel(); return s.group ? runGroup(s.group) : s.agent?.mcp?.length ? runGroup(soloGroup(s.agent)) : generate(false, s.agent); }
  if (opts.agent) return generate(false, agentById(opts.agent));
  if (mode === "image") return genImage(opts.prompt ?? S.chat.messages.at(-1)?.content ?? "", opts);
  return generate();
}

function startGenerating() { S.generating = true; S.abort = new AbortController(); setComposerState(); renderMessages(); }
async function finishGenerating() {
  S.generating = false; S.abort = null; setComposerState();
  renderMessages();
  await saveChat().catch(() => {});
  refreshStatus();
}

// ---- Chat
async function generate(isContinue = false, agent = null) {
  let msg;
  if (isContinue) {
    msg = S.chat.messages[S.chat.messages.length - 1];
    delete msg.error; msg._base = msg.stats ? { tokens: msg.stats.tokens } : null;
  } else {
    msg = { role: "assistant", content: "", reasoning: "", model: modelName() };
    if (agent) msg.agent = { id: agent.id, name: agent.name, icon: agent.icon, color: agent.color };
    if (S.web || agent?.web) msg.web = { stage: "query" };
  }
  const messages = buildMessages();
  if (!isContinue) S.chat.messages.push(msg);
  startGenerating();
  const t0 = performance.now(); let tokens = 0;
  try {
    if (S.kb && !isContinue && !agent?.kb) msg.kb = { stage: "searching", name: (KB.list.find(k => k.id === S.kb) || {}).name };
    await streamChat({ messages, web: S.web && !isContinue && !agent, kb: isContinue ? "" : S.kb, ...sampling(), ...(agent ? { agent_id: agent.id } : {}) }, S.abort.signal, j => {
      if (j.kb) { msg.kb = { ...msg.kb, ...j.kb }; renderLastMessage(); return; }
      if (j.engine) { msg.loadingModel = j.engine.stage === "loading" ? j.engine.model : null; if (j.engine.stage === "ready" && j.engine.model) msg.model = j.engine.model + (j.engine.device ? ` · ${j.engine.device.toUpperCase()}` : ""); renderLastMessage(); return; }
      if (j.llmlocal) { msg.web = { ...msg.web, ...j.llmlocal }; renderLastMessage(); return; }
      const d = j.choices?.[0]?.delta || {};
      if (d.content) { msg.content += d.content; tokens++; }
      if (d.reasoning_content) { msg.reasoning = (msg.reasoning || "") + d.reasoning_content; tokens++; }
      if (j.timings) {
        const t = j.timings; const prev = isContinue && msg._base ? msg._base : null;
        msg.stats = { tps: t.predicted_per_second || 0, tokens: (t.predicted_n || tokens) + (prev?.tokens || 0),
                      prompt: t.prompt_n || 0, cached: t.cache_n || 0 };
      }
      renderLastMessage();
    });
  } catch (e) {
    if (e.name !== "AbortError") msg.error = e.message;
  } finally {
    if (!msg.stats && tokens) msg.stats = { tps: tokens / ((performance.now() - t0) / 1000), tokens };
    delete msg._base; delete msg.loadingModel;
    if (msg.web && msg.web.stage !== "done" && msg.web.stage !== "error") delete msg.web;
    await finishGenerating();
  }
}

// ---- Codex
async function runAgent(workspace) {
  const msg = { role: "assistant", mode: "codex", workspace, model: modelName(), content: "", steps: [] };
  const messages = buildMessages();
  S.chat.messages.push(msg);
  startGenerating();
  let base = 0, lastPred = 0;
  const lastStep = type => { let s = msg.steps.at(-1); if (!s || s.type !== type) { s = { type, text: "" }; msg.steps.push(s); } return s; };
  try {
    const where = { ...(workspace === "__mcp" ? { mcp_only: true } : { workspace }), kb: S.kb || "" };
    await streamChat({ chat_id: S.chat.id, ...where, messages, ...sampling() }, S.abort.signal, j => {
      if (j.timings) {
        const t = j.timings;
        if ((t.predicted_n || 0) < lastPred) base += lastPred;
        lastPred = t.predicted_n || 0;
        msg.stats = { tps: t.predicted_per_second || 0, tokens: base + lastPred, lastOut: lastPred, prompt: t.prompt_n || 0, cached: t.cache_n || 0 };
      }
      const a = j.agent; if (!a) { if (j.timings) renderLastMessage(); return; }
      if (a.type === "text") { lastStep("text").text += a.delta; msg.content += a.delta; }
      else if (a.type === "reasoning") lastStep("reasoning").text += a.delta;
      else if (a.type === "notice") msg.steps.push({ type: "notice", text: a.text, level: a.level });
      else if (a.type === "tool_start") { msg.steps.push({ type: "tool", id: a.id, name: a.name, args: a.args, status: "running" }); msg.content += msg.content && !msg.content.endsWith("\n") ? "\n" : ""; }
      else if (a.type === "approval") { const s = msg.steps.find(x => x.id === a.id); if (s) s.status = "approval"; }
      else if (a.type === "tool_end") { const s = msg.steps.find(x => x.id === a.id); if (s) Object.assign(s, { status: a.ok ? "ok" : "error", ok: a.ok, result: a.result, image: a.image }); }
      else if (a.type === "step_end") { base += lastPred; lastPred = 0; }
      else if (a.type === "trace") msg.trace = a.trace;
      else if (a.type === "checkpoint") msg.checkpoint = { id: a.id, changes: a.changes };
      renderLastMessage();
    }, "/api/agent");
  } catch (e) {
    if (e.name !== "AbortError") msg.error = e.message;
  } finally {
    msg.steps.forEach(s => { if (s.status === "running" || s.status === "approval") s.status = "error"; delete s._open; });
    await finishGenerating();
  }
}

// ---- Imagem
async function genImage(prompt, opts = {}) {
  if (!prompt) return toast("Descreva a imagem.");
  const preset = opts.preset || S.status.settings.image_preset;
  const presetInfo = S.media?.image?.presets?.[preset] || {};
  const size = $("#imageSizeSelect").value.split("x").map(Number);
  const msg = { role: "assistant", mode: "image", request: prompt, image: { stage: "start", preset, presetName: presetInfo.name } };
  S.chat.messages.push(msg);
  startGenerating();
  try {
    await streamChat({ prompt, preset, width: size[0] || 0, height: size[1] || 0 }, S.abort.signal, j => {
      if (j.image) { Object.assign(msg.image, j.image); renderLastMessage(); }
    }, "/api/image/generate");
    if (!msg.image.id && !msg.error) msg.error = "A geração terminou sem imagem.";
  } catch (e) {
    msg.error = e.name === "AbortError" ? "Geração cancelada." : e.message;
  } finally {
    await finishGenerating();
  }
}

function setComposerState() {
  const b = $("#sendBtn");
  b.textContent = S.generating ? "Parar" : "Enviar";
  b.classList.toggle("stop", S.generating);
}
$("#sendBtn").onclick = () => S.generating ? S.abort?.abort() : send();
function setWeb(on) {
  S.web = on; $("#webBtn").classList.toggle("on", on);
  lsSet("web", on ? "1" : "0");
  updateHint();
}
$("#webBtn").onclick = () => { setWeb(!S.web); toast(S.web ? "Pesquisa na web ligada" : "Pesquisa na web desligada"); };
function autoGrow() { const t = $("#input"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 260) + "px"; }
$("#input").addEventListener("input", autoGrow);
$("#input").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    stopSpeaking();
    const lb = $(".lightbox"); if (lb) return lb.remove();
    if (S.generating) S.abort?.abort();
    $$(".modal.open").forEach(m => m.classList.remove("open"));
  }
});

$("#exportBtn").onclick = () => {
  if (!S.chat?.messages.length) return toast("Nada para exportar.");
  const txt = `# ${S.chat.title}\n\n` + S.chat.messages.map(m => {
    const who = m.role === "user" ? "Você" : m.mode === "codex" ? "Codex" : (m.model || "Assistente");
    const body = m.role === "assistant" ? (m.mode === "image" ? `![imagem](${m.image?.path || ""})\n\n${m.image?.prompt || ""}` : m.mode === "codex" ? m.content : splitThink(m).content) : m.content;
    const atts = (m.attachments || []).map(a => `> 📎 ${a.name}`).join("\n");
    return `**${who}:**\n\n${atts ? atts + "\n\n" : ""}${body}`;
  }).join("\n\n---\n\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([txt], { type: "text/markdown" }));
  a.download = (S.chat.title || "conversa").replace(/[\\/:*?"<>|]/g, "_").slice(0, 60) + ".md"; a.click();
  URL.revokeObjectURL(a.href);
};
$("#toggleSide").onclick = () => $("#app").classList.toggle("side-hidden");

// ------------------------------------------------------------------ modais
function openModal(id) {
  $("#" + id).classList.add("open");
  if (id === "settingsModal") fillSettings();
  if (id === "backupModal") { loadBackupInfo(); $("#restoreResult").textContent = ""; }
  if (id === "agentsModal") { renderAgentsModal(); loadAgents(); }
  if (id === "kbModal") { renderKb(); loadKbs(); }
  if (id === "modelsModal") { renderLocalModels(); renderEngine(); loadLog(); loadMedia(); }
}
$$("[data-open]").forEach(b => b.onclick = () => openModal(b.dataset.open));
$$(".modal").forEach(m => m.addEventListener("mousedown", e => { if (e.target === m || e.target.closest("[data-close]")) m.classList.remove("open"); }));
function switchTab(id) {
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === id));
  $$(".tab-pane").forEach(p => p.classList.toggle("active", p.id === id));
  if (id === "tabEngine") loadLog();
  if (id === "tabMedia") { renderMedia(); loadMedia(); }
  if (id === "tabHF" && !$("#hfResults").innerHTML) hfSearch("GGUF");
}
$$(".tab").forEach(t => t.onclick = () => switchTab(t.dataset.tab));
$$("[data-folder]").forEach(b => b.onclick = () => post("/api/open-folder", { which: b.dataset.folder }));

// ------------------------------------------------------------------ modelos locais
function renderMemBar() {
  const m = S.status.memory; if (!m) return;
  const gb = mb => (mb / 1024).toFixed(1);
  const bar = (used, total) => `<span class="track"><div style="width:${total ? Math.min(100, used / total * 100) : 0}%"></div></span>`;
  const html = (m.vram_total ? `<span title="VRAM ocupada pelos modelos carregados (estimativa)">🎮 GPU ${bar(m.vram_used, m.vram_total)} <b>${gb(m.vram_used)} / ${gb(m.vram_total)} GB</b></span>` : "") +
    `<span title="${t("RAM ocupada pelos modelos que rodam na CPU (estimativa). Disponível no PC agora: {gb} GB", { gb: gb(m.ram_avail) })}">🧠 RAM (modelos na CPU) ${bar(m.ram_used, m.ram_total)} <b>${gb(m.ram_used)} / ${gb(m.ram_total)} GB</b></span>`;
  if ($("#memBar").dataset.sig !== html) { $("#memBar").innerHTML = html; $("#memBar").dataset.sig = html; }
}
// cartão da pergunta rápida (Ctrl+Shift+Space): modelo, GPU/CPU e carregar agora
function renderQuickCard() {
  const st = S.status, q = st.quick || {}, box = $("#quickCard");
  const hk = esc(S.desktopCfg?.hotkeyLabel || "Ctrl+Shift+Space");
  const opts = `<option value="">${esc(t("O mesmo modelo principal do app"))}</option>` + st.models.map(m =>
    `<option value="${esc(m.path)}" ${m.path === q.model ? "selected" : ""}>${esc(m.name)} (${fmtSize(m.size)})</option>`).join("");
  const state = !q.model ? `<span class="muted">${esc(t("usa o modelo principal"))}</span>`
    : q.state === "ready" ? `<span class="tag fit">● ${esc(t("carregado"))} · ${esc((q.on || "gpu").toUpperCase())}</span>`
    : q.state === "loading" ? `<span class="tag on"><span class="spin"></span> ${esc(t("carregando..."))}</span>`
    : `<span class="tag">${esc(t("descarregado"))}</span>`;
  const html = `<div class="qc-head"><b>⚡ ${esc(t("Pergunta rápida"))}</b> <kbd>${hk}</kbd><span class="spacer"></span>${state}</div>
    <div class="qc-row"><select class="input small-input qc-model" id="qcModel">${opts}</select>
      <select class="input small-input" id="qcDevice" ${q.model ? "" : "disabled"}><option value="gpu" ${q.device !== "cpu" ? "selected" : ""}>🎮 GPU (${esc(t("rápido"))})</option><option value="cpu" ${q.device === "cpu" ? "selected" : ""}>🧠 CPU (RAM)</option></select>
      <label class="check"><input type="checkbox" id="qcKeep" ${q.keep ? "checked" : ""} ${q.model ? "" : "disabled"}> ${esc(t("Manter carregado"))}</label>
      <span class="spacer"></span>
      ${q.model && q.state === "ready" ? `<button class="btn small" id="qcUnload">${esc(t("Descarregar"))}</button>` : ""}
      ${q.model ? `<button class="btn small primary" id="qcLoad" ${q.state === "loading" ? "disabled" : ""}>${q.state === "ready" ? esc(t("Recarregar")) : esc(t("Carregar agora"))}</button>` : ""}</div>
    ${q.error ? `<div class="warn-box">${esc(trText(q.error))}</div>` : ""}`;
  if (box.dataset.sig !== html) { box.innerHTML = html; box.dataset.sig = html; }
}
$("#quickCard").addEventListener("change", async e => {
  const body = e.target.id === "qcModel" ? { quick_model: e.target.value } : e.target.id === "qcDevice" ? { quick_device: e.target.value }
    : e.target.id === "qcKeep" ? { quick_keep_loaded: e.target.checked } : null;
  if (!body) return;
  if (body.quick_model === "") { await api("/api/settings", { method: "PUT", body }); return refreshStatus(); }
  try { await post("/api/quick/load", body); } catch (err) { toast(err.message, 5000); }
  refreshStatus();
});
$("#quickCard").addEventListener("click", async e => {
  if (e.target.id === "qcLoad") { e.target.disabled = true; await post("/api/quick/load", { quick_device: $("#qcDevice").value }).catch(err => toast(err.message, 5000)); toast(t("Carregando o modelo da pergunta rápida...")); }
  if (e.target.id === "qcUnload") { await post("/api/quick/unload"); toast(t("Modelo da pergunta rápida descarregado")); }
  refreshStatus();
});

function renderLocalModels() {
  renderMemBar(); renderQuickCard();
  const st = S.status; const mms = S.media?.mmproj || []; const mtps = S.media?.mtp || [];
  const html = st.models.length ? st.models.map(m => {
    const on = st.engine.model === m.path && st.engine.state === "ready";
    const extra = (st.extras || []).find(x => x.model === m.path && (x.state === "ready" || x.state === "loading"));
    const vis = mms.length ? `<select class="input small-input" data-mm="${esc(m.path)}" title="Arquivo de visão (mmproj): permite o modelo ver imagens">
        <option value="">Sem visão</option>${mms.map(x => `<option value="${esc(x)}" ${x === m.mmproj ? "selected" : ""}>👁 ${esc(baseName(x))}</option>`).join("")}</select>` : "";
    const acc = mtps.length ? `<select class="input small-input" data-mtp="${esc(m.path)}" title="${esc(t("Acelerador MTP: o modelo gera vários tokens de uma vez (mais rápido). Use o MTP do mesmo modelo."))}">
        <option value="">${esc(t("Sem acelerador"))}</option>${mtps.map(x => `<option value="${esc(x)}" ${x === m.mtp ? "selected" : ""}>⚡ ${esc(baseName(x))}</option>`).join("")}</select>` : "";
    const visionNoFile = (m.info?.caps || []).some(c => c.key === "vision") && !m.mmproj;
    return `<div class="model-card ${on ? "loaded" : ""}">
      <div class="mc-head"><span class="mc-name" title="${esc(m.path)}">${esc(m.name)}</span>
        <div class="mc-status">${on ? '<span class="tag on">● carregado</span>' : ""}${extra ? `<span class="tag on" title="Carregado como modelo extra (agentes/pergunta rápida)">extra · ${(extra.device || "gpu").toUpperCase()}${extra.state === "loading" ? "…" : ""}</span>` : ""}${fitTag(m.size)}<span class="meta">${fmtSize(m.size)}</span></div></div>
      <div class="mc-tags">${capsHTML(m.info, true)}${m.info?.params ? `<span class="meta-pill">🧩 ${esc(m.info.params)}</span>` : ""}${m.quant?.quant ? `<span class="meta-pill" title="${esc(m.quant.tip)}">${esc(m.quant.quant)} ${starsHTML(m.quant)}</span>` : ""}${m.mmproj ? '<span class="tag vis">👁 visão</span>' : ""}${m.mtp ? `<span class="tag neon" title="${esc(t("Acelerador MTP ativo"))}">⚡ MTP</span>` : ""}${m.custom ? '<span class="tag on" title="Este modelo tem ajustes próprios">⚙ ajustes próprios</span>' : ""}
        ${visionNoFile ? '<span class="warn-pill" title="Este modelo tem visão, mas o arquivo mmproj não foi baixado. Baixe de novo com Incluir visão ou escolha o arquivo ao lado.">👁 sem arquivo de visão</span>' : ""}</div>
      <div class="mc-actions">${vis}${acc}<span class="spacer"></span>
        ${extra ? `<button class="btn small" data-unload-extra="${esc(m.path)}">Descarregar</button>` : ""}<button class="btn small" data-msettings="${esc(m.path)}" title="Ajustes deste modelo (contexto, temperatura...)">⚙️</button>
        <button class="btn small primary" data-load="${esc(m.path)}">${on ? "Recarregar" : "Carregar"}</button>
        <button class="btn small danger" data-del="${esc(m.path)}">Excluir</button></div></div>`;
  }).join("") : '<p class="muted">Nenhum modelo ainda. Vá na aba <b>Baixar modelos</b>.</p>';
  if ($("#localModels").dataset.sig !== html) { $("#localModels").innerHTML = html; $("#localModels").dataset.sig = html; }
}
$("#localModels").addEventListener("click", async e => {
  const l = e.target.dataset.load, d = e.target.dataset.del, ux = e.target.dataset.unloadExtra, msx = e.target.dataset.msettings;
  if (msx) return openModelSettings(msx);
  if (ux) { await post("/api/unload", { extra: ux }); toast("Modelo extra descarregado"); return refreshStatus(); }
  try {
    if (l) { await post("/api/load", { model: l }); $("#modelSelect").value = l; toast("Carregando modelo..."); $("#modelsModal").classList.remove("open"); }
    if (d && confirm(t("Excluir o arquivo do modelo do disco?"))) { await post("/api/models/delete", { path: d }); toast("Modelo excluído"); }
  } catch (err) { toast(err.message, 5000); }
  refreshStatus();
});
$("#localModels").addEventListener("change", async e => {
  const mt = e.target.dataset.mtp;
  if (mt !== undefined) {
    await post("/api/models/mtp", { model: mt, mtp: e.target.value });
    toast(S.status.engine.model === mt ? "Recarregue o modelo para aplicar." : t("Acelerador configurado."));
    return refreshStatus();
  }
  const model = e.target.dataset.mm; if (model === undefined) return;
  await post("/api/models/mmproj", { model, mmproj: e.target.value });
  toast(S.status.engine.model === model ? "Recarregue o modelo para aplicar." : "Visão configurada.");
  refreshStatus();
});

function fitTag(size) {
  const vram = S.status?.gpu?.vram_mb; if (!vram) return "";
  const gb = vram / 1024; const need = size / 1073741824 + 1.2; // modelo + contexto/overhead aproximado
  if (need <= gb * 0.92) return '<span class="tag fit" title="Cabe inteiro na VRAM: rápido">cabe na GPU</span>';
  if (need <= gb * 1.25) return '<span class="tag tight" title="Pode precisar reduzir contexto ou camadas na GPU">no limite</span>';
  return '<span class="tag big" title="Vai dividir entre GPU e RAM: bem mais lento">grande demais</span>';
}

// ------------------------------------------------------------------ Hugging Face
const CHIPS = ["Qwen", "gemma", "Llama", "Mistral", "DeepSeek", "coder", "VL", "abliterated", "uncensored", "bartowski", "unsloth"];
$("#hfChips").innerHTML = CHIPS.map(c => `<span class="chip">${c}</span>`).join("");
$("#hfChips").onclick = e => { if (e.target.classList.contains("chip")) { $("#hfQuery").value = e.target.textContent; hfSearch(e.target.textContent); } };
$("#hfSearchBtn").onclick = () => hfSearch($("#hfQuery").value);
$("#hfQuery").onkeydown = e => { if (e.key === "Enter") hfSearch($("#hfQuery").value); };

const CAP_FILTERS = [["vision", "👁 Visão"], ["audio", "🎧 Áudio"], ["tools", "🛠️ Codex"], ["reasoning", "🧠 Raciocínio"],
  ["code", "💻 Programação"], ["uncensored", "🔓 Sem censura"], ["moe", "⚡ MoE rápido"], ["fits", "🖥️ Cabe na minha GPU"]];
S.capFilter = new Set(); S.hfResults = [];
$("#capFilters").innerHTML = '<span class="muted small-note">Filtrar:</span>' + CAP_FILTERS.map(([k, l]) => `<span class="chip" data-cap="${k}">${l}</span>`).join("");
$("#capFilters").onclick = e => {
  const k = e.target.dataset?.cap; if (!k) return;
  S.capFilter.has(k) ? S.capFilter.delete(k) : S.capFilter.add(k);
  e.target.classList.toggle("on", S.capFilter.has(k)); renderHfResults();
};
function fitsGpu(sizeBytes) { const vram = S.status?.gpu?.vram_mb; return vram && sizeBytes && sizeBytes / 1073741824 + 1.2 <= vram / 1024 * 0.92; }
function renderHfResults() {
  const box = $("#hfResults");
  const list = S.hfResults.filter(r => [...S.capFilter].every(k => k === "fits" ? fitsGpu(q4Size(r)) : (r.caps || []).some(c => c.key === k)));
  box.innerHTML = list.length ? list.map(r => `<div class="item clickable hf-item ${r.chat ? "" : "not-chat"}" data-repo="${esc(r.id)}">
      <div class="name-col"><span class="name" title="${esc(r.id)}">${esc(r.id)}</span>
      <div class="sub">${capsHTML(r, true)}${r.params ? `<span class="meta-pill">🧩 ${esc(r.params)}</span>` : ""}${r.ctx ? `<span class="meta-pill">📏 ${esc(r.ctx)}</span>` : ""}
      ${r.chat && q4Size(r) ? (fitsGpu(q4Size(r)) ? '<span class="tag fit" title="Em Q4_K_M cabe inteiro na sua placa">cabe</span>' : '<span class="tag tight" title="Em Q4_K_M não cabe inteiro na VRAM: vai ficar mais lento">pesado</span>') : ""}</div></div>
      <span class="meta">⤓ ${fmtNum(r.downloads)}<br>♥ ${fmtNum(r.likes)}</span></div>`).join("")
    : `<p class="muted">${S.hfResults.length ? "Nenhum resultado com esses filtros." : "Nada encontrado."}</p>`;
}
async function hfSearch(q) {
  const box = $("#hfResults"); box.innerHTML = '<p class="muted">Buscando...</p>'; $("#hfFiles").innerHTML = "";
  try { S.hfResults = await api("/api/hf/search?q=" + encodeURIComponent(q.trim())); renderHfResults(); }
  catch (e) { box.innerHTML = `<p class="muted">Erro: ${esc(e.message)}</p>`; }
}
$("#hfResults").addEventListener("click", async e => {
  const it = e.target.closest("[data-repo]"); if (!it) return;
  $$("#hfResults .item").forEach(x => x.classList.toggle("sel", x === it));
  S.selectedRepo = it.dataset.repo;
  const box = $("#hfFiles"); box.innerHTML = '<p class="muted">Carregando arquivos...</p>';
  try {
    const { files, mmproj, info, mtp, mtp_size } = await api("/api/hf/files?repo=" + encodeURIComponent(S.selectedRepo));
    // melhor arquivo para este PC: o de maior qualidade que cabe inteiro na VRAM
    const fitting = files.filter(f => fitsGpu(f.size) && f.stars);
    const best = fitting.sort((a, b) => b.stars - a.stars || a.size - b.size)[0]?.path; // entre os melhores, o menor (sobra VRAM para o contexto)
    box.innerHTML = `<div class="repo-card"><div class="row between"><b>${esc(S.selectedRepo)}</b><a href="https://huggingface.co/${esc(S.selectedRepo)}" target="_blank" rel="noopener" class="meta">ver página ↗</a></div>
      ${info ? capsHTML(info) : ""}
      ${info && !info.chat ? `<div class="warn-box">${(info.caps || []).some(c => c.key === "imagegen") ? "🎨 Este é um modelo de <b>gerar imagens</b>, não de conversa. Use os modelos de imagem em Modelos → Mídia." : "🔎 Este modelo não serve para conversar."}</div>` : ""}
      <p class="muted small-note">Passe o mouse nos ícones para ver o que significam. ⭐ = melhor qualidade que cabe na sua placa.</p></div>
      ${mmproj ? `<label class="check vis-check"><input type="checkbox" id="withMmproj" checked> 👁 Incluir visão (o modelo poderá ver imagens) <small class="muted">${esc(baseName(mmproj))}</small></label>` : ""}
      ${mtp ? `<label class="check vis-check" title="${esc(t("Os arquivos MTP não são modelos sozinhos: são um acelerador que funciona junto com o modelo grande e ocupa um pouco mais de VRAM."))}"><input type="checkbox" id="withMtp" checked> ⚡ ${t("Incluir acelerador MTP (respostas mais rápidas, +{size})", { size: fmtSize(mtp_size) })} <small class="muted">${esc(baseName(mtp))}</small></label>` : ""}` +
      (files.length ? files.map(f => `<div class="item file-item ${f.path === best ? "best" : ""}"><div class="name-col"><span class="name" title="${esc(f.path)}">${f.path === best ? "⭐ " : ""}${esc(f.path.split("/").pop())}${f.parts > 1 ? ` <small class="muted">${t("({n} partes)", { n: f.parts })}</small>` : ""}</span>
        <div class="sub">${f.quant ? `<span class="meta-pill">${esc(f.quant)}</span>` : ""}${starsHTML(f)}<small class="muted">${esc(f.quality || "")}</small></div></div>
        ${fitTag(f.size)}<span class="meta">${fmtSize(f.size)}</span><button class="btn small ${f.path === best ? "primary" : ""}" data-dl="${esc(f.path)}">Baixar</button></div>`).join("")
        : '<p class="muted">Nenhum arquivo .gguf neste repositório.</p>');
  } catch (err) { box.innerHTML = `<p class="muted">Erro: ${esc(err.message)}</p>`; }
});
$("#hfFiles").addEventListener("click", async e => {
  const p = e.target.dataset.dl; if (!p) return;
  try { await post("/api/models/download", { repo: S.selectedRepo, path: p, mmproj: !!$("#withMmproj")?.checked, mtp: !!$("#withMtp")?.checked }); toast("Download iniciado"); e.target.disabled = true; }
  catch (err) { toast(err.message, 5000); }
  refreshStatus();
});

// ------------------------------------------------------------------ mídia (Whisper e imagens)
function renderMedia() {
  const m = S.media; const box = $("#mediaInfo");
  if (!m) { box.innerHTML = '<p class="muted">Carregando...</p>'; return; }
  const running = S.status.tasks.some(t => t.status === "running");
  const dis = running ? "disabled" : "";
  const w = m.whisper, im = m.image;
  const html = `
    <div class="media-sec">
      <h4>🎧 Áudio e vídeo: transcrição com Whisper</h4>
      <p class="muted small-note">Transforma a fala de áudios e vídeos anexados em texto para o modelo entender. Roda no seu PC, com o whisper.cpp (licença MIT).</p>
      <div class="row wrap">
        ${w.installed ? `<span class="tag fit">✓ Motor instalado</span><small class="muted">${esc(w.version)}</small>` : ""}
        <button class="btn small ${w.installed ? "" : "primary"}" data-media="whisper:cuda" ${dis}>${w.installed ? "Reinstalar" : "Instalar"} GPU (CUDA, ~650 MB)</button>
        <button class="btn small" data-media="whisper:cpu" ${dis}>${w.installed ? "Reinstalar" : "Instalar"} CPU (~5 MB, mais lento)</button>
      </div>
      <div class="list">${Object.entries(w.available).map(([k, label]) => {
        const have = w.models.includes(`ggml-${k}.bin`);
        return `<div class="item"><span class="name">${esc(label)}</span>${have ? '<span class="tag fit">✓ baixado</span>' : `<button class="btn small" data-media="whisper_model:${k}" ${dis}>Baixar</button>`}</div>`;
      }).join("")}</div>
    </div>
    <div class="media-sec">
      <h4>🎨 Geração de imagens: stable-diffusion.cpp</h4>
      <p class="muted small-note">Use o modo <b>🎨 Imagem</b> na caixa de mensagem. O Codex também consegue criar imagens para os projetos.</p>
      <div class="row wrap">
        ${im.installed ? `<span class="tag fit">✓ Motor instalado</span><small class="muted">${esc(im.version)}</small>` : ""}
        <button class="btn small ${im.installed ? "" : "primary"}" data-media="sd:vulkan" ${dis}>${im.installed ? "Reinstalar" : "Instalar"} Vulkan (recomendado, ~30 MB)</button>
        <button class="btn small" data-media="sd:cuda" ${dis}>CUDA (~860 MB)</button>
        <button class="btn small" data-media="sd:cpu" ${dis}>CPU (muito lento)</button>
      </div>
      <div class="list">${Object.entries(im.presets).map(([k, p]) => `<div class="item"><span class="name"><b>${esc(p.name)}</b> <small class="muted">${esc(p.desc)}</small></span>
        ${p.installed ? '<span class="tag fit">✓ baixado</span>' : `<button class="btn small" data-media="image_preset:${k}" ${dis}>Baixar</button>`}</div>`).join("")}</div>
    </div>
    <div class="media-sec">
      <h4>👁 Ver imagens (visão)</h4>
      <p class="muted small-note">Para o modelo <b>enxergar</b> imagens e quadros de vídeo, ele precisa de um arquivo de visão (<i>mmproj</i>). Ao baixar um modelo com visão (ex.: Gemma 3, Qwen2.5-VL, Qwen3-VL), deixe marcado "Incluir visão". Para modelos já baixados, escolha o arquivo em <b>Meus modelos</b>.</p>
    </div>`;
  if (box.dataset.sig !== html) { box.innerHTML = html; box.dataset.sig = html; }
}
$("#mediaInfo").addEventListener("click", async e => {
  const v = e.target.dataset.media; if (!v) return;
  const [what, value] = v.split(":");
  try { await post("/api/media/install", { what, value }); toast("Download iniciado"); } catch (err) { toast(err.message, 5000); }
  await refreshStatus(); renderMedia();
});

// ------------------------------------------------------------------ tarefas
function renderTasks() {
  const html = S.status.tasks.map(t => {
    const pct = t.total ? Math.min(100, t.done / t.total * 100) : 0;
    const info = t.status === "running" ? `${fmtSize(t.done)}${t.total ? " / " + fmtSize(t.total) + ` (${pct.toFixed(0)}%)` : ""} ${t.detail ? "· " + esc(t.detail) : ""}`
      : t.status === "done" ? window.t("Concluído") : t.status === "cancelled" ? window.t("Cancelado") : window.t("Erro: {e}", { e: esc(t.error) });
    return `<div class="task ${t.status}"><div class="row between"><span>${esc(t.label)} <span class="muted">— ${info}</span></span>
      ${t.status === "running" ? `<button class="btn small" data-cancel="${t.id}">Cancelar</button>` : ""}</div>
      <div class="bar"><div style="width:${t.status === "done" ? 100 : pct}%"></div></div></div>`;
  }).join("");
  if ($("#tasks").dataset.sig !== html) { $("#tasks").innerHTML = html; $("#tasks").dataset.sig = html; }
}
$("#tasks").addEventListener("click", e => { const id = e.target.dataset.cancel; if (id) post("/api/tasks/cancel", { id }).then(refreshStatus); });

// ------------------------------------------------------------------ motor
function renderEngine() {
  const st = S.status; const g = st.gpu; const b = st.backends;
  const rec = g.vendor === "nvidia" ? "cuda" : "vulkan";
  const running = st.tasks.some(t => t.kind === "engine" && t.status === "running");
  const box = (id, title, desc) => `<div class="box"><b>${title} ${id === rec ? '<span class="tag on">recomendado</span>' : ""}</b>
    <small>${desc}${b[id] ? "<br>" + t("✅ Instalado: {v}", { v: esc(b[id].version) }) : ""}</small>
    <button class="btn small ${b[id] ? "" : "primary"}" data-install="${id}" ${running ? "disabled" : ""}>${b[id] ? "Atualizar" : "Instalar"}</button></div>`;
  const html = `<p>${g.name ? `GPU detectada: <b>${esc(g.name)}</b> (${(g.vram_mb / 1024).toFixed(0)} GB VRAM)` : "Nenhuma GPU NVIDIA detectada."}</p>
    <div class="engine-card">${box("cuda", "CUDA", "Para placas NVIDIA. O mais rápido.")}${box("vulkan", "Vulkan", "Funciona em NVIDIA, AMD e Intel.")}${box("cpu", "CPU", "Sem GPU. Lento, mas funciona em qualquer PC.")}</div>
    ${st.engine.error ? `<div class="msg" style="padding:0;max-width:none"><div class="err">${esc(st.engine.error)}</div></div>` : ""}
    ${reaBoxHTML(running)}`;
  if ($("#engineInfo").dataset.sig !== html) { $("#engineInfo").innerHTML = html; $("#engineInfo").dataset.sig = html; }
}
// REA (engenharia reversa) como componente do motor: instala uma vez e funciona sem internet
function reaBoxHTML(running) {
  const r = S.media?.rea; if (!r) return "";
  return `<div class="rea-box"><div class="rea-head"><b>🔬 REA · ${t("engenharia reversa")}</b>${r.installed ? `<span class="tag fit">✅ ${esc(r.version)} · Node ${esc(r.node)}</span>` : ""}</div>
    <small class="muted">${t("O Codex passa a entender programas sem o código-fonte: apps Electron/JavaScript, .exe/.dll, .NET, Go, Rust, pacotes e bancos SQLite. Baixa uma vez (~290 MB, com um Node.js portátil) e depois funciona sem internet, sem instalar nada no Windows.")}</small>
    <div class="row wrap">${r.installed ? `<button class="btn small" data-rea="install" ${running ? "disabled" : ""}>${t("Reinstalar")}</button><button class="btn small danger" data-rea="uninstall">${t("Remover")}</button>`
      : `<button class="btn small primary" data-rea="install" ${running ? "disabled" : ""}>${t("Instalar REA {v}", { v: esc(r.pinned) })}</button>`}</div></div>`;
}
document.addEventListener("click", async e => {
  const ra = e.target.closest("[data-rea]")?.dataset.rea; if (!ra) return;
  if (ra === "open") { openModal("settingsModal"); return showSettingsTab("codex"); }
  if (ra === "install") { try { await post("/api/media/install", { what: "rea", value: "install" }); toast(t("Instalando o REA... acompanhe o progresso no topo da janela.")); } catch (err) { toast(err.message, 5000); } return refreshStatus(); }
  if (ra === "uninstall") { if (!confirm(t("Remover o REA do motor?"))) return; await post("/api/rea/uninstall"); toast(t("REA removido")); await loadMedia(); renderEngine(); renderReaPlaces(); }
});
// o REA aparece no Motor, em Configurações → Codex e como indicador na barra do Codex
function renderReaPlaces() {
  const running = S.status?.tasks?.some(t => t.kind === "engine" && t.status === "running");
  const box = $("#reaSettings"); if (box) { const h = reaBoxHTML(running); if (box.dataset.sig !== h) { box.innerHTML = h; box.dataset.sig = h; } }
  const chip = $("#reaChip"), r = S.media?.rea;
  if (chip) {
    chip.hidden = !r;
    if (r) { chip.className = "rea-chip" + (r.installed ? " on" : ""); chip.textContent = r.installed ? "🔬 REA" : "🔬 " + t("Instalar REA");
      chip.title = r.installed ? t("REA instalado: o Codex pode fazer engenharia reversa (sem internet). Clique para ver.") : t("Instale o REA para o Codex entender programas sem o código-fonte."); }
  }
}
$("#engineInfo").addEventListener("click", async e => {
  const b = e.target.dataset.install; if (!b) return;
  try { await post("/api/engine/install", { backend: b }); toast("Baixando motor..."); } catch (err) { toast(err.message, 5000); }
  refreshStatus();
});
async function loadLog() {
  try {
    const { log } = await api("/api/log"); const el = $("#engineLog");
    const stick = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    el.textContent = log.join("\n") || t("(vazio: carregue um modelo)");
    if (stick) el.scrollTop = el.scrollHeight;
  } catch {}
}

// ------------------------------------------------------------------ configurações
const NUM_FIELDS = ["temperature", "top_p", "top_k", "min_p", "repeat_penalty", "max_tokens", "ctx_size", "gpu_layers", "cpu_percent",
  "search_results", "agent_max_steps", "image_steps", "extra_idle_minutes"];
const DEFAULTS = { system_prompt: "", temperature: 0.7, top_p: 0.95, top_k: 40, min_p: 0.05, repeat_penalty: 1.0, max_tokens: 0,
  ctx_size: 8192, gpu_layers: 999, cpu_percent: 0, backend: "auto", extra_args: "", search_provider: "duckduckgo",
  search_region: "br-pt", search_results: 4, auto_load: true, agent_confirm_commands: true, agent_confirm_writes: false,
  agent_max_steps: 40, quick_model: "", quick_device: "gpu", quick_keep_loaded: true, vram_guard: true, rea_codex: true, reply_language: "auto", auto_summarize: true, use_recommended: true, extra_idle_minutes: 10, whisper_language: "auto", image_steps: 0, image_enhance: true, image_offload: true, image_unload_llm: false };
function cpuLabel() {
  const pct = +$("#cpuRange").value; const n = S.status?.gpu?.cpu_count || 0;
  $("#cpuLabel").textContent = pct ? t("{pct}% · {n} de {total} threads", { pct, n: Math.max(1, Math.round(n * pct / 100)), total: n }) : t("Automático ({n} threads no PC)", { n });
}
$("#cpuRange").oninput = cpuLabel;
function fillQuickModels() {
  const cur = S.status.settings.quick_model || "";
  $("#quickModelSelect").innerHTML = '<option value="">O mesmo modelo principal do app</option>' +
    S.status.models.map(m => `<option value="${esc(m.path)}" ${m.path === cur ? "selected" : ""}>${esc(m.name)} (${fmtSize(m.size)})</option>`).join("");
}
function fillSettings(src = S.status.settings) {
  fillQuickModels();
  src = { ...src, language: src.language || LANG };
  const f = $("#settingsForm");
  for (const el of f.elements) if (el.name && src[el.name] !== undefined) { if (el.type === "checkbox") el.checked = !!src[el.name]; else el.value = src[el.name]; }
  S.wsEdit = [...(S.status.settings.workspaces || [])]; renderWorkspaceList(); cpuLabel(); loadMcp(); loadMedia();
  showProviderFields(); renderStatsSummary();
}
function renderWorkspaceList() {
  $("#workspaceList").innerHTML = S.wsEdit.length ? S.wsEdit.map((w, i) => `<div class="item"><span class="name" title="${esc(w)}">📁 ${esc(w)}</span><button type="button" class="btn small danger" data-ws-del="${i}">Remover</button></div>`).join("")
    : '<p class="muted small-note">Nenhuma pasta liberada.</p>';
}
$("#workspaceList").onclick = e => { const i = e.target.dataset.wsDel; if (i !== undefined) { S.wsEdit.splice(+i, 1); renderWorkspaceList(); } };
$("#addWorkspace").onclick = async () => { const d = await desktop.chooseFolder(); if (d && !S.wsEdit.includes(d)) { S.wsEdit.push(d); renderWorkspaceList(); } };
function showProviderFields() {
  const p = $("#searchProvider").value;
  $$("[data-prov]").forEach(el => el.style.display = el.dataset.prov === p ? "" : "none");
}
$("#searchProvider").onchange = showProviderFields;
function renderStatsSummary() {
  const g = S.status?.stats || {};
  $("#statsSummary").textContent = t("{a} gerados · {b} de entrada · {c} respostas · {d} pesquisas", { a: fmtNum(g.completion_tokens || 0), b: fmtNum((g.prompt_tokens || 0) + (g.cached_tokens || 0)), c: g.requests || 0, d: g.searches || 0 }) +
    (g.since ? t(" (desde {date})", { date: new Date(g.since * 1000).toLocaleDateString(LANG) }) : "");
}
$("#resetStats").onclick = async () => {
  if (!confirm(t("Zerar o contador geral de tokens?"))) return;
  S.status.stats = await post("/api/stats/reset"); renderStatsSummary(); renderStatsBar();
};
async function initDesktopSettings() {
  const cfg = await desktop.getConfig();
  $("#hotkeyInput").value = cfg.hotkey; $("#autoStart").checked = cfg.autoStart;
  $("#hideOnBlur").checked = cfg.quickHideOnBlur; $("#dataDir").textContent = cfg.homeDir;
  // grava a combinacao de teclas pressionada
  const recordKeys = e => {
    e.preventDefault();
    if (["Control", "Shift", "Alt", "Meta"].includes(e.key)) return;
    const mods = [e.ctrlKey && "Ctrl", e.altKey && "Alt", e.shiftKey && "Shift", e.metaKey && "Super"].filter(Boolean);
    if (!mods.length) return toast("Use pelo menos um modificador (Ctrl, Alt ou Shift).");
    const key = e.code === "Space" ? "Space" : e.key.length === 1 ? e.key.toUpperCase() : e.key;
    e.target.value = [...mods, key].join("+");
  };
  $("#hotkeyInput").onkeydown = recordKeys;
  $("#hotkeySave").onclick = async () => {
    const r = await desktop.setHotkey($("#hotkeyInput").value);
    toast(r.ok ? t("Atalho salvo: {k}", { k: r.hotkey }) : t("Esse atalho já está em uso por outro programa. Tente outro."), 4000);
    if (!r.ok) $("#hotkeyInput").value = r.hotkey;
  };
  $("#autoStart").onchange = e => desktop.setOption("autoStart", e.target.checked);
  $("#hideOnBlur").onchange = e => desktop.setOption("quickHideOnBlur", e.target.checked);
  $("#changeDataDir").onclick = async () => { const d = await desktop.chooseHomeDir(); if (d) $("#dataDir").textContent = d; };
  // atalho de voz (pergunta rápida)
  $("#voiceHotkeyInput").value = cfg.voiceHotkey || "";
  $("#voiceHotkeyInput").onkeydown = recordKeys;
  $("#voiceHotkeySave").onclick = async () => {
    const r = await desktop.setVoiceHotkey($("#voiceHotkeyInput").value);
    toast(r.ok ? t("Atalho salvo: {k}", { k: r.hotkey }) : t("Esse atalho já está em uso por outro programa. Tente outro."), 4000);
    if (!r.ok) $("#voiceHotkeyInput").value = r.hotkey;
  };
  // atalho da tela (pergunta rápida)
  $("#screenHotkeyInput").value = cfg.screenHotkey || "";
  $("#screenHotkeyInput").onkeydown = recordKeys;
  $("#screenHotkeySave").onclick = async () => {
    const r = await desktop.setScreenHotkey($("#screenHotkeyInput").value);
    toast(r.ok ? t("Atalho salvo: {k}", { k: r.hotkey }) : t("Esse atalho já está em uso por outro programa. Tente outro."), 4000);
    if (!r.ok) $("#screenHotkeyInput").value = r.hotkey;
  };
  // vozes do Windows para ler as respostas
  const fillVoices = () => {
    const vs = speechSynthesis.getVoices(); const cur = ls("ttsVoice", "");
    $("#ttsVoice").innerHTML = `<option value="">${t("Automática (idioma do app)")}</option>` + vs.map(v => `<option value="${esc(v.voiceURI)}" ${v.voiceURI === cur ? "selected" : ""}>${esc(v.name)} (${esc(v.lang)})</option>`).join("");
  };
  fillVoices(); speechSynthesis.onvoiceschanged = fillVoices;
  $("#ttsVoice").onchange = e => { lsSet("ttsVoice", e.target.value); speakText(t("Esta é a voz que vai ler as respostas.")); };
  // atualizações automáticas pelo GitHub
  let current = "";
  const showUpdate = s => {
    current = s.current || current;
    const v = s.version;
    const txt = { idle: "", checking: t("Verificando atualizações..."), latest: t("Você está na versão mais recente."),
      downloading: t("Baixando a versão {v}... {p}%", { v, p: s.percent || 0 }), ready: t("Versão {v} pronta para instalar.", { v }),
      manual: t("A versão {v} troca o Electron e precisa do instalador completo.", { v }),
      error: t("Não foi possível verificar: {e}", { e: s.error }), dev: t("Atualização automática só funciona no app instalado.") }[s.status] || "";
    $("#updateText").textContent = t("Versão {v}", { v: current }) + (txt ? " · " + txt : "");
    $("#updateBtn").textContent = t(s.status === "ready" ? "Reiniciar e atualizar" : s.status === "manual" ? "Baixar instalador" : "Verificar atualizações");
    $("#updateBtn").disabled = ["checking", "downloading"].includes(s.status);
  };
  desktop.onUpdateState(showUpdate);
  showUpdate(await desktop.updateInfo());
  $("#updateBtn").onclick = async () => {
    const s = await desktop.updateInfo();
    if (["ready", "manual"].includes(s.status)) desktop.installUpdate(); else showUpdate(await desktop.checkUpdates());
  };
}
$("#resetSettings").onclick = () => fillSettings(DEFAULTS);
// se algum campo estiver fora do permitido, mostra qual (o navegador sozinho só destaca o campo, que pode estar fora da tela)
// abas das Configurações
function showSettingsTab(key) {
  $$(".set-tab").forEach(b => b.classList.toggle("active", b.dataset.setTab === key));
  $$(".set-pane").forEach(s => s.classList.toggle("active", s.dataset.setPane === key));
  $(".set-body").scrollTop = 0; lsSet("setTab", key);
}
$(".set-nav").addEventListener("click", e => { const b = e.target.closest("[data-set-tab]"); if (b) showSettingsTab(b.dataset.setTab); });
showSettingsTab(ls("setTab", "general"));
$("#settingsForm").addEventListener("invalid", e => {
  const el = e.target;
  const pane = el.closest("[data-set-pane]"); if (pane && !pane.classList.contains("active")) showSettingsTab(pane.dataset.setPane); const label = el.closest("label")?.firstChild?.textContent?.trim() || el.name;
  toast(`${t("Valor inválido em")} "${label}": ${el.validationMessage}`, 6000);
  el.scrollIntoView({ block: "center" });
}, true);
$("#settingsForm").onsubmit = async e => {
  e.preventDefault();
  const data = { workspaces: S.wsEdit };
  for (const el of e.target.elements) if (el.name) data[el.name] = el.type === "checkbox" ? el.checked : NUM_FIELDS.includes(el.name) ? Number(el.value) : el.value;
  try {
    const old = S.status.settings;
    await api("/api/settings", { method: "PUT", body: data });
    $("#settingsModal").classList.remove("open");
    data.threads = 0; // a porcentagem de CPU substitui o antigo numero fixo de threads
    const reloadKeys = ["ctx_size", "gpu_layers", "cpu_percent", "backend", "extra_args"];
    const needReload = S.status.engine.state === "ready" && reloadKeys.some(k => String(old[k]) !== String(data[k]));
    toast(needReload ? "Salvo. Recarregue o modelo para aplicar contexto/GPU." : "Configurações salvas");
    if (data.language && data.language !== LANG) return setTimeout(() => setLanguage(data.language), 600);
    refreshStatus();
  } catch (err) { toast(err.message, 5000); }
};

// ------------------------------------------------------------------ backup
async function loadBackupInfo() {
  try {
    const i = await api("/api/backup/info");
    $("#backupInfo").textContent = t("{n} conversas ({s})", { n: i.chats, s: fmtSize(i.chats_size) }) + (i.files ? t(" · {n} anexos e imagens ({s})", { n: i.files, s: fmtSize(i.files_size) }) : "");
  } catch {}
}
$("#backupBtn").onclick = () => {
  const a = document.createElement("a");
  a.href = `/api/backup?attachments=${$("#backupFiles").checked ? 1 : 0}`; a.click();
  toast("Escolha onde salvar o arquivo de backup.");
};
$("#restoreBtn").onclick = () => $("#restoreInput").click();
$("#restoreInput").onchange = async e => {
  const file = e.target.files[0]; e.target.value = ""; if (!file) return;
  const out = $("#restoreResult"); out.className = "small-note"; out.textContent = t("Restaurando...");
  try {
    const r = await fetch(`/api/restore?settings=${$("#restoreSettings").checked ? 1 : 0}`, { method: "POST", body: file });
    const j = await r.json(); if (!r.ok) throw new Error(j.error);
    out.textContent = t("✅ {a} conversas novas, {b} atualizadas, {c} já estavam em dia, {d} arquivos restaurados.", { a: j.added, b: j.updated, c: j.skipped, d: j.files });
    refreshStatus(); loadBackupInfo();
  } catch (err) { out.className = "small-note err-text"; out.textContent = "⚠ " + err.message; }
};

// ------------------------------------------------------------------ inicio
async function openChatFromHash() {
  const m = location.hash.match(/chat=([\w-]+)/); if (!m) return;
  history.replaceState(null, "", location.pathname);
  if (S.generating) return;
  try { S.chat = await api("/api/chats/" + m[1]); renderMessages(); renderChatList(); } catch {}
}
window.addEventListener("hashchange", openChatFromHash);

(async function init() {
  setWeb(S.web);
  setMode(S.mode);
  await refreshStatus();
  loadMedia();
  loadAgents().then(updateHint);
  loadKbs(); loadMcp();
  renderMessages();
  await openChatFromHash();
  initDesktopSettings();
  setInterval(() => {
    if (!S.generating) refreshStatus();
    if ($("#modelsModal").classList.contains("open") && $("#tabEngine").classList.contains("active")) loadLog();
    if ($("#modelsModal").classList.contains("open") && $("#tabMedia").classList.contains("active")) renderMedia();
  }, 1500);
  $("#input").focus();
})();
