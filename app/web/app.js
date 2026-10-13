"use strict";
const S = {
  status: null,
  chat: null,          // conversa aberta {id, title, created, messages}
  generating: false,
  abort: null,
  selectedRepo: "",
  chatFilter: "",
  web: (() => { try { return localStorage.getItem("web") === "1"; } catch { return false; } })(),
};

// ------------------------------------------------------------------ util
let toastTimer;
function toast(msg, ms = 2600) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), ms);
}

// ------------------------------------------------------------------ status
async function refreshStatus() {
  try {
    S.status = await api("/api/status");
  } catch { $("#statusPill").textContent = "Servidor offline"; $("#statusPill").className = "pill error"; return; }
  renderTopbar(); renderChatList(); renderTasks(); renderStatsBar();
  if ($("#modelsModal").classList.contains("open")) { renderLocalModels(); renderEngine(); }
}

function renderTopbar() {
  const st = S.status; const e = st.engine;
  const sel = $("#modelSelect"); const prev = sel.value || e.model || st.settings.last_model;
  const opts = st.models.map(m => `<option value="${esc(m.path)}">${esc(m.name)} (${fmtSize(m.size)})</option>`).join("");
  if (sel.dataset.sig !== opts) {
    sel.innerHTML = opts || '<option value="">Nenhum modelo baixado</option>';
    sel.dataset.sig = opts;
    if (st.models.some(m => m.path === prev)) sel.value = prev;
  }
  const pill = $("#statusPill"); const btn = $("#loadBtn");
  const name = (st.models.find(m => m.path === e.model) || {}).name || e.model;
  const map = { stopped: ["Nenhum modelo carregado", ""], loading: ["Carregando " + name + "...", "loading"],
                ready: ["● " + name + (e.backend ? ` · ${e.backend.toUpperCase()}` : ""), "ready"], error: ["Erro no motor (clique)", "error"] };
  pill.textContent = map[e.state][0]; pill.className = "pill " + map[e.state][1];
  pill.title = e.error || "";
  const loadedSelected = (e.state === "ready" || e.state === "loading") && sel.value === e.model;
  btn.textContent = loadedSelected ? (e.state === "loading" ? "Cancelar" : "Descarregar") : "Carregar";
  btn.className = "btn " + (loadedSelected ? "" : "primary");
  btn.disabled = !st.models.length;
  updateHint();
}

function updateHint() {
  const st = S.status; if (!st) return;
  let h = "";
  if (!Object.keys(st.backends).length) h = "Primeiro passo: abra Modelos → Motor e instale o motor.";
  else if (!st.models.length) h = "Baixe um modelo em Modelos → Baixar modelos.";
  else if (st.engine.state !== "ready") h = st.engine.state === "loading" ? "Carregando modelo na memória..." : "Selecione um modelo e clique em Carregar.";
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
    if (!confirm("Excluir esta conversa?")) return;
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

// ------------------------------------------------------------------ mensagens
function msgHTML(msg, idx, isLast) {
  const streaming = isLast && S.generating && msg.role === "assistant";
  if (msg.role === "user") {
    return `<div class="msg user ${isLast ? "last" : ""}" data-i="${idx}"><div class="role">Você</div>
      <div class="bubble">${esc(msg.content)}</div>
      <div class="actions"><button data-act="copy">Copiar</button><button data-act="edit">Editar</button><button data-act="del">Excluir</button></div></div>`;
  }
  const { content, reasoning, open } = splitThink(msg);
  const thinking = streaming && (open || (reasoning && !content));
  let live = "";
  if (streaming) {
    if (msg.web && msg.web.stage !== "done" && msg.web.stage !== "error") live = "";
    else if (msg.stats?.tokens) live = `⚡ ${msg.stats.tps.toFixed(1)} tok/s · ${fmtNum(msg.stats.tokens)} tokens`;
    else live = "processando o prompt...";
  }
  let html = `<div class="msg assistant ${isLast ? "last" : ""}" data-i="${idx}"><div class="role">${esc(msg.model || "Assistente")}${live ? `<span class="live">${live}</span>` : ""}</div>`;
  if (msg.web) html += webBoxHTML(msg.web, streaming);
  if (reasoning) html += `<details class="think" ${thinking ? "open" : ""}><summary>${thinking ? "Pensando..." : "Raciocínio"}</summary><div class="think-body">${esc(reasoning)}</div></details>`;
  html += `<div class="content ${streaming ? "cursor" : ""}">${linkCitations(md(content), msg.web?.sources)}</div>`;
  if (msg.error) html += `<div class="err">${esc(msg.error)}</div>`;
  if (!streaming) {
    const s = msg.stats;
    const st = s ? `<span class="stats" title="${s.prompt !== undefined ? `Entrada: ${s.prompt + (s.cached || 0)} tokens (${s.cached || 0} reaproveitados do cache)\nSaída: ${s.tokens} tokens` : ""}">${s.tps.toFixed(1)} tok/s · ${fmtNum(s.tokens)} tokens gerados${s.prompt !== undefined ? ` · ${fmtNum(s.prompt + (s.cached || 0))} de entrada` : ""}</span>` : "";
    html += `<div class="actions"><button data-act="copy">Copiar</button>${isLast ? '<button data-act="regen">Regenerar</button><button data-act="continue">Continuar</button>' : ""}<button data-act="del">Excluir</button>${st}</div>`;
  }
  return html + "</div>";
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
        <li>Selecione o modelo no topo e clique em <b>Carregar</b></li></ol>` : ""}</div>`;
    return;
  }
  const n = S.chat.messages.length;
  box.innerHTML = S.chat.messages.map((m, i) => msgHTML(m, i, i === n - 1)).join("");
  box.scrollTop = box.scrollHeight;
  renderStatsBar();
}

