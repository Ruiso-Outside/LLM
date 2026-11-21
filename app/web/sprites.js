"use strict";
// Setor Sprites: pixel art com IA local (SDXL + LoRA Pixel Art XL) e envio para o Arasaka Construct pelo MCP.
// Também mantém o indicador da conexão com o Construct na barra de cima.

const SP = { status: null, preset: "", size: 32, result: null, busy: false, zoom: 0, timer: null, abort: null };
const VIEW_LABEL = { baixo: "Frente", esquerda: "Esquerda", direita: "Direita", cima: "Costas" };

// ------------------------------------------------------------------ indicador do Construct (barra de cima)
function constructChipHTML(c) {
  if (!c || !c.installed) return `<span class="mcp-dot"></span> ${t("Construct ausente")}`;
  if (c.state === "pronto") return `<span class="mcp-dot ok"></span> Construct · ${t("{n} ferramentas", { n: c.tools })}`;
  if (c.state === "conectando") return `<span class="spin"></span> Construct · ${t("conectando...")}`;
  if (c.state === "erro") return `<span class="mcp-dot bad"></span> Construct · ${t("erro")}`;
  return `<span class="mcp-dot"></span> Construct · ${t("desconectado")}`;
}
function constructTitle(c) {
  if (!c || !c.installed) return t("Arasaka Construct não encontrado neste PC. Instale pela Arasaka Central (aba Apps).");
  return [`Arasaka Construct ${c.version || ""} (MCP)`, c.project ? t("Projeto: {p}", { p: c.project }) : t("Sem projeto aberto"),
    c.error ? trText(c.error) : "", c.command].filter(Boolean).join("\n");
}
async function refreshConstructChip() {
  clearTimeout(SP.chipTimer);
  let c; try { c = await api("/api/construct"); } catch { SP.chipTimer = setTimeout(refreshConstructChip, 15000); return; }
  // enquanto conecta (a Mikoshi conecta sozinha logo depois de abrir), olha de novo logo
  SP.chipTimer = setTimeout(refreshConstructChip, c.installed && c.state !== "pronto" && c.state !== "erro" && (SP.chipTries = (SP.chipTries || 0) + 1) < 20 ? 1500 : 15000);
  for (const el of [$("#constructChip"), $("#spConstructPill")]) {
    if (!el) continue;
    el.hidden = !c.installed && el.id === "constructChip";
    el.innerHTML = constructChipHTML(c); el.title = constructTitle(c);
    el.classList.toggle("ok", c.state === "pronto"); el.classList.toggle("bad", c.state === "erro");
  }
  if (SP.status) { SP.status.construct = c; if (!$("#sprites").hidden) renderConstruct(); }
}
$("#constructChip").onclick = () => openSprites(true);
$("#spConstructPill").onclick = () => $("#spConstruct").scrollIntoView({ behavior: "smooth" });
refreshConstructChip();

// ------------------------------------------------------------------ abrir / fechar
function openSprites(focusConstruct) {
  if (document.body.classList.contains("studio-open")) closeStudio();
  document.body.classList.add("sprites-open"); $("#sprites").hidden = false; $("#spritesBtn").classList.add("on");
  $$("#modes button").forEach(b => b.classList.remove("on"));
  refreshSprites().then(() => { if (focusConstruct) $("#spConstruct").scrollIntoView({ behavior: "smooth" }); });
  clearInterval(SP.timer); SP.timer = setInterval(() => refreshSprites(), 2000);
}
function closeSprites() {
  document.body.classList.remove("sprites-open"); $("#sprites").hidden = true; $("#spritesBtn").classList.remove("on");
  clearInterval(SP.timer); if (typeof setMode === "function") setMode(S.mode);
}
$("#spritesBtn").onclick = () => document.body.classList.contains("sprites-open") ? closeSprites() : openSprites();
$("#spritesClose").onclick = closeSprites;
$("#modes").addEventListener("click", () => { if (document.body.classList.contains("sprites-open")) closeSprites(); }, true);
$("#studioBtn").addEventListener("click", () => { if (document.body.classList.contains("sprites-open")) closeSprites(); }, true);

