// Gera app/web/i18n/<idioma>.js (window.DICT_X) a partir de i18n/source.jsonl.
// English e Español: o DICT de app/web/i18n.js e, aqui, só o que não está nele.
//   node i18n/seed.js   -> atualiza source.jsonl com os textos novos do DICT
//   node i18n/add.js <arquivo>   -> textos novos já com as 12 línguas (fora do DICT)
//   node ../Hub/scripts/i18n.js todo . / merge . <arquivo>   -> traduz
//   node i18n/gen.js    -> gera os arquivos
const fs = require("fs"), path = require("path");
const out = path.join(__dirname, "..", "app", "web", "i18n");
fs.mkdirSync(out, { recursive: true });
const rows = fs.readFileSync(path.join(__dirname, "source.jsonl"), "utf8").split(/\r?\n/).filter(Boolean).map(JSON.parse);
const ph = (s) => (String(s).match(/\{\w+\}/g) || []).sort().join(",");
const src = fs.readFileSync(path.join(__dirname, "..", "app", "web", "i18n.js"), "utf8");
const inDict = (pt) => src.includes(JSON.stringify(pt) + ": [");
for (const c of ["en", "es", "th", "zh", "ja", "ko", "id", "vi", "fr", "de", "ru"]) {
  const d = {};
  for (const o of rows) if (o[c] && o[c] !== o.pt && ph(o[c]) === ph(o.pt) && !((c === "en" || c === "es") && inDict(o.pt))) d[o.pt] = o[c];
  fs.writeFileSync(path.join(out, c + ".js"), `"use strict";\n// gerado por i18n/gen.js\nwindow.DICT_X = ${JSON.stringify(d)};\n`);
  console.log(c, Object.keys(d).length);
}
