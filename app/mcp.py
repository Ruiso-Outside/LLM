"""Cliente MCP (Model Context Protocol) do LLM Local.

Conecta o Codex e os agentes a ferramentas de outros programas, como o Roblox Studio
(ler e alterar o jogo, rodar testes, ler o console). Suporta servidores locais (stdio:
o app abre o programa e conversa por stdin/stdout) e remotos (HTTP "streamable").

Configuracao em data/mcp.json. As ferramentas aparecem para o modelo como
mcp__<servidor>__<ferramenta>.
"""
import base64
import json
import os
import re
import shlex
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

PROTOCOL = "2025-06-18"
CLIENT_INFO = {"name": "LLM Local", "version": "1"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ID_RE = re.compile(r"^[a-z0-9_]{1,20}$")
PREFIX = "mcp__"
FILE = None


class MCPError(Exception):
    pass


def configure(data_dir):
    global FILE
    FILE = Path(data_dir) / "mcp.json"


# ---------------------------------------------------------------- configuracao

def roblox_bat():
    """Caminho do mcp.bat que o Roblox Studio instala (None se nao estiver instalado)."""
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "Roblox" / "mcp.bat"
    return p if p.is_file() else None


def preset(kind):
    if kind == "roblox":
        bat = roblox_bat()
        if not bat:
            raise MCPError("Roblox Studio não encontrado neste PC (falta %LOCALAPPDATA%\\Roblox\\mcp.bat).")
        return {"id": "roblox", "name": "Roblox Studio", "type": "stdio", "command": "cmd.exe",
                "args": ["/c", str(bat)], "env": {}, "url": "", "enabled": True, "auto_approve": False}
    raise MCPError("modelo desconhecido")


def slug(name, taken=()):
    base = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")[:16] or "mcp"
    sid, n = base, 2
    while sid in taken:
        sid, n = f"{base}{n}", n + 1
    return sid


def split_command(line):
    """'npx -y pacote "C:\\minha pasta"' -> ('npx', ['-y', 'pacote', 'C:\\minha pasta'])."""
    parts = [p[1:-1] if len(p) > 1 and p[0] == p[-1] and p[0] in "\"'" else p
             for p in shlex.split(line or "", posix=False)]
    if not parts:
        raise MCPError("Informe o comando do servidor.")
    return parts[0], parts[1:]


def _clean(s, taken):
    typ = "http" if s.get("type") == "http" else "stdio"
    sid = s.get("id") if ID_RE.match(str(s.get("id") or "")) and s.get("id") not in taken else slug(s.get("name"), taken)
    out = {"id": sid, "name": str(s.get("name") or sid)[:60], "type": typ, "enabled": bool(s.get("enabled", True)),
           "auto_approve": bool(s.get("auto_approve")), "command": "", "args": [], "env": {}, "url": ""}
    if typ == "http":
        url = str(s.get("url") or "").strip()
        if not re.match(r"^https?://", url):
            raise MCPError(f"{out['name']}: endereço inválido (use http:// ou https://).")
        out["url"] = url
    else:
        if s.get("command_line") is not None:
            out["command"], out["args"] = split_command(s["command_line"])
        else:
            out["command"] = str(s.get("command") or "").strip()
            out["args"] = [str(a) for a in (s.get("args") or [])][:100]
        if not out["command"]:
            raise MCPError(f"{out['name']}: informe o comando.")
    env = s.get("env") or {}
    if isinstance(env, str):  # "CHAVE=valor" por linha
        env = dict(l.split("=", 1) for l in env.splitlines() if "=" in l)
    out["env"] = {str(k).strip(): str(v) for k, v in env.items() if str(k).strip()}
    return out


def load():
    try:
        return json.loads(FILE.read_text("utf-8")).get("servers", [])
    except (OSError, ValueError, AttributeError):
        return []


def save(servers):
    out, taken = [], set()
    for s in (servers or [])[:30]:
        c = _clean(s, taken)
        taken.add(c["id"])
        out.append(c)
    FILE.write_text(json.dumps({"servers": out}, ensure_ascii=False, indent=1), "utf-8")
    MANAGER.sync(out)
    return out


def command_line(s):
    return subprocess.list2cmdline([s["command"]] + s["args"]) if s.get("command") else ""


# ---------------------------------------------------------------- transportes

class StdioClient:
    """Servidor local: JSON-RPC, uma mensagem JSON por linha em stdin/stdout."""

    def __init__(self, cfg):
        self.cfg, self.proc, self.lock = cfg, None, threading.Lock()
        self.pending, self.next_id = {}, 1
        self.stderr = deque(maxlen=40)
        self.on_notify = None

    def start(self):
        env = dict(os.environ, **self.cfg.get("env", {}))
        try:
            self.proc = subprocess.Popen([self.cfg["command"]] + self.cfg["args"], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                         creationflags=NO_WINDOW)
        except OSError as e:
            raise MCPError(f"Não foi possível iniciar \"{command_line(self.cfg)}\": {e}") from e
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read_err(self):
        for raw in iter(self.proc.stderr.readline, b""):
            self.stderr.append(raw.decode("utf-8", "replace").rstrip())

    def _read(self):
        for raw in iter(self.proc.stdout.readline, b""):
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if "method" in msg:
                self._incoming(msg)
            elif msg.get("id") in self.pending:
                slot = self.pending[msg["id"]]
                slot["msg"] = msg
                slot["ev"].set()
        for slot in list(self.pending.values()):  # processo terminou
            slot["ev"].set()

    def _incoming(self, msg):
        if "id" not in msg:  # notificacao
            if self.on_notify:
                self.on_notify(msg["method"])
            return
        if msg["method"] == "ping":
            self._write({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
        else:
            self._write({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "não suportado"}})

    def _write(self, obj):
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        with self.lock:
            try:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
            except (OSError, ValueError) as e:
                raise MCPError("O servidor MCP fechou." + self._err_tail()) from e

    def _err_tail(self):
        tail = " | ".join(l for l in list(self.stderr)[-3:] if l)
        return f" ({tail[:300]})" if tail else ""

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def notify(self, method, params=None):
        self._write({"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})})

    def request(self, method, params=None, timeout=60, ping=None):
        with self.lock:
            rid = self.next_id
            self.next_id += 1
        slot = {"ev": threading.Event(), "msg": None}
        self.pending[rid] = slot
        try:
            self._write({"jsonrpc": "2.0", "id": rid, "method": method, **({"params": params} if params is not None else {})})
            end = time.time() + timeout
            while not slot["ev"].wait(0.5):
                if ping and not ping():
                    self._cancel(rid)
                    raise MCPError("cancelado")
                if time.time() > end:
                    self._cancel(rid)
                    raise MCPError(f"O servidor MCP não respondeu em {timeout}s.")
        finally:
            self.pending.pop(rid, None)
        if slot["msg"] is None:
            raise MCPError("O servidor MCP fechou." + self._err_tail())
        return _result(slot["msg"])

    def _cancel(self, rid):
        try:
            self.notify("notifications/cancelled", {"requestId": rid})
        except MCPError:
            pass

    def close(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            if os.name == "nt":  # cmd.exe /c ... deixa o programa filho rodando: encerra a arvore
                subprocess.run(["taskkill", "/pid", str(p.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
            else:
                p.kill()
        if p:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
            for f in (p.stdin, p.stdout, p.stderr):
                try:
                    f.close()
                except OSError:
                    pass


class HttpClient:
    """Servidor remoto (Streamable HTTP): cada mensagem e um POST; a resposta vem em JSON ou SSE."""

    def __init__(self, cfg):
        self.cfg, self.session, self.next_id, self.ok = cfg, None, 1, False
        self.on_notify = None

    def start(self):
        self.ok = True

    def alive(self):
        return self.ok

    def _post(self, obj, timeout):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.cfg["url"], data=json.dumps(obj).encode("utf-8"), headers=headers)
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            raise MCPError(f"HTTP {e.code}: {e.reason}") from e
        except (urllib.error.URLError, OSError) as e:
            raise MCPError(f"Sem conexão com {self.cfg['url']}: {e}") from e

    def notify(self, method, params=None):
        with self._post({"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}, 30):
            pass

    def request(self, method, params=None, timeout=60, ping=None):
        rid = self.next_id
        self.next_id += 1
        with self._post({"jsonrpc": "2.0", "id": rid, "method": method, **({"params": params} if params is not None else {})},
                        timeout) as r:
            self.session = r.headers.get("Mcp-Session-Id") or self.session
            if "text/event-stream" in (r.headers.get("Content-Type") or ""):
                for raw in iter(r.readline, b""):
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        msg = json.loads(line[5:])
                    except ValueError:
                        continue
                    if isinstance(msg, dict) and msg.get("id") == rid and "method" not in msg:
                        return _result(msg)
                raise MCPError("O servidor MCP encerrou a resposta sem resultado.")
            return _result(json.loads(r.read().decode("utf-8")))

    def close(self):
        self.ok = False


def _result(msg):
    if msg.get("error"):
        e = msg["error"]
        raise MCPError(f"{e.get('message', 'erro')} (código {e.get('code')})")
    return msg.get("result") or {}


# ---------------------------------------------------------------- conexao e ferramentas

class Server:
    def __init__(self, cfg):
        self.cfg = cfg
        self.client = None
        self.tools = []
        self.state, self.error, self.info, self.instructions = "parado", "", {}, ""
        self.lock = threading.Lock()

    def connect(self, ping=None):
        with self.lock:
            if self.client and self.client.alive() and self.state == "pronto":
                return self
            self._close()
            self.state, self.error = "conectando", ""
            c = HttpClient(self.cfg) if self.cfg["type"] == "http" else StdioClient(self.cfg)
            try:
                c.start()
                init = c.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": CLIENT_INFO},
                                 timeout=45, ping=ping)
                c.notify("notifications/initialized")
                self.info = init.get("serverInfo") or {}
                self.instructions = str(init.get("instructions") or "")[:3000]
                self.client = c
                c.on_notify = self._notified
                self.tools = self._list_tools(ping)
                self.state = "pronto"
            except MCPError as e:
                c.close()
                self.client, self.state, self.error = None, "erro", str(e)
                raise MCPError(f"{self.cfg['name']}: {e}") from e
        return self

    def _list_tools(self, ping=None):
        tools, cursor = [], None
        for _ in range(20):
            r = self.client.request("tools/list", {"cursor": cursor} if cursor else {}, timeout=45, ping=ping)
            tools += [t for t in r.get("tools") or [] if t.get("name")]
            cursor = r.get("nextCursor")
            if not cursor:
                break
        return tools

    def _notified(self, method):
        if method == "notifications/tools/list_changed":
            threading.Thread(target=self._refresh_tools, daemon=True).start()

    def _refresh_tools(self):
        try:
            self.tools = self._list_tools()
        except MCPError:
            pass

    def call(self, tool, args, timeout=300, ping=None):
        self.connect(ping)
        try:
            return self.client.request("tools/call", {"name": tool, "arguments": args or {}}, timeout=timeout, ping=ping)
        except MCPError:
            if not self.client or not self.client.alive():
                self.state = "erro"
            raise

    def empty_hint(self):
        hint = " Abra o Roblox Studio com um jogo (place) e tente de novo." if "roblox" in self.cfg["name"].lower() else ""
        return f"{self.cfg['name']}: conectado, mas sem ferramentas disponíveis.{hint}"

    def _close(self):
        if self.client:
            self.client.close()
        self.client = None

    def close(self):
        with self.lock:
            self._close()
            self.state = "parado"

    def public(self):
        err = self.error or (self.empty_hint() if self.state == "pronto" and not self.tools else "")
        return {**self.cfg, "command_line": command_line(self.cfg), "state": self.state, "error": err,
                "server_info": self.info,
                "tools": [{"name": t["name"], "description": (t.get("description") or "")[:300],
                           "read_only": bool((t.get("annotations") or {}).get("readOnlyHint"))} for t in self.tools]}


def tool_name(sid, tool):
    name = re.sub(r"[^A-Za-z0-9_-]", "_", f"{PREFIX}{sid}__{tool}")
    return name[:64]


class Manager:
    def __init__(self):
        self.servers = {}
        self.lock = threading.Lock()

    def sync(self, cfgs=None):
        """Aplica a configuracao: fecha servidores removidos ou alterados."""
        cfgs = load() if cfgs is None else cfgs
        with self.lock:
            new = {}
            for c in cfgs:
                old = self.servers.get(c["id"])
                same = old and {k: old.cfg.get(k) for k in ("type", "command", "args", "env", "url")} == \
                    {k: c.get(k) for k in ("type", "command", "args", "env", "url")}
                if same:
                    old.cfg = c
                    new[c["id"]] = old
                else:
                    if old:
                        old.close()
                    new[c["id"]] = Server(c)
            for sid, old in self.servers.items():
                if sid not in new:
                    old.close()
            self.servers = new

    def get(self, sid):
        if not self.servers and FILE:
            self.sync()
        return self.servers.get(sid)

    def all(self):
        if not self.servers and FILE:
            self.sync()
        return list(self.servers.values())

    def toolset(self, ids, ping=None, on_error=None):
        """Conecta aos servidores pedidos e devolve (ferramentas no formato OpenAI, mapa nome->(servidor, ferramenta))."""
        tools, mapping = [], {}
        for sid in ids:
            srv = self.get(sid)
            if not srv:
                continue
            try:
                fresh = srv.state != "pronto"
                srv.connect(ping)
                if not srv.tools and not fresh:  # ex.: Roblox Studio foi aberto depois: lista de novo
                    srv.tools = srv._list_tools(ping)
            except MCPError as e:
                if on_error:
                    on_error(srv.cfg["name"], str(e))
                continue
            if not srv.tools and on_error:
                on_error(srv.cfg["name"], srv.empty_hint())
            for t in srv.tools:
                name = tool_name(sid, t["name"])
                if name in mapping:
                    continue
                mapping[name] = (srv, t)
                schema = t.get("inputSchema") or {"type": "object", "properties": {}}
                if schema.get("type") != "object":
                    schema = {"type": "object", "properties": {}}
                desc = f"[{srv.cfg['name']}] " + (t.get("description") or t.get("title") or t["name"])
                tools.append({"type": "function", "function": {"name": name, "description": desc[:1500], "parameters": schema}})
        return tools, mapping

    def stop(self):
        for s in list(self.servers.values()):
            s.close()


MANAGER = Manager()


def needs_approval(srv, tool):
    """Ferramentas so de leitura (readOnlyHint) e servidores marcados como confiaveis nao pedem confirmacao."""
    return not srv.cfg.get("auto_approve") and not (tool.get("annotations") or {}).get("readOnlyHint")


def result_text(res, save_image=None, limit=20_000):
    """Converte o resultado de tools/call em texto para o modelo. Imagens sao salvas (save_image) se possivel."""
    texts, images = [], []
    for c in res.get("content") or []:
        typ = c.get("type")
        if typ == "text":
            texts.append(c.get("text", ""))
        elif typ == "image" and c.get("data"):
            fid = None
            if save_image:
                try:
                    fid = save_image(base64.b64decode(c["data"]), c.get("mimeType") or "image/png")
                except (ValueError, OSError):
                    fid = None
            images.append(fid)
            texts.append("[imagem retornada pela ferramenta]")
        elif typ == "resource":
            r = c.get("resource") or {}
            texts.append(r.get("text") or f"[recurso {r.get('uri', '')}]")
        elif typ == "resource_link":
            texts.append(f"[link: {c.get('uri', '')}]")
        elif typ == "audio":
            texts.append("[áudio retornado pela ferramenta]")
    if not texts and res.get("structuredContent") is not None:
        texts.append(json.dumps(res["structuredContent"], ensure_ascii=False))
    text = "\n".join(t for t in texts if t) or "(sem saída)"
    if len(text) > limit:
        text = text[:limit] + f"\n... (+{len(text) - limit} caracteres)"
    if res.get("isError"):
        text = "Erro da ferramenta: " + text
    return text, [i for i in images if i]
