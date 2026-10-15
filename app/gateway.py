"""API local do Piphin LLM para outros programas (Visual Studio, VS Code, Unreal Engine, scripts...).

Fala dois "idiomas" na mesma porta (padrao 11434, a mesma do Ollama):
- Ollama: /api/tags, /api/show, /api/chat, /api/generate, /api/embed, /api/ps, /api/version
- OpenAI: /v1/models, /v1/chat/completions, /v1/completions, /v1/embeddings
Os pedidos vao para os modelos do Piphin LLM (carregados sob demanda). So aceita conexoes do proprio PC,
bloqueia paginas da web e pode exigir uma chave (Authorization: Bearer <chave> ou X-API-Key).
"""
import base64
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

OLLAMA_VERSION = "0.12.6"  # versao do Ollama que anunciamos para os clientes
ALIASES = {"piphin-chat": "chat", "piphin-codex": "codex", "piphin-agentes": "agents"}
SAMPLING = {"temperature": "temperature", "top_p": "top_p", "top_k": "top_k", "min_p": "min_p",
            "repeat_penalty": "repeat_penalty", "num_predict": "max_tokens", "seed": "seed", "stop": "stop"}


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Gateway:
    """Liga, desliga e reinicia a API conforme as configuracoes."""

    def __init__(self):
        self.httpd, self.port, self.error, self.S = None, 0, "", None
        self.lock = threading.Lock()

    def configure(self, server_module):
        self.S = server_module

    def apply(self):
        s = self.S.load_settings()
        want = int(s.get("api_port") or 11434) if s.get("api_enabled") else 0
        with self.lock:
            if self.httpd and want == self.port:
                return
            self._stop()
            if not want:
                return
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", want), make_handler(self.S))
            except OSError as e:
                self.error = f"A porta {want} já está em uso (o Ollama ou outro programa está aberto?): {e.strerror or e}"
                return
            self.httpd.daemon_threads = True
            self.port, self.error = want, ""
            threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
            self.S.diag_log(f"API local ligada em http://127.0.0.1:{want}")

    def _stop(self):
        if self.httpd:
            h, self.httpd = self.httpd, None
            threading.Thread(target=lambda: (h.shutdown(), h.server_close()), daemon=True).start()
        self.port = 0

    def stop(self):
        with self.lock:
            self._stop()

    def status(self):
        s = self.S.load_settings()
        return {"enabled": bool(s.get("api_enabled")), "running": bool(self.httpd), "port": self.port or int(s.get("api_port") or 11434),
                "error": self.error, "require_key": bool(s.get("api_require_key")), "key": s.get("api_key", ""),
                "models": [m["name"] for m in model_list(self.S)]}


GATEWAY = Gateway()


# ---------------------------------------------------------------- modelos com nomes no estilo do Ollama

def ollama_name(rel):
    return re.sub(r"[^a-z0-9._-]+", "-", Path(rel).stem.lower()).strip("-") + ":latest"


def model_list(S):
    """Modelos para os clientes: os apelidos dos modos e todos os modelos baixados."""
    s = S.load_settings()
    mm = s.get("mode_models") or {}
    out = []
    for alias, mode in ALIASES.items():
        rel = mm.get(mode) or S.ENGINE_PROC.model or s.get("last_model", "")
        if rel and (S.MODELS / rel).is_file():
            out.append({"name": alias + ":latest", "rel": rel, "alias": True})
    for m in S.list_models():
        out.append({"name": ollama_name(m["path"]), "rel": m["path"], "alias": False, "info": m})
    return out


def resolve(S, name):
    """Nome pedido pelo cliente -> caminho do modelo ('' = o principal carregado)."""
    name = (name or "").strip().lower()
    base = name.split(":")[0]
    for m in model_list(S):
        if m["name"] == name or m["name"].split(":")[0] == base or Path(m["rel"]).stem.lower() == base or m["rel"].lower() == name:
            return m["rel"]
    return ""


def details(S, rel):
    info = next((m for m in S.list_models() if m["path"] == rel), None) or {}
    q = (info.get("quant") or {}).get("quant", "")
    params = (info.get("info") or {}).get("params", "")
    return {"format": "gguf", "family": "", "families": None, "parameter_size": params or "", "quantization_level": q or ""}


def capabilities(S, rel):
    caps = ["completion", "tools"]  # o motor roda com --jinja: chamadas de ferramenta funcionam nos modelos que suportam
    if S.mmproj_for(rel):
        caps.append("vision")
    if "embed" in rel.lower():
        caps = ["embedding"]
    return caps


# ---------------------------------------------------------------- conversao Ollama <-> OpenAI

