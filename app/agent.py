"""Codex do LLM Local: agente de programacao que trabalha SOMENTE dentro das
pastas que o usuario liberou nas Configuracoes.

O modelo usa "tool calling" (llama-server com --jinja). Cada ferramenta valida
o caminho; comandos e exclusoes pedem confirmacao do usuario pela interface.
"""
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


def system_prompt(root, has_image_tool):
    return f"""Voce e o Codex do LLM Local, um engenheiro de software autonomo trabalhando no computador do usuario.

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


# ---------------------------------------------------------------- loop do agente

class AgentRun:
    """Executa uma resposta do Codex. emit(evento) envia SSE; retorna False se o cliente desconectou."""

    PENDING = {}  # id -> {"event": Event, "answer": dict}
    SESSION_AUTO = {}  # chat_id -> {"commands": bool, "files": bool}

    def __init__(self, engine_call, emit, settings, image_fn=None):
        self.engine_call, self.emit, self.s, self.image_fn = engine_call, emit, settings, image_fn
        self.alive = True

    def send(self, obj):
        if self.alive:
            self.alive = self.emit(obj)
        return self.alive

    # -- confirmacao
    def needs_approval(self, name, chat_id):
        auto = self.SESSION_AUTO.get(chat_id, {})
        if name == "run_command":
            return self.s.get("agent_confirm_commands", True) and not auto.get("commands")
        if name == "delete_path":
            return not auto.get("files")
        if name in ("write_file", "edit_file"):
            return self.s.get("agent_confirm_writes", False) and not auto.get("files")
        return False

    def ask(self, call_id, name, args, chat_id):
        ev = threading.Event()
        self.PENDING[call_id] = {"event": ev, "answer": None}
        self.send({"agent": {"type": "approval", "id": call_id, "name": name, "args": args}})
        try:
            for _ in range(1200):  # ate 10 minutos
                if ev.wait(0.5):
                    break
                if not self.send_ping():
                    return False
            ans = self.PENDING[call_id]["answer"] or {"ok": False}
        finally:
            self.PENDING.pop(call_id, None)
        if ans.get("ok") and ans.get("always"):
            kind = "commands" if name == "run_command" else "files"
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
            fid = self.image_fn(args["prompt"], args.get("width"), args.get("height"), dest)
            return {"text": f"Imagem criada: {ws.rel(dest)}", "image": fid}
        raise ToolError(f"Ferramenta desconhecida: {name}")

    # -- loop
    def run(self, workspace, history, chat_id, sampling):
        ws = Workspace(workspace)
        tools = TOOLS + ([IMAGE_TOOL] if self.image_fn else [])
        messages = [{"role": "system", "content": system_prompt(ws.root, bool(self.image_fn))}] + history
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
