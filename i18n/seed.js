// Atualiza i18n/source.jsonl (pt, en, es) com o DICT de app/web/i18n.js.
// Textos que não estão no DICT (vieram de i18n/add.js) continuam lá.
const fs = require("fs"), path = require("path"), vm = require("vm");
const src = fs.readFileSync(path.join(__dirname, "..", "app", "web", "i18n.js"), "utf8");
const ctx = { localStorage: { getItem: () => null }, navigator: { language: "pt-BR" }, document: { documentElement: {}, readyState: "complete", addEventListener() {}, write() {} }, window: {} };
vm.createContext(ctx);
vm.runInContext(src.replace(/\nif \(document\.readyState[^\n]*$/, "") + "\nthis.__DICT = DICT;", ctx);
const out = path.join(__dirname, "source.jsonl");
const old = new Map();
if (fs.existsSync(out)) for (const l of fs.readFileSync(out, "utf8").split(/\r?\n/)) if (l.trim()) { const o = JSON.parse(l); old.set(o.pt, o); }
const rows = new Map();
for (const [pt, [en, es]] of Object.entries(ctx.__DICT)) rows.set(pt, { ...(old.get(pt) || {}), pt, en, es });
for (const [pt, o] of old) if (!rows.has(pt)) rows.set(pt, o);
fs.writeFileSync(out, [...rows.values()].map((o) => JSON.stringify(o)).join("\n") + "\n");
console.log(rows.size, "textos");