def ollama_messages(msgs):
    out = []
    for m in msgs or []:
        role, content = m.get("role", "user"), m.get("content", "") or ""
        msg = {"role": role}
        if m.get("images"):
            parts = [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}} for img in m["images"]]
            msg["content"] = parts + [{"type": "text", "text": content}]
        else:
            msg["content"] = content
        if m.get("tool_calls"):
            msg["tool_calls"] = [{"id": f"call_{i}", "type": "function",
                                  "function": {"name": tc.get("function", {}).get("name", ""),
                                               "arguments": json.dumps(tc.get("function", {}).get("arguments", {}))}}
                                 for i, tc in enumerate(m["tool_calls"])]
        if role == "tool" and m.get("tool_name"):
            msg["name"] = m["tool_name"]
        out.append(msg)
    return out


def options_to_openai(opts):
    p = {}
    for k, v in (opts or {}).items():
        if k in SAMPLING:
            p[SAMPLING[k]] = v
    if p.get("max_tokens") is not None and p["max_tokens"] < 0:
        p.pop("max_tokens")
    return p


def _args(a):
    try:
        return json.loads(a) if isinstance(a, str) and a.strip() else (a or {})
    except ValueError:
        return {"_raw": a}


# ---------------------------------------------------------------- servidor HTTP

