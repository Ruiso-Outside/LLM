"use strict";
// Estúdio de treino: tela própria para criar conjuntos de dados, treinar (LoRA/QLoRA) e acompanhar tudo ao vivo.
// Carregado depois do app.js e do workspace.js.

const ST = { status: null, tab: "dash", run: null, runId: ls("stRun", ""), ds: ls("stDs", ""), exFilter: "", exQ: "", exOffset: 0,
  examples: null, editing: null, base: "", preset: "balanced", timer: null, from: "new", parent: "", parentFolder: "" };
const fmtBig = n => n == null ? "—" : n >= 1e9 ? (n / 1e9).toFixed(2) + " B" : n >= 1e6 ? (n / 1e6).toFixed(1) + " M" : n >= 1e3 ? (n / 1e3).toFixed(1) + " k" : String(Math.round(n));
const fmtGB = b => b == null ? "—" : (b / 2 ** 30).toFixed(2) + " GB";
const fmtDur = s => { if (s == null || !isFinite(s)) return "—"; s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return h ? `${h}h ${m}min` : m ? `${m}min ${x}s` : `${x}s`; };
const num = (v, d = 4) => v == null ? "—" : (+v).toPrecision(d).replace(/\.?0+$/, "");
const PRESETS = {
  fast: { label: "⚡ Rápido", lora_r: 8, lora_alpha: 16, epochs: 1, lr: 2e-4, max_len: 1024, grad_accum: 4 },
  balanced: { label: "⚖️ Equilibrado", lora_r: 16, lora_alpha: 32, epochs: 2, lr: 2e-4, max_len: 2048, grad_accum: 4 },
  quality: { label: "💎 Qualidade", lora_r: 32, lora_alpha: 64, epochs: 3, lr: 1e-4, max_len: 4096, grad_accum: 8 },
};
const STATE_LABEL = { starting: "iniciando", loading: "carregando", training: "treinando", done: "concluído", stopped: "parado",
  error: "erro", exporting: "exportando", exported: "exportado" };

// ------------------------------------------------------------------ abrir / fechar / abas
function openStudio() {
  document.body.classList.add("studio-open"); $("#studio").hidden = false; $("#studioBtn").classList.add("on");
  $$("#modes button").forEach(b => b.classList.remove("on"));
  refreshStudio(true); clearInterval(ST.timer); ST.timer = setInterval(refreshStudio, 1500);
}
function closeStudio() {
  document.body.classList.remove("studio-open"); $("#studio").hidden = true; $("#studioBtn").classList.remove("on");
  clearInterval(ST.timer); setMode(S.mode);
}
$("#studioBtn").onclick = () => document.body.classList.contains("studio-open") ? closeStudio() : openStudio();
$("#studioClose").onclick = closeStudio;
$("#modes").addEventListener("click", () => { if (document.body.classList.contains("studio-open")) closeStudio(); }, true);
function stTab(tab) {
  ST.tab = tab; $$(".st-tabs button").forEach(b => b.classList.toggle("on", b.dataset.stTab === tab));
  $$(".st-pane").forEach(p => p.classList.toggle("on", p.dataset.stPane === tab)); renderStudio(true);
}
$(".st-tabs").onclick = e => { const b = e.target.closest("[data-st-tab]"); if (b) stTab(b.dataset.stTab); };

// ------------------------------------------------------------------ atualização periódica
async function refreshStudio(full = false) {
  try { ST.status = await api("/api/train/status"); } catch { return; }
  const st = ST.status;
  if (st.active) ST.runId = st.active;
  if (!ST.runId && st.runs.length) ST.runId = st.runs[0].id;
  if (ST.runId) {
    const since = ST.run && ST.run.id === ST.runId ? ST.run.n_steps || ST.run.steps.length : 0;
    try {
      const r = await api(`/api/train/run?id=${ST.runId}&since=${since}`);
      if (since && ST.run?.id === r.id) { const steps = ST.run.steps.concat(r.steps); ST.run = { ...r, steps }; }
      else ST.run = r;
    } catch { ST.run = null; ST.runId = ""; }
  }
  if (!ST.ds && st.datasets.length) ST.ds = st.datasets[0].id;
  renderStudio(full);
}
function renderStudio(full) {
  const st = ST.status; if (!st) return;
  const g = st.gpu;
  $("#stGpu").innerHTML = g ? `<span>🎮 <b>${(g.vram_used / 1024).toFixed(1)}</b>/${(g.vram_total / 1024).toFixed(0)} GB</span><span>⚙️ <b>${g.util}%</b></span><span>🌡️ <b>${g.temp}°C</b></span><span>⚡ <b>${Math.round(g.power)} W</b></span>` : "";
  const task = (S.status?.tasks || []).find(x => x.status === "running" && /treino|Ambiente de treino|exemplos de treino/i.test(x.label));
  const tb = $("#stTask"); tb.hidden = !task;
  if (task) tb.innerHTML = `<b>${esc(task.label)}</b> · ${esc(task.detail || "")}${task.total ? `<div class="bar"><div style="width:${Math.min(100, task.done / task.total * 100)}%"></div></div>` : ""}`;
  if (ST.tab === "dash") renderDash();
  if (ST.tab === "runs") renderRuns();
  if (ST.tab === "env") renderEnv();
  if (full && ST.tab === "data") renderData();
  if (full && ST.tab === "new") renderNew();
}