// ------------------------------------------------------------------ contador de tokens
function chatTotals(chat) {
  let input = 0, output = 0, ctxUsed = 0;
  for (const m of chat?.messages || []) {
    if (m.role !== "assistant" || !m.stats) continue;
    const inp = (m.stats.prompt || 0) + (m.stats.cached || 0);
    input += inp; output += m.stats.tokens || 0;
    if (m.stats.prompt !== undefined) ctxUsed = inp + (m.stats.tokens || 0);
  }
  return { input, output, ctxUsed };
}

function renderStatsBar() {
  const st = S.status; const bar = $("#statsBar"); if (!st) return;
  if (st.engine.state !== "ready" && !S.chat?.messages.length) { bar.innerHTML = ""; return; }
  const t = chatTotals(S.chat); const g = st.stats || {};
  const nctx = st.engine.n_ctx || st.settings.ctx_size;
  const pct = nctx ? Math.min(100, t.ctxUsed / nctx * 100) : 0;
  const parts = [];
  if (st.engine.state === "ready")
    parts.push(`<span class="ctx-meter ${pct > 85 ? "high" : pct > 60 ? "mid" : ""}" title="Quanto da memória de contexto do modelo esta conversa já ocupa. Ao chegar em 100%, comece uma nova conversa ou aumente o contexto nas Configurações.">Contexto <span class="track"><div style="width:${pct}%"></div></span><b>${fmtNum(t.ctxUsed)} / ${fmtNum(nctx)}</b></span>`);
  if (S.chat?.messages.length)
    parts.push(`<span title="Tokens desta conversa: entrada (o que o modelo leu, somando todas as mensagens) e saída (o que ele escreveu)">Conversa: <b>${fmtNum(t.input + t.output)}</b> tokens (↑${fmtNum(t.input)} ↓${fmtNum(t.output)})</span>`);
  const gTotal = (g.prompt_tokens || 0) + (g.cached_tokens || 0) + (g.completion_tokens || 0);
  parts.push(`<span title="Desde ${g.since ? new Date(g.since * 1000).toLocaleDateString("pt-BR") : "o início"}: ${fmtNum(g.completion_tokens || 0)} gerados, ${fmtNum((g.prompt_tokens || 0) + (g.cached_tokens || 0))} de entrada, ${g.requests || 0} respostas, ${g.searches || 0} pesquisas na web">Total geral: <b>${fmtNum(gTotal)}</b> tokens</span>`);
  const html = parts.join("");
  if (bar.dataset.sig !== html) { bar.innerHTML = html; bar.dataset.sig = html; }
}

let rafPending = false;
function renderLastMessage() {
  if (rafPending) return; rafPending = true;
  requestAnimationFrame(() => {
    rafPending = false;
    const box = $("#messages"); const n = S.chat.messages.length;
    const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    const el = box.querySelector(`.msg[data-i="${n - 1}"]`);
    const think = el?.querySelector("details.think");
    const keepOpen = think ? think.open : null;
    const tmp = document.createElement("div"); tmp.innerHTML = msgHTML(S.chat.messages[n - 1], n - 1, true);
    const fresh = tmp.firstElementChild;
    const newThink = fresh.querySelector("details.think");
    if (newThink && keepOpen !== null && S.generating) newThink.open = keepOpen;
    if (el) el.replaceWith(fresh); else box.appendChild(fresh);
    if (stick) box.scrollTop = box.scrollHeight;
    renderStatsBar();
  });
}