async function refreshSprites() {
  try { SP.status = await api("/api/sprites"); } catch { return; }
  if (!SP.preset || !SP.status.models.some(m => m.key === SP.preset)) SP.preset = SP.status.preset;
  renderModels(); renderSetup(); renderConstruct(); renderSizes();
}
const spModel = () => SP.status?.models.find(m => m.key === SP.preset) || SP.status?.models[0];
function renderModels() {
  const sel = $("#spModel"); if (!SP.status || sel.matches(":focus")) return;
  sel.innerHTML = SP.status.models.map(m => `<option value="${esc(m.key)}" ${m.key === SP.preset ? "selected" : ""}>${esc(m.name)} — ${m.installed ? "✓ " + t("baixado") : t("não baixado, {size}", { size: fmtSize(m.bytes) })}</option>`).join("");
}
$("#spModel").onchange = e => { SP.preset = e.target.value; renderSetup(); };

// ------------------------------------------------------------------ instalação (motor + modelo)
function taskBar(task) {
  const pct = task.total ? Math.round(100 * task.done / task.total) : 0;
  const err = task.status === "error" ? `<div class="err-text">${esc(trText(task.error))}</div>` : "";
  return `<div class="sp-task"><div class="row"><small>${esc(task.label)} · ${esc(task.detail || "")}</small><span class="spacer"></span>
    <small>${task.total ? `${fmtSize(task.done)} / ${fmtSize(task.total)} (${pct}%)` : ""}</small>
    ${task.status === "running" ? `<button class="btn small" data-sp-cancel="${esc(task.id)}">${t("Cancelar")}</button>` : ""}</div>
    <div class="bar"><div style="width:${pct}%"></div></div>${err}</div>`;
}
function renderSetup() {
  const s = SP.status, box = $("#spSetup"); if (!s) return;
  const running = s.tasks.filter(x => x.status === "running");
  const m = spModel();
  const engOk = s.engine.installed && !s.engine.problem, modelOk = m.installed;
  box.hidden = engOk && modelOk && !s.tasks.length;
  if (box.hidden) return;
  const engBtn = s.os === "windows"
    ? `<button class="btn small" data-sp-install="sd" data-v="cuda">${t("Instalar motor (NVIDIA CUDA)")}</button> <button class="btn small" data-sp-install="sd" data-v="vulkan">Vulkan</button>`
    : `<button class="btn small" data-sp-install="sd" data-v="vulkan">${t("Instalar motor (Vulkan, ~40 MB)")}</button>`;
  box.innerHTML = `<div class="sp-label">${t("Preparar a IA de pixel art (uma vez só)")}</div>
    <div class="sp-step ${engOk ? "done" : ""}"><div><b>1.</b> ${t("Motor stable-diffusion.cpp")}</div>
      ${engOk ? `<small class="muted">✓ ${esc(s.engine.version)}</small>` : s.engine.problem ? `<div class="warn-box">${esc(trText(s.engine.problem))}</div>${engBtn}` : engBtn}</div>
    <div class="sp-step ${modelOk ? "done" : ""}"><div><b>2.</b> ${esc(m.name)}</div>
      ${modelOk ? `<small class="muted">✓ ${t("baixado")}</small>` : `<div><small class="muted">${esc(trText(m.desc))}</small></div>
      <button class="btn small primary" data-sp-install="image_preset" data-v="${esc(m.key)}">${t("Baixar modelo ({size})", { size: fmtSize(m.bytes) })}</button>
      <small class="muted">${t("Vai para {dir}. Dá para escolher outro modelo no campo Modelo.", { dir: m.dir })}</small>`}</div>
    ${s.tasks.map(taskBar).join("")}`;
  if (running.length) box.querySelectorAll("[data-sp-install]").forEach(b => b.disabled = true);
}
$("#spSetup").addEventListener("click", async e => {
  const c = e.target.closest("[data-sp-cancel]");
  if (c) { await post("/api/tasks/cancel", { id: c.dataset.spCancel }); return refreshSprites(); }
  const b = e.target.closest("[data-sp-install]"); if (!b) return;
  const what = b.dataset.spInstall, value = b.dataset.v;
  const mm = SP.status.models.find(x => x.key === value);
  if (what === "image_preset" && !confirm(t("Baixar {name} ({size}) do Hugging Face?", { name: mm?.name || value, size: fmtSize(mm?.bytes || 0) }))) return;
  b.disabled = true;
  try { await post("/api/media/install", { what, value }); toast(t("Download iniciado")); } catch (err) { toast(trText(err.message), 5000); }
  refreshSprites();
});