def make_handler(S):
    class GatewayHandler(S.Handler):
        server_version = "PiphinLLM-API"

        def log_message(self, *a):
            pass

        # -- seguranca: so do proprio PC, sem paginas da web, chave opcional
        def allowed(self):
            origin = self.headers.get("Origin")
            if origin and not re.match(r"^(https?://(127\.0\.0\.1|localhost)(:\d+)?|vscode-webview://.*|vscode-file://.*|null)$", origin):
                self.send_json({"error": "origem bloqueada: a API do Piphin LLM só aceita programas do próprio PC"}, 403)
                return False
            s = S.load_settings()
            if s.get("api_require_key") and s.get("api_key"):
                auth = self.headers.get("Authorization", "")
                key = auth[7:].strip() if auth.lower().startswith("bearer ") else self.headers.get("X-API-Key", "")
                if key != s["api_key"]:
                    self.send_json({"error": "chave de API inválida ou ausente (Authorization: Bearer <chave>)"}, 401)
                    return False
            return True

        def ndjson(self, obj):
            self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

        def upstream(self, port, path, payload, timeout=3600):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            try:
                return urllib.request.urlopen(req, timeout=timeout)
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")
                try:
                    msg = json.loads(msg)["error"]["message"]
                except (ValueError, KeyError, TypeError):
                    pass
                raise RuntimeError(msg) from None
            except (urllib.error.URLError, OSError) as e:
                raise RuntimeError(f"Motor não respondeu: {e}") from None

        def lease(self, name):
            rel = resolve(S, name)
            if not rel and S.ENGINE_PROC.state != "ready":
                last = S.load_settings().get("last_model", "")
                if last and (S.MODELS / last).is_file():
                    rel = last
                else:
                    raise RuntimeError("Nenhum modelo carregado no Piphin LLM.")
            return S.POOL.use(rel, S.load_settings())

        def sampling(self, payload, rel):
            """Amostragem recomendada do modelo, sem sobrescrever o que o cliente mandou."""
            mine = {k: payload[k] for k in ("temperature", "top_p", "top_k", "min_p", "repeat_penalty") if k in payload}
            S.apply_model_sampling(payload, rel)
            payload.update(mine)
            return payload

        # -- rotas
        def do_OPTIONS(self):
            self.send_response(204)
            self.end_headers()

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

        def do_GET(self):
            if not self.allowed():
                return
            p = self.path.split("?")[0].rstrip("/") or "/"
            if p == "/":
                return self.send_text("Ollama is running")  # alguns clientes testam assim
            if p == "/api/version":
                return self.send_json({"version": OLLAMA_VERSION})
            if p == "/api/tags":
                models = []
                for m in model_list(S):
                    f = S.MODELS / m["rel"]
                    st = f.stat()
                    models.append({"name": m["name"], "model": m["name"], "modified_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                                   "size": S.model_bytes(m["rel"]), "digest": hashlib.sha256(m["rel"].encode()).hexdigest(),
                                   "details": details(S, m["rel"])})
                return self.send_json({"models": models})
            if p == "/api/ps":
                loaded = [(S.ENGINE_PROC.model, S.ENGINE_PROC.device)] if S.ENGINE_PROC.state == "ready" else []
                loaded += [(m, d) for (m, d), e in list(S.POOL.extra.items()) if e.state == "ready"]
                return self.send_json({"models": [{"name": ollama_name(m), "model": ollama_name(m), "size": S.model_bytes(m),
                                                   "size_vram": S.model_bytes(m) if d == "gpu" else 0, "details": details(S, m),
                                                   "expires_at": "2099-01-01T00:00:00Z"} for m, d in loaded]})
            if p == "/v1/models":
                return self.send_json({"object": "list", "data": [{"id": m["name"].replace(":latest", ""), "object": "model",
                                                                    "created": int(time.time()), "owned_by": "piphin"} for m in model_list(S)]})
            self.send_json({"error": "rota não encontrada"}, 404)

        def send_text(self, text):
            d = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(d)))
            self.end_headers()
            self.wfile.write(d)

        def do_POST(self):
            if not self.allowed():
                return
            p = self.path.split("?")[0].rstrip("/")
            try:
                b = self.body()
            except ValueError:
                return self.send_json({"error": "JSON inválido"}, 400)
            try:
                if p == "/api/show":
                    rel = resolve(S, b.get("model") or b.get("name"))
                    if not rel:
                        return self.send_json({"error": "modelo não encontrado"}, 404)
                    ctx = int(S.load_settings().get("ctx_size") or 8192)
                    return self.send_json({"modelfile": "", "parameters": "", "template": "", "details": details(S, rel),
                                           "model_info": {"general.architecture": "llama", "llama.context_length": ctx},
                                           "capabilities": capabilities(S, rel), "modified_at": now_iso()})
                if p == "/api/chat":
                    return self.ollama_chat(b)
                if p == "/api/generate":
                    return self.ollama_generate(b)
                if p in ("/api/embed", "/api/embeddings"):
                    inputs = b.get("input", b.get("prompt", ""))
                    vecs = S.embed_texts(inputs if isinstance(inputs, list) else [inputs])
                    if p == "/api/embeddings":
                        return self.send_json({"embedding": vecs[0] if vecs else []})
                    return self.send_json({"model": b.get("model", ""), "embeddings": vecs})
                if p in ("/api/pull", "/api/push", "/api/create", "/api/copy", "/api/delete"):
                    return self.send_json({"error": "Gerencie os modelos pelo Piphin LLM (Modelos → Baixar modelos)."}, 501)
                if p == "/v1/chat/completions":
                    return self.openai_proxy(b, "/v1/chat/completions")
                if p == "/v1/completions":
                    return self.openai_proxy(b, "/v1/completions")
                if p == "/v1/embeddings":
                    inputs = b.get("input", "")
                    vecs = S.embed_texts(inputs if isinstance(inputs, list) else [inputs])
                    return self.send_json({"object": "list", "model": b.get("model", ""),
                                           "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vecs)]})
                self.send_json({"error": "rota não encontrada"}, 404)
            except RuntimeError as e:
                try:
                    self.send_json({"error": str(e)}, 503)
                except OSError:
                    pass

        do_PUT = do_POST

        def do_DELETE(self):
            self.send_json({"error": "Gerencie os modelos pelo Piphin LLM."}, 501)

        # -- OpenAI: repassa para o motor (mantem o streaming)
        def openai_proxy(self, b, path):
            with self.lease(b.get("model")) as eng:
                payload = dict(b)
                payload.pop("model", None)
                self.sampling(payload, eng.model)
                up = self.upstream(eng.port, path, payload)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", up.headers.get("Content-Type") or "application/json")
                    if not b.get("stream"):
                        data = up.read()
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        return
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    for line in iter(up.readline, b""):
                        self.wfile.write(line)
                        self.wfile.flush()
                finally:
                    up.close()

        # -- Ollama /api/chat
        def ollama_chat(self, b):
            name, stream = b.get("model", ""), b.get("stream", True) is not False
            with self.lease(name) as eng:
                payload = {"messages": ollama_messages(b.get("messages")), "stream": True, **options_to_openai(b.get("options"))}
                if b.get("tools"):
                    payload["tools"] = b["tools"]
                if b.get("format") == "json":
                    payload["response_format"] = {"type": "json_object"}
                elif isinstance(b.get("format"), dict):
                    payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "saida", "schema": b["format"]}}
                if b.get("think") is False:
                    payload["chat_template_kwargs"] = {"enable_thinking": False}
                self.sampling(payload, eng.model)
                self.relay(self.upstream(eng.port, "/v1/chat/completions", payload), name, stream, chat=True)

        # -- Ollama /api/generate (com "suffix" = completar no meio do codigo)
        def ollama_generate(self, b):
            name, stream = b.get("model", ""), b.get("stream", True) is not False
            if not b.get("prompt") and not b.get("suffix"):
                # pedido vazio = so carregar o modelo (comportamento do Ollama)
                with self.lease(name):
                    return self.send_json({"model": name, "created_at": now_iso(), "response": "", "done": True, "done_reason": "load"})
            with self.lease(name) as eng:
                opts = options_to_openai(b.get("options"))
                if b.get("suffix") is not None:
                    payload = {"input_prefix": b.get("prompt", ""), "input_suffix": b["suffix"], "stream": True,
                               "n_predict": opts.get("max_tokens", 256), **{k: v for k, v in opts.items() if k != "max_tokens"}}
                    return self.relay_native(self.upstream(eng.port, "/infill", payload), name, stream)
                if b.get("raw"):
                    payload = {"prompt": b.get("prompt", ""), "stream": True, "n_predict": opts.get("max_tokens", -1),
                               **{k: v for k, v in opts.items() if k != "max_tokens"}}
                    return self.relay_native(self.upstream(eng.port, "/completion", payload), name, stream)
                msgs = ([{"role": "system", "content": b["system"]}] if b.get("system") else []) + \
                    ollama_messages([{"role": "user", "content": b.get("prompt", ""), "images": b.get("images")}])
                payload = {"messages": msgs, "stream": True, **opts}
                self.sampling(payload, eng.model)
                self.relay(self.upstream(eng.port, "/v1/chat/completions", payload), name, stream, chat=False)

        def start_ndjson(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()

        def final(self, name, chat, text, calls, timings, t0, reason="stop"):
            out = {"model": name, "created_at": now_iso(), "done": True, "done_reason": reason,
                   "total_duration": int((time.time() - t0) * 1e9), "load_duration": 0,
                   "prompt_eval_count": (timings or {}).get("prompt_n", 0), "eval_count": (timings or {}).get("predicted_n", 0),
                   "eval_duration": int((timings or {}).get("predicted_ms", 0) * 1e6)}
            if chat:
                msg = {"role": "assistant", "content": text}
                if calls:
                    msg["tool_calls"] = [{"function": {"name": c["name"], "arguments": _args(c["arguments"])}} for c in calls]
                out["message"] = msg
            else:
                out["response"] = text
            return out

        def relay(self, up, name, stream, chat):
            """Converte o streaming do motor (SSE no formato OpenAI) para o formato do Ollama (NDJSON)."""
            t0, text, calls, timings, reason = time.time(), "", {}, None, "stop"
            if stream:
                self.start_ndjson()
            try:
                for raw in iter(up.readline, b""):
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:") or line == "data: [DONE]":
                        continue
                    try:
                        j = json.loads(line[5:])
                    except ValueError:
                        continue
                    timings = j.get("timings") or timings
                    ch = (j.get("choices") or [{}])[0]
                    reason = ch.get("finish_reason") or reason
                    d = ch.get("delta") or {}
                    for tc in d.get("tool_calls") or []:
                        c = calls.setdefault(tc.get("index", 0), {"name": "", "arguments": ""})
                        fn = tc.get("function") or {}
                        c["name"] += fn.get("name") or ""
                        c["arguments"] += fn.get("arguments") or ""
                    piece = d.get("content") or ""
                    if piece:
                        text += piece
                        if stream:
                            chunk = {"model": name, "created_at": now_iso(), "done": False}
                            if chat:
                                chunk["message"] = {"role": "assistant", "content": piece}
                            else:
                                chunk["response"] = piece
                            self.ndjson(chunk)
            finally:
                up.close()
            fin = self.final(name, chat, "" if stream else text, [calls[i] for i in sorted(calls)], timings, t0,
                             "stop" if reason in ("stop", "tool_calls") else reason)
            if stream:
                self.ndjson(fin)
            else:
                self.send_json(fin)

        def relay_native(self, up, name, stream):
            """Streaming das rotas nativas do motor (/infill, /completion) para o formato do Ollama."""
            t0, text, timings = time.time(), "", None
            if stream:
                self.start_ndjson()
            try:
                for raw in iter(up.readline, b""):
                    line = raw.decode("utf-8", "replace").strip()
                    if line.startswith("data:"):
                        line = line[5:]
                    if not line:
                        continue
                    try:
                        j = json.loads(line)
                    except ValueError:
                        continue
                    timings = j.get("timings") or timings
                    piece = j.get("content") or ""
                    if piece:
                        text += piece
                        if stream:
                            self.ndjson({"model": name, "created_at": now_iso(), "response": piece, "done": False})
                    if j.get("stop"):
                        break
            finally:
                up.close()
            fin = self.final(name, False, "" if stream else text, [], timings, t0)
            if stream:
                self.ndjson(fin)
            else:
                self.send_json(fin)

    return GatewayHandler
