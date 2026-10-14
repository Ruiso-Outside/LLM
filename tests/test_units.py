"""Testes de unidade dos modulos do servidor (sem motor nem rede)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import agent  # noqa: E402
import agents  # noqa: E402
import catalog  # noqa: E402
import kb  # noqa: E402
import mcp  # noqa: E402
import modelsettings  # noqa: E402


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class ChunkText(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(kb.chunk_text("a\nb\nc"), [(1, 3, "a\nb\nc")])

    def test_long_text_overlaps_and_covers_all_lines(self):
        text = "\n".join(f"linha {i} " + "x" * 80 for i in range(1, 101))
        chunks = kb.chunk_text(text)
        self.assertGreater(len(chunks), 3)
        self.assertEqual(chunks[0][0], 1)
        self.assertEqual(chunks[-1][1], 100)
        for (_, end, _), (start, _, _) in zip(chunks, chunks[1:]):
            self.assertLessEqual(start, end + 1)  # sem buracos entre trechos
        self.assertTrue(all(len(c[2]) <= kb.CHUNK + 200 for c in chunks))

    def test_huge_single_line_is_split(self):
        chunks = kb.chunk_text("y" * (kb.CHUNK * 3))
        self.assertGreaterEqual(len(chunks), 3)


class ModelSettings(TempDirCase):
    def setUp(self):
        super().setUp()
        modelsettings.configure(self.tmp)

    def test_families(self):
        self.assertEqual(modelsettings.recommended("gemma-3-4b-it-Q4_K_M.gguf")[1], "Gemma")
        rec, fam = modelsettings.recommended("Qwen3-8B-Q4_K_M.gguf", caps=["reasoning"])
        self.assertEqual((fam, rec["temperature"], rec["top_k"]), ("Qwen3 (modo raciocínio)", 0.6, 20))
        self.assertTrue(modelsettings.recommended("modelo-desconhecido.gguf")[0]["generic"])

    def test_context_fits_vram(self):
        GB = 1024 ** 3
        self.assertEqual(modelsettings.recommended("x.gguf", model_size=5 * GB, vram_bytes=16 * GB)[0]["ctx_size"], 32768)
        self.assertEqual(modelsettings.recommended("x.gguf", model_size=5 * GB, vram_bytes=16 * GB, ctx_max=4096)[0]["ctx_size"], 4096)

    def test_effective_priority(self):
        rec, _ = modelsettings.recommended("gemma-3.gguf")
        base = {"temperature": 0.7, "ctx_size": 8192}
        self.assertEqual(modelsettings.effective(base, "gemma-3.gguf", rec)["temperature"], 1.0)
        self.assertEqual(modelsettings.effective(base, "gemma-3.gguf", rec, use_recommended=False)["temperature"], 0.7)
        modelsettings.save("gemma-3.gguf", {"temperature": 0.33})
        self.assertEqual(modelsettings.effective(base, "gemma-3.gguf", rec)["temperature"], 0.33)
        self.assertEqual(modelsettings.effective(base, "gemma-3.gguf", rec)["ctx_size"], 8192)


class Agents(TempDirCase):
    def setUp(self):
        super().setUp()
        agents.configure(self.tmp)

    def test_verdict_uses_last_one(self):
        self.assertEqual(agents.verdict_of("VEREDITO: REPROVADO ... depois\n**VEREDITO: APROVADO**"), "APROVADO")
        self.assertEqual(agents.verdict_of("Veredito - reprovada"), "REPROVADO")
        self.assertIsNone(agents.verdict_of("sem veredito"))

    def test_save_validates(self):
        doc = agents.save({"agents": [{"id": "a1", "name": "A", "temperature": 9, "mcp": ["roblox", "../x"], "kb": "nope"}],
                           "groups": [{"id": "g1", "steps": [{"agent": "a1", "role": "validator"}, {"agent": "zz"}],
                                       "max_retries": 99}]})
        a = doc["agents"][0]
        self.assertEqual((a["temperature"], a["mcp"], a["kb"], a["device"]), (2.0, ["roblox"], "", "auto"))
        self.assertEqual(doc["groups"][0]["steps"], [{"agent": "a1", "role": "validator"}])
        self.assertEqual(doc["groups"][0]["max_retries"], 5)

    def test_templates(self):
        doc, gid = agents.template("math")
        g = next(g for g in doc["groups"] if g["id"] == gid)
        self.assertEqual([s["role"] for s in g["steps"]], ["agent", "agent", "validator"])


class CodexWorkspace(TempDirCase):
    def test_sandbox_blocks_outside_paths(self):
        ws = agent.Workspace(self.tmp)
        self.assertEqual(ws.path("a/b.txt"), (self.tmp / "a/b.txt").resolve())
        for bad in ("../fora.txt", "C:/Windows/win.ini", "a/../../x"):
            with self.assertRaises(agent.ToolError):
                ws.path(bad)

    def test_edit_requires_unique_match(self):
        ws = agent.Workspace(self.tmp)
        agent.tool_write_file(ws, "f.txt", "um\ndois\num\n")
        with self.assertRaises(agent.ToolError):
            agent.tool_edit_file(ws, "f.txt", "um", "1")
        agent.tool_edit_file(ws, "f.txt", "dois", "2")
        self.assertIn("2", (self.tmp / "f.txt").read_text())

    def test_checkpoint_undo_and_diff(self):
        root = self.tmp / "proj"
        root.mkdir()
        (root / "old.txt").write_text("versao 1\n")
        ws = agent.Workspace(root)
        ck = agent.Checkpoint(self.tmp / "ck", ws.root)
        ck.touch(ws.path("old.txt"))
        ck.touch(ws.path("new.txt"))
        agent.tool_edit_file(ws, "old.txt", "versao 1", "versao 2")
        agent.tool_write_file(ws, "new.txt", "novo\n")
        d = {f["path"]: f for f in agent.diff_checkpoint(ck.dir)["files"]}
        self.assertEqual((d["old.txt"]["status"], d["new.txt"]["status"]), ("modified", "created"))
        agent.undo_checkpoint(ck.dir)
        self.assertEqual((root / "old.txt").read_text(), "versao 1\n")
        self.assertFalse((root / "new.txt").exists())
        with self.assertRaises(agent.ToolError):
            agent.undo_checkpoint(ck.dir)


class Catalog(unittest.TestCase):
    def test_quant_info(self):
        self.assertIn("Q4_K_M", str(catalog.quant_info("Qwen3-8B-Q4_K_M.gguf")))

    def test_caps_from_tags(self):
        caps = catalog.model_caps({"id": "x/y", "pipeline_tag": "image-text-to-text", "tags": ["vision"]})
        self.assertIsInstance(caps, dict)


class ModelFiles(unittest.TestCase):
    """Arquivos .gguf que nao sao modelos de conversa (MTP, visao, imatrix) e a escolha do acelerador."""

    @classmethod
    def setUpClass(cls):
        import os
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["LLM_HOME"] = cls._tmp.name
        import server
        cls.server = server

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_detects_mtp(self):
        s = self.server
        for name in ("MTP/mtp-gemma-4-12b-it-Q8_0.gguf", "mtp-gemma-4-12b-it.gguf",
                     "Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-FastMTP-32K.gguf", "modelo_mtp.gguf"):
            self.assertTrue(s.is_mtp(name), name)
        for name in ("gemma-4-12b-it-Q8_0.gguf", "Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-IQ3_XS.gguf", "smtpbot-7b.gguf"):
            self.assertFalse(s.is_mtp(name), name)
        self.assertTrue(s.is_aux_file("imatrix_unsloth.gguf"))
        self.assertTrue(s.is_aux_file("mmproj-BF16.gguf"))

    def test_hf_files_hides_aux(self):
        tree = [{"path": p, "size": n} for p, n in [("MTP/mtp-g-Q8_0.gguf", 444), ("g-Q8_0.gguf", 12000), ("mmproj-BF16.gguf", 167),
                                                    ("imatrix_unsloth.gguf", 13), ("g-Q4_K_M.gguf", 6800)]]
        self.assertEqual([f["path"] for f in self.server.hf_files("x/y", tree)], ["g-Q4_K_M.gguf", "g-Q8_0.gguf"])

    def test_pick_mtp(self):
        tree = [{"path": p, "size": n} for p, n in [("MTP/mtp-g-BF16.gguf", 822), ("MTP/mtp-g-F16.gguf", 822),
                                                    ("MTP/mtp-g-Q8_0.gguf", 444), ("mtp-g.gguf", 444), ("MTP/mtp-g-Q4_0.gguf", 300)]]
        self.assertEqual(self.server.pick_mtp(tree)["path"], "MTP/mtp-g-Q8_0.gguf")
        self.assertEqual(self.server.pick_mtp(tree, "g-Q4_0.gguf")["path"], "MTP/mtp-g-Q4_0.gguf")
        self.assertIsNone(self.server.pick_mtp([{"path": "g.gguf", "size": 1}]))


class VramGuard(unittest.TestCase):
    """Protecao de VRAM: descarrega extras (e depois o principal) so quando nada esta gerando."""

    @classmethod
    def setUpClass(cls):
        import os
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["LLM_HOME"] = cls._tmp.name
        import server
        cls.server = server

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_guard(self):
        s = self.server

        class Eng:
            def __init__(self, busy=0):
                self.busy, self.state, self.stopped = busy, "ready", False

            def stop(self):
                self.stopped = True
        busy = Eng(busy=1)
        s.POOL.extra = {("a.gguf", "gpu"): busy}
        s.vram_guard()
        self.assertFalse(busy.stopped)  # gerando: nao mexe
        idle, cpu = Eng(), Eng()
        s.POOL.extra = {("a.gguf", "gpu"): idle, ("b.gguf", "cpu"): cpu}
        s.vram_guard()
        self.assertTrue(idle.stopped)
        self.assertFalse(cpu.stopped)  # so libera a GPU
        self.assertIn("a", s.DIAG["guard"]["what"])
        s.POOL.extra = {}


class McpHelpers(TempDirCase):
    def test_split_command(self):
        self.assertEqual(mcp.split_command('npx -y pkg "C:\\minha pasta"'), ("npx", ["-y", "pkg", "C:\\minha pasta"]))
        with self.assertRaises(mcp.MCPError):
            mcp.split_command("  ")

    def test_save_cleans_config(self):
        mcp.configure(self.tmp)
        out = mcp.save([{"name": "Meu Servidor", "command_line": "node s.js --x", "env": "A=1\nB = 2\nlixo"},
                        {"name": "Meu Servidor", "type": "http", "url": "https://ex.com/mcp"}])
        self.assertEqual([s["id"] for s in out], ["meu_servidor", "meu_servidor2"])
        self.assertEqual((out[0]["command"], out[0]["args"], out[0]["env"]), ("node", ["s.js", "--x"], {"A": "1", "B": " 2"}))
        with self.assertRaises(mcp.MCPError):
            mcp.save([{"name": "x", "type": "http", "url": "ftp://nao"}])
        mcp.MANAGER.stop()

    def test_tool_name_is_valid(self):
        n = mcp.tool_name("roblox", "run code/with spaces" + "x" * 80)
        self.assertLessEqual(len(n), 64)
        self.assertRegex(n, r"^[A-Za-z0-9_-]+$")

    def test_result_text(self):
        res = {"content": [{"type": "text", "text": "ok"}, {"type": "image", "data": "aGk=", "mimeType": "image/png"}], "isError": True}
        text, imgs = mcp.result_text(res, lambda data, mime: "fid1")
        self.assertTrue(text.startswith("Erro da ferramenta: ok"))
        self.assertEqual(imgs, ["fid1"])
        self.assertEqual(mcp.result_text({"structuredContent": {"a": 1}})[0], '{"a": 1}')
        self.assertIn("+", mcp.result_text({"content": [{"type": "text", "text": "z" * 50}]}, limit=10)[0])

    def test_compacts_huge_json_results(self):
        big = {"evidence_id": "ev_1", "normalized_result": {"summary": {"browser_windows": 2, "ipc": {"operations": 48}},
                                                          "graph": {"nodes": [{"id": i, "pad": "x" * 200} for i in range(5000)]}}}
        import json
        text, _ = mcp.result_text({"content": [{"type": "text", "text": json.dumps(big)}]}, limit=5000)
        self.assertLess(len(text), 6000)
        self.assertIn('"browser_windows": 2', text)
        self.assertIn("itens omitidos", text)
        self.assertTrue(text.startswith("[resultado com"))

    def test_rea_profiles_and_node(self):
        self.assertTrue(set(mcp.REA_ESSENTIALS) <= set(mcp.REA_WINDOWS))
        self.assertLessEqual(len(mcp.REA_ESSENTIALS), 10)
        for v, ok in [((22, 19), True), ((22, 18), False), ((24, 11), True), ((24, 10), False), ((26, 0), True), ((20, 5), False), (None, False)]:
            self.assertEqual(mcp.rea_node_ok(v), ok, v)
        self.assertIn("--token-limit", mcp.REA_CLI_PROMPT)

    def test_approval_rules(self):
        srv = mcp.Server({"id": "s", "name": "S", "auto_approve": False})
        self.assertTrue(mcp.needs_approval(srv, {"name": "w"}))
        self.assertFalse(mcp.needs_approval(srv, {"name": "r", "annotations": {"readOnlyHint": True}}))
        srv.cfg["auto_approve"] = True
        self.assertFalse(mcp.needs_approval(srv, {"name": "w"}))


if __name__ == "__main__":
    unittest.main()