// ------------------------------------------------------------------ formulário
function renderSizes() {
  const box = $("#spSizes"); if (box.childElementCount || !SP.status) return;
  box.innerHTML = SP.status.sizes.map(n => `<button type="button" data-size="${n}" class="${n === SP.size ? "on" : ""}">${n}</button>`).join("");
}
$("#spSizes").onclick = e => {
  const b = e.target.closest("[data-size]"); if (!b) return;
  SP.size = +b.dataset.size; $$("#spSizes button").forEach(x => x.classList.toggle("on", x === b));
};
$("#spColors").oninput = e => { $("#spColorsVal").textContent = e.target.value; };
function spParams() {
  return { preset: SP.preset, size: SP.size, colors: +$("#spColors").value, frames: +$("#spFrames").value || 1,
    views: $$("#spViews input:checked").map(x => x.value), outline: $("#spOutline").checked,
    remove_bg: $("#spBg").checked, mode: $("#spMode").value };
}
function setProgress(html) { const p = $("#spProgress"); p.hidden = !html; p.innerHTML = html || ""; }

$("#spGenerate").onclick = async () => {
  if (SP.busy) { SP.abort?.abort(); return; }
  const prompt = $("#spPrompt").value.trim(); if (!prompt) return toast(t("Descreva o sprite."));
  SP.busy = true; SP.abort = new AbortController(); $("#spGenerate").textContent = t("Parar");
  setProgress(`<span class="spin"></span> ${t("Preparando...")}`);
  try {
    await streamChat({ prompt, seed: +$("#spSeed").value, ...spParams() }, SP.abort.signal, ev => {
      const s = ev.sprite; if (!s) return;
      if (s.stage === "unload") setProgress(`<span class="spin"></span> ${t("Liberando a GPU (descarregando o modelo de texto)...")}`);
      else if (s.stage === "image") setProgress(`<span class="spin"></span> ${t("Imagem {i} de {n}", { i: s.index + 1, n: s.total })}${s.view ? " · " + t(VIEW_LABEL[s.view] || s.view) : ""} · ${t("carregando o modelo...")}`);
      else if (s.stage === "progress" && s.step) setProgress(`<span class="spin"></span> ${t("Imagem {i} de {n}", { i: s.index + 1, n: s.total })} · ${t("passo {a}/{b}", { a: s.step, b: s.total_steps || s.total })} · ${esc(s.speed || "")}`);
      else if (s.stage === "pixel") setProgress(`<span class="spin"></span> ${t("Transformando em pixel art...")}`);
      else if (s.stage === "done") { setProgress(""); showResult(s); toast(t("Pronto em {s} s", { s: s.seconds })); }
    }, "/api/sprites/generate");
  } catch (err) {
    setProgress(err.name === "AbortError" ? "" : `<span class="err-text">${esc(trText(err.message))}</span>`);
  }
  SP.busy = false; $("#spGenerate").textContent = t("Gerar sprite");
};

$("#spPixelate").onclick = () => $("#spFile").click();
$("#spFile").onchange = async e => {
  const files = [...e.target.files]; e.target.value = ""; if (!files.length) return;
  setProgress(`<span class="spin"></span> ${t("Transformando em pixel art...")}`);
  try {
    const ids = [];
    for (const f of files) { // qualquer imagem vira PNG antes (o pixel.py lê PNG)
      const img = await loadImage(URL.createObjectURL(f));
      const c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight;
      c.getContext("2d").drawImage(img, 0, 0);
      ids.push((await uploadBlob(await canvasBlob(c, "image/png"), f.name.replace(/\.\w+$/, "") + ".png")).id);
    }
    const p = spParams();
    const r = await post("/api/sprites/pixelate", { ids, rows: 1, ...p });
    showResult({ ...r, sources: ids, views: [], subject: files[0].name.replace(/\.\w+$/, "") });
    setProgress("");
  } catch (err) { setProgress(`<span class="err-text">${esc(trText(err.message))}</span>`); }
};

