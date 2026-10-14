"""Codex do LLM Local: agente de programacao que trabalha SOMENTE dentro das
pastas que o usuario liberou nas Configuracoes.

O modelo usa "tool calling" (llama-server com --jinja). Cada ferramenta valida
o caminho; comandos e exclusoes pedem confirmacao do usuario pela interface.
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import mcp
import rea

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".idea", ".vs",
             "target", "bin", "obj", ".gradle", ".cache"}
MAX_READ_CHARS = 60_000
MAX_OUTPUT = 12_000


class ToolError(Exception):
    pass


# ---------------------------------------------------------------- definicao das ferramentas

def _fn(name, desc, props, required=()):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": list(required)}}}


S = {"type": "string"}
I = {"type": "integer"}
TOOLS = [
    _fn("list_files", "Lista arquivos e pastas (em arvore). Use primeiro para entender o projeto.",
        {"path": S | {"description": "Pasta relativa a raiz do projeto. Padrao: ."},
         "max_depth": I | {"description": "Profundidade (1-6). Padrao: 3"}}),
    _fn("read_file", "Le um arquivo de texto com numeros de linha. Para arquivos grandes, leia por partes.",
        {"path": S, "start_line": I, "end_line": I}, ["path"]),
    _fn("write_file", "Cria ou substitui um arquivo inteiro com o conteudo informado (cria as pastas necessarias).",
        {"path": S, "content": S | {"description": "Conteudo COMPLETO do arquivo"}}, ["path", "content"]),
    _fn("edit_file", "Substitui um trecho exato de um arquivo. old_text deve aparecer exatamente uma vez "
        "(inclua linhas vizinhas para torna-lo unico) a menos que replace_all seja true.",
        {"path": S, "old_text": S, "new_text": S, "replace_all": {"type": "boolean"}}, ["path", "old_text", "new_text"]),
    _fn("search_files", "Procura um texto ou expressao regular nos arquivos do projeto.",
        {"pattern": S | {"description": "Expressao regular (Python)"}, "path": S,
         "glob": S | {"description": "Filtro de nome, ex.: *.py"}}, ["pattern"]),
    _fn("delete_path", "Apaga um arquivo ou pasta (pede confirmacao ao usuario).", {"path": S}, ["path"]),
    _fn("run_command", "Executa um comando no PowerShell do Windows, na raiz do projeto (ou em cwd). "
        "Use para instalar dependencias, compilar, testar e rodar scripts que terminam sozinhos. "
        "NAO inicie servidores ou programas que ficam rodando para sempre.",
        {"command": S, "cwd": S | {"description": "Subpasta relativa onde rodar"},
         "timeout": I | {"description": "Segundos (padrao 120, maximo 900)"}}, ["command"]),
]
IMAGE_TOOL = _fn("generate_image", "Gera uma imagem PNG a partir de uma descricao (em ingles funciona melhor) e "
                 "salva no projeto. Use para icones, ilustracoes, texturas e assets.",
                 {"prompt": S, "path": S | {"description": "Caminho do PNG a criar, ex.: assets/logo.png"},
                  "width": I, "height": I}, ["prompt", "path"])


KB_TOOL = _fn("search_knowledge", "Procura trechos relevantes na base de conhecimento do usuario (documentacao, specs, "
              "codigo de referencia). Use antes de decidir como implementar algo e sempre que precisar de um detalhe "
              "dos documentos. Pode chamar varias vezes com consultas diferentes e especificas.",
              {"query": S | {"description": "O que procurar, em linguagem natural (ex.: 'como o login valida o token')"}},
              ["query"])


def system_prompt(root, has_image_tool):
    return f"""Voce e o Codex do Piphin LLM, um engenheiro de software autonomo trabalhando no computador do usuario.

Ambiente:
- Sistema: Windows. Comandos rodam no PowerShell (use sintaxe do PowerShell, nao bash).
- Pasta do projeto (raiz): {root}
- Todos os caminhos das ferramentas sao RELATIVOS a essa pasta; voce nao tem acesso fora dela.
- Data de hoje: {datetime.now():%d/%m/%Y}.