$("#messages").addEventListener("click", async ev => {
  const cb = ev.target.closest(".copy-code");
  if (cb) {
    await navigator.clipboard.writeText(cb.closest(".code").querySelector("code").textContent);
    cb.textContent = "Copiado!"; setTimeout(() => cb.textContent = "Copiar", 1200); return;
  }
  const b = ev.target.closest("[data-act]"); if (!b || S.generating) return;
  const i = +b.closest(".msg").dataset.i; const msg = S.chat.messages[i];
  switch (b.dataset.act) {
    case "copy": await navigator.clipboard.writeText(splitThink(msg).content || msg.content); toast("Copiado"); break;
    case "del": S.chat.messages.splice(i, 1); renderMessages(); saveChat(); break;
    case "regen": S.chat.messages.pop(); renderMessages(); generate(); break;
    case "continue": generate(true); break;
    case "edit": {
      const el = b.closest(".msg");
      el.querySelector(".bubble").outerHTML = `<textarea class="input edit-area">${esc(msg.content)}</textarea>`;
      el.querySelector(".actions").innerHTML = '<button data-act="save-edit">Salvar e reenviar</button><button data-act="cancel-edit">Cancelar</button>';
      el.querySelector("textarea").focus(); break;
    }
    case "cancel-edit": renderMessages(); break;
    case "save-edit": {
      const txt = b.closest(".msg").querySelector("textarea").value.trim(); if (!txt) return;
      S.chat.messages.splice(i); S.chat.messages.push({ role: "user", content: txt });
      renderMessages(); generate(); break;
    }
  }
});

// ------------------------------------------------------------------ envio / streaming
function buildMessages(upto) {
  const out = []; const sp = S.status.settings.system_prompt;
  if (sp && sp.trim()) out.push({ role: "system", content: sp });
  for (const m of S.chat.messages.slice(0, upto)) {
    const content = m.role === "assistant" ? splitThink(m).content : m.content;
    if (content || m.role === "user") out.push({ role: m.role, content });
  }
  return out;
}

async function send() {
  const inp = $("#input"); const text = inp.value.trim();
  if (!text || S.generating) return;
  if (S.status?.engine.state !== "ready") return toast(S.status?.engine.state === "loading" ? "Aguarde o modelo terminar de carregar." : "Carregue um modelo primeiro (botão Carregar no topo).");
  if (!S.chat) S.chat = { id: uid(), title: text.slice(0, 60).replace(/\s+/g, " "), created: Date.now() / 1000, messages: [] };
  S.chat.messages.push({ role: "user", content: text });
  inp.value = ""; autoGrow();
  renderMessages();
  await generate();
}