// ------------------------------------------------------------------ resultado
function slugName(s) { return (s || "sprite").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40) || "sprite"; }
function showResult(r) {
  SP.result = r;
  const z = SP.zoom || Math.max(2, Math.min(8, Math.floor(420 / Math.max(r.sheet_w, r.sheet_h))));
  const url = id => `/api/uploads/${encodeURIComponent(id)}`;
  const c = SP.status?.construct;
  $("#spResult").innerHTML = `
    <div class="sp-card">
      <div class="row"><b>${esc(r.subject || "")}</b><span class="spacer"></span>
        <small class="muted">${r.size}×${r.size} · ${t("{c} colunas × {r} linhas", { c: r.cols, r: r.rows })}${r.seed != null ? " · " + t("semente {s}", { s: r.seed }) : ""}</small></div>
      <div class="sp-zoom">${[2, 4, 8, 12].map(k => `<button type="button" data-zoom="${k}" class="${k === z ? "on" : ""}">×${k}</button>`).join("")}</div>
      <div class="sp-stage"><img class="px" src="${url(r.sheet)}" style="width:${r.sheet_w * z}px;height:${r.sheet_h * z}px" alt=""></div>
      <div class="sp-pal">${r.palette.map(h => `<span title="${h}" style="background:${h}"></span>`).join("")}</div>
      ${r.sprites.length > 1 ? `<div class="sp-frames">${r.sprites.map((id, i) => `<a href="${url(id)}" download="${slugName(r.subject)}_${i + 1}.png" title="${t("Baixar quadro {n}", { n: i + 1 })}"><img class="px" src="${url(id)}" style="width:${r.size * 2}px;height:${r.size * 2}px" alt=""></a>`).join("")}</div>` : ""}
      <div class="sp-row wrap">
        <a class="btn" href="${url(r.sheet)}" download="${slugName(r.subject)}.png">${t("Baixar PNG")}</a>
        ${r.sources?.length ? `<button class="btn" id="spRedo" title="${esc(t("Refaz a pixel art com o tamanho, as cores e as opções atuais, sem gerar de novo"))}">${t("Reprocessar")}</button>` : ""}
      </div>
    </div>
    <div class="sp-card">
      <div class="sp-label">${t("Enviar ao Arasaka Construct")}</div>
      ${c?.installed ? `<div class="sp-row wrap">
          <input id="spName" class="input small-input" value="${esc(slugName(r.subject))}" title="${esc(t("Nome do sprite"))}">
          <label class="sp-field inline"><span>FPS</span><input id="spFps" class="input small-input" type="number" min="1" max="60" value="8"></label>
          <button class="btn primary" id="spSend" ${c.project ? "" : "disabled"}>${t("Enviar")}</button></div>
        <small class="muted">${c.project ? t("Grava assets/mikoshi/<nome>.png e sprites/<nome>.sprite.luau em {p}", { p: c.project }) : t("Escolha um projeto do Construct abaixo.")}</small>
        <div id="spSendLog"></div>`
      : `<small class="muted">${t("Arasaka Construct não encontrado neste PC. Instale pela Arasaka Central (aba Apps).")}</small>`}
    </div>`;
}
$("#spResult").addEventListener("click", async e => {
  const zb = e.target.closest("[data-zoom]");
  if (zb) { SP.zoom = +zb.dataset.zoom; return showResult(SP.result); }
  if (e.target.id === "spRedo") {
    const r = SP.result;
    try {
      const n = await post("/api/sprites/pixelate", { ids: r.sources, rows: r.rows, ...spParams() });
      showResult({ ...r, ...n });
    } catch (err) { toast(trText(err.message), 5000); }
  }
  if (e.target.id === "spSend") {
    const r = SP.result, b = e.target; b.disabled = true;
    $("#spSendLog").innerHTML = `<span class="spin"></span> ${t("Enviando...")}`;
    try {
      const out = await post("/api/sprites/construct", { sheet: r.sheet, name: $("#spName").value.trim(), size: r.size, cols: r.cols,
        rows: r.rows, views: r.views, fps: +$("#spFps").value || 8 });
      $("#spSendLog").innerHTML = `<div class="ok-text">✓ ${esc(out.path)} · ${esc(out.sprite)}</div>`;
      toast(t("Sprite enviado ao Arasaka Construct."));
    } catch (err) { $("#spSendLog").innerHTML = `<div class="err-text">${esc(trText(err.message))}</div>`; }
    b.disabled = false; refreshConstructChip();
  }
});

