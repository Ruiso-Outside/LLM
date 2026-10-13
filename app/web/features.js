"use strict";
// Janela principal: ajustes por modelo, alterações do Codex (ver/desfazer), bases de conhecimento
// e resumo automático do contexto. Carregado antes do app.js; usa S/app.js só quando é chamado.

// ------------------------------------------------------------------ ajustes por modelo
const MS = { model: null, rec: null };
async function openModelSettings(path) {
  const r = await api("/api/models/settings?model=" + encodeURIComponent(path));
  MS.model = path; MS.rec = r.recommended;
  $("#msTitle").textContent = t("Ajustes de {name}", { name: modelNameOf(path) });
  $("#msFamily").textContent = t("Família detectada: {f}", { f: t(r.family) }) + (r.family === "Genérico" ? " · " + t("sem recomendação específica (valem as configurações globais)") : "");
  for (const el of $("#msForm").elements) {
    el.value = r.settings[el.name] ?? "";
    el.placeholder = r.recommended[el.name] != null ? String(r.recommended[el.name]) : "";
  }
  openModal("modelSettingsModal");
}
$("#msUseRec").onclick = () => { for (const el of $("#msForm").elements) if (MS.rec?.[el.name] != null) el.value = MS.rec[el.name]; };
$("#msClear").onclick = () => { for (const el of $("#msForm").elements) el.value = ""; };
$("#msSave").onclick = async () => {
  if (!$("#msForm").reportValidity()) return;
  const vals = {}; for (const el of $("#msForm").elements) if (el.value !== "") vals[el.name] = Number(el.value);
  try {
    await api("/api/models/settings", { method: "PUT", body: { model: MS.model, settings: Object.keys(vals).length ? vals : null } });
    $("#modelSettingsModal").classList.remove("open");
    const loaded = S.status.engine.model === MS.model || (S.status.extras || []).some(x => x.model === MS.model);
    toast(loaded ? "Ajustes salvos. Recarregue o modelo para aplicar contexto/GPU." : "Ajustes salvos");
    refreshStatus();
  } catch (e) { toast(e.message, 5000); }
};

