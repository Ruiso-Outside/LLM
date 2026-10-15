"""Teste de integracao: sobe o servidor de verdade com o llama-server falso e exercita a API."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

TESTS = Path(__file__).resolve().parent
FAKE_MCP = [sys.executable, str(TESTS / "fake_mcp.py")]


def free_port():
    """Porta livre longe das do app instalado (8765+); o motor usa as seguintes (porta+1, +2...)."""
    import random
    for _ in range(50):
        base = random.randrange(20000, 40000, 10)
        try:
            for p in range(base, base + 6):
                with socket.socket() as s:
                    s.bind(("127.0.0.1", p))
            return base
        except OSError:
            continue
    raise RuntimeError("sem porta livre")


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls._tmp.name)
        cls.ws = cls.home / "projeto"
        (cls.ws / "app").mkdir(parents=True)
        (cls.ws / "app" / "readme.txt").write_text("Projeto - versao 1\n", "utf-8")
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = dict(os.environ, LLM_HOME=str(cls.home), LLM_PORT=str(cls.port), PYTHONIOENCODING="utf-8", PIPHIN_TRAIN_FAKE="1")
        env.pop("LLM_PARENT_PID", None)
        cls.proc = subprocess.Popen([sys.executable, str(TESTS / "run_server.py")], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                cls.call("/api/status")
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.2)
        else:
            cls.proc.kill()
            raise RuntimeError("servidor não subiu: " + cls.proc.stdout.read().decode("utf-8", "replace"))
        cls.call("/api/settings", {"workspaces": [str(cls.ws)], "ctx_size": 8192}, "PUT")
        cls.call("/api/load", {"model": "Qwen3-8B-Q4_K_M.gguf"})
        for _ in range(100):
            if cls.call("/api/status")["engine"]["state"] == "ready":
                break
            time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.call("/api/mcp", {"servers": []}, "PUT")
            cls.call("/api/unload", {"all": True})
        except (urllib.error.URLError, OSError):
            pass
        if os.name == "nt":
            subprocess.run(["taskkill", "/pid", str(cls.proc.pid), "/T", "/F"], capture_output=True)
        else:
            cls.proc.kill()
        cls.proc.wait(10)
        cls.proc.stdout.close()
        time.sleep(0.5)
        cls._tmp.cleanup()

    # -- auxiliares
    @classmethod
    def call(cls, path, body=None, method=None):
        req = urllib.request.Request(cls.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Origin": cls.base},
                                     method=method or ("POST" if body is not None else "GET"))
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def sse(self, path, body, on_event=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Origin": self.base})
        events = []
        with urllib.request.urlopen(req, timeout=60) as r:
            for raw in r:
                line = raw.decode("utf-8").strip()
                if line.startswith("data:") and line != "data: [DONE]":
                    ev = json.loads(line[5:])
                    events.append(ev)
                    if on_event:
                        on_event(ev)
        return events

    @staticmethod
    def text_of(events, key=None):
        if key:
            return "".join(e[key].get("delta", "") for e in events if key in e and e[key].get("type") in ("text", "delta"))
        return "".join((e.get("choices") or [{}])[0].get("delta", {}).get("content", "") for e in events)

    def approve_all(self, kind):
        def on_event(ev):
            a = ev.get(kind) or {}
            if a.get("type") == "approval":
                threading.Thread(target=self.call, args=("/api/agent/approve", {"id": a["id"], "ok": True}), daemon=True).start()
        return on_event

    # -- testes
    def test_01_status(self):
        st = self.call("/api/status")
        self.assertEqual(st["engine"]["state"], "ready")
        self.assertEqual({m["path"] for m in st["models"]}, {"Qwen3-8B-Q4_K_M.gguf", "gemma-3-4b-it-Q4_K_M.gguf"})
        self.assertEqual(st["settings"]["ctx_size"], 8192)

    def test_02_origin_blocked(self):
        req = urllib.request.Request(self.base + "/api/settings", data=b"{}", method="PUT",
                                     headers={"Content-Type": "application/json", "Origin": "https://site-malicioso.com"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(cm.exception.code, 403)

    def test_03_chat_stream(self):
        ev = self.sse("/api/chat", {"messages": [{"role": "user", "content": "oi"}], "temperature": 0.5})
        text = self.text_of(ev)
        self.assertIn("[Qwen3-8B-Q4_K_M]", text)
        self.assertIn("tools=0", text)
        self.assertTrue(any("timings" in e for e in ev))

    def test_04_codex_with_folder_and_undo(self):
        ev = self.sse("/api/agent", {"chat_id": "teste-codex", "workspace": str(self.ws),
                                     "messages": [{"role": "user", "content": "faça"}]})
        ck = next(e["agent"] for e in ev if e.get("agent", {}).get("type") == "checkpoint")
        self.assertTrue((self.ws / "app" / "hello.py").exists())
        self.assertIn("versao 2", (self.ws / "app" / "readme.txt").read_text())
        self.call("/api/codex/undo", {"chat_id": "teste-codex", "run_id": ck["id"]})
        self.assertFalse((self.ws / "app" / "hello.py").exists())
        self.assertIn("versao 1", (self.ws / "app" / "readme.txt").read_text())

    def test_05_codex_rejects_unlisted_folder(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.sse("/api/agent", {"workspace": str(self.home), "messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(cm.exception.code, 403)

    def test_06_mcp_config_and_test(self):
        r = self.call("/api/mcp", {"servers": [{"name": "Fake", "command": FAKE_MCP[0], "args": FAKE_MCP[1:]}]}, "PUT")
        self.assertEqual(r["servers"][0]["id"], "fake")
        self.assertIn("roblox_detected", r)
        r = self.call("/api/mcp/test", {"id": "fake"})
        self.assertEqual(sorted(t["name"] for t in r["servers"][0]["tools"]), ["echo", "set_value", "snapshot"])
        with self.assertRaises(urllib.error.HTTPError):
            self.call("/api/mcp", {"servers": [{"name": "x", "type": "http", "url": "nada"}]}, "PUT")

    def test_07_codex_mcp_only_with_approval(self):
        self.call("/api/mcp", {"servers": [{"id": "fake", "name": "Fake", "command": FAKE_MCP[0], "args": FAKE_MCP[1:]}]}, "PUT")
        approvals = []
        on = self.approve_all("agent")
        ev = self.sse("/api/agent", {"chat_id": "teste-mcp", "mcp_only": True, "messages": [{"role": "user", "content": "use"}]},
                      lambda e: (approvals.append(e) if e.get("agent", {}).get("type") == "approval" else None, on(e)))
        names = [e["agent"]["name"] for e in ev if e.get("agent", {}).get("type") == "tool_start"]
        self.assertEqual(names, ["mcp__fake__echo", "mcp__fake__set_value"])
        # echo e somente leitura (sem confirmacao); set_value altera (pede confirmacao)
        self.assertEqual([a["agent"]["name"] for a in approvals], ["mcp__fake__set_value"])
        text = self.text_of(ev, "agent")
        self.assertIn("eco: ola", text)
        self.assertIn("valor = 42", text)
        self.assertIn("tools=3", text)  # sem pasta: so as ferramentas MCP

    def test_08_codex_mcp_denied(self):
        self.call("/api/mcp", {"servers": [{"id": "fake", "name": "Fake", "command": FAKE_MCP[0], "args": FAKE_MCP[1:]}]}, "PUT")

        def deny(ev):
            a = ev.get("agent") or {}
            if a.get("type") == "approval":
                threading.Thread(target=self.call, args=("/api/agent/approve", {"id": a["id"], "ok": False}), daemon=True).start()
        ev = self.sse("/api/agent", {"chat_id": "teste-negar", "mcp_only": True, "messages": [{"role": "user", "content": "use"}]}, deny)
        self.assertIn("NEGOU", self.text_of(ev, "agent"))

    def test_09_agent_with_mcp_tools(self):
        self.call("/api/mcp", {"servers": [{"id": "fake", "name": "Fake", "command": FAKE_MCP[0], "args": FAKE_MCP[1:],
                                            "auto_approve": True}]}, "PUT")
        doc = self.call("/api/agents", {"agents": [{"id": "ag1", "name": "Construtor", "instructions": "Use as ferramentas.",
                                                    "mcp": ["fake"]}], "groups": []}, "PUT")
        self.assertEqual(doc["agents"][0]["mcp"], ["fake"])
        ev = self.sse("/api/group/run", {"group_id": "agent:ag1", "messages": [{"role": "user", "content": "faça"}]})
        g = [e["group"] for e in ev if "group" in e]
        self.assertEqual([x["name"] for x in g if x["type"] == "tool_start"], ["mcp__fake__echo", "mcp__fake__set_value"])
        self.assertFalse(any(x["type"] == "approval" for x in g))  # servidor marcado como confiavel
        done = next(x for x in g if x["type"] == "done")
        self.assertIn("valor = 42", done["final"])

    def test_10_group_without_tools(self):
        r = self.call("/api/agents/template", {"kind": "math"})
        ev = self.sse("/api/group/run", {"group_id": r["group_id"], "messages": [{"role": "user", "content": "crie"}]})
        g = [e["group"] for e in ev if "group" in e]
        self.assertEqual(sum(1 for x in g if x["type"] == "step_start"), 3)
        self.assertTrue(any(x["type"] == "done" for x in g))

    def test_11_chat_with_screen_attachment(self):
        req = urllib.request.Request(self.base + "/api/upload", data=b"\xff\xd8\xff\xe0fakejpeg",
                                     headers={"X-Filename": "tela.jpg", "Content-Type": "image/jpeg", "Origin": self.base})
        with urllib.request.urlopen(req, timeout=30) as r:
            fid = json.loads(r.read())["id"]
        ev = self.sse("/api/chat", {"messages": [{"role": "user", "content": "o que é isto?",
                                                   "attachments": [{"kind": "image", "id": fid, "name": "Print da tela"},
                                                                   {"kind": "text", "name": "Texto copiado", "text": "erro 42"}]}]})
        self.assertIn("[Qwen3-8B-Q4_K_M]", self.text_of(ev))

    def test_13_mtp_accelerator(self):
        models = self.home / "models"
        (models / "mtp").mkdir(exist_ok=True)
        for rel in ("mtp-gemma-4-12b-it-Q8_0.gguf", "mtp/gemma__mtp-gemma-Q8_0.gguf", "mtp/gemma__quebrado-mtp.gguf",
                    "imatrix_unsloth.gguf"):
            (models / rel).write_bytes(b"GGUF")
        st = self.call("/api/status")
        self.assertEqual({m["path"] for m in st["models"]}, {"Qwen3-8B-Q4_K_M.gguf", "gemma-3-4b-it-Q4_K_M.gguf"})
        self.assertEqual(self.call("/api/media")["mtp"],
                         ["mtp-gemma-4-12b-it-Q8_0.gguf", "mtp/gemma__mtp-gemma-Q8_0.gguf", "mtp/gemma__quebrado-mtp.gguf"])
        with self.assertRaises(urllib.error.HTTPError):
            self.call("/api/models/mtp", {"model": "gemma-3-4b-it-Q4_K_M.gguf", "mtp": "../fora.gguf"})

        def load_and_wait():
            self.call("/api/load", {"model": "gemma-3-4b-it-Q4_K_M.gguf"})
            for _ in range(100):
                e = self.call("/api/status")["engine"]
                if e["state"] in ("ready", "error"):
                    return e
                time.sleep(0.2)
        try:
            self.call("/api/models/mtp", {"model": "gemma-3-4b-it-Q4_K_M.gguf", "mtp": "mtp/gemma__mtp-gemma-Q8_0.gguf"})
            self.assertEqual(next(m for m in self.call("/api/status")["models"] if m["path"].startswith("gemma"))["mtp"],
                             "mtp/gemma__mtp-gemma-Q8_0.gguf")
            e = load_and_wait()
            self.assertEqual((e["state"], e["mtp"], e["mtp_error"]), ("ready", True, False))
            self.assertIn("mtp=sim", self.text_of(self.sse("/api/chat", {"messages": [{"role": "user", "content": "oi"}]})))
            # acelerador recusado pelo motor: carrega de novo sem ele
            self.call("/api/models/mtp", {"model": "gemma-3-4b-it-Q4_K_M.gguf", "mtp": "mtp/gemma__quebrado-mtp.gguf"})
            e = load_and_wait()
            self.assertEqual((e["state"], e["mtp"], e["mtp_error"]), ("ready", False, True))
        finally:
            self.call("/api/models/mtp", {"model": "gemma-3-4b-it-Q4_K_M.gguf", "mtp": ""})
            self.call("/api/load", {"model": "Qwen3-8B-Q4_K_M.gguf"})
            for _ in range(100):
                if self.call("/api/status")["engine"]["state"] == "ready":
                    break
                time.sleep(0.2)

    def test_14_quick_model_on_gpu(self):
        quick = "gemma-3-4b-it-Q4_K_M.gguf"
        try:
            q = self.call("/api/quick/load", {"quick_model": quick, "quick_device": "gpu", "quick_keep_loaded": True})
            self.assertEqual((q["model"], q["device"], q["keep"]), (quick, "gpu", True))
            for _ in range(100):
                q = self.call("/api/status")["quick"]
                if q["state"] == "ready":
                    break
                time.sleep(0.2)
            self.assertEqual((q["state"], q["on"]), ("ready", "gpu"))
            extra = next(x for x in self.call("/api/status")["extras"] if x["model"] == quick)
            self.assertEqual(extra["device"], "gpu")
            # a pergunta rapida usa esse motor ja carregado, com as camadas ajustadas pelo llama.cpp (-ngl auto)
            ev = self.sse("/api/chat", {"messages": [{"role": "user", "content": "oi"}], "model": quick, "device": "gpu"})
            text = self.text_of(ev)
            self.assertIn("[gemma-3-4b-it-Q4_K_M]", text)
            self.assertIn("ngl=auto", text)
            self.assertEqual(sum(1 for x in self.call("/api/status")["extras"] if x["model"] == quick), 1)
            # descarregar desliga o "manter carregado"
            q = self.call("/api/quick/unload", {})
            self.assertEqual((q["state"], q["keep"]), ("stopped", False))
        finally:
            self.call("/api/settings", {"quick_model": "", "quick_keep_loaded": True}, "PUT")
            self.call("/api/unload", {"extra": "all"})

    def test_15_codex_with_knowledge_base(self):
        docs = self.home / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "receita.txt").write_text("Receita de bolo de chocolate: misture farinha, ovos e chocolate. Asse por 40 minutos.", "utf-8")
        (docs / "jogo.md").write_text("# Obby\nO jogador pula plataformas e evita a lava.", "utf-8")
        base = self.call("/api/kb/create", {"name": "Docs do projeto", "folders": [str(docs)]})
        self.call("/api/kb/index", {"id": base["id"]})
        for _ in range(100):
            k = next(x for x in self.call("/api/kb")["bases"] if x["id"] == base["id"])
            if k["status"] not in ("nova", "indexando"):
                break
            time.sleep(0.2)
        self.assertGreaterEqual(k["n_chunks"], 2)
        ev = self.sse("/api/agent", {"chat_id": "teste-kb", "workspace": str(self.ws), "kb": base["id"],
                                     "messages": [{"role": "user", "content": "como fazer o bolo?"}]})
        a = [e["agent"] for e in ev if "agent" in e]
        self.assertTrue(any(x["type"] == "notice" and "Docs do projeto" in x["text"] for x in a))
        self.assertEqual([x["name"] for x in a if x["type"] == "tool_start"], ["search_knowledge"])
        result = next(x["result"] for x in a if x["type"] == "tool_end")
        self.assertIn("[D1]", result)
        self.assertIn("bolo de chocolate", result)
        self.assertIn("bolo de chocolate", self.text_of(ev, "agent"))  # a resposta final usou o trecho
        # sem base escolhida, o Codex nao recebe a ferramenta
        ev = self.sse("/api/agent", {"chat_id": "teste-kb2", "workspace": str(self.ws), "messages": [{"role": "user", "content": "oi"}]})
        self.assertNotIn("search_knowledge", [e["agent"].get("name") for e in ev if e.get("agent", {}).get("type") == "tool_start"])

    def test_16_mode_models_switch(self):
        quick, main = "gemma-3-4b-it-Q4_K_M.gguf", "Qwen3-8B-Q4_K_M.gguf"

        def wait_main(model):
            for _ in range(100):
                e = self.call("/api/status")["engine"]
                if e["model"] == model and e["state"] == "ready":
                    return e
                time.sleep(0.2)
            self.fail("modelo principal nao ficou pronto")

        def extras():
            return {x["model"] for x in self.call("/api/status")["extras"] if x["state"] in ("ready", "loading")}
        try:
            s = self.call("/api/settings", {"mode_models": {"chat": main, "codex": quick, "agents": ""}, "mode_switch": True}, "PUT")
            self.assertEqual(s["mode_models"]["codex"], quick)
            # modelo extra que nao e o da pergunta rapida mantida: sai na troca de modo
            self.call("/api/settings", {"quick_model": "", "quick_keep_loaded": False}, "PUT")
            self.sse("/api/chat", {"messages": [{"role": "user", "content": "oi"}], "model": quick, "device": "gpu"})
            self.assertIn(quick, extras())
            self.call("/api/load", {"model": main, "free_extras": True})
            wait_main(main)
            self.assertEqual(extras(), set())
            # o da pergunta rapida marcado como "manter carregado" fica
            self.call("/api/quick/load", {"quick_model": quick, "quick_device": "gpu", "quick_keep_loaded": True})
            for _ in range(100):
                if quick in extras():
                    break
                time.sleep(0.2)
            self.call("/api/load", {"model": main, "free_extras": True})
            wait_main(main)
            self.assertEqual(extras(), {quick})
        finally:
            self.call("/api/settings", {"mode_models": {}, "quick_model": "", "quick_keep_loaded": True}, "PUT")
            self.call("/api/unload", {"extra": "all"})
            self.call("/api/load", {"model": main})
            wait_main(main)

    def test_17_local_api_ollama_and_openai(self):
        port = free_port() + 7
        api = f"http://127.0.0.1:{port}"

        def req(path, body=None, headers=None, method=None):
            r = urllib.request.Request(api + path, data=None if body is None else json.dumps(body).encode(),
                                       headers={"Content-Type": "application/json", **(headers or {})},
                                       method=method or ("POST" if body is not None else "GET"))
            return urllib.request.urlopen(r, timeout=60)

        def lines(resp):
            return [json.loads(l) for l in resp.read().decode("utf-8").splitlines() if l.strip()]
        try:
            st = self.call("/api/settings", {"api_enabled": True, "api_port": port}, "PUT")
            self.assertTrue(st["api_enabled"])
            for _ in range(50):
                if self.call("/api/integration")["running"]:
                    break
                time.sleep(0.1)
            self.assertEqual(req("/").read().decode(), "Ollama is running")
            self.assertIn("version", json.loads(req("/api/version").read()))
            tags = [m["name"] for m in json.loads(req("/api/tags").read())["models"]]
            self.assertIn("qwen3-8b-q4_k_m:latest", tags)
            self.assertIn("piphin-codex:latest", tags)
            show = json.loads(req("/api/show", {"model": "qwen3-8b-q4_k_m:latest"}).read())
            self.assertIn("tools", show["capabilities"])  # o modo Agente das IDEs exige ferramentas
            # Ollama /api/chat em streaming (NDJSON)
            out = lines(req("/api/chat", {"model": "qwen3-8b-q4_k_m", "messages": [{"role": "user", "content": "oi"}]}))
            self.assertFalse(out[0]["done"])
            self.assertTrue(out[-1]["done"])
            self.assertIn("[Qwen3-8B-Q4_K_M]", "".join(o["message"]["content"] for o in out))
            # sem streaming e com ferramenta: devolve tool_calls com argumentos como objeto
            tools = [{"type": "function", "function": {"name": "clima", "parameters": {"type": "object", "properties": {"cidade": {"type": "string"}}}}}]
            out = lines(req("/api/chat", {"model": "qwen3-8b-q4_k_m", "stream": False, "tools": tools,
                                          "messages": [{"role": "user", "content": "clima?"}]}))
            self.assertEqual(out[-1]["message"]["tool_calls"][0]["function"], {"name": "clima", "arguments": {"cidade": "Recife"}})
            # /api/generate com sufixo = completar no meio do codigo (rota /infill do motor)
            out = lines(req("/api/generate", {"model": "qwen3-8b-q4_k_m", "prompt": "int soma(", "suffix": "}"}))
            self.assertIn("infill", "".join(o.get("response", "") for o in out))
            # OpenAI /v1
            ids = [m["id"] for m in json.loads(req("/v1/models").read())["data"]]
            self.assertIn("piphin-chat", ids)
            r = json.loads(req("/v1/chat/completions", {"model": "piphin-chat", "messages": [{"role": "user", "content": "oi"}]}).read())
            self.assertEqual(r["choices"][0]["message"]["content"], "consulta teste")
            sse = req("/v1/chat/completions", {"model": "piphin-chat", "stream": True, "messages": [{"role": "user", "content": "oi"}]}).read().decode()
            self.assertIn("data: [DONE]", sse)
            # paginas da web sao bloqueadas
            with self.assertRaises(urllib.error.HTTPError) as cm:
                req("/api/tags", headers={"Origin": "https://site-malicioso.com"})
            self.assertEqual(cm.exception.code, 403)
            # chave obrigatoria
            st = self.call("/api/settings", {"api_require_key": True}, "PUT")
            key = self.call("/api/integration")["key"]
            self.assertTrue(key.startswith("pk-"))
            with self.assertRaises(urllib.error.HTTPError) as cm:
                req("/v1/models")
            self.assertEqual(cm.exception.code, 401)
            self.assertEqual(req("/v1/models", headers={"Authorization": f"Bearer {key}"}).status, 200)
            # desligar fecha a porta
            self.call("/api/settings", {"api_enabled": False, "api_require_key": False}, "PUT")
            time.sleep(0.5)
            with self.assertRaises((urllib.error.URLError, OSError)):
                req("/api/version")
        finally:
            self.call("/api/settings", {"api_enabled": False, "api_require_key": False}, "PUT")

    def test_18_training_studio_fake(self):
        st = self.call("/api/train/status")
        self.assertFalse(st["env"]["installed"])
        self.assertTrue(st["base_models"])
        ds = self.call("/api/train/dataset/create", {"name": "UE5", "system": "Especialista em Unreal."})
        for i in range(4):
            self.call("/api/train/dataset/example", {"id": ds["id"], "example": {"user": f"pergunta {i}", "assistant": f"resposta {i}"}})
        r = self.call("/api/train/start", {"name": "ia-teste", "dataset_id": ds["id"], "base_repo": "Qwen/Qwen2.5-0.5B-Instruct",
                                           "epochs": 2, "grad_accum": 1, "eval_every": 2, "free_gpu": False})
        with self.assertRaises(urllib.error.HTTPError):  # um treino por vez
            self.call("/api/train/start", {"dataset_id": ds["id"], "base_repo": "x/y"})
        for _ in range(100):
            d = self.call(f"/api/train/run?id={r['id']}")
            if d["state"] not in ("starting", "loading", "training"):
                break
            time.sleep(0.2)
        self.assertEqual(d["state"], "done")
        self.assertEqual(d["setup"]["train_examples"], 4)
        self.assertGreater(d["setup"]["trainable_params"], 0)
        self.assertTrue(d["steps"] and d["evals"])
        self.assertLess(d["steps"][-1]["loss"], d["steps"][0]["loss"])  # o erro cai
        self.assertGreater(d["result"]["adapter_size"], 0)
        # o dataset da execucao leva a instrucao de sistema do conjunto
        run_ds = (self.home / "data" / "train" / "runs" / r["id"] / "dataset.jsonl").read_text("utf-8").splitlines()
        self.assertEqual(json.loads(run_ds[0])["messages"][0]["role"], "system")
        # exportar gera o GGUF em models/treinados e ele aparece em Meus modelos
        self.call("/api/train/export", {"id": r["id"], "name": "IA Unreal", "quant": "Q4_K_M"})
        for _ in range(100):
            d = self.call(f"/api/train/run?id={r['id']}")
            if d["state"] != "exporting":
                break
            time.sleep(0.2)
        self.assertEqual(d["state"], "exported")
        models = [m for m in self.call("/api/status")["models"] if m["path"].startswith("treinados/")]
        self.assertEqual([m["path"] for m in models], ["treinados/IA-Unreal-Q4_K_M.gguf"])
        self.assertEqual(models[0]["info"]["trained"]["base"], "Qwen/Qwen2.5-0.5B-Instruct")
        runs = self.call("/api/train/status")["runs"]
        self.assertEqual(runs[0]["state"], "exported")
        self.assertTrue(runs[0]["has_adapter"])
        # continuar a mesma IA com conteudo novo: parte do adaptador anterior e revisa os exemplos antigos
        ds2 = self.call("/api/train/dataset/create", {"name": "UE5 editor"})
        for i in range(3):
            self.call("/api/train/dataset/example", {"id": ds2["id"], "example": {"user": f"nova {i}", "assistant": f"resp {i}"}})
        self.call("/api/train/dataset/example", {"id": ds2["id"], "example": {"user": "pergunta 0", "assistant": "resposta 0"}})
        r2 = self.call("/api/train/start", {"name": "ia-teste", "dataset_id": ds2["id"], "parent_run": r["id"], "base_repo": "x/ignorado",
                                            "lora_r": 4, "epochs": 1, "grad_accum": 1, "free_gpu": False})
        for _ in range(100):
            d2 = self.call(f"/api/train/run?id={r2['id']}")
            if d2["state"] not in ("starting", "loading", "training"):
                break
            time.sleep(0.2)
        self.assertEqual(d2["state"], "done", d2.get("error"))
        self.assertEqual(d2["base_repo"], "Qwen/Qwen2.5-0.5B-Instruct")  # o modelo base vem da IA anterior
        self.assertEqual((d2["generation"], d2["parent_name"]), (2, "ia-teste"))
        self.assertEqual(d2["cfg"]["lora_r"], 16)
        self.assertEqual((d2["cfg"]["new_examples"], d2["cfg"]["replay_examples"]), (4, 3))  # "pergunta 0" repetida entra uma vez so
        self.assertEqual(d2["setup"]["train_examples"], 7)
        self.assertTrue((self.home / "data" / "train" / "runs" / r2["id"] / "parent_adapter" / "adapter_config.json").is_file())
        with self.assertRaises(urllib.error.HTTPError):  # pasta sem adaptador LoRA
            self.call("/api/train/start", {"dataset_id": ds2["id"], "parent_adapter": str(self.home)})
        self.call("/api/train/run/delete", {"id": r2["id"]})
        self.call("/api/train/run/delete", {"id": r["id"]})
        self.assertFalse(any(x["id"] == r["id"] for x in self.call("/api/train/status")["runs"]))

    def test_12_summarize_and_backup(self):
        r = self.call("/api/summarize", {"messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]})
        self.assertIn("Resumo", r["summary"])
        self.assertIn("chats", self.call("/api/backup/info"))


if __name__ == "__main__":
    unittest.main()
