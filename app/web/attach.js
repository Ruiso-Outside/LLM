"use strict";
// Processa arquivos anexados: texto/código, PDF, Office, imagens, áudio e vídeo.
// Cada arquivo vira um ou mais "anexos" que o servidor converte para o modelo.

const TEXT_EXT = /\.(txt|md|markdown|csv|tsv|json|jsonl|xml|html?|css|scss|sass|less|js|mjs|cjs|ts|tsx|jsx|py|pyw|java|kt|kts|c|h|cpp|cc|hpp|cs|go|rs|rb|php|lua|luau|sh|bash|ps1|psm1|bat|cmd|sql|yaml|yml|toml|ini|cfg|conf|log|env|gitignore|dockerfile|vue|svelte|swift|dart|r|tex|srt|vtt|gradle|properties|rbxlx|gd|glsl|hlsl|shader)$/i;
const OFFICE_EXT = /\.(docx|pptx|xlsx|odt)$/i;
const AUDIO_EXT = /\.(mp3|wav|ogg|oga|m4a|flac|aac|opus|wma|webm)$/i;
const VIDEO_EXT = /\.(mp4|m4v|webm|mkv|mov|avi|wmv)$/i;
const MAX_TEXT = 400_000;

function attachKind(file) {
  const n = file.name, t = file.type || "";
  if (t.startsWith("image/")) return "image";
  if (t.startsWith("video/") || (VIDEO_EXT.test(n) && !t.startsWith("audio/"))) return "video";
  if (t.startsWith("audio/") || AUDIO_EXT.test(n)) return "audio";
  if (t === "application/pdf" || /\.pdf$/i.test(n)) return "pdf";
  if (OFFICE_EXT.test(n)) return "office";
  if (t.startsWith("text/") || TEXT_EXT.test(n) || t === "application/json") return "text";
  return "unknown";
}

async function uploadBlob(blob, name) {
  const r = await fetch("/api/upload", { method: "POST", body: blob,
    headers: { "X-Filename": encodeURIComponent(name), "Content-Type": blob.type || "application/octet-stream" } });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || "Falha no envio");
  return j;
}

const canvasBlob = (canvas, type = "image/jpeg", q = 0.88) => new Promise(res => canvas.toBlob(res, type, q));

async function loadImage(src) {
  const img = new Image(); img.src = src; await img.decode(); return img;
}

// Reduz imagens grandes (economiza tokens do modelo de visão)
async function prepareImage(file, maxSide = 1600) {
  const url = URL.createObjectURL(file);
  try {
    const img = await loadImage(url);
    const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
    if (scale === 1 && /image\/(png|jpeg|webp)/.test(file.type)) return file;
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * scale); c.height = Math.round(img.naturalHeight * scale);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    return await canvasBlob(c, file.type === "image/png" ? "image/png" : "image/jpeg");
  } finally { URL.revokeObjectURL(url); }
}

// ---- PDF (pdf.js embutido)
let pdfjsLib = null;
async function getPdfjs() {
  if (!pdfjsLib) {
    pdfjsLib = await import("./vendor/pdfjs/pdf.min.mjs");
    pdfjsLib.GlobalWorkerOptions.workerSrc = "./vendor/pdfjs/pdf.worker.min.mjs";
  }
  return pdfjsLib;
}

async function processPdf(file, onStatus) {
  const lib = await getPdfjs();
  const doc = await lib.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
  const pages = [];
  for (let i = 1; i <= doc.numPages; i++) {
    onStatus(t("lendo página {a}/{b}", { a: i, b: doc.numPages }));
    const tc = await (await doc.getPage(i)).getTextContent();
    let line = "", out = [];
    for (const it of tc.items) { line += it.str; if (it.hasEOL) { out.push(line); line = ""; } }
    if (line) out.push(line);
    pages.push(`--- Página ${i} ---\n` + out.join("\n"));
  }
  const text = pages.join("\n\n");
  if (text.replace(/--- Página \d+ ---|\s/g, "").length >= 10) return [{ kind: "text", name: file.name, text: text.slice(0, MAX_TEXT), pages: doc.numPages }];
  // PDF escaneado (sem texto): manda as primeiras páginas como imagens
  const atts = [];
  for (let i = 1; i <= Math.min(doc.numPages, 6); i++) {
    onStatus(t("PDF sem texto: convertendo página {n} em imagem", { n: i }));
    const page = await doc.getPage(i);
    const vp = page.getViewport({ scale: 1.6 });
    const c = document.createElement("canvas"); c.width = vp.width; c.height = vp.height;
    await page.render({ canvasContext: c.getContext("2d"), viewport: vp }).promise;
    const up = await uploadBlob(await canvasBlob(c), `${file.name}-p${i}.jpg`);
    atts.push({ kind: "image", id: up.id, name: `${file.name} (página ${i})` });
  }
  return atts;
}