// ------------------------------------------------------------------ gráficos (SVG, sem bibliotecas)
function lineChart(title, series, opts = {}) {
  const W = 600, H = 150, P = { l: 46, r: 10, t: 8, b: 18 };
  const all = series.flatMap(s => s.points.filter(p => p[1] != null && isFinite(p[1])));
  const legend = series.map(s => { const last = s.points.at(-1); return `<span><i style="background:${s.color}"></i>${esc(s.name)}${last ? ` <b>${(opts.fmt || num)(last[1])}</b>` : ""}</span>`; }).join("");
  if (all.length < 2) return `<div class="chart"><div class="chart-h"><b>${esc(title)}</b><div class="chart-legend">${legend}</div></div><div class="empty-c">${t("Aguardando dados...")}</div></div>`;
  let x0 = Math.min(...all.map(p => p[0])), x1 = Math.max(...all.map(p => p[0])), y0 = Math.min(...all.map(p => p[1])), y1 = Math.max(...all.map(p => p[1]));
  if (opts.zero) y0 = Math.min(0, y0);
  if (y1 === y0) { y1 += 1; y0 -= opts.zero ? 0 : 1; }
  if (x1 === x0) x1 += 1;
  const X = x => P.l + (x - x0) / (x1 - x0) * (W - P.l - P.r), Y = y => P.t + (1 - (y - y0) / (y1 - y0)) * (H - P.t - P.b);
  const grid = [0, .5, 1].map(f => { const v = y0 + (y1 - y0) * f, y = Y(v); return `<line x1="${P.l}" x2="${W - P.r}" y1="${y}" y2="${y}" stroke="#ffffff10"/><text x="${P.l - 6}" y="${y + 4}" text-anchor="end" fill="#7d8478" font-size="10">${(opts.fmt || num)(v)}</text>`; }).join("");
  const lines = series.map(s => {
    let pts = s.points.filter(p => p[1] != null && isFinite(p[1]));
    if (pts.length > 400) { const k = Math.ceil(pts.length / 400); pts = pts.filter((_, i) => i % k === 0 || i === pts.length - 1); }
    if (!pts.length) return "";
    const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
    const area = s.fill ? `<path d="${d}L${X(pts.at(-1)[0]).toFixed(1)},${H - P.b}L${X(pts[0][0]).toFixed(1)},${H - P.b}Z" fill="${s.color}" opacity=".10"/>` : "";
    const dots = s.dots ? pts.map(p => `<circle cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="2.6" fill="${s.color}"/>`).join("") : "";
    return area + `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="1.8" style="filter:drop-shadow(0 0 3px ${s.color}88)"/>` + dots;
  }).join("");
  const xl = `<text x="${P.l}" y="${H - 4}" fill="#7d8478" font-size="10">${(opts.xfmt || (v => v))(x0)}</text><text x="${W - P.r}" y="${H - 4}" text-anchor="end" fill="#7d8478" font-size="10">${(opts.xfmt || (v => v))(x1)}</text>`;
  return `<div class="chart"><div class="chart-h"><b>${esc(title)}</b><div class="chart-legend">${legend}</div></div><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${grid}${lines}${xl}</svg></div>`;
}