// ------------------------------------------------------------------ painel do Construct
function renderConstruct() {
  const s = SP.status, box = $("#spConstruct"); if (!s) return;
  const c = s.construct;
  const mcpCmd = `claude mcp add --transport http mikoshi ${s.mcp_url}`;
  const opts = (c.recent || []).map(p => `<option value="${esc(p)}" ${p === c.project ? "selected" : ""}>${esc(p.split(/[\\/]/).pop())} — ${esc(p)}</option>`).join("");
  box.innerHTML = `<div class="sp-label">${t("Arasaka Construct (MCP)")}</div>
    <div class="row">${constructChipHTML(c)}<span class="spacer"></span>
      ${c.installed ? `<button class="btn small" data-c="connect">${c.state === "pronto" ? t("Reconectar") : t("Conectar")}</button>` : ""}</div>
    ${c.error ? `<div class="err-text small-note">${esc(trText(c.error))}</div>` : ""}
    ${c.installed ? `<small class="muted">${t("Conecta sozinha ao abrir: a Mikoshi acha o editor ({cmd}) e conversa com ele por MCP. As ferramentas dele ficam no Codex (Configurações → MCP).", { cmd: c.command })}</small>
      ${c.state === "pronto" && !c.can_sprites ? `<div class="warn-box">${t("Este Construct é antigo e não recebe imagens. Atualize-o pela Arasaka Central para enviar sprites.")}</div>` : ""}
      <div class="sp-label">${t("Projeto")}</div>
      <div class="sp-row"><select id="spProject" class="input">${opts || `<option value="">${t("(nenhum projeto recente)")}</option>`}${c.project && !(c.recent || []).includes(c.project) ? `<option selected value="${esc(c.project)}">${esc(c.project)}</option>` : ""}</select>
        <button class="btn small" data-c="pick">${t("Outra pasta…")}</button></div>
      <small class="muted">${c.project_choice ? t("Escolhido por você.") : t("Sem escolha: usa o projeto aberto por último no editor.")}</small>`
    : `<small class="muted">${t("Não encontrei o editor neste PC. Instale o Arasaka Construct pela Arasaka Central (aba Apps); a Mikoshi conecta sozinha depois.")}</small>`}
    <details class="sp-mcp"><summary>${t("Usar os sprites da Mikoshi em outros assistentes")}</summary>
      <small class="muted">${t("A Mikoshi também é um servidor MCP (generate_sprite, pixelate_image, sprite_status). No Claude Code, junto com o Construct:")}</small>
      <div class="code"><pre><code>${esc(mcpCmd)}</code></pre></div></details>`;
}
$("#spConstruct").addEventListener("click", async e => {
  const a = e.target.closest("[data-c]")?.dataset.c; if (!a) return;
  if (a === "connect") {
    e.target.disabled = true; e.target.innerHTML = `<span class="spin"></span>`;
    try { await post("/api/construct/connect"); } catch (err) { toast(trText(err.message), 5000); }
    await refreshSprites(); refreshConstructChip();
  }
  if (a === "pick") {
    const dir = desktop?.chooseFolder ? await desktop.chooseFolder() : prompt(t("Pasta do projeto (a que tem project.luau):"));
    if (dir) setConstructProject(dir);
  }
});
$("#spConstruct").addEventListener("change", e => { if (e.target.id === "spProject") setConstructProject(e.target.value); });
async function setConstructProject(path) {
  try { await post("/api/construct/project", { path }); toast(t("Projeto do Construct: {p}", { p: path.split(/[\\/]/).pop() })); }
  catch (err) { toast(trText(err.message), 5000); }
  await refreshSprites(); setTimeout(refreshConstructChip, 1500);
}
