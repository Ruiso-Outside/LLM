"use strict";
// Área de trabalho: trilho de navegação, painel do sistema, paleta de comandos (Ctrl+K), atalhos de teclado
// e o registro de travamentos da janela. Carregado depois do app.js.

const MODE_NAMES = { chat: "💬 Chat", codex: "🛠️ Codex", image: "🎨 Imagem", agents: "👥 Agentes" };
function renderModeTag() { $("#modeTag").textContent = t(MODE_NAMES[S.mode] || ""); }

// ------------------------------------------------------------------ painel do sistema (direita)
const gb = mb => (mb / 1024).toFixed(1);
function gauge(label, used, total, extra = "", fmt = null) {
  const pct = total ? Math.min(100, used / total * 100) : 0;
  const cls = pct >= 97 ? "full" : pct >= 88 ? "high" : "";
  return `<div class="gauge ${cls}"><div class="g-top"><span>${label}</span><b>${fmt ? `${fmt(used)} / ${fmt(total)}` : `${gb(used)} / ${gb(total)} GB`}</b></div>
    <div class="g-track"><div style="width:${pct.toFixed(1)}%"></div></div>${extra ? `<small class="muted">${extra}</small>` : ""}</div>`;
}
function liveGpu(st) {
  const g = st.gpu_live || {};
  return g.vram_total ? { used: g.vram_used, total: g.vram_total, util: g.gpu_util, full: g.full, real: true }
    : { used: st.memory?.vram_used || 0, total: st.memory?.vram_total || 0, util: null, full: false, real: false };
}
let lastGuard = 0;
function renderGpuChip() {
  const st = S.status; if (!st) return;
  const gd = st.gpu_live?.guard;
  if (gd && gd.at > lastGuard) {
    if (lastGuard) toast(t("Proteção de VRAM: a placa de vídeo encheu e eu descarreguei {what}.", { what: gd.what }), 9000);
    lastGuard = gd.at;
  }
  const g = liveGpu(st), chip = $("#gpuChip");
  const pct = g.total ? g.used / g.total * 100 : 0;
  chip.hidden = !g.total;
  chip.className = "gpu-chip" + (pct >= 97 ? " full" : pct >= 88 ? " high" : "");
  chip.innerHTML = `🎮 <b>${gb(g.used)}</b>/${gb(g.total)} GB${g.util != null ? ` <span class="muted">· ${g.util}%</span>` : ""}`;
  const warn = $("#vramWarn");
  warn.hidden = !g.full;
  if (g.full) warn.innerHTML = `⚠ ${t("A memória da placa de vídeo está cheia. O Windows pode passar a usar a RAM no lugar e o PC pode travar. Reduza o contexto, descarregue os modelos extras ou use um modelo menor.")}
    <button class="btn small" data-unload-extras>${t("Descarregar extras")}</button>`;
}
function renderInspector() {
  renderGpuChip();
  if (!$("#app").classList.contains("insp-open") || !S.status) return;
  const st = S.status, e = st.engine, g = liveGpu(st), m = st.memory || {};
  const engines = [];
  if (e.state !== "stopped") engines.push({ name: modelName() || e.model, device: e.device || "gpu", state: e.state, main: true, mtp: e.mtp });
  for (const x of st.extras || []) if (x.state === "ready" || x.state === "loading")
    engines.push({ name: x.name, device: x.device, state: x.state, model: x.model, quick: st.quick?.model === x.model });
  const tot = S.chat ? chatTotals(S.chat) : null, nctx = e.n_ctx || st.settings.ctx_size;
  const last = [...(S.chat?.messages || [])].reverse().find(x => x.stats?.tps);
  const html = `
    <section class="insp-sec"><h5>${t("Memória")}</h5>
      ${g.total ? gauge("🎮 GPU", g.used, g.total, g.real ? (g.util != null ? t("uso da GPU: {n}%", { n: g.util }) : "") : t("estimativa (sem leitura da placa)")) : ""}
      ${m.ram_total ? gauge("🧠 RAM", m.ram_total - (m.ram_avail || 0), m.ram_total) : ""}
    </section>
    <section class="insp-sec"><h5>${t("Modelos carregados")}</h5>
      ${engines.length ? engines.map(x => `<div class="eng ${x.state}"><span class="eng-dot"></span><div class="eng-name"><b title="${esc(x.name)}">${esc(x.name)}</b>
        <small class="muted">${x.main ? t("principal") : x.quick ? t("pergunta rápida") : t("extra")} · ${esc((x.device || "gpu").toUpperCase())}${x.mtp ? " · ⚡ MTP" : ""}${x.state === "loading" ? " · " + t("carregando...") : ""}</small></div>
        <button class="icon-btn" title="${esc(t("Descarregar"))}" ${x.main ? "data-unload-main" : `data-unload-extra="${esc(x.model)}"`}>⏏</button></div>`).join("")
        : `<p class="muted small-note">${t("Nenhum modelo carregado.")}</p>`}
    </section>
    ${tot ? `<section class="insp-sec"><h5>${t("Esta conversa")}</h5>
      ${gauge("📏 " + t("Contexto"), tot.ctxUsed, nctx, "", fmtNum)}
      <div class="kv"><span>${t("Tokens")}</span><b>${fmtNum(tot.input + tot.output)}</b></div>
      ${last ? `<div class="kv"><span>${t("Última velocidade")}</span><b>${last.stats.tps.toFixed(1)} tok/s</b></div>` : ""}
    </section>` : ""}
    ${typeof MCP !== "undefined" && MCP.list.length ? `<section class="insp-sec"><h5>${t("Ferramentas MCP")}</h5>
      ${MCP.list.map(s => `<div class="kv"><span>${s.state === "pronto" ? "🟢" : s.state === "erro" ? "🔴" : "⚪"} ${esc(s.name)}</span><b>${s.cli_mode ? t("terminal") : s.tools.length ? mcpOn(s).length + "/" + s.tools.length : "—"}</b></div>`).join("")}
    </section>` : ""}
    <section class="insp-sec"><h5>${t("Diagnóstico")}</h5>
      <p class="muted small-note">${t("Se o app travar, o ocorrido fica registrado no relatório (VRAM, RAM e o que estava rodando).")}</p>
      <div class="row wrap"><button class="btn small" data-open-diag>${t("Abrir relatório")}</button><button class="btn small" data-unload-all>${t("Descarregar tudo")}</button></div>
    </section>`;
  const body = $("#inspBody");
  if (body.dataset.sig !== html) { body.innerHTML = html; body.dataset.sig = html; }
}
function setInspector(open) {
  $("#app").classList.toggle("insp-open", open); lsSet("insp", open ? "1" : "0");
  renderInspector();
}
$("#toggleInspector").onclick = () => setInspector(!$("#app").classList.contains("insp-open"));
$("#closeInspector").onclick = () => setInspector(false);
$("#gpuChip").onclick = () => setInspector(true);
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-unload-main],[data-unload-extra],[data-unload-all],[data-unload-extras],[data-open-diag]");
  if (!b || b.closest(".model-card")) return; // os cartões de Meus modelos têm o próprio tratamento
  if (b.dataset.openDiag !== undefined) return desktop?.openDiag ? desktop.openDiag() : toast(t("Disponível no app desktop."));
  try {
    if (b.dataset.unloadMain !== undefined) await post("/api/unload", {});
    else if (b.dataset.unloadExtra) await post("/api/unload", { extra: b.dataset.unloadExtra });
    else if (b.dataset.unloadExtras !== undefined) await post("/api/unload", { extra: "all" });
    else if (b.dataset.unloadAll !== undefined) await post("/api/unload", { all: true });
    toast(t("Modelo descarregado"));
  } catch (err) { toast(err.message, 5000); }
  refreshStatus();
});

