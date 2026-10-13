// Gera o pacote de atualização a partir de dist/win-unpacked:
//   dist/app-patch-X.Y.Z.zip  -> pastas resources/app e resources/server
//   dist/patch.json           -> versão, versão do Electron, tamanho e SHA-512
//   node scripts/make-patch.js            (só gera)
//   node scripts/make-patch.js --upload   (gera e envia para o Release vX.Y.Z; precisa de GH_TOKEN)
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");
const pkg = require("../package.json");

const { version } = pkg;
const electron = pkg.devDependencies.electron;
const { owner, repo } = pkg.build.publish[0];
const dist = path.join(__dirname, "..", "dist");
const res = path.join(dist, "win-unpacked", "resources");
const file = `app-patch-${version}.zip`;
const fail = msg => { console.error("✗ " + msg); process.exit(1); };

const builtVersion = JSON.parse(fs.readFileSync(path.join(res, "app", "package.json"), "utf8")).version;
if (builtVersion !== version) fail(`dist/win-unpacked é da versão ${builtVersion}, não ${version}. Rode o build de novo.`);
if (!fs.existsSync(path.join(res, "server", "server.py"))) fail("resources/server/server.py não encontrado.");

const zip = path.join(dist, file);
fs.rmSync(zip, { force: true });
// tar.exe (Windows 10/11) cria .zip com -a
const t = spawnSync("tar", ["-a", "-c", "-f", zip, "-C", res, "app", "server"], { encoding: "utf8" });
if (t.status !== 0) fail("tar falhou: " + t.stderr);
const data = fs.readFileSync(zip);
const manifest = { version, electron, file, size: data.length,
  sha512: crypto.createHash("sha512").update(data).digest("base64"), date: new Date().toISOString() };
fs.writeFileSync(path.join(dist, "patch.json"), JSON.stringify(manifest, null, 2));
console.log(`✓ ${file} (${(data.length / 1e6).toFixed(1)} MB) e patch.json gerados`);

async function upload() {
  const token = process.env.GH_TOKEN;
  if (!token) fail("defina GH_TOKEN para enviar ao GitHub.");
  const h = { Authorization: `Bearer ${token}`, "User-Agent": "llm-local-release", Accept: "application/vnd.github+json" };
  const rels = await (await fetch(`https://api.github.com/repos/${owner}/${repo}/releases?per_page=100`, { headers: h })).json();
  const rel = rels.find(r => r.tag_name === `v${version}`);
  if (!rel) fail(`Release v${version} não encontrado.`);
  for (const name of [file, "patch.json"]) {
    const old = rel.assets.find(a => a.name === name);
    if (old) await fetch(`https://api.github.com/repos/${owner}/${repo}/releases/assets/${old.id}`, { method: "DELETE", headers: h });
    const body = fs.readFileSync(path.join(dist, name));
    const r = await fetch(`https://uploads.github.com/repos/${owner}/${repo}/releases/${rel.id}/assets?name=${encodeURIComponent(name)}`,
      { method: "POST", headers: { ...h, "Content-Type": name.endsWith(".json") ? "application/json" : "application/zip" }, body });
    if (!r.ok) fail(`falha ao enviar ${name} (HTTP ${r.status}): ${await r.text()}`);
    console.log(`✓ enviado ${name}`);
  }
}

if (process.argv.includes("--upload")) upload().catch(e => fail(e.message));
