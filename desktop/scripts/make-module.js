// Gera dist/piphin-module-llm-<versão>.zip: o Piphin LLM como módulo do Piphin Hub.
// Leva o mesmo servidor Python (app/) do app separado; desktop/module/ tem só o que muda dentro do Hub.
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const desk = path.join(__dirname, "..");
const pkg = require(path.join(desk, "package.json"));
const stage = path.join(desk, "dist", "module-stage");
const out = path.join(desk, "dist", `piphin-module-llm-${pkg.version}.zip`);

fs.rmSync(stage, { recursive: true, force: true });
fs.mkdirSync(path.join(stage, "icons"), { recursive: true });

const manifest = JSON.parse(fs.readFileSync(path.join(desk, "module", "module.json"), "utf8"));
manifest.version = pkg.version;
fs.writeFileSync(path.join(stage, "module.json"), JSON.stringify(manifest, null, 2));
fs.copyFileSync(path.join(desk, "module", "backend.js"), path.join(stage, "backend.js"));
fs.cpSync(path.join(desk, "module", "web"), path.join(stage, "web"), { recursive: true });
fs.copyFileSync(path.join(desk, "icon.png"), path.join(stage, "icons", "llm.png"));
fs.cpSync(path.join(desk, "..", "app"), path.join(stage, "server"), {
  recursive: true,
  filter: (src) => !/[\\/]__pycache__([\\/]|$)/.test(src) && !src.endsWith(".pyc"),
});

fs.rmSync(out, { force: true });
const tar = path.join(process.env.SystemRoot || "C:\\Windows", "System32", "tar.exe");
execFileSync(tar, ["-a", "-c", "-f", out, "-C", stage, "."], { stdio: "inherit" });
fs.rmSync(stage, { recursive: true, force: true });
console.log("módulo:", out, `(${(fs.statSync(out).size / 1048576).toFixed(1)} MB)`);
