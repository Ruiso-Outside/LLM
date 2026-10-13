"""Cliente MCP contra um servidor MCP falso (stdio)."""
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "app"))
import mcp  # noqa: E402

FAKE = [sys.executable, str(TESTS / "fake_mcp.py")]


class McpClient(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        mcp.configure(self._tmp.name)
        mcp.save([{"name": "Fake", "command": FAKE[0], "args": FAKE[1:]}])

    def tearDown(self):
        mcp.MANAGER.stop()
        self._tmp.cleanup()

    def test_connect_lists_all_pages(self):
        tools, mapping = mcp.MANAGER.toolset(["fake"])
        self.assertEqual(sorted(mapping), ["mcp__fake__echo", "mcp__fake__set_value", "mcp__fake__snapshot"])
        srv = mcp.MANAGER.get("fake")
        self.assertEqual((srv.state, srv.info["name"], srv.instructions), ("pronto", "fake", "Servidor de teste."))
        self.assertEqual(tools[0]["function"]["parameters"]["required"], ["text"])
        self.assertTrue(tools[0]["function"]["description"].startswith("[Fake]"))

    def test_calls(self):
        srv = mcp.MANAGER.get("fake")
        self.assertEqual(mcp.result_text(srv.call("echo", {"text": "oi"}))[0], "eco: oi")
        self.assertEqual(mcp.result_text(srv.call("set_value", {"value": "7"}))[0], "valor = 7")
        text, imgs = mcp.result_text(srv.call("snapshot", {}), lambda data, mime: f"{mime}:{data[:4].hex()}")
        self.assertEqual(imgs, ["image/png:89504e47"])
        self.assertTrue(mcp.result_text(srv.call("nao_existe", {}))[0].startswith("Erro da ferramenta"))

    def test_reconnects_after_crash(self):
        srv = mcp.MANAGER.get("fake")
        srv.connect()
        srv.client.close()  # simula o programa fechando
        self.assertEqual(mcp.result_text(srv.call("echo", {"text": "de novo"}))[0], "eco: de novo")

    def test_bad_command_reports_error(self):
        mcp.save([{"name": "Quebrado", "command": "comando-que-nao-existe-xyz"}])
        errors = []
        tools, _ = mcp.MANAGER.toolset(["quebrado"], on_error=lambda name, err: errors.append(err))
        self.assertEqual(tools, [])
        self.assertTrue(errors and "Quebrado" in errors[0])
        self.assertEqual(mcp.MANAGER.get("quebrado").public()["state"], "erro")

    def test_config_change_restarts_server(self):
        srv = mcp.MANAGER.get("fake")
        srv.connect()
        mcp.save([{"id": "fake", "name": "Fake renomeado", "command": FAKE[0], "args": FAKE[1:], "auto_approve": True}])
        self.assertIs(mcp.MANAGER.get("fake"), srv)  # mesmo comando: so atualiza as opcoes
        self.assertTrue(srv.cfg["auto_approve"])
        mcp.save([{"id": "fake", "name": "Fake", "command": FAKE[0], "args": FAKE[1:] + ["--x"]}])
        self.assertIsNot(mcp.MANAGER.get("fake"), srv)
        self.assertEqual(srv.state, "parado")


if __name__ == "__main__":
    unittest.main()