// ------------------------------------------------------------------ Codex: ver e desfazer alterações
const CKPT_LABEL = { created: "criado", modified: "alterado", deleted: "apagado" };
function checkpointHTML(msg) {
  const c = msg.checkpoint; if (!c?.changes?.length) return "";
  const parts = ["created", "modified", "deleted"].map(s => [s, c.changes.filter(x => x.status === s).length]).filter(x => x[1])
    .map(([s, n]) => t(`{n} ${CKPT_LABEL[s]}(s)`, { n }));
  return `<div class="ckpt ${c.undone ? "undone" : ""}">📁 ${parts.join(" · ")}${c.undone ? ` · <b>${t("alterações desfeitas")}</b>` : ""}</div>`;
}
function colorDiff(text) {
  return text.split("\n").map(l => {
    const e = esc(l);
    if (l.startsWith("+++") || l.startsWith("---")) return `<span class="dh">${e}</span>`;
    if (l.startsWith("@@")) return `<span class="dat">${e}</span>`;
    if (l.startsWith("+")) return `<span class="da">${e}</span>`;
    if (l.startsWith("-")) return `<span class="dd">${e}</span>`;
    return e;
  }).join("\n");
}
async function showCodexDiff(msg) {
  const box = $("#diffBody"); box.innerHTML = `<p class="muted">${t("Carregando...")}</p>`; openModal("diffModal");
  try {
    const d = await api(`/api/codex/diff?chat_id=${encodeURIComponent(S.chat.id)}&run_id=${msg.checkpoint.id}`);
    box.innerHTML = (d.undone ? `<div class="warn-box">${t("Estas alterações já foram desfeitas.")}</div>` : "") +
      (d.files.map(f => `<div class="diff-file"><div class="diff-head"><span class="ck-st ck-${f.status}">${t(CKPT_LABEL[f.status])}</span><code>${esc(f.path)}</code>
        ${f.added != null ? `<span class="add-n">+${f.added}</span><span class="del-n">−${f.removed}</span>` : ""}</div><pre class="udiff">${colorDiff(f.diff)}</pre></div>`).join("")
        || `<p class="muted">${t("Nenhuma alteração.")}</p>`);
  } catch (e) { box.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}
async function undoCodex(msg) {
  const n = msg.checkpoint.changes.length;
  if (!confirm(t("Desfazer as alterações deste pedido ({n} arquivos)? Eles voltam a ficar como estavam antes. Comandos executados não são desfeitos.", { n }))) return;
  try {
    const r = await post("/api/codex/undo", { chat_id: S.chat.id, run_id: msg.checkpoint.id });
    msg.checkpoint.undone = true; await saveChat(); renderMessages();
    toast(t("Desfeito: {n} arquivos restaurados", { n: r.restored.length }));
  } catch (e) { toast(e.message, 5000); }
}

// ------------------------------------------------------------------ bases de conhecimento
const KB = { list: [], embed: "", pdf: null, busy: false };
async function loadKbs() {
  try { const r = await api("/api/kb"); KB.list = r.bases; KB.embed = r.embed_model; } catch { return; }
  renderKbSelect();
  if ($("#kbModal").classList.contains("open")) renderKb();
  if (!KB.busy) { const p = KB.list.find(k => k.pending_pdfs && k.status !== "indexando"); if (p) processPendingPdfs(p.id); }
}
function renderKbSelect() {
  const sel = $("#kbSelect"); const cur = ls("kb", "");
  const html = `<option value="">📚 ${t("Sem base")}</option>` + KB.list.map(k => `<option value="${k.id}">📚 ${esc(k.name)}</option>`).join("");
  if (sel.dataset.sig !== html) { sel.innerHTML = html; sel.dataset.sig = html; }
  sel.value = KB.list.some(k => k.id === cur) ? cur : "";
  sel.hidden = !KB.list.length || !["chat", "agents"].includes(S.mode);
  S.kb = sel.hidden ? "" : sel.value;
}
$("#kbSelect").onchange = e => { lsSet("kb", e.target.value); S.kb = e.target.value; };

function kbStatus(k) {
  if (KB.pdf?.id === k.id) return t("lendo PDF {i}/{n}: {f}", { i: KB.pdf.i, n: KB.pdf.n, f: KB.pdf.file });
  const st = { nova: t("ainda não indexada"), indexando: t("indexando..."), pdfs_pendentes: t("{n} PDFs pendentes", { n: k.pending_pdfs }) }[k.status] || "";
  return [k.indexed ? t("{f} arquivos · {c} trechos", { f: k.n_files, c: k.n_chunks }) : "", st].filter(Boolean).join(" · ");
}
function renderKb() {
  const running = (S.status?.tasks || []).filter(x => x.status === "running" && (x.kind === "kb" || /embeddings/i.test(x.label)));
  $("#kbEmbed").innerHTML = (KB.embed
    ? `<span class="tag fit">✓ ${t("Modelo de embeddings")}</span> <small class="muted">${esc(KB.embed)}</small>`
    : `<div class="warn-box">${t("Para criar bases, baixe primeiro o modelo de embeddings (Qwen3-Embedding 0.6B, ~610 MB, entende português).")}
       <button class="btn small primary" id="kbGetEmbed" ${running.length ? "disabled" : ""}>${t("Baixar")}</button></div>`) +
    running.map(x => `<div class="task running"><span>${esc(x.label)} <span class="muted">— ${x.total ? `${x.done}/${x.total}` : ""} ${esc(x.detail || "")}</span></span>
      <div class="bar"><div style="width:${x.total ? Math.min(100, x.done / x.total * 100) : 0}%"></div></div></div>`).join("");
  const html = KB.list.length ? KB.list.map(k => `<div class="kb-item" data-kb="${k.id}">
      <div class="row between"><b class="kb-name">📚 ${esc(k.name)}</b><span class="meta">${esc(kbStatus(k))}</span></div>
      <div class="kb-folders">${k.folders.map(f => `<span class="kb-folder" title="${esc(f)}">📁 ${esc(baseName(f))}<button class="att-x" data-kb-rmfolder="${esc(f)}" title="${t("Remover")}">✕</button></span>`).join("") || `<small class="muted">${t("Nenhuma pasta.")}</small>`}</div>
      <div class="row wrap"><button class="btn small" data-kb-act="folder">+ ${t("Pasta")}</button>
        <button class="btn small primary" data-kb-act="index" ${KB.embed && k.folders.length && k.status !== "indexando" ? "" : "disabled"}>${k.indexed ? t("Atualizar índice") : t("Indexar")}</button>
        <button class="btn small" data-kb-act="rename">${t("Renomear")}</button><button class="btn small danger" data-kb-act="delete">${t("Excluir")}</button></div></div>`).join("")
    : `<p class="muted">${t("Nenhuma base ainda.")}</p>`;
  if ($("#kbList").dataset.sig !== html) { $("#kbList").innerHTML = html; $("#kbList").dataset.sig = html; }
}
$("#kbEmbed").addEventListener("click", async e => {
  if (e.target.id !== "kbGetEmbed") return;
  try { await post("/api/media/install", { what: "embed_model", value: "qwen3-embedding" }); toast("Download iniciado"); } catch (err) { toast(err.message, 5000); }
  await refreshStatus(); renderKb();
});
$("#kbNew").onclick = async () => {
  if (!KB.embed) return toast("Baixe primeiro o modelo de embeddings.");
  const dir = await desktop.chooseFolder(); if (!dir) return;
  await post("/api/kb/create", { name: baseName(dir), folders: [dir] });
  await loadKbs(); toast("Base criada. Clique em Indexar.");
};
$("#kbList").addEventListener("click", async e => {
  const item = e.target.closest("[data-kb]"); if (!item) return;
  const id = item.dataset.kb; const k = KB.list.find(x => x.id === id);
  const rm = e.target.dataset.kbRmfolder;
  if (rm) { await api("/api/kb/" + id, { method: "PUT", body: { folders: k.folders.filter(f => f !== rm) } }); return loadKbs(); }
  const act = e.target.dataset.kbAct;
  if (act === "folder") { const d = await desktop.chooseFolder(); if (d) { await api("/api/kb/" + id, { method: "PUT", body: { folders: [...k.folders, d] } }); loadKbs(); } }
  if (act === "index") { try { await post("/api/kb/index", { id }); toast("Indexando..."); } catch (err) { toast(err.message, 5000); } refreshStatus(); setTimeout(loadKbs, 800); }
  if (act === "delete" && confirm(t("Excluir a base \"{name}\"? Seus arquivos não são apagados, só o índice.", { name: k.name }))) {
    await api("/api/kb/" + id, { method: "DELETE" }); if (ls("kb", "") === id) lsSet("kb", ""); loadKbs();
  }
  if (act === "rename") {
    const b = item.querySelector(".kb-name"); const inp = document.createElement("input");
    inp.className = "input small-input"; inp.value = k.name; b.replaceWith(inp); inp.focus(); inp.select();
    const done = async ok => { if (ok && inp.value.trim()) await api("/api/kb/" + id, { method: "PUT", body: { name: inp.value.trim() } }); $("#kbList").dataset.sig = ""; loadKbs(); };
    inp.onkeydown = ev => { if (ev.key === "Enter") done(true); if (ev.key === "Escape") { ev.stopPropagation(); done(false); } };
    inp.onblur = () => done(true);
  }
});

// PDFs: o texto é extraído aqui (pdf.js) e enviado ao servidor, que gera os embeddings
async function pdfText(buf) {
  const lib = await getPdfjs();
  const doc = await lib.getDocument({ data: new Uint8Array(buf) }).promise;
  const pages = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const tc = await (await doc.getPage(i)).getTextContent();
    let line = ""; const lines = [];
    for (const it of tc.items) { line += it.str; if (it.hasEOL) { lines.push(line); line = ""; } }
    if (line) lines.push(line);
    pages.push(lines.join("\n"));
  }
  return pages.join("\n\n");
}
async function processPendingPdfs(id) {
  if (KB.busy) return; KB.busy = true;
  try {
    const pending = await api("/api/kb/pending?id=" + id);
    for (const [i, path] of pending.entries()) {
      KB.pdf = { id, i: i + 1, n: pending.length, file: baseName(path) }; renderKb();
      try {
        const buf = await (await fetch(`/api/kb/file?id=${id}&path=${encodeURIComponent(path)}`)).arrayBuffer();
        await post("/api/kb/add_text", { id, path, text: await pdfText(buf) });
      } catch (err) { console.warn("PDF", path, err); await post("/api/kb/add_text", { id, path, text: "" }).catch(() => {}); }
    }
  } finally { KB.pdf = null; KB.busy = false; }
  loadKbs();
}