// ------------------------------------------------------------------ Painel
const kpi = (label, value, sub = "", cls = "") => `<div class="kpi ${cls}"><small>${esc(t(label))}</small><b title="${esc(String(value))}">${value}</b>${sub ? `<span title="${esc(sub)}">${sub}</span>` : ""}</div>`;
function renderDash() {
  const r = ST.run, box = $("#stDash");
  if (!r) {
    const env = ST.status.env;
    box.innerHTML = `<div class="st-card hi"><b style="font-size:16px">${t("Treine uma IA só sua")}</b>
      <p class="muted" style="margin:0">${t("1) Instale o ambiente (aba Ambiente). 2) Monte um dataset de exemplos (aba Dados): importe conversas, gere exemplos a partir das suas pastas de código e revise. 3) Escolha um modelo base pequeno e treine (aba Nova run). O resultado vira um modelo em Meus modelos.")}</p>
      <div class="st-row">${env.installed ? "" : `<button class="st-btn" data-st-go="env">${t("Instalar o ambiente")}</button>`}<button class="btn" data-st-go="data">${t("Montar dados")}</button><button class="btn" data-st-go="new">${t("Nova run")}</button></div></div>`;
    return;
  }
  const steps = r.steps || [], evals = r.evals || [], gpu = r.gpu || [];
  const s = r.setup || {}, res = r.result || {}, ex = r.export || {};
  // execuções antigas podem não ter o "último passo" salvo: usa o último ponto da série
  const l = r.last?.step ? r.last : steps.length ? { ...steps.at(-1), total_steps: s.total_steps, tokens: null } : {};
  const pct = l.total_steps ? l.step / l.total_steps * 100 : 0;
  const running = ["starting", "loading", "training", "exporting"].includes(r.state);
  const lastG = gpu.at(-1) || {};
  const peakPower = gpu.length ? Math.max(...gpu.map(g => g.power)) : null, maxTemp = gpu.length ? Math.max(...gpu.map(g => g.temp)) : null;
  const avgUtil = gpu.length ? gpu.reduce((a, g) => a + g.util, 0) / gpu.length : null;
  const firstLoss = steps[0]?.loss, bestEval = evals.length ? Math.min(...evals.map(e => e.eval_loss)) : null, lastEval = evals.at(-1);
  const html = `
    <div class="st-row" style="justify-content:space-between">
      <div><b style="font-size:18px">${esc(r.name || "")}</b> <span class="st-state ${r.state}">${t(STATE_LABEL[r.state] || r.state)}</span>
        <div class="muted small-note">${esc(r.base_repo || "")} · ${t("dados")}: ${esc(r.dataset || "")}</div></div>
      <div class="st-row">${running && r.state !== "exporting" ? `<button class="btn" data-st-stop>${t("Parar e salvar")}</button><button class="btn danger" data-st-kill>${t("Forçar parada")}</button>` : ""}
        <select class="input small-input" id="stRunPick">${ST.status.runs.map(x => `<option value="${x.id}" ${x.id === r.id ? "selected" : ""}>${esc(x.name || x.id)} · ${t(STATE_LABEL[x.state] || x.state)}</option>`).join("")}</select></div>
    </div>
    ${r.error ? `<div class="warn-box" style="margin-top:10px">${esc(r.error)}</div>` : ""}
    <div class="st-sec">${t("Progresso")}</div>
    <div class="st-grid">
      ${kpi("Passo", l.step ? `${l.step} / ${l.total_steps}` : "—", `<div class="st-progress"><div style="width:${pct}%"></div></div>`, "hi")}
      ${kpi("Época", l.epoch != null ? (+l.epoch).toFixed(2) : "—", r.cfg ? t("de {n}", { n: r.cfg.epochs }) : "")}
      ${kpi("Loss (treino)", num(l.loss), firstLoss ? t("início: {v}", { v: num(firstLoss) }) : "", "hi")}
      ${kpi("Loss (avaliação)", lastEval ? num(lastEval.eval_loss) : "—", bestEval != null ? t("melhor: {v}", { v: num(bestEval) }) : "")}
      ${kpi("Perplexidade", lastEval ? num(lastEval.ppl, 4) : "—", t("menor = melhor"))}
      ${kpi("Taxa de aprendizado", l.lr != null ? (+l.lr).toExponential(2) : "—", r.cfg ? t("máx.: {v}", { v: (+r.cfg.lr).toExponential(1) }) : "")}
      ${kpi("Norma do gradiente", num(l.grad_norm), t("estabilidade do treino"))}
      ${kpi("Tempo", fmtDur(l.elapsed_s ?? res.duration_s), running && l.eta_s != null ? t("faltam {v}", { v: fmtDur(l.eta_s) }) : "")}
    </div>
    <div class="st-sec">${t("Modelo e pesos")}</div>
    <div class="st-grid">
      ${kpi("Parâmetros totais", fmtBig(s.total_params), esc(s.quant || ""))}
      ${kpi("Treináveis (LoRA)", fmtBig(s.trainable_params), s.trainable_pct != null ? t("{p}% do modelo", { p: s.trainable_pct }) : "", "hi")}
      ${kpi("LoRA r / α", s.lora_r ? `${s.lora_r} / ${s.lora_alpha}` : "—", s.lora_r ? t("escala α/r = {v}", { v: (s.lora_alpha / s.lora_r).toFixed(2) }) : "")}
      ${kpi("Camadas adaptadas", s.target_modules ? s.target_modules.length : "—", (s.target_modules || []).join(", "))}
      ${kpi("Precisão de cálculo", esc(s.compute_dtype || "—"), s.max_len ? t("contexto máx.: {n}", { n: s.max_len }) : "")}
      ${kpi("Pesos do adaptador", res.adapter_size ? fmtSize(res.adapter_size) : "—", res.adapter_size ? t("salvo em safetensors") : t("ao terminar"))}
    </div>
    <div class="st-sec">${t("Dados")}</div>
    <div class="st-grid">
      ${kpi("Exemplos", s.train_examples != null ? `${s.train_examples} + ${s.eval_examples}` : "—", t("treino + avaliação"))}
      ${kpi("Tokens de treino", fmtBig(s.train_tokens), t("por época"))}
      ${kpi("Tokens processados", fmtBig(l.tokens), "")}
      ${kpi("Velocidade", l.tok_s != null ? `${Math.round(l.tok_s)} tok/s` : "—", l.step_time ? t("{s} s por passo", { s: l.step_time }) : "")}
    </div>
    <div class="st-sec">${t("Hardware e consumo")}</div>
    <div class="st-grid">
      ${kpi("VRAM do treino", fmtGB(l.mem_alloc), l.mem_peak ? t("pico: {v} · reservado: {r}", { v: fmtGB(l.mem_peak), r: fmtGB(l.mem_reserved) }) : "", l.mem_peak && s.vram_total && l.mem_peak / s.vram_total > .92 ? "warn" : "")}
      ${kpi("VRAM da placa", lastG.vram_used != null ? `${(lastG.vram_used / 1024).toFixed(1)} GB` : "—", lastG.vram_total ? t("de {v} GB", { v: (lastG.vram_total / 1024).toFixed(0) }) : "")}
      ${kpi("Uso da GPU", lastG.util != null ? `${lastG.util}%` : "—", avgUtil != null ? t("média: {v}%", { v: avgUtil.toFixed(0) }) : "")}
      ${kpi("Temperatura", lastG.temp != null ? `${lastG.temp} °C` : "—", maxTemp != null ? t("máx.: {v} °C", { v: maxTemp }) : "", lastG.temp > 83 ? "warn" : "")}
      ${kpi("Consumo", lastG.power != null ? `${Math.round(lastG.power)} W` : "—", peakPower != null ? t("pico: {v} W · limite: {l} W", { v: Math.round(peakPower), l: Math.round(lastG.power_limit || 0) }) : "")}
      ${kpi("Energia gasta", r.energy_wh != null ? `${(+r.energy_wh).toFixed(1)} Wh` : "—", r.energy_wh ? t("≈ {v} kWh", { v: (r.energy_wh / 1000).toFixed(3) }) : "")}
      ${kpi("Clock da GPU", lastG.clock ? `${lastG.clock} MHz` : "—", esc(s.device || ""))}
    </div>
    <div class="st-sec">${t("Gráficos")}</div>
    <div class="charts">
      ${lineChart(t("Loss"), [{ name: t("treino"), color: "#a3e635", points: steps.map(x => [x.step, x.loss]), fill: true },
        { name: t("avaliação"), color: "#22d3ee", points: evals.map(e => [e.step, e.eval_loss]), dots: true }], { xfmt: v => t("passo {n}", { n: v }) })}
      ${lineChart(t("Taxa de aprendizado"), [{ name: "lr", color: "#e879f9", points: steps.map(x => [x.step, x.lr]) }], { fmt: v => (+v).toExponential(1), zero: true })}
      ${lineChart(t("Norma do gradiente"), [{ name: "grad", color: "#fbbf24", points: steps.map(x => [x.step, x.grad_norm]) }])}
      ${lineChart(t("Velocidade (tokens/s)"), [{ name: "tok/s", color: "#38bdf8", points: steps.map(x => [x.step, x.tok_s]), fill: true }], { fmt: v => Math.round(v), zero: true })}
      ${lineChart(t("Memória da GPU (GB)"), [{ name: t("placa"), color: "#a3e635", points: gpu.map(x => [x.t, x.vram_used / 1024]), fill: true },
        { name: t("treino (pico)"), color: "#fb7185", points: steps.map(x => [x.elapsed_s, (x.mem_peak || 0) / 2 ** 30]) }], { fmt: v => (+v).toFixed(1), zero: true, xfmt: v => fmtDur(v) })}
      ${lineChart(t("Consumo (W) e temperatura (°C)"), [{ name: "W", color: "#fbbf24", points: gpu.map(x => [x.t, x.power]) },
        { name: "°C", color: "#fb7185", points: gpu.map(x => [x.t, x.temp]) }, { name: t("uso %"), color: "#22d3ee", points: gpu.map(x => [x.t, x.util]) }], { fmt: v => Math.round(v), zero: true, xfmt: v => fmtDur(v) })}
    </div>
    ${["done", "stopped", "exported", "exporting"].includes(r.state) || ex.stage ? exportCardHTML(r) : ""}
    ${accelCardHTML(r)}
    <div class="st-sec">${t("Registro")}</div>
    <div class="st-log">${(r.events || []).slice(-80).map(e => `<div>${new Date(e.t * 1000).toLocaleTimeString()} · ${esc(e.msg)}</div>`).join("") || "—"}</div>`;
  if (box.dataset.sig !== html) { const y = $(".st-body").scrollTop; box.innerHTML = html; box.dataset.sig = html; $(".st-body").scrollTop = y; }
}
function accelCardHTML(r) {
  if (r.draft_for) return `<div class="st-card"><b>⚡ ${t("Draft model de {n}", { n: esc(r.parent_name || "") })}</b>
    <p class="muted small-note">${t("Gere o modelo em Q8_0: ao terminar, ele é ligado automaticamente como draft model (speculative decoding) do modelo de origem (se ele já tiver sido gerado).")}</p></div>`;
  if (!r.has_adapter || !["done", "stopped", "exported"].includes(r.state)) return "";
  const busy = ST.status?.active;
  return `<div class="st-sec">⚡ ${t("Draft model (speculative decoding)")}</div><div class="st-card">
    <p>${t("Treina um modelo pequeno da mesma família ({b}) com os mesmos exemplos desta IA. Ele escreve um rascunho de vários tokens e a sua IA só confere: as respostas saem mais rápidas, com a mesma qualidade.", { b: esc((r.draft_base || "").split("/").pop() || "—") })}</p>
    <div class="st-row"><button class="st-btn" data-st-accel="${r.id}" ${r.draft_base && !busy ? "" : "disabled"}>⚡ ${t("Treinar draft model")}</button>
      <span class="muted small-note">${r.draft_base ? t("Leva bem menos tempo que o treino principal. Ocupa ~0,5 a 1 GB a mais de VRAM quando ativo.") : t("Não há modelo pequeno conhecido para esta família.")}</span></div>
    <span class="muted small-note">${t("Sem treinar nada, você também pode ligar o speculative decoding N-gram em Modelos (acelera muito edições de código).")}</span></div>`;
}