Como trabalhar:
1. Entenda o pedido. Se o projeto ja existe, use list_files e read_file antes de alterar.
2. Planeje rapidamente e execute em passos, usando as ferramentas. Nao peca permissao para cada passo: faca.
3. Escreva arquivos COMPLETOS e funcionais (nada de "resto do codigo aqui"). Para mudancas pequenas, use edit_file.
4. Quando fizer sentido, rode comandos para instalar dependencias, compilar e testar, e corrija os erros que aparecerem.
5. Nunca rode servidores ou programas interativos que nao terminam sozinhos; explique ao usuario como inicia-los.
6. Ao terminar, responda com um resumo curto do que foi feito, arquivos criados e como executar.
{"7. Para criar imagens (icones, ilustracoes, texturas), use generate_image." if has_image_tool else ""}
Responda no idioma do usuario."""


def mcp_prompt(servers, has_workspace):
    """Instrucoes extras quando o Codex tem ferramentas MCP (ex.: Roblox Studio)."""
    if not servers:
        return ""
    lines = ["", "Ferramentas externas (MCP): as ferramentas com nome mcp__<servidor>__<acao> controlam outros programas "
             "do usuario. Use-as quando o pedido envolver esses programas."]
    for s in servers:
        lines.append(f"- {s.cfg['name']}" + (f": {s.instructions}" if s.instructions else ""))
        if s.cfg["id"] == "roblox" or "roblox" in s.cfg["name"].lower():
            lines.append("  Dicas para o Roblox Studio: o codigo e Luau. Antes de alterar, consulte o jogo (ex.: liste os "
                         "filhos de workspace/ServerScriptService com run_code e print). Para criar ou editar scripts, "
                         "use run_code definindo a propriedade Source. Depois de alterar, teste com o modo Play e leia o "
                         "console (get_console_output) para corrigir erros. Volte ao modo de edicao ao terminar.")
    if not has_workspace:
        lines.append("Neste pedido NAO ha pasta de projeto: trabalhe apenas com as ferramentas externas.")
    return "\n".join(lines)


def system_prompt_mcp_only():
    return f"""Voce e o Codex do Piphin LLM, um agente autonomo trabalhando no computador do usuario.
