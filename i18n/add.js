// Junta ao source.jsonl textos novos com todas as traduções (linhas ["pt","en","es","th",...] como no merge do Hub).
//   node i18n/add.js arquivo.jsonl
const fs = require("fs"), path = require("path");
const CODES = ["pt", "en", "es", "th", "zh", "ja", "ko", "id", "vi", "fr", "de", "ru"];
const out = path.join(__dirname, "source.jsonl");
const rows = new Map(fs.readFileSync(out, "utf8").split(/\r?\n/).filter(Boolean).map((l) => { const o = JSON.parse(l); return [o.pt, o]; }));
let n = 0;
for (const l of fs.readFileSync(process.argv[2], "utf8").split(/\r?\n/)) {
  if (!l.trim()) continue;
  const a = JSON.parse(l), o = Object.fromEntries(CODES.map((c, i) => [c, a[i]]));
  rows.set(o.pt, { ...(rows.get(o.pt) || {}), ...o }); n++;
}
fs.writeFileSync(out, [...rows.values()].map((o) => JSON.stringify(o)).join("\n") + "\n");
console.log("juntados:", n, "· total:", rows.size);