function exportCardHTML(r) {
  const ex = r.export || {}, res = r.result || {};
  if (ex.stage === "done") return `<div class="st-sec">${t("Modelo final")}</div><div class="st-card hi">
    <div class="st-grid">${kpi("Arquivo", esc((ex.out_path || "").split(/[\\/]/).pop()), "", "hi")}${kpi("Tamanho", fmtSize(ex.size || 0))}
      ${kpi("Parâmetros finais", fmtBig(ex.params), t("LoRA já juntado ao modelo"))}${kpi("Quantização", esc(r.cfg?.quant_type || ""))}</div>
    <div class="st-row"><button class="st-btn" data-st-use="${esc((ex.out_path || "").replace(/\\/g, "/").split("/models/").pop())}">${t("Usar no modo Codex")}</button>
      <span class="muted small-note">${t("O modelo já aparece em Modelos → Meus modelos.")}</span></div></div>`;
  if (r.state === "exporting") return `<div class="st-sec">${t("Modelo final")}</div><div class="st-card"><span class="spin"></span> ${esc(t({ start: "Preparando...", merge: "Juntando o LoRA ao modelo base...", convert: "Convertendo para GGUF...", quantize: "Quantizando..." }[ex.stage] || "Exportando..."))}</div>`;
  if (!res.adapter_dir && r.state !== "done" && r.state !== "stopped") return "";
  return `<div class="st-sec">${t("Modelo final")}</div><div class="st-card hi">
    <div class="st-grid">${kpi("Loss final", num(res.final_loss), "", "hi")}${kpi("Melhor avaliação", num(res.best_eval))}${kpi("Duração", fmtDur(res.duration_s))}${kpi("Adaptador LoRA", fmtSize(res.adapter_size || 0))}</div>
    <div class="st-row"><input class="input small-input" id="stExpName" value="${esc((r.name || "minha-ia") + ((r.generation || 1) > 1 ? "-v" + r.generation : ""))}" style="max-width:240px">
      <select class="input small-input" id="stExpQuant">${r.draft_for ? `<option value="Q8_0">Q8_0 (${t("recomendado para draft model")})</option>` : ""}<option value="Q4_K_M">Q4_K_M (${t("leve, recomendado")})</option><option value="Q5_K_M">Q5_K_M</option><option value="Q6_K">Q6_K</option><option value="Q8_0">Q8_0 (${t("quase sem perda")})</option><option value="F16">F16 (${t("sem quantizar")})</option></select>
      <button class="st-btn" data-st-export>${t("Merge + exportar GGUF")}</button></div>
    <span class="muted small-note">${t("Junta o LoRA ao modelo base, converte para GGUF e quantiza. Usa a RAM (o modelo base em bf16) e leva alguns minutos.")}</span></div>`;
}

// ------------------------------------------------------------------ Execuções
function renderRuns() {
  const runs = ST.status.runs, box = $("#stRuns");
  const html = runs.length ? runs.map(r => `<div class="run-row" data-st-open="${r.id}">
      <div><b>${esc(r.name || r.id)}${(r.generation || 1) > 1 ? ` <span class="gen-tag">v${r.generation}</span>` : ""}${r.draft_for ? ` <span class="gen-tag">⚡</span>` : ""}</b><small>${esc(r.base_repo || "")}${r.parent_name ? " · " + esc(t("continua de {n}", { n: r.parent_name })) : ""}</small></div>
      <div><span class="st-state ${r.state}">${t(STATE_LABEL[r.state] || r.state)}</span><small>${r.started ? new Date(r.started * 1000).toLocaleString() : ""}</small></div>
      <div>${num(r.last?.loss)}<small>${t("loss")}</small></div>
      <div>${r.last?.step ? `${r.last.step}/${r.last.total_steps}` : "—"}<small>${t("passos")}</small></div>
      <div>${r.energy_wh ? (+r.energy_wh).toFixed(1) + " Wh" : "—"}<small>${t("energia")}</small></div>
      <button class="icon-btn" data-st-del="${r.id}" title="${esc(t("Apagar"))}">🗑️</button></div>`).join("")
    : `<p class="muted">${t("Nenhuma run ainda. Crie uma na aba Nova run.")}</p>`;
  if (box.dataset.sig !== html) { box.innerHTML = html; box.dataset.sig = html; }
}

