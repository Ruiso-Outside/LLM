"""REA (Reverse Engineer Anything) como componente do motor do LLM Local.

Instala uma vez, dentro de engine/rea, um Node.js portatil oficial e o pacote rea-agents numa versao fixa.
Depois disso funciona sem internet e sem nada instalado no Windows. O Codex usa o REA pelo terminal
(rea.cmd) com a saida limitada; o modo MCP (opcional) usa a mesma copia.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

REA_VERSION = "6.5.0"  # versao testada; atualizar aqui de proposito (o REA muda rapido)
NODE_MAJOR = 24  # o REA pede Node 22.19+, 24.11+ ou 26+
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ROOT = None
_download = _get_json = None


def configure(engine_dir, download, get_json):
    global ROOT, _download, _get_json
    ROOT = Path(engine_dir) / "rea"
    _download, _get_json = download, get_json


def node_exe():
    return ROOT / "node" / "node.exe"


def rea_script():
    return ROOT / "pkg" / "node_modules" / "rea-agents" / "scripts" / "rea.mjs"


def cli_path():
    return ROOT / "rea.cmd"


def installed():
    return bool(ROOT) and node_exe().is_file() and rea_script().is_file() and cli_path().is_file()


def status():
    info = {}
    try:
        info = json.loads((ROOT / "versao.json").read_text("utf-8"))
    except (OSError, ValueError, TypeError):
        pass
    return {"installed": installed(), "version": info.get("rea", ""), "node": info.get("node", ""),
            "pinned": REA_VERSION, "path": str(ROOT) if ROOT else ""}


def mcp_command():
    """Comando do servidor MCP do REA usando a copia local (sem npx e sem internet)."""
    return str(node_exe()), [str(rea_script()), "mcp"]


def _env():
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "node") + os.pathsep + env.get("PATH", "")
    env.update(NO_UPDATE_NOTIFIER="1", NPM_CONFIG_UPDATE_NOTIFIER="false", NPM_CONFIG_FUND="false", NPM_CONFIG_AUDIT="false")
    return env


def _pick_node():
    """Versao LTS mais nova do Node 24 com pacote .zip para Windows x64."""
    for rel in _get_json("https://nodejs.org/dist/index.json"):
        v = rel.get("version", "")
        if v.startswith(f"v{NODE_MAJOR}.") and rel.get("lts") and "win-x64-zip" in rel.get("files", []):
            return v
    raise RuntimeError(f"Não encontrei o Node.js {NODE_MAJOR} para Windows em nodejs.org.")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def install(task):
    """Baixa o Node.js portatil e o rea-agents fixo para engine/rea (uma vez)."""
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / "_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        # 1) Node.js portatil oficial, conferido pelo SHA-256 publicado em nodejs.org
        task["detail"] = "Consultando o Node.js..."
        ver = _pick_node()
        name = f"node-{ver}-win-x64"
        base = f"https://nodejs.org/dist/{ver}/"
        with urllib.request.urlopen(base + "SHASUMS256.txt", timeout=30) as r:
            sums = r.read().decode("utf-8", "replace")
        m = re.search(rf"^([0-9a-f]{{64}})\s+{re.escape(name)}\.zip$", sums, re.M)
        if not m:
            raise RuntimeError("Não encontrei a assinatura SHA-256 do Node.js.")
        task["detail"] = f"Node.js {ver}"
        zpath = tmp / f"{name}.zip"
        _download(base + f"{name}.zip", zpath, task, 0)
        if _sha256(zpath) != m.group(1):
            raise RuntimeError("O Node.js baixado está corrompido (SHA-256 diferente). Tente de novo.")
        task["detail"] = "Extraindo o Node.js..."
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tmp)
        shutil.rmtree(ROOT / "node", ignore_errors=True)
        shutil.move(str(tmp / name), str(ROOT / "node"))
        # 2) rea-agents na versao fixa, sem scripts de instalacao
        task["detail"] = f"Instalando o REA {REA_VERSION} (cerca de 250 MB)..."
        task["total"], task["done"] = 0, 0
        npm = ROOT / "node" / "node_modules" / "npm" / "bin" / "npm-cli.js"
        shutil.rmtree(ROOT / "pkg", ignore_errors=True)
        (ROOT / "pkg").mkdir()
        cmd = [str(node_exe()), str(npm), "install", f"rea-agents@{REA_VERSION}", "--prefix", str(ROOT / "pkg"),
               "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund", "--loglevel=error"]
        p = subprocess.Popen(cmd, cwd=str(ROOT), env=_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             creationflags=NO_WINDOW)
        out = []
        for raw in iter(p.stdout.readline, b""):
            out.append(raw.decode("utf-8", "replace").rstrip())
            if task.get("cancel"):
                p.kill()
                raise RuntimeError("cancelado")
        if p.wait() != 0 or not rea_script().is_file():
            raise RuntimeError("Falha ao instalar o REA: " + " | ".join(l for l in out[-4:] if l))
        # 3) atalho para o terminal do Codex
        cli_path().write_text('@echo off\r\nset NO_UPDATE_NOTIFIER=1\r\n'
                              '"%~dp0node\\node.exe" "%~dp0pkg\\node_modules\\rea-agents\\scripts\\rea.mjs" %*\r\n', "utf-8")
        (ROOT / "versao.json").write_text(json.dumps({"rea": REA_VERSION, "node": ver, "installed": time.time()}), "utf-8")
        task["detail"] = f"REA {REA_VERSION} pronto (funciona sem internet)"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def uninstall():
    if ROOT and ROOT.exists():
        shutil.rmtree(ROOT)


def cli_prompt():
    """Instrucoes curtas para o Codex usar o REA local pelo PowerShell."""
    exe = str(cli_path())
    return f"""REA (engenharia reversa) esta instalado neste PC e funciona sem internet. Use para entender programas sem o
codigo-fonte (apps Electron/JavaScript, executaveis .exe/.dll, .NET, Go, Rust, pacotes, bancos SQLite).
- Comando (PowerShell): & "{exe}" <comando> "<caminho absoluto>" --format md --token-limit 3000
- SEMPRE use --token-limit (sem ele a saida pode ter milhoes de tokens). Para ver mais, repita com --token-offset.
- App Electron/JS (pasta ou .asar): analyze-javascript-application "<alvo>" --filter-output normalized_result.summary,normalized_result.statistics,normalized_result.limitations
- Visao geral de qualquer arquivo: inspect-artifact "<arquivo>"  |  extrair pacote: extract-artifact
- .NET: inspect-managed-artifact e inspect-managed-members  |  Go/Rust: inspect-go-binary, inspect-rust-binary
- Recursos de .exe/.dll: inspect-pe-resources  |  SQLite: inspect-sqlite-database
- Ajuda de um comando: & "{exe}" <comando> --help
- Use o REA so em software que o usuario tem ou esta autorizado a analisar. Cite as evidencias e os limites que o REA informar."""