async function generate(isContinue = false) {
  const st = S.status.settings;
  const modelName = (S.status.models.find(m => m.path === S.status.engine.model) || {}).name || "";
  let msg, messages;
  if (isContinue) {
    msg = S.chat.messages[S.chat.messages.length - 1];
    messages = buildMessages(); delete msg.error;
    msg._base = msg.stats ? { tokens: msg.stats.tokens } : null;
  } else {
    msg = { role: "assistant", content: "", reasoning: "", model: modelName };
    if (S.web) msg.web = { stage: "query" };
    messages = buildMessages(); S.chat.messages.push(msg);
  }
  S.generating = true; S.abort = new AbortController(); setComposerState();
  renderMessages();
  const t0 = performance.now(); let tokens = 0;
  try {
    const body = { messages, web: S.web && !isContinue, temperature: +st.temperature, top_p: +st.top_p, top_k: +st.top_k,
      min_p: +st.min_p, repeat_penalty: +st.repeat_penalty, max_tokens: +st.max_tokens };
    await streamChat(body, S.abort.signal, j => {
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
    delete msg._base;
    if (msg.web && msg.web.stage !== "done" && msg.web.stage !== "error") delete msg.web;
    S.generating = false; S.abort = null; setComposerState();
    renderMessages();
    await saveChat().catch(() => {});
    refreshStatus();
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
  try { localStorage.setItem("web", on ? "1" : "0"); } catch {}
  updateHint();
}
$("#webBtn").onclick = () => { setWeb(!S.web); toast(S.web ? "Pesquisa na web ligada" : "Pesquisa na web desligada"); };
setWeb(S.web);
function autoGrow() { const t = $("#input"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 260) + "px"; }
$("#input").addEventListener("input", autoGrow);
$("#input").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { if (S.generating) S.abort?.abort(); $$(".modal.open").forEach(m => m.classList.remove("open")); }
});

$("#exportBtn").onclick = () => {
  if (!S.chat?.messages.length) return toast("Nada para exportar.");
  const txt = `# ${S.chat.title}\n\n` + S.chat.messages.map(m =>
    `**${m.role === "user" ? "Você" : (m.model || "Assistente")}:**\n\n${m.role === "assistant" ? splitThink(m).content : m.content}`).join("\n\n---\n\n");
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
  if (id === "modelsModal") { renderLocalModels(); renderEngine(); loadLog(); }
}
$$("[data-open]").forEach(b => b.onclick = () => openModal(b.dataset.open));
$$(".modal").forEach(m => m.addEventListener("mousedown", e => { if (e.target === m || e.target.closest("[data-close]")) m.classList.remove("open"); }));
function switchTab(id) {
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === id));
  $$(".tab-pane").forEach(p => p.classList.toggle("active", p.id === id));
  if (id === "tabEngine") loadLog();
  if (id === "tabHF" && !$("#hfResults").innerHTML) hfSearch("GGUF");
}
$$(".tab").forEach(t => t.onclick = () => switchTab(t.dataset.tab));
$$("[data-folder]").forEach(b => b.onclick = () => post("/api/open-folder", { which: b.dataset.folder }));