// ------------------------------------------------------------------ Ambiente
function renderEnv() {
  const e = ST.status.env, p = e.probe || {}, box = $("#stEnv");
  const busy = (S.status?.tasks || []).some(x => x.status === "running" && /Ambiente de treino/.test(x.label));
  const html = `<div class="st-card ${e.installed ? "hi" : ""}">
    <b style="font-size:15px">${e.installed ? "✅ " + t("Ambiente de treino pronto") : t("Ambiente de treino não instalado")}</b>
    <p class="muted small-note" style="margin:0">${t("Instala uma vez, dentro do app (engine/train): Python 3.12 portátil, PyTorch com CUDA, transformers, peft (LoRA), bitsandbytes (4 bits) e os conversores do llama.cpp. Cerca de 5 a 6 GB. Os modelos base são baixados do Hugging Face na primeira execução.")}</p>
    ${p.torch ? `<div class="st-grid">${kpi("PyTorch", esc(p.torch || "—"), p.cuda_version ? "CUDA " + esc(p.cuda_version) : "")}${kpi("Placa", esc(p.device || "—"), p.capability ? t("arquitetura {c}", { c: p.capability }) : "")}
      ${kpi("VRAM", p.vram_gb ? p.vram_gb + " GB" : "—", "")}${kpi("4 bits (bitsandbytes)", p.bnb ? "✅" : "❌", esc(p.bnb_error || ""))}${kpi("Python", esc(p.python || "—"), "")}${kpi("Espaço usado", fmtSize(e.size || 0), "")}</div>` : ""}
    ${p.error ? `<div class="warn-box">${esc(p.error)}</div>` : ""}
    <div class="st-row"><button class="st-btn" data-st-install ${busy ? "disabled" : ""}>${e.installed ? t("Reinstalar / atualizar") : t("Instalar o ambiente de treino")}</button>
      ${e.installed ? `<button class="btn danger" data-st-uninstall>${t("Remover")}</button>` : ""}</div></div>`;
  if (box.dataset.sig !== html) { box.innerHTML = html; box.dataset.sig = html; }
}

// ------------------------------------------------------------------ Dados
async function loadExamples() {
  if (!ST.ds) { ST.examples = null; return; }
  try { ST.examples = await api(`/api/train/examples?id=${ST.ds}&status=${ST.exFilter}&offset=${ST.exOffset}&limit=40&q=${encodeURIComponent(ST.exQ)}`); }
  catch { ST.examples = null; }
}
async function renderData() {
  await loadExamples();
  const dss = ST.status.datasets, d = dss.find(x => x.id === ST.ds), box = $("#stData");
  const items = ST.examples?.items || [];
  box.innerHTML = `<div class="st-cols">
    <div><div class="st-row" style="margin-bottom:10px"><button class="st-btn" data-st-newds>+ ${t("Novo dataset")}</button></div>
      ${dss.map(x => `<div class="ds-item ${x.id === ST.ds ? "sel" : ""}" data-st-ds="${x.id}"><b>${esc(x.name)}</b><small>${t("{a} aprovados · {p} pendentes · ~{t} tokens", { a: x.approved, p: x.pending, t: fmtBig(x.tokens) })}</small></div>`).join("")
        || `<p class="muted small-note">${t("Nenhum dataset ainda.")}</p>`}</div>
    <div>${d ? `
      <div class="st-card">
        <div class="st-row"><input class="input" id="stDsName" value="${esc(d.name)}" style="max-width:300px"><button class="btn small" data-st-dssave>${t("Salvar")}</button>
          <span class="spacer"></span><a class="btn small" href="/api/train/export_dataset?id=${d.id}">${t("Exportar JSONL")}</a><button class="btn small danger" data-st-dsdel>${t("Apagar dataset")}</button></div>
        <label>${t("System prompt (vai em todos os exemplos)")}<textarea class="input" id="stDsSystem" rows="2" placeholder="${esc(t("Ex.: Você é um especialista em Unreal Engine 5 e C++. Responda com código compilável e explique as macros UCLASS/UPROPERTY."))}">${esc(d.system || "")}</textarea></label>
        <div class="st-grid">${kpi("Exemplos", d.n)}${kpi("Aprovados", d.approved, "", "hi")}${kpi("Pendentes", d.pending, t("revise antes de treinar"), d.pending ? "warn" : "")}${kpi("Tokens aprovados", fmtBig(d.tokens))}</div>
      </div>
      <div class="st-sec">${t("Adicionar exemplos")}</div>
      <div class="st-card"><div class="st-row">
        <button class="btn" data-st-gen>🤖 ${t("Gerar a partir de pastas")}</button>
        <button class="btn" data-st-impchats>💬 ${t("Importar todas as conversas")}</button>
        <label class="btn" style="flex-direction:row">📄 ${t("Importar JSONL")}<input type="file" id="stJsonl" accept=".jsonl,.json,.txt" hidden></label>
        <button class="btn" data-st-add>✍️ ${t("Escrever um exemplo")}</button></div>
        <div id="stGenForm" hidden><div class="grid">
          <label class="full">${t("Pastas (ex.: a pasta Source do projeto da Unreal, documentação)")}<div class="st-row"><span id="stGenFolders" class="muted small-note">${t("nenhuma")}</span><button class="btn small" data-st-addfolder>+ ${t("Pasta")}</button></div></label>
          <label>${t("Assunto")}<input class="input" id="stGenTopic" value="Unreal Engine 5 e C++"></label>
          <label>${t("Exemplos por chunk")}<input class="input" id="stGenPer" type="number" min="1" max="8" value="3"></label>
          <label>${t("Máximo de chunks")}<input class="input" id="stGenMax" type="number" min="1" max="2000" value="40"></label>
          <label class="full">${t("Orientação extra (opcional)")}<input class="input" id="stGenExtra" placeholder="${esc(t("Ex.: foque em replicação de rede e GAS"))}"></label></div>
          <p class="muted small-note">${t("Usa o modelo carregado no topo para criar perguntas e respostas a partir dos arquivos. Os exemplos entram como pendentes para você revisar. Um modelo maior (ex.: 27B) gera dados melhores.")}</p>
          <div class="st-row"><button class="st-btn" data-st-genrun>${t("Gerar exemplos")}</button></div></div>
      </div>
      <div class="st-sec">${t("Exemplos")}</div>
      <div class="st-row" style="margin-bottom:10px">
        ${["", "pending", "approved", "rejected"].map(f => `<button class="preset ${ST.exFilter === f ? "sel" : ""}" data-st-filter="${f}">${t({ "": "Todos", pending: "Pendentes", approved: "Aprovados", rejected: "Rejeitados" }[f])}</button>`).join("")}
        <input class="input small-input" id="stExQ" placeholder="${esc(t("Buscar..."))}" value="${esc(ST.exQ)}" style="max-width:220px">
        <span class="spacer"></span>${items.some(x => x.status === "pending") ? `<button class="btn small" data-st-approveall>${t("Aprovar os pendentes desta página")}</button>` : ""}</div>
      ${ST.editing === "new" ? exEditHTML({ id: "", messages: [] }) : ""}
      ${items.map(x => ST.editing === x.id ? exEditHTML(x) : exHTML(x)).join("") || `<p class="muted">${t("Nenhum exemplo aqui.")}</p>`}
      ${ST.examples && ST.examples.total > ST.exOffset + 40 || ST.exOffset ? `<div class="st-row"><button class="btn small" data-st-page="-1" ${ST.exOffset ? "" : "disabled"}>←</button><span class="muted">${ST.exOffset + 1}–${Math.min(ST.exOffset + 40, ST.examples.total)} / ${ST.examples.total}</span><button class="btn small" data-st-page="1" ${ST.examples.total > ST.exOffset + 40 ? "" : "disabled"}>→</button></div>` : ""}
    ` : `<div class="st-card"><p class="muted" style="margin:0">${t("Crie um dataset para começar. Cada exemplo é um pedido e a resposta ideal: é com eles que a IA aprende o seu jeito.")}</p></div>`}</div></div>`;
  ST.genFolders = ST.genFolders || [];
}
const msgOf = (x, role) => (x.messages.find(m => m.role === role) || {}).content || "";
function exHTML(x) {
  return `<div class="ex ${x.status}" data-ex="${x.id}"><div class="q">${esc(msgOf(x, "user"))}</div><div class="a">${esc(msgOf(x, "assistant"))}</div>
    <div class="meta"><span>${esc(x.source || "")}</span><span class="spacer"></span>
      ${x.status !== "approved" ? `<button class="btn small" data-st-rev="approved">✓ ${t("Aprovar")}</button>` : ""}${x.status !== "rejected" ? `<button class="btn small" data-st-rev="rejected">✗ ${t("Rejeitar")}</button>` : ""}
      <button class="btn small" data-st-edit>${t("Editar")}</button><button class="btn small danger" data-st-rev="delete">🗑️</button></div></div>`;
}
function exEditHTML(x) {
  return `<div class="ex approved" data-ex="${x.id}"><label>${t("Pedido")}<textarea class="input" id="stExU">${esc(msgOf(x, "user"))}</textarea></label>
    <label>${t("Resposta ideal")}<textarea class="input" id="stExA" rows="8">${esc(msgOf(x, "assistant"))}</textarea></label>
    <div class="meta"><span class="spacer"></span><button class="btn small" data-st-cancel>${t("Cancelar")}</button><button class="st-btn" data-st-saveex>${t("Salvar aprovado")}</button></div></div>`;
}