// ------------------------------------------------------------------ paleta de comandos (Ctrl+K)
const PAL = { items: [], sel: 0 };
const norm = s => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
function paletteItems() {
  const st = S.status || { models: [], chats: [] };
  const act = (icon, label, run, hint = "") => ({ icon, label: t(label), hint, run });
  const items = [
    act("➕", "Nova conversa", () => newChat(), "Ctrl+N"),
    ...Object.entries(MODE_NAMES).map(([k, v], i) => act(v.split(" ")[0], t("Modo") + " " + v.split(" ").slice(1).join(" "), () => !S.generating && setMode(k), "Ctrl+" + (i + 1))),
    act("🌐", S.web ? "Desligar a pesquisa na web" : "Ligar a pesquisa na web", () => setWeb(!S.web)),
    act("🧠", "Abrir Modelos", () => openModal("modelsModal")),
    act("⬇️", "Baixar modelos", () => { openModal("modelsModal"); switchTab("tabHF"); }),
    act("📚", "Abrir bases de conhecimento", () => openModal("kbModal")),
    act("🤖", "Abrir agentes e grupos", () => openModal("agentsModal")),
    act("⚙️", "Abrir Configurações", () => openModal("settingsModal")),
    act("💾", "Backup das conversas", () => openModal("backupModal")),
    act("▤", "Painel do sistema", () => setInspector(!$("#app").classList.contains("insp-open")), "Ctrl+I"),
    act("☰", "Mostrar/ocultar conversas", () => $("#app").classList.toggle("side-hidden"), "Ctrl+B"),
    act("⏏", "Descarregar todos os modelos", () => post("/api/unload", { all: true }).then(refreshStatus)),
    act("🩺", "Abrir relatório de diagnóstico", () => desktop?.openDiag?.()),
    act("⤓", "Exportar conversa (.md)", () => $("#exportBtn").click()),
  ];
  for (const m of st.models) items.push({ icon: "▶", label: t("Carregar {name}", { name: m.name }), hint: fmtSize(m.size), group: t("Modelos"),
    run: () => post("/api/load", { model: m.path }).then(() => { $("#modelSelect").value = m.path; toast(t("Carregando modelo...")); refreshStatus(); }) });
  for (const c of (st.chats || []).slice(0, 200)) items.push({ icon: "💬", label: c.title || t("Sem título"), group: t("Conversas"),
    run: async () => { if (S.generating) return toast(t("Aguarde terminar ou clique em Parar.")); S.chat = await api("/api/chats/" + c.id); renderMessages(); renderChatList(); } });
  return items;
}
function renderPalette() {
  const words = norm($("#paletteInput").value).split(/\s+/).filter(Boolean);
  const all = paletteItems();
  PAL.items = (words.length ? all.filter(x => words.every(w => norm(x.label + " " + (x.group || "")).includes(w))) : all.filter(x => !x.group || x.group === t("Modelos"))).slice(0, 60);
  PAL.sel = Math.min(PAL.sel, Math.max(0, PAL.items.length - 1));
  $("#paletteList").innerHTML = PAL.items.length ? PAL.items.map((x, i) => `<div class="pal-item ${i === PAL.sel ? "sel" : ""}" data-i="${i}">
      <span class="pal-ic">${x.icon}</span><span class="pal-label">${esc(x.label)}</span>${x.group ? `<small class="muted">${esc(x.group)}</small>` : ""}${x.hint ? `<kbd>${esc(x.hint)}</kbd>` : ""}</div>`).join("")
    : `<p class="muted pal-empty">${t("Nada encontrado.")}</p>`;
  $("#paletteList .sel")?.scrollIntoView({ block: "nearest" });
}
function openPalette() { $("#palette").hidden = false; $("#paletteInput").value = ""; PAL.sel = 0; renderPalette(); $("#paletteInput").focus(); }
function closePalette() { $("#palette").hidden = true; }
function runPalette(i) { const x = PAL.items[i]; closePalette(); if (x) Promise.resolve(x.run()).catch(err => toast(err.message, 5000)); }
$("#paletteBtn").onclick = $("#paletteTop").onclick = openPalette;
$("#paletteInput").addEventListener("input", () => { PAL.sel = 0; renderPalette(); });
$("#paletteInput").addEventListener("keydown", e => {
  if (e.key === "ArrowDown") { e.preventDefault(); PAL.sel = Math.min(PAL.items.length - 1, PAL.sel + 1); renderPalette(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); PAL.sel = Math.max(0, PAL.sel - 1); renderPalette(); }
  else if (e.key === "Enter") { e.preventDefault(); runPalette(PAL.sel); }
  else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closePalette(); }
});
$("#paletteList").addEventListener("click", e => { const it = e.target.closest(".pal-item"); if (it) runPalette(+it.dataset.i); });
$("#palette").addEventListener("mousedown", e => { if (e.target.id === "palette") closePalette(); });

