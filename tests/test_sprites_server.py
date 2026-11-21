"""Integracao do setor Sprites: servidor de verdade, motor de imagem falso (fake_sd.py) e Construct falso.

Confere a conexao automatica com o Arasaka Construct (sem configuracao), a geracao com a LoRA de pixel art,
o envio ao projeto do Construct e o servidor MCP da propria Mikoshi (POST /mcp)."""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "app"))
import pixel  # noqa: E402
from test_server import free_port  # noqa: E402


class SpritesServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls._tmp.name) / "home"
        cls.proj = Path(cls._tmp.name) / "Jogo"
        cls.proj.mkdir(parents=True)
        (cls.proj / "project.luau").write_text("return {}", "utf-8")
        recent = Path(cls._tmp.name) / "recentes.txt"
        recent.write_text(str(cls.proj) + "\n", "utf-8")
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = dict(os.environ, LLM_HOME=str(cls.home), LLM_PORT=str(cls.port), PYTHONIOENCODING="utf-8", FAKE_SD="1",
                   ARASAKA_CONSTRUCT_EDITOR=str(TESTS / "fake_construct.py"), ARASAKA_CONSTRUCT_RECENT=str(recent))
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

    @classmethod
    def tearDownClass(cls):
        if os.name == "nt":
            subprocess.run(["taskkill", "/pid", str(cls.proc.pid), "/T", "/F"], capture_output=True)
        else:
            cls.proc.kill()
        cls.proc.wait(10)
        cls.proc.stdout.close()
        time.sleep(0.5)
        cls._tmp.cleanup()

    @classmethod
    def call(cls, path, body=None, method=None, headers=None):
        req = urllib.request.Request(cls.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Origin": cls.base, **(headers or {})},
                                     method=method or ("POST" if body is not None else "GET"))
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())

    def sse(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Origin": self.base})
        events = []
        with urllib.request.urlopen(req, timeout=120) as r:
            for raw in r:
                line = raw.decode("utf-8").strip()
                if line.startswith("data:"):
                    events.append(json.loads(line[5:]))
        return events

    def wait_construct(self):
        for _ in range(100):
            c = self.call("/api/construct")
            if c["state"] == "pronto":
                return c
            time.sleep(0.1)
        self.fail(f"o Construct não conectou sozinho: {c}")

    def test_1_construct_connects_by_itself(self):
        c = self.wait_construct()
        self.assertEqual((c["tools"], c["version"], c["project"], c["can_sprites"]), (4, "9.9.9", str(self.proj), True))
        servers = self.call("/api/mcp")["servers"]
        self.assertEqual([s["id"] for s in servers], ["construct"])
        self.assertTrue(servers[0]["builtin"])

    def test_2_generate_sheet_and_send(self):
        st = self.call("/api/sprites")
        self.assertTrue(st["engine"]["installed"])
        self.assertEqual(st["engine"]["problem"], "")
        self.assertTrue(st["model"]["installed"])
        self.assertGreater(st["download_bytes"], 7e9)
        evs = self.sse("/api/sprites/generate", {"prompt": "green slime", "size": 16, "colors": 8, "views": ["baixo", "esquerda"],
                                                 "frames": 2, "seed": 10, "mode": "rapido"})
        errors = [e for e in evs if "error" in e]
        self.assertEqual(errors, [])
        stages = [e["sprite"]["stage"] for e in evs]
        self.assertIn("progress", stages)
        done = evs[-1]["sprite"]
        self.assertEqual(done["stage"], "done")
        self.assertEqual((done["cols"], done["rows"], done["sheet_w"], done["sheet_h"]), (2, 2, 32, 32))
        self.assertLessEqual(len(done["palette"]), 8)
        args = json.loads((self.home / "data" / "uploads" / (done["sources"][0] + ".args.json")).read_text("utf-8"))
        prompt = args[args.index("-p") + 1]
        self.assertIn("pixel art, green slime", prompt)
        self.assertIn("<lora:pixel-art-xl:1.2>", prompt)
        self.assertIn("<lora:lcm-sdxl:1>", prompt)
        self.assertEqual(args[args.index("--sampling-method") + 1], "lcm")
        self.assertEqual(args[args.index("--steps") + 1], "8")
        self.assertTrue(args[args.index("--lora-model-dir") + 1].endswith(os.path.join("pixel-art-xl", "loras")))
        self.assertIn("-n", args)
        # reprocessar sem gerar de novo
        r = self.call("/api/sprites/pixelate", {"ids": done["sources"], "rows": 2, "size": 32, "colors": 4, "outline": True})
        self.assertEqual((r["sheet_w"], r["sheet_h"]), (64, 64))
        # enviar ao Construct
        self.wait_construct()
        out = self.call("/api/sprites/construct", {"sheet": done["sheet"], "name": "slime", "size": 16, "cols": 2, "rows": 2,
                                                   "views": ["baixo", "esquerda"], "fps": 6})
        self.assertEqual(out["sprite"], "sprites/slime.sprite.luau")
        png = (self.proj / "assets" / "mikoshi" / "slime.png").read_bytes()
        img = pixel.decode_png(png)
        self.assertEqual((img.w, img.h), (32, 32))
        anims = json.loads((self.proj / "sprites" / "slime.sprite.luau").read_text("utf-8")[7:])["animations"]
        self.assertEqual([(a["name"], a["frames"], a["fps"]) for a in anims], [("parado", 1, 4), ("andando", 2, 6)])
        self.assertEqual(anims[1]["directions"], ["baixo", "esquerda"])

    def test_3_mikoshi_mcp_server(self):
        r = self.call("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                      headers={"Origin": ""})
        self.assertEqual(r["result"]["serverInfo"]["name"], "arasaka-mikoshi")
        tools = self.call("/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertIn("generate_sprite", [t["name"] for t in tools])
        self.wait_construct()
        r = self.call("/mcp", {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "generate_sprite", "arguments": {"prompt": "red chest", "size": 32, "construct_name": "bau"}}})["result"]
        self.assertFalse(r.get("isError"), r)
        self.assertIn("Gravado no Arasaka Construct", r["content"][0]["text"])
        self.assertTrue((self.proj / "sprites" / "bau.sprite.luau").exists())
        self.assertTrue(base64.b64decode(r["content"][1]["data"]).startswith(b"\x89PNG"))
        # um site nao pode usar o servidor local
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.call("/mcp", {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}, headers={"Origin": "https://exemplo.com"})
        self.assertEqual(e.exception.code, 403)

    def test_4_choose_project(self):
        other = Path(self._tmp.name) / "Outro"
        other.mkdir(exist_ok=True)
        (other / "project.luau").write_text("return {}", "utf-8")
        with self.assertRaises(urllib.error.HTTPError):
            self.call("/api/construct/project", {"path": self._tmp.name})
        c = self.call("/api/construct/project", {"path": str(other)})
        self.assertEqual((c["project"], c["project_choice"]), (str(other), str(other)))
        self.call("/api/construct/project", {"path": ""})
        self.assertEqual(self.call("/api/construct")["project"], str(self.proj))


if __name__ == "__main__":
    unittest.main()