// ------------------------------------------------------------------ Nova execução
function renderNew() {
  const st = ST.status, box = $("#stNew"), p = PRESETS[ST.preset];
  if (!ST.base) ST.base = st.base_models[1]?.repo || "";
  const dss = st.datasets;
  box.innerHTML = `${st.env.installed ? "" : `<div class="warn-box" style="margin-bottom:12px">${t("Instale o ambiente de treino primeiro (aba Ambiente).")}</div>`}
    <div class="st-card">
      <div class="grid"><label>${t("Nome da IA")}<input class="input" id="stName" value="${esc(ls("stName", "IA Unreal"))}"></label>
        <label>${t("Dataset")}<select class="input" id="stDsPick">${dss.map(d => `<option value="${d.id}" ${d.id === ST.ds ? "selected" : ""}>${esc(d.name)} · ${t("{n} aprovados", { n: d.approved })}</option>`).join("") || `<option value="">${t("Crie um dataset na aba Dados")}</option>`}</select></label></div>
      <div class="st-sec" style="margin-top:4px">${t("Ponto de partida")}</div>
      <div class="preset-row"><button class="preset ${ST.from === "new" ? "sel" : ""}" data-st-from="new">✨ ${t("Do zero (modelo base)")}</button>
        <button class="preset ${ST.from === "continue" ? "sel" : ""}" data-st-from="continue">🔁 ${t("Continuar uma IA já treinada")}</button></div>
      ${ST.from === "continue" ? continueHTML(st) : `
      <div class="st-sec">${t("Modelo base")}</div>
      <div class="base-cards">${st.base_models.map(b => `<div class="base-card ${b.repo === ST.base ? "sel" : ""}" data-st-base="${esc(b.repo)}"><b>${esc(b.repo.split("/")[1])}</b>
        <small>${esc(b.params)} · ${t("baixa ~{d} GB · VRAM ~{v} GB", { d: b.download_gb, v: b.vram_gb })}</small><small>${esc(t(b.note))}</small></div>`).join("")}</div>
      <label>${t("Ou outro repositório do Hugging Face (formato safetensors)")}<input class="input" id="stBaseCustom" placeholder="org/modelo" value="${st.base_models.some(b => b.repo === ST.base) ? "" : esc(ST.base)}"></label>`}
      <div class="st-sec">${t("Preset")}</div>
      <div class="preset-row">${Object.entries(PRESETS).map(([k, v]) => `<button class="preset ${k === ST.preset ? "sel" : ""}" data-st-preset="${k}">${t(v.label)}</button>`).join("")}</div>
      <details><summary style="cursor:pointer;margin-top:6px">${t("Hiperparâmetros")}</summary>
        <div class="grid" style="margin-top:10px">
          <label>LoRA r <input class="input" id="stR" type="number" min="1" max="256" value="${p.lora_r}" ${ST.from === "continue" ? "disabled" : ""}><small class="muted">${t("tamanho do adaptador: maior aprende mais, ocupa mais")}</small></label>
          <label>LoRA alpha <input class="input" id="stA" type="number" min="1" max="512" value="${p.lora_alpha}" ${ST.from === "continue" ? "disabled" : ""}><small class="muted">${t("força do adaptador (normalmente 2×r)")}</small></label>
          <label>${t("Épocas")} <input class="input" id="stEp" type="number" min="0.1" max="20" step="0.1" value="${p.epochs}"><small class="muted">${t("quantas vezes passa pelos dados (demais = decora)")}</small></label>
          <label>${t("Taxa de aprendizado")} <input class="input" id="stLr" value="${p.lr}"></label>
          <label>${t("Contexto máximo (tokens)")} <input class="input" id="stLen" type="number" min="256" max="32768" value="${p.max_len}"></label>
          <label>${t("Acúmulo de gradiente")} <input class="input" id="stAcc" type="number" min="1" max="64" value="${p.grad_accum}"><small class="muted">${t("lote efetivo = lote × acúmulo")}</small></label>
          <label>${t("Lote")} <input class="input" id="stBs" type="number" min="1" max="16" value="1"></label>
          <label>LoRA dropout <input class="input" id="stDrop" type="number" min="0" max="0.5" step="0.01" value="0.05"></label>
          <label>${t("Avaliar a cada (passos)")} <input class="input" id="stEval" type="number" min="1" value="25"></label>
          <label>${t("Semente")} <input class="input" id="stSeed" type="number" value="42"></label>
          <label class="check"><input type="checkbox" id="st4b" checked> ${t("Carregar o modelo em 4 bits (QLoRA): usa bem menos VRAM")}</label>
          <label class="check"><input type="checkbox" id="stFree" checked> ${t("Descarregar os modelos do chat antes de treinar")}</label>
        </div></details>
      <div class="st-row"><button class="st-btn" data-st-start ${st.env.installed && !st.active ? "" : "disabled"}>🚀 ${t("Começar o treino")}</button>
        ${st.active ? `<span class="muted">${t("Já existe um treino rodando.")}</span>` : ""}</div>
    </div>`;
}