// ---- Áudio: decodifica no navegador e converte para WAV 16 kHz mono
async function decodeTo16k(arrayBuffer) {
  const ctx = new AudioContext();
  let buf;
  try { buf = await ctx.decodeAudioData(arrayBuffer); } finally { ctx.close(); }
  const off = new OfflineAudioContext(1, Math.max(1, Math.ceil(buf.duration * 16000)), 16000);
  const src = off.createBufferSource(); src.buffer = buf; src.connect(off.destination); src.start();
  const out = await off.startRendering();
  return { samples: out.getChannelData(0), duration: buf.duration };
}

function wavBlob(samples, rate = 16000) {
  const buf = new ArrayBuffer(44 + samples.length * 2); const v = new DataView(buf);
  const str = (o, s) => [...s].forEach((ch, i) => v.setUint8(o + i, ch.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE"); str(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, "data");
  v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, samples[i])) * 0x7fff, true);
  return new Blob([buf], { type: "audio/wav" });
}

async function audioAttachment(arrayBuffer, name, onStatus, ctx) {
  onStatus(t("convertendo áudio"));
  const { samples, duration } = await decodeTo16k(arrayBuffer);
  const up = await uploadBlob(wavBlob(samples), name.replace(/\.[^.]+$/, "") + ".wav");
  const att = { kind: "audio", id: up.id, name, duration };
  if (!ctx.modelHasAudio && ctx.whisperReady) {
    onStatus(t("transcrevendo {n}s de áudio", { n: Math.round(duration) }));
    att.transcript = (await post("/api/transcribe", { id: up.id })).text;
  }
  return att;
}

// ---- Vídeo: quadros espalhados + trilha de áudio
function once(el, ev) { return new Promise((res, rej) => { el.addEventListener(ev, res, { once: true }); el.addEventListener("error", () => rej(new Error("formato de vídeo não suportado")), { once: true }); }); }

async function processVideo(file, onStatus, ctx) {
  const url = URL.createObjectURL(file);
  const v = document.createElement("video"); v.muted = true; v.preload = "auto"; v.src = url;
  try {
    await once(v, "loadedmetadata");
    const duration = v.duration || 0;
    const n = Math.max(3, Math.min(10, Math.round(duration / 12)));
    const frames = [];
    if (ctx.modelHasVision) {
      for (let i = 0; i < n; i++) {
        const ts = ((i + 0.5) * duration) / n;
        onStatus(t("extraindo quadro {a}/{b}", { a: i + 1, b: n }));
        v.currentTime = ts; await once(v, "seeked");
        const scale = Math.min(1, 768 / Math.max(v.videoWidth, v.videoHeight));
        const c = document.createElement("canvas"); c.width = Math.round(v.videoWidth * scale); c.height = Math.round(v.videoHeight * scale);
        c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
        const up = await uploadBlob(await canvasBlob(c), `${file.name}-${Math.round(ts)}s.jpg`);
        frames.push({ id: up.id, t: ts });
      }
    }
    const att = { kind: "video", name: file.name, duration, frames };
    if (ctx.whisperReady && file.size < 700 * 1024 * 1024) {
      try {
        const a = await audioAttachment(await file.arrayBuffer(), file.name, onStatus, { ...ctx, modelHasAudio: false });
        att.audio = a.id; att.transcript = a.transcript;
      } catch { /* vídeo sem áudio */ }
    }
    if (!frames.length && !att.transcript) throw new Error("o modelo não tem visão e o Whisper não está instalado");
    return [att];
  } finally { URL.revokeObjectURL(url); }
}

// Ponto de entrada: retorna uma lista de anexos prontos
async function processFile(file, onStatus, ctx) {
  const kind = attachKind(file);
  if (kind === "image") {
    onStatus(t("enviando imagem"));
    const up = await uploadBlob(await prepareImage(file), file.name);
    return [{ kind: "image", id: up.id, name: file.name }];
  }
  if (kind === "text") {
    let text = await file.text();
    if (text.length > MAX_TEXT) text = text.slice(0, MAX_TEXT) + "\n... (arquivo cortado)";
    return [{ kind: "text", name: file.name, text }];
  }
  if (kind === "pdf") return processPdf(file, onStatus);
  if (kind === "office") {
    onStatus(t("lendo documento"));
    const up = await uploadBlob(file, file.name);
    const { text } = await post("/api/extract", { id: up.id });
    return [{ kind: "text", name: file.name, text: text.slice(0, MAX_TEXT) }];
  }
  if (kind === "audio") return [await audioAttachment(await file.arrayBuffer(), file.name, onStatus, ctx)];
  if (kind === "video") return processVideo(file, onStatus, ctx);
  // desconhecido: tenta como texto se for pequeno e legível
  if (file.size < 1024 * 1024) {
    const text = await file.text();
    if (!/[\u0000-\u0008\u000E-\u001F]/.test(text.slice(0, 4000))) return [{ kind: "text", name: file.name, text }];
  }
  throw new Error("tipo de arquivo não suportado");
}

const ATTACH_ICON = { text: "📄", image: "🖼️", audio: "🎵", video: "🎬", pdf: "📕", office: "📘", unknown: "📎" };