function kbBoxHTML(k, streaming) {
  const name = esc(k.name || "");
  if (k.stage === "searching" || k.stage === "loading") return `<div class="web-box kb-box"><span class="status">📚 ${t("Consultando {name}...", { name })}</span></div>`;
  if (k.stage === "error") return `<div class="web-box kb-box"><span class="status err">📚 ${esc(trText(k.text))}</span></div>`;
  if (!k.sources?.length) return `<div class="web-box kb-box"><span class="status">📚 ${t("Nada relevante encontrado em {name}", { name })}</span></div>`;
  const items = k.sources.map(s => `<li><a href="#" data-kb-open="${esc(s.path)}" title="${esc(s.path)}">${esc(s.file)}</a><small>${t("linhas {l}", { l: s.lines })} · ${Math.round(s.score * 100)}%</small></li>`).join("");
  return `<details class="web-box kb-box"${streaming ? " open" : ""}><summary>📚 ${t("Consultou {name} · {n} trechos", { name, n: k.sources.length })}</summary><ol>${items}</ol></details>`;
}
function linkDocCitations(html, sources) {
  if (!sources?.length) return html;
  return html.split(/(<pre[\s\S]*?<\/pre>|<code>[\s\S]*?<\/code>)/).map((part, i) => i % 2 ? part :
    part.replace(/\[D(\d{1,2})\]/g, (m, n) => { const s = sources[+n - 1]; return s ? `<a href="#" class="cite doc" data-kb-open="${esc(s.path)}" title="${esc(s.file)} · ${t("linhas {l}", { l: s.lines })}">D${n}</a>` : m; })).join("");
}
document.addEventListener("click", e => {
  const a = e.target.closest("[data-kb-open]"); if (!a) return;
  e.preventDefault(); desktop.showItem(a.dataset.kbOpen);
});