function continueHTML(st) {
  const done = st.runs.filter(r => r.has_adapter && !r.draft_for && !["starting", "loading", "training"].includes(r.state));
  if (!ST.parent && !ST.parentFolder && done[0]) ST.parent = done[0].id;
  return `<div class="base-cards" style="margin-top:10px">${done.map(r => `<div class="base-card ${!ST.parentFolder && r.id === ST.parent ? "sel" : ""}" data-st-parent="${r.id}">
      <b>${esc(r.name || r.id)} <span class="gen-tag">v${r.generation || 1}</span></b>
      <small>${esc((r.base_repo || "").split("/").pop())} · ${esc(r.dataset || "")}</small>
      <small>${r.started ? new Date(r.started * 1000).toLocaleDateString() : ""} · ${t("loss")} ${num(r.result?.final_loss ?? r.last?.loss)}</small></div>`).join("")
      || `<p class="muted">${t("Nenhum treino concluído ainda. Treine uma IA do zero primeiro, ou use a pasta de um adaptador LoRA.")}</p>`}</div>
    <div class="st-row"><button class="st-btn ghost" data-st-pfolder>📂 ${t("Usar a pasta de um adaptador LoRA")}</button>
      ${ST.parentFolder ? `<span class="base-card sel" style="cursor:default">${esc(ST.parentFolder)}</span>` : ""}</div>
    <label class="check"><input type="checkbox" id="stReplay" checked> ${t("Revisar também os exemplos dos treinos anteriores (recomendado: evita que a IA esqueça o que já aprendeu)")}</label>
    <small class="muted">${t("A IA continua com o mesmo modelo base e o mesmo tamanho de adaptador (LoRA r/alpha). Escolha no Dataset o conteúdo novo. Arquivos .gguf não podem ser treinados de novo: o treino continua a partir do adaptador LoRA salvo na run.")}</small>`;
}

