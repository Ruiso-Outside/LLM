"use strict";
// Funcoes compartilhadas entre a janela principal e a pergunta rapida.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: { "Content-Type": "application/json" } };
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
  const r = await fetch(path, init);
  const txt = await r.text();
  let j; try { j = JSON.parse(txt); } catch { j = { error: txt }; }
  if (!r.ok) throw new Error(j.error || `Erro ${r.status}`);
  return j;
}
const post = (p, body = {}) => api(p, { method: "POST", body });
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtSize = b => b >= 1e9 ? (b / 1e9).toFixed(1) + " GB" : b >= 1e6 ? (b / 1e6).toFixed(0) + " MB" : (b / 1e3).toFixed(0) + " KB";
const fmtNum = n => n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "k" : String(n);
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
// ------------------------------------------------------------------ markdown
function inline(s) { // s ja escapado
  const codes = [];
  s = s.replace(/`([^`\n]+)`/g, (m, c) => { codes.push(c); return `\u0001${codes.length - 1}\u0001`; });
  s = s.replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, "<strong>$1</strong>")
       .replace(/(^|[^\w*])\*(?=\S)([^*\n]*?\S)\*(?!\*)/g, "$1<em>$2</em>")
       .replace(/(^|\W)_(?=\S)([^_\n]*?\S)_(?=\W|$)/g, "$1<em>$2</em>")
       .replace(/~~(?=\S)([^~]*?\S)~~/g, "<del>$1</del>")
       .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
       .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
  return s.replace(/\u0001(\d+)\u0001/g, (m, i) => `<code>${codes[i]}</code>`);
}
const codeBlock = (lang, code) =>
  `<div class="code"><div class="code-h"><span>${esc(lang || "código")}</span><button class="copy-code">Copiar</button></div><pre><code>${esc(code)}</code></pre></div>`;
const indentOf = l => l.match(/^\s*/)[0].replace(/\t/g, "    ").length;
const LIST_RE = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;

function md(src) {
  const lines = src.replace(/\r/g, "").split("\n");
  const out = []; let para = []; let i = 0;
  const flush = () => { if (para.length) { out.push("<p>" + inline(esc(para.join("\n"))).replace(/\n/g, "<br>") + "</p>"); para = []; } };
  while (i < lines.length) {
    const l = lines[i]; let m;
    if ((m = l.match(/^\s*(```+|~~~+)\s*([^\s`]*)/))) {
      flush(); const fence = m[1]; const code = []; i++;
      while (i < lines.length && !lines[i].trim().startsWith(fence)) code.push(lines[i++]);
      i++; out.push(codeBlock(m[2], code.join("\n"))); continue;
    }
    if (!l.trim()) { flush(); i++; continue; }
    if ((m = l.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/))) { flush(); const n = m[1].length; out.push(`<h${n}>${inline(esc(m[2]))}</h${n}>`); i++; continue; }
    if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(l)) { flush(); out.push("<hr>"); i++; continue; }
    if (/^\s*>/.test(l)) {
      flush(); const q = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push("<blockquote>" + md(q.join("\n")) + "</blockquote>"); continue;
    }
    if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      flush();
      const row = s => s.trim().replace(/^\||\|$/g, "").split("|").map(c => inline(esc(c.trim())));
      const head = row(l); i += 2; const body = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) body.push(row(lines[i++]));
      out.push('<div class="tbl"><table><thead><tr>' + head.map(c => `<th>${c}</th>`).join("") + "</tr></thead><tbody>" +
        body.map(r => "<tr>" + r.map(c => `<td>${c}</td>`).join("") + "</tr>").join("") + "</tbody></table></div>");
      continue;
    }
    if ((m = l.match(LIST_RE))) {
      flush();
      const base = indentOf(l); const ordered = /\d/.test(m[2]); const start = parseInt(m[2]) || 1;
      const items = [];
      while (i < lines.length) {
        const cur = lines[i]; const mm = cur.match(LIST_RE);
        if (mm && indentOf(cur) <= base + 1 && /\d/.test(mm[2]) === ordered) { items.push([mm[3]]); i++; continue; }
        if (!items.length) break;
        if (cur.trim() === "") {
          const nx = lines[i + 1];
          if (nx !== undefined && nx.trim() && indentOf(nx) > base) { items[items.length - 1].push(""); i++; continue; }
          break;
        }
        if (indentOf(cur) > base) { items[items.length - 1].push(cur.slice(Math.min(indentOf(cur), base + 2))); i++; continue; }
        break;
      }
      const tag = ordered ? "ol" : "ul";
      out.push(`<${tag}${ordered && start !== 1 ? ` start="${start}"` : ""}>` + items.map(([first, ...rest]) =>
        `<li>${inline(esc(first))}${rest.length ? md(rest.join("\n")) : ""}</li>`).join("") + `</${tag}>`);
      continue;
    }
    para.push(l); i++;
  }
  flush();
  return out.join("");
}

function splitThink(msg) {
  let content = msg.content || ""; let reasoning = msg.reasoning || ""; let open = false;
  const m = content.match(/^\s*<think>([\s\S]*?)(<\/think>|$)/);
  if (m) { reasoning += m[1]; content = content.slice(m[0].length); open = !m[2]; }
  return { content: content.replace(/^\s+/, ""), reasoning: reasoning.trim(), open };
}

function webBoxHTML(w, streaming) {
  const label = { query: "Criando a consulta de pesquisa...", search: `Pesquisando: “${esc(w.query)}”...`,
                  read: `Lendo ${w.sources?.length || 0} páginas sobre “${esc(w.query)}”...` }[w.stage];
  if (label) return `<div class="web-box"><span class="status">🌐 ${label}</span></div>`;
  if (w.stage === "error") return `<div class="web-box"><span class="status err">🌐 ${esc(w.text)}${w.query ? ` (consulta: “${esc(w.query)}”)` : ""}. Respondendo sem a web.</span></div>`;
  const items = (w.sources || []).map(s => {
    let host = ""; try { host = new URL(s.url).hostname.replace(/^www\./, ""); } catch {}
    return `<li><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title || host)}</a><small>${esc(host)}</small></li>`;
  }).join("");
  return `<details class="web-box"${streaming ? " open" : ""}><summary>🌐 Pesquisou “${esc(w.query)}” · ${w.sources?.length || 0} fontes</summary><ol>${items}</ol></details>`;
}

function linkCitations(html, sources) {
  if (!sources?.length) return html;
  // nao mexe dentro de blocos de codigo
  return html.split(/(<pre[\s\S]*?<\/pre>|<code>[\s\S]*?<\/code>)/).map((part, i) => i % 2 ? part :
    part.replace(/\[(\d{1,2})\]/g, (m, n) => {
      const s = sources[+n - 1];
      return s ? `<a class="cite" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer" title="${esc(s.title)}">${n}</a>` : m;
    })).join("");
}

// Le o stream SSE do /api/chat e chama onEvent(json) para cada evento.
async function streamChat(body, signal, onEvent, url = "/api/chat") {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  if (!r.ok) { let e; try { e = (await r.json()).error; } catch { e = "Erro " + r.status; } throw new Error(e); }
  const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
  while (true) {
    const { done, value } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true }); let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
      if (!line.startsWith("data:")) continue;
      const data = line.slice(5).trim(); if (data === "[DONE]") continue;
      let j; try { j = JSON.parse(data); } catch { continue; }
      if (j.error) throw new Error(j.error.message || JSON.stringify(j.error));
      onEvent(j);
    }
  }
}

// Ponte com o processo principal do Electron (desktop/preload.js).
const desktop = window.llmDesktop;