// ------------------------------------------------------------------ resumo automático do contexto
function estimateTokens(msgs) {
  let chars = 0;
  for (const m of msgs) {
    chars += (m.content || "").length + (m.reasoning ? 0 : 0);
    for (const a of m.attachments || []) chars += (a.text?.length || 0) + (a.kind === "image" ? 3000 : 0);
    if (m.trace) chars += JSON.stringify(m.trace).length / 2;
  }
  return Math.round(chars / 3.5);
}
async function maybeSummarize() {
  const st = S.status.settings;
  if (!st.auto_summarize || !S.chat || S.status.engine.state !== "ready") return;
  const nctx = S.status.engine.n_ctx || st.ctx_size;
  const msgs = S.chat.messages; const from = S.chat.summary?.upto || 0;
  const used = Math.max(from ? 0 : chatTotals(S.chat).ctxUsed, estimateTokens(msgs.slice(from)) + Math.round((S.chat.summary?.text.length || 0) / 3.5));
  if (used < nctx * 0.8) return;
  const upto = msgs.length - 1 - 4; // mantém as 4 últimas mensagens + a nova
  if (upto - from < 2) return;
  const part = msgs.slice(from, upto).map(m => ({
    role: m.role,
    content: m.role === "assistant" ? (m.mode === "image" ? `[imagem: ${m.image?.prompt || ""}]` : (splitThink(m).content || m.content || ""))
      : (m.content || "") + (m.attachments || []).map(a => a.kind === "text" ? `\n[arquivo ${a.name}]\n${(a.text || "").slice(0, 3000)}` : `\n[${a.kind}: ${a.name}]`).join(""),
  }));
  if (S.chat.summary) part.unshift({ role: "assistant", content: "Resumo da parte anterior:\n" + S.chat.summary.text });
  $("#hint").textContent = t("📝 Resumindo a conversa anterior para caber no contexto...");
  try {
    const r = await post("/api/summarize", { messages: part });
    S.chat.summary = { upto, text: r.summary, at: Date.now() / 1000 };
    await saveChat();
  } catch (e) { toast(t("Não foi possível resumir: {e}", { e: e.message }), 5000); }
  updateHint();
}
function summaryDividerHTML(s) {
  return `<div class="summary-divider"><details><summary>📝 ${t("As mensagens acima foram resumidas para caber no contexto")}</summary><div class="summary-text">${md(s.text)}</div></details></div>`;
}