// ------------------------------------------------------------------ ações
$("#studio").addEventListener("click", async e => {
  const el = e.target.closest("[data-st-go],[data-st-stop],[data-st-kill],[data-st-export],[data-st-use],[data-st-open],[data-st-del],[data-st-install],[data-st-uninstall],[data-st-ds],[data-st-newds],[data-st-dssave],[data-st-dsdel],[data-st-gen],[data-st-genrun],[data-st-addfolder],[data-st-impchats],[data-st-add],[data-st-filter],[data-st-rev],[data-st-edit],[data-st-cancel],[data-st-saveex],[data-st-approveall],[data-st-page],[data-st-base],[data-st-preset],[data-st-start],[data-st-from],[data-st-parent],[data-st-pfolder],[data-st-accel]");
  if (!el) return;
  const d = el.dataset, did = ST.ds;
  try {
    if (d.stGo) return stTab(d.stGo);
    if (d.stStop !== undefined) { await post("/api/train/stop", { id: ST.runId }); return toast(t("Parando... o que foi treinado até aqui será salvo.")); }
    if (d.stKill !== undefined) { if (confirm(t("Forçar a parada? O progresso deste treino pode ser perdido."))) await post("/api/train/stop", { id: ST.runId, force: true }); return; }
    if (d.stExport !== undefined) { await post("/api/train/export", { id: ST.runId, name: $("#stExpName").value, quant: $("#stExpQuant").value }); toast(t("Gerando o modelo...")); return refreshStudio(); }
    if (d.stUse) { const mm = { ...(S.status.settings.mode_models || {}), codex: d.stUse }; await api("/api/settings", { method: "PUT", body: { mode_models: mm } }); await refreshStatus(); return toast(t("Pronto: o modo Codex vai usar esse modelo.")); }
    if (d.stOpen && !e.target.closest("[data-st-del]")) { ST.runId = d.stOpen; lsSet("stRun", d.stOpen); ST.run = null; await refreshStudio(); return stTab("dash"); }
    if (d.stDel) { if (!confirm(t("Apagar esta run e os arquivos dela?"))) return; await post("/api/train/run/delete", { id: d.stDel }); if (ST.runId === d.stDel) { ST.runId = ""; ST.run = null; } return refreshStudio(); }
    if (d.stInstall !== undefined) { await post("/api/train/install"); toast(t("Instalando o ambiente de treino... acompanhe o progresso acima.")); return refreshStatus(); }
    if (d.stUninstall !== undefined) { if (!confirm(t("Remover o ambiente de treino (~5 GB)? Os datasets e as runs ficam."))) return; await post("/api/train/uninstall"); return refreshStudio(); }
    if (d.stDs) { ST.ds = d.stDs; lsSet("stDs", d.stDs); ST.exOffset = 0; ST.editing = null; await refreshStudio(); return renderData(); }
    if (d.stNewds !== undefined) { const name = prompt(t("Nome do dataset:"), t("Unreal Engine 5")); if (!name) return; const m = await post("/api/train/dataset/create", { name }); ST.ds = m.id; lsSet("stDs", m.id); await refreshStudio(); return renderData(); }
    if (d.stDssave !== undefined) { await post("/api/train/dataset/update", { id: did, name: $("#stDsName").value, system: $("#stDsSystem").value }); toast(t("Salvo")); await refreshStudio(); return renderData(); }
    if (d.stDsdel !== undefined) { if (!confirm(t("Apagar este dataset e todos os exemplos?"))) return; await post("/api/train/dataset/delete", { id: did }); ST.ds = ""; await refreshStudio(); return renderData(); }
    if (d.stGen !== undefined) { $("#stGenForm").hidden = !$("#stGenForm").hidden; return; }
    if (d.stAddfolder !== undefined) { const f = await desktop?.chooseFolder?.(); if (f) { ST.genFolders = [...new Set([...(ST.genFolders || []), f])]; $("#stGenFolders").textContent = ST.genFolders.join(" · "); } else if (!desktop) toast(t("Escolher pastas só funciona no app desktop.")); return; }
    if (d.stGenrun !== undefined) {
      if (!ST.genFolders?.length) return toast(t("Escolha pelo menos uma pasta."));
      if (S.status.engine.state !== "ready") return toast(t("Carregue um modelo no topo para gerar os exemplos."));
      await post("/api/train/dataset/generate", { id: did, folders: ST.genFolders, topic: $("#stGenTopic").value, per_chunk: +$("#stGenPer").value, max_chunks: +$("#stGenMax").value, extra: $("#stGenExtra").value });
      toast(t("Gerando exemplos... eles aparecem como pendentes.")); return refreshStatus();
    }
    if (d.stImpchats !== undefined) { const r = await post("/api/train/dataset/import_chats", { id: did }); toast(t("{n} exemplos importados das conversas", { n: r.added })); await refreshStudio(); return renderData(); }
    if (d.stAdd !== undefined) { ST.editing = "new"; return renderData(); }
    if (d.stFilter !== undefined) { ST.exFilter = d.stFilter; ST.exOffset = 0; return renderData(); }
    if (d.stPage) { ST.exOffset = Math.max(0, ST.exOffset + (+d.stPage) * 40); return renderData(); }
    if (d.stEdit !== undefined) { ST.editing = el.closest("[data-ex]").dataset.ex; return renderData(); }
    if (d.stCancel !== undefined) { ST.editing = null; return renderData(); }
    if (d.stSaveex !== undefined) { await post("/api/train/dataset/example", { id: did, example: { id: el.closest("[data-ex]").dataset.ex || undefined, user: $("#stExU").value, assistant: $("#stExA").value, status: "approved" } }); ST.editing = null; await refreshStudio(); return renderData(); }
    if (d.stRev) { await post("/api/train/dataset/review", { id: did, ids: [el.closest("[data-ex]").dataset.ex], status: d.stRev }); await refreshStudio(); return renderData(); }
    if (d.stApproveall !== undefined) { await post("/api/train/dataset/review", { id: did, ids: (ST.examples?.items || []).filter(x => x.status === "pending").map(x => x.id), status: "approved" }); await refreshStudio(); return renderData(); }
    if (d.stBase) { ST.base = d.stBase; $("#stBaseCustom").value = ""; $$(".base-card").forEach(c => c.classList.toggle("sel", c.dataset.stBase === ST.base)); return; }
    if (d.stPreset) { ST.preset = d.stPreset; return renderNew(); }
    if (d.stFrom) { ST.from = d.stFrom; return renderNew(); }
    if (d.stAccel) {
      const r = await post("/api/train/start", { draft_for: d.stAccel, free_gpu: true });
      ST.runId = r.id; ST.run = null; lsSet("stRun", r.id); toast(t("Treinando o draft model...")); await refreshStudio(); return stTab("dash");
    }
    if (d.stParent) {
      ST.parent = d.stParent; ST.parentFolder = "";
      const r = ST.status.runs.find(x => x.id === d.stParent);
      if (r?.name) $("#stName").value = r.name;  // mesma IA, nova versao
      const keep = $("#stName").value; renderNew(); $("#stName").value = keep; return;
    }
    if (d.stPfolder !== undefined) {
      if (!desktop) return toast(t("Escolher pastas só funciona no app desktop."));
      const f = await desktop.chooseFolder?.(); if (!f) return;
      ST.parentFolder = f; const keep = $("#stName").value; renderNew(); $("#stName").value = keep; return;
    }
    if (d.stStart !== undefined) {
      const cont = ST.from === "continue";
      const base = cont ? "" : $("#stBaseCustom").value.trim() || ST.base;
      if (cont && !ST.parent && !ST.parentFolder) return toast(t("Escolha qual IA continuar treinando."));
      if (!cont && !/^[\w.-]+\/[\w.-]+$/.test(base)) return toast(t("Escolha um modelo base válido (org/modelo)."));
      lsSet("stName", $("#stName").value);
      const cfg = { name: $("#stName").value, dataset_id: $("#stDsPick").value, base_repo: base, lora_r: +$("#stR").value, lora_alpha: +$("#stA").value,
        epochs: +$("#stEp").value, lr: +$("#stLr").value, max_len: +$("#stLen").value, grad_accum: +$("#stAcc").value, batch_size: +$("#stBs").value,
        lora_dropout: +$("#stDrop").value, eval_every: +$("#stEval").value, seed: +$("#stSeed").value, quant4bit: $("#st4b").checked, free_gpu: $("#stFree").checked };
      if (cont) Object.assign(cfg, ST.parentFolder ? { parent_adapter: ST.parentFolder } : { parent_run: ST.parent }, { replay: $("#stReplay").checked });
      const r = await post("/api/train/start", cfg);
      ST.runId = r.id; ST.run = null; lsSet("stRun", r.id); toast(t("Fine-tuning iniciado")); await refreshStudio(); return stTab("dash");
    }
  } catch (err) { toast(trText(err.message), 6000); }
});
$("#studio").addEventListener("change", async e => {
  if (e.target.id === "stRunPick") { ST.runId = e.target.value; ST.run = null; lsSet("stRun", ST.runId); return refreshStudio(); }
  if (e.target.id === "stJsonl" && e.target.files[0]) {
    try { const r = await post("/api/train/dataset/import_jsonl", { id: ST.ds, text: await e.target.files[0].text() }); toast(t("{n} exemplos importados", { n: r.added })); await refreshStudio(); renderData(); }
    catch (err) { toast(err.message, 6000); }
  }
});
$("#studio").addEventListener("keydown", e => { if (e.target.id === "stExQ" && e.key === "Enter") { ST.exQ = e.target.value; ST.exOffset = 0; renderData(); } });
