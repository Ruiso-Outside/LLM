// Prepara e confere o Release do GitHub usado pela atualização automática.
//   node scripts/release-check.js            -> cria o Release da versão atual (antes do electron-builder)
//   node scripts/release-check.js --verify   -> confere que existe UM Release com os arquivos baixáveis
//   ... --verify --wait-installer            -> também espera (até 25 min) o GitHub Actions anexar o instalador
//                                               NSIS + latest.yml, usados pelas versões antigas (até a 1.3.0)
// Motivo: quando o electron-builder cria o Release sozinho, às vezes cria dois com a mesma
// tag (os envios rodam em paralelo) e os arquivos ficam divididos, quebrando o latest.yml.
const { version } = require("../package.json");
const { owner, repo } = require("../package.json").build.publish[0];

const token = process.env.GH_TOKEN;
const tag = `v${version}`;
const api = (path, opts = {}) => fetch(`https://api.github.com/repos/${owner}/${repo}${path}`, {
  ...opts, headers: { Authorization: `Bearer ${token}`, "User-Agent": "llm-local-release", Accept: "application/vnd.github+json", ...opts.headers },
});
const fail = msg => { console.error("✗ " + msg); process.exit(1); };

async function releasesForTag() {
  const r = await api("/releases?per_page=100");
  if (!r.ok) fail(`não foi possível listar os Releases (HTTP ${r.status}). GH_TOKEN está certo?`);
  return (await r.json()).filter(x => x.tag_name === tag);
}

async function prepare() {
  if (!token) fail("defina a variável GH_TOKEN com um token do GitHub (permissão de escrita no repositório).");
  const ref = await api(`/git/ref/tags/${tag}`);
  if (!ref.ok) fail(`a tag ${tag} não existe no GitHub. Rode: git tag ${tag} && git push origin ${tag}`);
  const existing = await releasesForTag();
  if (existing.length > 1) fail(`já existem ${existing.length} Releases com a tag ${tag}. Apague os duplicados no GitHub.`);
  if (existing.length === 1) return console.log(`✓ Release ${tag} já existe; o electron-builder vai enviar os arquivos para ele.`);
  const r = await api("/releases", { method: "POST", body: JSON.stringify({ tag_name: tag, name: version, draft: false, prerelease: false }) });
  if (!r.ok) fail(`não foi possível criar o Release (HTTP ${r.status}): ${await r.text()}`);
  console.log(`✓ Release ${tag} criado.`);
}

const INSTALLER = ["latest.yml", `LLM-Local-Setup-${version}.exe`, `LLM-Local-Setup-${version}.exe.blockmap`];

async function waitInstaller() {
  console.log("… esperando o GitHub Actions gerar e anexar o instalador (workflow \"Instalador Windows\")");
  for (let i = 0; i < 150; i++) {
    const rels = await releasesForTag();
    const names = (rels[0]?.assets || []).map(a => a.name);
    if (INSTALLER.every(n => names.includes(n))) return console.log("✓ instalador anexado pelo GitHub Actions");
    await new Promise(r => setTimeout(r, 10000));
  }
  fail("o instalador não apareceu em 25 min. Veja https://github.com/" + owner + "/" + repo + "/actions");
}

async function verify() {
  if (process.argv.includes("--wait-installer")) await waitInstaller();
  const rels = await releasesForTag();
  if (rels.length !== 1) fail(`esperado 1 Release com a tag ${tag}, encontrados ${rels.length}.`);
  const names = rels[0].assets.map(a => a.name);
  const needed = ["patch.json", `app-patch-${version}.zip`, `LLM-Local-${version}-win-x64.zip`, ...INSTALLER];
  const missing = needed.filter(n => !names.includes(n));
  if (missing.length) fail(`faltam arquivos no Release: ${missing.join(", ")}`);
  for (const n of needed) {
    const r = await fetch(`https://github.com/${owner}/${repo}/releases/download/${tag}/${n}?v=${Date.now()}`, { method: "HEAD", redirect: "follow" });
    if (!r.ok) fail(`${n} não baixa (HTTP ${r.status}). O repositório está público?`);
  }
  console.log(`✓ Release ${tag} ok: ${needed.join(", ")}`);
  console.log(`  ${rels[0].html_url}`);
}

(process.argv.includes("--verify") ? verify() : prepare()).catch(e => fail(e.message));
