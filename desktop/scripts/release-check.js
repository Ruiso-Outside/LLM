// Prepara e confere o Release do GitHub usado pela atualização automática.
//   node scripts/release-check.js            -> cria o Release da versão atual (antes do electron-builder)
//   node scripts/release-check.js --verify   -> confere que existe UM Release com os 3 arquivos baixáveis
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

async function verify() {
  const rels = await releasesForTag();
  if (rels.length !== 1) fail(`esperado 1 Release com a tag ${tag}, encontrados ${rels.length}.`);
  const names = rels[0].assets.map(a => a.name);
  const needed = ["latest.yml", `LLM-Local-Setup-${version}.exe`, `LLM-Local-Setup-${version}.exe.blockmap`];
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