- Sistema: Windows. Data de hoje: {datetime.now():%d/%m/%Y}.
- Nao ha pasta de projeto neste pedido; voce so tem as ferramentas externas listadas abaixo.
Como trabalhar: entenda o pedido, consulte o estado atual antes de alterar, execute em passos sem pedir permissao para
cada um, confira o resultado e corrija os erros. Ao terminar, responda com um resumo curto do que foi feito.
Responda no idioma do usuario."""


# ---------------------------------------------------------------- execucao das ferramentas

class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ToolError(f"Pasta do projeto nao existe: {self.root}")

    def path(self, rel):
        rel = (rel or ".").strip().strip('"').replace("\\", "/")
        p = Path(rel)
        p = (p if p.is_absolute() else self.root / p).resolve()
        if p != self.root and self.root not in p.parents:
            raise ToolError("Acesso negado: caminho fora da pasta do projeto.")
        return p

    def rel(self, p):
        return Path(p).relative_to(self.root).as_posix() or "."


def _read_text(p):
    data = p.read_bytes()
    if b"\0" in data[:8000]:
        raise ToolError("Arquivo binario: nao e possivel ler como texto.")
    for enc in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def tool_list_files(ws, path=".", max_depth=3):
    base = ws.path(path)
    if not base.is_dir():
        raise ToolError("Nao e uma pasta.")
    max_depth = max(1, min(int(max_depth or 3), 6))
    lines, count = [], 0

    def walk(d, depth, prefix):
        nonlocal count
        try:
            entries = sorted(d.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except OSError:
            return
        for e in entries:
            if count >= 500:
                return
            count += 1
            if e.is_dir():
                if e.name in SKIP_DIRS:
                    lines.append(f"{prefix}{e.name}/ (ignorada)")
                    continue
                lines.append(f"{prefix}{e.name}/")
                if depth < max_depth:
                    walk(e, depth + 1, prefix + "  ")
            else:
                size = e.stat().st_size
                lines.append(f"{prefix}{e.name} ({size // 1024} KB)" if size >= 1024 else f"{prefix}{e.name}")

    walk(base, 1, "")
    if not lines:
        return "(pasta vazia)"
    return "\n".join(lines) + ("\n... (lista cortada em 500 itens)" if count >= 500 else "")


def tool_read_file(ws, path, start_line=None, end_line=None):
    p = ws.path(path)
    if not p.is_file():
        raise ToolError("Arquivo nao encontrado.")
    lines = _read_text(p).splitlines()
    a = max(1, int(start_line or 1))
    b = min(len(lines), int(end_line or len(lines)))
    out, size = [], 0
    for i in range(a, b + 1):
        row = f"{i:>5}| {lines[i - 1]}"
        size += len(row)
        if size > MAX_READ_CHARS:
            out.append(f"... (cortado; o arquivo tem {len(lines)} linhas. Leia a partir da linha {i})")
            break
        out.append(row)
    return "\n".join(out) if out else "(arquivo vazio)"


def tool_write_file(ws, path, content):
    p = ws.path(path)
    existed = p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, "utf-8", newline="")
    n = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    return f"{'Atualizado' if existed else 'Criado'}: {ws.rel(p)} ({n} linhas)"


def tool_edit_file(ws, path, old_text, new_text, replace_all=False):
    p = ws.path(path)
    if not p.is_file():
        raise ToolError("Arquivo nao encontrado.")
    text = _read_text(p)
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")
        old_text, new_text = old_text.replace("\r\n", "\n"), new_text.replace("\r\n", "\n")
    n = text.count(old_text)
    if n == 0:
        raise ToolError("old_text nao encontrado. Leia o arquivo de novo e copie o trecho exatamente.")
    if n > 1 and not replace_all:
        raise ToolError(f"old_text aparece {n} vezes. Inclua mais contexto ou use replace_all.")
    text = text.replace(old_text, new_text) if replace_all else text.replace(old_text, new_text, 1)
    p.write_text(text.replace("\n", "\r\n") if crlf else text, "utf-8", newline="")
    return f"Editado: {ws.rel(p)} ({n if replace_all else 1} substituicao)"


def tool_search_files(ws, pattern, path=".", glob="*"):
    base = ws.path(path)
    try:
        rx = re.compile(pattern, re.I)
    except re.error as e:
        raise ToolError(f"Expressao regular invalida: {e}")
    hits = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not Path(f).match(glob or "*"):
                continue
            fp = Path(root) / f
            try:
                if fp.stat().st_size > 2_000_000:
                    continue
                for i, line in enumerate(_read_text(fp).splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{ws.rel(fp)}:{i}: {line.strip()[:200]}")
                        if len(hits) >= 200:
                            return "\n".join(hits) + "\n... (limite de 200 resultados)"
            except (ToolError, OSError):
                continue
    return "\n".join(hits) or "Nenhum resultado."


def tool_delete_path(ws, path):
    p = ws.path(path)
    if p == ws.root:
        raise ToolError("Nao e permitido apagar a raiz do projeto.")
    if p.is_dir():
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()
    else:
        raise ToolError("Caminho nao existe.")
    return f"Apagado: {ws.rel(p)}"


def _trim_output(s):
    if len(s) <= MAX_OUTPUT:
        return s
    half = MAX_OUTPUT // 2
    return s[:half] + f"\n\n... ({len(s) - MAX_OUTPUT} caracteres omitidos) ...\n\n" + s[-half:]


def tool_run_command(ws, command, cwd=None, timeout=120, heartbeat=None):
    d = ws.path(cwd or ".")
    timeout = max(5, min(int(timeout or 120), 900))
    proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command],
                            cwd=str(d), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            creationflags=NO_WINDOW)
    chunks = []
    reader = threading.Thread(target=lambda: chunks.append(proc.stdout.read()), daemon=True)
    reader.start()
    start = time.time()
    timed_out = False
    while proc.poll() is None:
        if time.time() - start > timeout:
            timed_out = True
            break
        if heartbeat and not heartbeat():
            timed_out = None  # usuario cancelou
            break
        time.sleep(0.5)
    if proc.poll() is None:
        subprocess.run(["taskkill", "/pid", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
    reader.join(5)
    out = (chunks[0] if chunks else b"").decode("utf-8", "replace").replace("\r\n", "\n").strip()
    if timed_out is None:
        raise ToolError("Comando interrompido pelo usuario.")
    head = f"[codigo de saida: {proc.returncode}]" if not timed_out else f"[tempo esgotado apos {timeout}s; processo encerrado]"
    return head + ("\n" + _trim_output(out) if out else "\n(sem saida)")


# ---------------------------------------------------------------- pontos de restauracao
# Antes do Codex alterar um arquivo pela primeira vez num pedido, a versao original e copiada para
# data/checkpoints/<conversa>/<pedido>/. "Desfazer" devolve tudo como estava antes do pedido.
# Comandos (run_command) nao sao desfeitos: o que um comando faz fora das ferramentas nao e rastreado.

MAX_DIR_BACKUP = 300 * 1024 * 1024


class Checkpoint:
    def __init__(self, folder, workspace_root):
        self.dir = Path(folder)
        self.ws = Path(workspace_root)
        self.entries = {}

    def touch(self, abs_path):
        """Guarda o estado original de abs_path (uma vez por pedido)."""
        abs_path = Path(abs_path)
        rel = abs_path.relative_to(self.ws).as_posix()
        if rel in self.entries:
            return
        files = self.dir / "files"
        if abs_path.is_file():
            dest = files / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(abs_path, dest)
            entry = {"path": rel, "existed": True, "kind": "file"}
        elif abs_path.is_dir():
            size = sum(f.stat().st_size for f in abs_path.rglob("*") if f.is_file())
            if size > MAX_DIR_BACKUP:
                raise ToolError("Pasta grande demais para guardar um ponto de restauração; apague por partes.")
            shutil.copytree(abs_path, files / rel)
            entry = {"path": rel, "existed": True, "kind": "dir"}
        else:
            entry = {"path": rel, "existed": False, "kind": "file"}
        self.entries[rel] = entry
        self.save()

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "manifest.json").write_text(json.dumps({
            "workspace": str(self.ws), "created": time.time(), "undone": False,
            "entries": list(self.entries.values())}, ensure_ascii=False, indent=1), "utf-8")

    def summary(self):
        out = []
        for e in self.entries.values():
            now = (self.ws / e["path"]).exists()
            status = ("modified" if now else "deleted") if e["existed"] else ("created" if now else None)
            if status:
                out.append({"path": e["path"], "status": status})
        return out


def _manifest(folder):
    m = json.loads((Path(folder) / "manifest.json").read_text("utf-8"))
    return m, Path(m["workspace"])


def undo_checkpoint(folder):
    """Devolve os arquivos ao estado de antes do pedido. Retorna o que foi restaurado."""
    folder = Path(folder)
    m, ws = _manifest(folder)
    if m.get("undone"):
        raise ToolError("Este pedido já foi desfeito.")
    done = []
    for e in m["entries"]:
        target = (ws / e["path"]).resolve()
        if ws.resolve() not in target.parents:
            continue
        backup = folder / "files" / e["path"]
        if e["existed"]:
            if e["kind"] == "dir":
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(backup, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
            done.append({"path": e["path"], "action": "restaurado"})
        elif target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            done.append({"path": e["path"], "action": "removido"})
    m["undone"] = True
    (folder / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), "utf-8")
    return done


def _lines(p):
    try:
        data = Path(p).read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8000]:
        return "BIN"
    return data.decode("utf-8", "replace").replace("\r\n", "\n").splitlines(keepends=True)


def diff_checkpoint(folder, max_lines=600):
    """Diferencas entre o estado de antes do pedido e o atual, arquivo por arquivo."""
    folder = Path(folder)
    m, ws = _manifest(folder)
    out = []
    for e in m["entries"]:
        cur_path, old_path = ws / e["path"], folder / "files" / e["path"]
        if e["kind"] == "dir":
            out.append({"path": e["path"], "status": "deleted" if not cur_path.exists() else "modified", "diff": "(pasta)"})
            continue
        old = _lines(old_path) if e["existed"] else []
        new = _lines(cur_path) if cur_path.exists() else []
        status = ("modified" if cur_path.exists() else "deleted") if e["existed"] else ("created" if cur_path.exists() else None)
        if not status:
            continue
        if old == "BIN" or new == "BIN":
            out.append({"path": e["path"], "status": status, "diff": "(arquivo binário)"})
            continue
        d = list(difflib.unified_diff(old or [], new or [], f"antes/{e['path']}", f"depois/{e['path']}", n=3))
        text = "".join(d[:max_lines]) + (f"\n... (+{len(d) - max_lines} linhas)" if len(d) > max_lines else "")
        out.append({"path": e["path"], "status": status, "diff": text or "(sem diferenças)",
                    "added": sum(1 for l in d if l.startswith("+") and not l.startswith("+++")),
                    "removed": sum(1 for l in d if l.startswith("-") and not l.startswith("---"))})
    return {"undone": m.get("undone", False), "files": out}


# ---------------------------------------------------------------- loop do agente

def wait_approval(call_id, send_event, ping, pending):
    """Pede confirmacao pela interface e espera (ate 10 min). Retorna o dict da resposta ou None se desconectou."""
    ev = threading.Event()
    pending[call_id] = {"event": ev, "answer": None}
    send_event()
    try:
        for _ in range(1200):
            if ev.wait(0.5):
                break
            if not ping():
                return None
        return pending[call_id]["answer"] or {"ok": False}
    finally:
        pending.pop(call_id, None)


class AgentRun:
    """Executa uma resposta do Codex. emit(evento) envia SSE; retorna False se o cliente desconectou."""

    PENDING = {}  # id -> {"event": Event, "answer": dict}
    SESSION_AUTO = {}  # chat_id -> {"commands": bool, "files": bool}

    def __init__(self, engine_call, emit, settings, image_fn=None, checkpoint_dir=None, mcp_ids=(), save_image=None,
                 kb_fn=None, kb_name=""):
        self.engine_call, self.emit, self.s, self.image_fn = engine_call, emit, settings, image_fn
        self.checkpoint_dir = checkpoint_dir
        self.mcp_ids, self.save_image, self.mcp_map = list(mcp_ids or ()), save_image, {}
        self.kb_fn, self.kb_name = kb_fn, kb_name
        self.ckpt = None
        self.alive = True

    def send(self, obj):
        if self.alive:
            self.alive = self.emit(obj)
        return self.alive

    # -- confirmacao
    def needs_approval(self, name, chat_id):
        auto = self.SESSION_AUTO.get(chat_id, {})
        if name in self.mcp_map:
            srv, tool = self.mcp_map[name]
            return mcp.needs_approval(srv, tool) and not auto.get("mcp:" + srv.cfg["id"])
        if name == "run_command":
            return self.s.get("agent_confirm_commands", True) and not auto.get("commands")
        if name == "delete_path":
            return not auto.get("files")
        if name in ("write_file", "edit_file"):
            return self.s.get("agent_confirm_writes", False) and not auto.get("files")
        return False

    def ask(self, call_id, name, args, chat_id):
        ans = wait_approval(call_id, lambda: self.send({"agent": {"type": "approval", "id": call_id, "name": name, "args": args}}),
                            self.send_ping, self.PENDING)
        if ans is None:
            return False
        if ans.get("ok") and ans.get("always"):
            kind = ("mcp:" + self.mcp_map[name][0].cfg["id"]) if name in self.mcp_map else \
                "commands" if name == "run_command" else "files"
            self.SESSION_AUTO.setdefault(chat_id, {})[kind] = True
        return bool(ans.get("ok"))

    def send_ping(self):
        if self.alive:
            self.alive = self.emit(None)  # comentario SSE, so para detectar desconexao
        return self.alive

    @classmethod
    def answer(cls, call_id, ok, always=False):
        p = cls.PENDING.get(call_id)
        if p:
            p["answer"] = {"ok": ok, "always": always}
            p["event"].set()
            return True
        return False

    # -- ferramentas
    def execute(self, ws, name, args):
        if name == "search_knowledge" and self.kb_fn:
            return self.kb_fn(args.get("query", ""))
        if name in self.mcp_map:
            srv, tool = self.mcp_map[name]
            try:
                res = srv.call(tool["name"], args, ping=self.send_ping)
            except mcp.MCPError as e:
                raise ToolError(str(e)) from e
            text, images = mcp.result_text(res, self.save_image)
            return {"text": text, "image": images[0]} if images else text
        if ws is None:
            raise ToolError(f"Ferramenta indisponivel sem pasta de projeto: {name}")
        # guarda o estado original antes de qualquer alteracao (para "Desfazer")
        if self.ckpt and name in ("write_file", "edit_file", "delete_path") and args.get("path"):
            self.ckpt.touch(ws.path(args["path"]))
        if name == "list_files":
            return tool_list_files(ws, args.get("path", "."), args.get("max_depth", 3))
        if name == "read_file":
            return tool_read_file(ws, args["path"], args.get("start_line"), args.get("end_line"))
        if name == "write_file":
            return tool_write_file(ws, args["path"], args.get("content", ""))
        if name == "edit_file":
            return tool_edit_file(ws, args["path"], args["old_text"], args.get("new_text", ""), args.get("replace_all", False))
        if name == "search_files":
            return tool_search_files(ws, args["pattern"], args.get("path", "."), args.get("glob", "*"))
        if name == "delete_path":
            return tool_delete_path(ws, args["path"])
        if name == "run_command":
            return tool_run_command(ws, args["command"], args.get("cwd"), args.get("timeout", 120), self.send_ping)
        if name == "generate_image" and self.image_fn:
            dest = ws.path(args["path"])
            if dest.suffix.lower() != ".png":
                dest = dest.with_suffix(".png")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if self.ckpt:
                self.ckpt.touch(dest)
            fid = self.image_fn(args["prompt"], args.get("width"), args.get("height"), dest)
            return {"text": f"Imagem criada: {ws.rel(dest)}", "image": fid}
        raise ToolError(f"Ferramenta desconhecida: {name}")

    # -- loop
    def run(self, workspace, history, chat_id, sampling):
        ws = Workspace(workspace) if workspace else None
        if self.checkpoint_dir and ws:
            self.ckpt = Checkpoint(self.checkpoint_dir, ws.root)
        try:
            return self._run(ws, history, chat_id, sampling)
        finally:
            if self.ckpt and self.ckpt.entries:
                self.send({"agent": {"type": "checkpoint", "id": self.ckpt.dir.name, "changes": self.ckpt.summary()}})

    def _run(self, ws, history, chat_id, sampling):
        tools = (TOOLS + ([IMAGE_TOOL] if self.image_fn else [])) if ws else []
        if self.kb_fn:
            tools.append(KB_TOOL)
            self.send({"agent": {"type": "notice", "text": f"📚 Base de conhecimento: {self.kb_name}"}})
        servers = []
        if self.mcp_ids:
            self.send({"agent": {"type": "notice", "text": "🔌 Conectando às ferramentas MCP..."}})
            mtools, self.mcp_map = mcp.MANAGER.toolset(
                self.mcp_ids, self.send_ping,
                lambda name, err: self.send({"agent": {"type": "notice", "level": "error", "text": f"⚠ {err}"}}))
            tools += mtools
            servers = list({id(s): s for s, _ in self.mcp_map.values()}.values())
            self.send({"agent": {"type": "notice", "text": "🔌 " + ", ".join(
                f"{s.cfg['name']} ({len(s.tools)} ferramentas)" for s in servers)}} if servers else
                {"agent": {"type": "notice", "level": "error", "text": "⚠ Nenhuma ferramenta MCP disponível."}})
        rea_cli = ws is not None and rea.installed() and self.s.get("rea_codex", True)
        if rea_cli:
            self.send({"agent": {"type": "notice", "text": "🔬 REA disponível (engenharia reversa, sem internet)"}})
        if not tools:
            raise ToolError("Sem ferramentas: escolha uma pasta de projeto ou conecte um servidor MCP.")
        sp = (system_prompt(ws.root, bool(self.image_fn)) if ws else system_prompt_mcp_only()) + \
            mcp_prompt(servers, bool(ws)) + ("\n\n" + rea.cli_prompt() if rea_cli else "") + \
            (f"\n\nBase de conhecimento \"{self.kb_name}\": use search_knowledge para consultar os documentos do usuario "
             "antes de implementar e quando precisar de detalhes. Cite os trechos usados como [D1], [D2]." if self.kb_fn else "") + \
            ("\n" + self.s["_reply_rule"] if self.s.get("_reply_rule") else "")
        messages = [{"role": "system", "content": sp}] + history
        trace, last_timings = [], None
        max_steps = max(1, min(int(self.s.get("agent_max_steps") or 40), 200))
        for step in range(max_steps):
            payload = {"messages": messages, "tools": tools, "tool_choice": "auto", "stream": True,
                       "cache_prompt": True, "timings_per_token": True, "parallel_tool_calls": True, **sampling}
            content, calls = "", {}
            with self.engine_call(payload) as up:
                for raw in iter(up.readline, b""):
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:") or line == "data: [DONE]":
                        continue
                    try:
                        j = json.loads(line[5:])
                    except ValueError:
                        continue
                    if j.get("timings"):
                        last_timings = j["timings"]
                        self.send({"timings": j["timings"]})
                    ch = (j.get("choices") or [{}])[0]
                    d = ch.get("delta") or {}
                    if d.get("reasoning_content"):
                        self.send({"agent": {"type": "reasoning", "delta": d["reasoning_content"]}})
                    if d.get("content"):
                        content += d["content"]
                        self.send({"agent": {"type": "text", "delta": d["content"]}})
                    for tc in d.get("tool_calls") or []:
                        c = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                        c["id"] = tc.get("id") or c["id"]
                        fn = tc.get("function") or {}
                        c["name"] += fn.get("name") or ""
                        c["arguments"] += fn.get("arguments") or ""
                    if not self.alive:
                        return trace, last_timings
            tool_calls = []
            for i in sorted(calls):
                c = calls[i]
                tool_calls.append({"id": c["id"] or f"call_{uuid.uuid4().hex[:12]}", "type": "function",
                                   "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}})
            msg = {"role": "assistant", "content": content}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            messages.append(msg)
            trace.append(msg)
            if not tool_calls:
                break
            self.send({"agent": {"type": "step_end"}})
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                    if not isinstance(args, dict):
                        raise ValueError
                except ValueError:
                    args, result, ok = {}, "Erro: argumentos JSON invalidos. Tente de novo.", False
                else:
                    result, ok = None, True
                self.send({"agent": {"type": "tool_start", "id": tc["id"], "name": name, "args": _preview_args(args)}})
                extra = {}
                if result is None:
                    if self.needs_approval(name, chat_id):
                        allowed = self.ask(tc["id"], name, _preview_args(args), chat_id)
                        if not self.alive:
                            return trace, last_timings
                        if not allowed:
                            result, ok = "O usuario NEGOU esta acao. Nao tente de novo; siga sem ela ou pergunte o que ele prefere.", False
                    if result is None:
                        try:
                            r = self.execute(ws, name, args)
                            if isinstance(r, dict):
                                extra = {"image": r["image"]}
                                r = r["text"]
                            result = r
                        except ToolError as e:
                            result, ok = f"Erro: {e}", False
                        except (OSError, KeyError, TypeError, ValueError, RuntimeError) as e:
                            result, ok = f"Erro: {type(e).__name__}: {e}", False
                if not self.alive:
                    return trace, last_timings
                tmsg = {"role": "tool", "tool_call_id": tc["id"], "content": result}
                messages.append(tmsg)
                trace.append(tmsg)
                self.send({"agent": {"type": "tool_end", "id": tc["id"], "ok": ok, "result": _trim_output(result)[:6000], **extra}})
        else:
            self.send({"agent": {"type": "text", "delta": f"\n\n_(Parei após {max_steps} passos. Peça para continuar se quiser.)_"}})
        return trace, last_timings


def _preview_args(args):
    """Argumentos para mostrar na interface (conteudos longos resumidos)."""
    out = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 4000:
            out[k] = v[:4000] + f"\n... (+{len(v) - 4000} caracteres)"
        else:
            out[k] = v
    return out


def compact_history(trace_msgs, keep_full):
    """Converte o trace salvo de respostas antigas, encurtando resultados longos de ferramentas."""
    out = []
    for m in trace_msgs:
        m = dict(m)
        if m.get("role") == "tool" and not keep_full and len(m.get("content") or "") > 1500:
            m["content"] = m["content"][:1500] + "\n... (resultado antigo encurtado)"
        if m.get("role") == "assistant" and m.get("tool_calls") and not keep_full:
            calls = []
            for tc in m["tool_calls"]:
                tc = json.loads(json.dumps(tc))
                if len(tc["function"].get("arguments") or "") > 3000:
                    try:
                        a = json.loads(tc["function"]["arguments"])
                        for k in ("content", "new_text", "old_text"):
                            if isinstance(a.get(k), str) and len(a[k]) > 500:
                                a[k] = a[k][:500] + "... (encurtado)"
                        tc["function"]["arguments"] = json.dumps(a, ensure_ascii=False)
                    except ValueError:
                        pass
                calls.append(tc)
            m["tool_calls"] = calls
        out.append(m)
    return out