// ------------------------------------------------------------------ atalhos de teclado
document.addEventListener("keydown", e => {
  if (!e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === "k") { e.preventDefault(); $("#palette").hidden ? openPalette() : closePalette(); }
  else if (["1", "2", "3", "4"].includes(k) && !S.generating) { e.preventDefault(); setMode(Object.keys(MODE_NAMES)[+k - 1]); }
  else if (k === "b") { e.preventDefault(); $("#app").classList.toggle("side-hidden"); }
  else if (k === "i") { e.preventDefault(); setInspector(!$("#app").classList.contains("insp-open")); }
  else if (k === "n" && !e.shiftKey) { e.preventDefault(); if (!S.generating) newChat(); }
}, true);

// ------------------------------------------------------------------ travamentos da janela
// Tarefas que prendem a janela por mais de 2 s vão para o relatório de diagnóstico (ajuda a achar a causa).
try {
  new PerformanceObserver(list => {
    for (const en of list.getEntries()) if (en.duration > 2000)
      desktop?.diag?.(`tarefa longa de ${Math.round(en.duration)} ms (modo ${S.mode}, ${S.chat?.messages.length || 0} mensagens, gerando=${S.generating})`);
  }).observe({ type: "longtask", buffered: false });
} catch {}

setInspector(ls("insp", "0") === "1");
renderModeTag();
