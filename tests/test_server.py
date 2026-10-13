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
        env = dict(os.environ, LLM_HOME=str(cls.home), LLM_PORT=str(cls.port), PYTHONIOENCODING="utf-8")
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

    def test_12_summarize_and_backup(self):
        r = self.call("/api/summarize", {"messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]})
        self.assertIn("Resumo", r["summary"])
        self.assertIn("chats", self.call("/api/backup/info"))


if __name__ == "__main__":
    unittest.main()
