"""llama-server falso para os testes: chat (eco dos parametros), tool calling do Codex/MCP, resumo e embeddings."""
import hashlib
import json
import math
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

args = sys.argv[1:]
port = int(args[args.index("--port") + 1])
model = Path(args[args.index("-m") + 1]).stem
CTX = int(args[args.index("-c") + 1]) if "-c" in args else 4096
READY_AT = time.time() + 0.5
if "-md" in args and "quebrado" in args[args.index("-md") + 1]:
    sys.exit("erro: acelerador MTP incompativel")  # simula o llama.cpp recusando o arquivo


def embed(text, dim=512):
    v = [0.0] * dim
    for w in re.findall(r"\w{3,}", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def plan(req, msgs):
    """Decide a proxima chamada de ferramenta (ou None para a resposta final)."""
    names = [t["function"]["name"] for t in req.get("tools") or []]
    n_tools = sum(1 for m in msgs if m["role"] == "tool")
    if "search_knowledge" in names:  # roteiro com base de conhecimento: consulta a base e responde
        return ("search_knowledge", {"query": "receita de bolo de chocolate"}) if n_tools == 0 else None
    echo = next((n for n in names if n.endswith("__echo")), None)
    setv = next((n for n in names if n.endswith("__set_value")), None)
    if echo:  # roteiro MCP: echo (leitura) -> set_value (altera, pede confirmacao)
        steps = [(echo, {"text": "ola"})] + ([(setv, {"value": "42"})] if setv else [])
        return steps[n_tools] if n_tools < len(steps) else None
    if "write_file" in names:  # roteiro do Codex com pasta
        steps = [("write_file", {"path": "app/hello.py", "content": "print('ola')\n"}),
                 ("edit_file", {"path": "app/readme.txt", "old_text": "versao 1", "new_text": "versao 2"})]
        return steps[n_tools] if n_tools < len(steps) else None
    if names and n_tools == 0:  # cliente externo (API local) oferecendo uma ferramenta qualquer
        return (names[0], {"cidade": "Recife"})
    return None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200):
        d = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def do_GET(self):
        if self.path == "/health":
            ok = time.time() >= READY_AT
            return self.send({"status": "ok" if ok else "loading"}, 200 if ok else 503)
        self.send({"default_generation_settings": {"n_ctx": CTX}, "modalities": {}})

    def chunk(self, obj):
        self.wfile.write(b"data: " + json.dumps(obj, ensure_ascii=False).encode() + b"\n\n")
        self.wfile.flush()

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/embeddings"):
            inputs = req["input"] if isinstance(req["input"], list) else [req["input"]]
            return self.send({"data": [{"index": i, "embedding": embed(t)} for i, t in enumerate(inputs)]})
        if self.path in ("/infill", "/completion"):  # rotas nativas: completar codigo (com prefixo e sufixo)
            text = f"<{self.path[1:]} prefixo={req.get('input_prefix', req.get('prompt', ''))!r} sufixo={req.get('input_suffix', '')!r}>"
            if not req.get("stream"):
                return self.send({"content": text, "stop": True, "timings": {"predicted_n": 3, "prompt_n": 5}})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for w in text.split(" "):
                self.chunk({"content": w + " ", "stop": False})
            self.chunk({"content": "", "stop": True, "timings": {"predicted_n": 3, "prompt_n": 5}})
            return
        msgs = req["messages"]
        last = msgs[-1]["content"] if isinstance(msgs[-1]["content"], str) else json.dumps(msgs[-1]["content"])
        if not req.get("stream"):
            text = "- Resumo de teste." if "Resuma a conversa" in last else "consulta teste"
            if "tools" in req and not any(m["role"] == "tool" for m in msgs):  # cliente externo pedindo ferramenta
                tc = {"id": "c0", "type": "function", "function": {"name": req["tools"][0]["function"]["name"], "arguments": '{"cidade": "Recife"}'}}
                return self.send({"choices": [{"message": {"content": "", "tool_calls": [tc]}, "finish_reason": "tool_calls"}]})
            return self.send({"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "timings": {"predicted_n": 5}})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        t = {"prompt_n": 50, "cache_n": 0, "predicted_n": 3, "predicted_per_second": 40}
        call = plan(req, msgs)
        if call:
            n = sum(1 for m in msgs if m["role"] == "tool")
            self.chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": f"c{n}", "type": "function",
                                                                 "function": {"name": call[0], "arguments": json.dumps(call[1])}}]}}],
                        "timings": t})
        else:
            tools_out = " | ".join(m["content"] for m in msgs if m["role"] == "tool")
            info = f"[{model}] mtp={'sim' if '-md' in args else 'nao'} ngl={args[args.index('-ngl') + 1] if '-ngl' in args else '-'} temp={req.get('temperature')} tools={len(req.get('tools') or [])} resultados=<{tools_out}>"
            for w in info.split(" "):
                self.chunk({"choices": [{"delta": {"content": w + " "}}], "timings": t})
        self.wfile.write(b"data: [DONE]\n\n")


ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