// ------------------------------------------------------------------ modelos locais
function renderLocalModels() {
  const st = S.status;
  const html = st.models.length ? st.models.map(m => {
    const on = st.engine.model === m.path && st.engine.state === "ready";
    return `<div class="item"><span class="name" title="${esc(m.path)}">${esc(m.name)}</span>${on ? '<span class="tag on">carregado</span>' : ""}
      ${fitTag(m.size)}<span class="meta">${fmtSize(m.size)}</span>
      <button class="btn small" data-load="${esc(m.path)}">${on ? "Recarregar" : "Carregar"}</button>
      <button class="btn small danger" data-del="${esc(m.path)}">Excluir</button></div>`;
  }).join("") : '<p class="muted">Nenhum modelo ainda. Vá na aba <b>Baixar modelos</b>.</p>';
  if ($("#localModels").dataset.sig !== html) { $("#localModels").innerHTML = html; $("#localModels").dataset.sig = html; }
}
$("#localModels").addEventListener("click", async e => {
  const l = e.target.dataset.load, d = e.target.dataset.del;
  try {
    if (l) { await post("/api/load", { model: l }); $("#modelSelect").value = l; toast("Carregando modelo..."); $("#modelsModal").classList.remove("open"); }
    if (d && confirm("Excluir o arquivo do modelo do disco?")) { await post("/api/models/delete", { path: d }); toast("Modelo excluído"); }
  } catch (err) { toast(err.message, 5000); }
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
const CHIPS = ["Qwen", "gemma", "Llama", "Mistral", "DeepSeek", "Phi", "abliterated", "uncensored", "coder", "bartowski", "unsloth"];
$("#hfChips").innerHTML = CHIPS.map(c => `<span class="chip">${c}</span>`).join("");
$("#hfChips").onclick = e => { if (e.target.classList.contains("chip")) { $("#hfQuery").value = e.target.textContent; hfSearch(e.target.textContent); } };
$("#hfSearchBtn").onclick = () => hfSearch($("#hfQuery").value);
$("#hfQuery").onkeydown = e => { if (e.key === "Enter") hfSearch($("#hfQuery").value); };

async function hfSearch(q) {
  const box = $("#hfResults"); box.innerHTML = '<p class="muted">Buscando...</p>'; $("#hfFiles").innerHTML = "";
  try {
    const res = await api("/api/hf/search?q=" + encodeURIComponent(q.trim()));
    box.innerHTML = res.length ? res.map(r => `<div class="item clickable" data-repo="${esc(r.id)}"><span class="name" title="${esc(r.id)}">${esc(r.id)}</span>
      <span class="meta">⤓ ${fmtNum(r.downloads)} · ♥ ${fmtNum(r.likes)}</span></div>`).join("") : '<p class="muted">Nada encontrado.</p>';
  } catch (e) { box.innerHTML = `<p class="muted">Erro: ${esc(e.message)}</p>`; }
}
$("#hfResults").addEventListener("click", async e => {
  const it = e.target.closest("[data-repo]"); if (!it) return;
  $$("#hfResults .item").forEach(x => x.classList.toggle("sel", x === it));
  S.selectedRepo = it.dataset.repo;
  const box = $("#hfFiles"); box.innerHTML = '<p class="muted">Carregando arquivos...</p>';
  try {
    const files = await api("/api/hf/files?repo=" + encodeURIComponent(S.selectedRepo));
    const main = files.filter(f => !/mmproj/i.test(f.path));
    box.innerHTML = `<div class="row between"><b>${esc(S.selectedRepo)}</b><a href="https://huggingface.co/${esc(S.selectedRepo)}" target="_blank" rel="noopener" class="meta">ver página ↗</a></div>
      <p class="muted" style="margin:0;font-size:13px">Dica: <b>Q4_K_M</b> é o melhor equilíbrio. Q5/Q6/Q8 = mais qualidade e mais pesado.</p>` +
      (main.length ? main.map(f => `<div class="item"><span class="name" title="${esc(f.path)}">${esc(f.path.split("/").pop())}${f.parts > 1 ? ` <small class="muted">(${f.parts} partes)</small>` : ""}</span>
        ${fitTag(f.size)}<span class="meta">${fmtSize(f.size)}</span><button class="btn small primary" data-dl="${esc(f.path)}">Baixar</button></div>`).join("")
        : '<p class="muted">Nenhum arquivo .gguf neste repositório.</p>');
  } catch (err) { box.innerHTML = `<p class="muted">Erro: ${esc(err.message)}</p>`; }
});
$("#hfFiles").addEventListener("click", async e => {
  const p = e.target.dataset.dl; if (!p) return;
  try { await post("/api/models/download", { repo: S.selectedRepo, path: p }); toast("Download iniciado"); e.target.disabled = true; }
  catch (err) { toast(err.message, 5000); }
  refreshStatus();
});

// ------------------------------------------------------------------ tarefas
function renderTasks() {
  const html = S.status.tasks.map(t => {
    const pct = t.total ? Math.min(100, t.done / t.total * 100) : 0;
    const info = t.status === "running" ? `${fmtSize(t.done)}${t.total ? " / " + fmtSize(t.total) + ` (${pct.toFixed(0)}%)` : ""} ${t.detail && t.kind === "engine" ? "· " + esc(t.detail) : ""}`
      : t.status === "done" ? "Concluído" : t.status === "cancelled" ? "Cancelado" : "Erro: " + esc(t.error);
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
    <small>${desc}${b[id] ? `<br>✅ Instalado: ${esc(b[id].version)}` : ""}</small>
    <button class="btn small ${b[id] ? "" : "primary"}" data-install="${id}" ${running ? "disabled" : ""}>${b[id] ? "Atualizar" : "Instalar"}</button></div>`;
  const html = `<p>${g.name ? `GPU detectada: <b>${esc(g.name)}</b> (${(g.vram_mb / 1024).toFixed(0)} GB VRAM)` : "Nenhuma GPU NVIDIA detectada."}</p>
    <div class="engine-card">${box("cuda", "CUDA", "Para placas NVIDIA. O mais rápido.")}${box("vulkan", "Vulkan", "Funciona em NVIDIA, AMD e Intel.")}${box("cpu", "CPU", "Sem GPU. Lento, mas funciona em qualquer PC.")}</div>
    ${st.engine.error ? `<div class="msg" style="padding:0;max-width:none"><div class="err">${esc(st.engine.error)}</div></div>` : ""}`;
  if ($("#engineInfo").dataset.sig !== html) { $("#engineInfo").innerHTML = html; $("#engineInfo").dataset.sig = html; }
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
    el.textContent = log.join("\n") || "(vazio: carregue um modelo)";
    if (stick) el.scrollTop = el.scrollHeight;
  } catch {}
}

// ------------------------------------------------------------------ configurações
const NUM_FIELDS = ["temperature", "top_p", "top_k", "min_p", "repeat_penalty", "max_tokens", "ctx_size", "gpu_layers", "threads", "search_results"];
const DEFAULTS = { system_prompt: "", temperature: 0.7, top_p: 0.95, top_k: 40, min_p: 0.05, repeat_penalty: 1.0, max_tokens: 0,
  ctx_size: 8192, gpu_layers: 999, threads: 0, backend: "auto", extra_args: "", search_provider: "duckduckgo",
  search_region: "br-pt", search_results: 4, auto_load: true };
function fillSettings(src = S.status.settings) {
  const f = $("#settingsForm");
  for (const el of f.elements) if (el.name && src[el.name] !== undefined) { if (el.type === "checkbox") el.checked = !!src[el.name]; else el.value = src[el.name]; }
  showProviderFields(); renderStatsSummary();
}
function showProviderFields() {
  const p = $("#searchProvider").value;
  $$("[data-prov]").forEach(el => el.style.display = el.dataset.prov === p ? "" : "none");
}
$("#searchProvider").onchange = showProviderFields;
function renderStatsSummary() {
  const g = S.status?.stats || {};
  $("#statsSummary").textContent = `${fmtNum(g.completion_tokens || 0)} gerados · ${fmtNum((g.prompt_tokens || 0) + (g.cached_tokens || 0))} de entrada · ${g.requests || 0} respostas · ${g.searches || 0} pesquisas` +
    (g.since ? ` (desde ${new Date(g.since * 1000).toLocaleDateString("pt-BR")})` : "");
}
$("#resetStats").onclick = async () => {
  if (!confirm("Zerar o contador geral de tokens?")) return;
  S.status.stats = await post("/api/stats/reset"); renderStatsSummary(); renderStatsBar();
};
async function initDesktopSettings() {
  const cfg = await desktop.getConfig();
  $("#hotkeyInput").value = cfg.hotkey; $("#autoStart").checked = cfg.autoStart;
  $("#hideOnBlur").checked = cfg.quickHideOnBlur; $("#dataDir").textContent = cfg.homeDir;
  // grava a combinacao de teclas pressionada
  $("#hotkeyInput").onkeydown = e => {
    e.preventDefault();
    if (["Control", "Shift", "Alt", "Meta"].includes(e.key)) return;
    const mods = [e.ctrlKey && "Ctrl", e.altKey && "Alt", e.shiftKey && "Shift", e.metaKey && "Super"].filter(Boolean);
    if (!mods.length) return toast("Use pelo menos um modificador (Ctrl, Alt ou Shift).");
    const key = e.code === "Space" ? "Space" : e.key.length === 1 ? e.key.toUpperCase() : e.key;
    $("#hotkeyInput").value = [...mods, key].join("+");
  };
  $("#hotkeySave").onclick = async () => {
    const r = await desktop.setHotkey($("#hotkeyInput").value);
    toast(r.ok ? "Atalho salvo: " + r.hotkey : "Esse atalho já está em uso por outro programa. Tente outro.", 4000);
    if (!r.ok) $("#hotkeyInput").value = r.hotkey;
  };
  $("#autoStart").onchange = e => desktop.setOption("autoStart", e.target.checked);
  $("#hideOnBlur").onchange = e => desktop.setOption("quickHideOnBlur", e.target.checked);
  $("#changeDataDir").onclick = async () => { const d = await desktop.chooseHomeDir(); if (d) $("#dataDir").textContent = d; };
}
$("#resetSettings").onclick = () => fillSettings(DEFAULTS);
$("#settingsForm").onsubmit = async e => {
  e.preventDefault();
  const data = {};
  for (const el of e.target.elements) if (el.name) data[el.name] = el.type === "checkbox" ? el.checked : NUM_FIELDS.includes(el.name) ? Number(el.value) : el.value;
  try {
    const old = S.status.settings;
    await api("/api/settings", { method: "PUT", body: data });
    $("#settingsModal").classList.remove("open");
    const reloadKeys = ["ctx_size", "gpu_layers", "threads", "backend", "extra_args"];
    const needReload = S.status.engine.state === "ready" && reloadKeys.some(k => String(old[k]) !== String(data[k]));
    toast(needReload ? "Salvo. Recarregue o modelo para aplicar contexto/GPU." : "Configurações salvas");
    refreshStatus();
  } catch (err) { toast(err.message, 5000); }
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
  await refreshStatus();
  renderMessages();
  await openChatFromHash();
  initDesktopSettings();
  setInterval(() => {
    if (!S.generating) refreshStatus();
    if ($("#modelsModal").classList.contains("open") && $("#tabEngine").classList.contains("active")) loadLog();
  }, 1500);
  $("#input").focus();
})();
