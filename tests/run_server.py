"""Sobe o servidor do LLM Local para os testes, com o llama-server falso e modelos falsos.

Uso: LLM_HOME=<pasta temporaria> LLM_PORT=<porta> python tests/run_server.py
"""
import os
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
HOME = Path(os.environ["LLM_HOME"])
GB = 1024 ** 3
for name, size in [("models/Qwen3-8B-Q4_K_M.gguf", 5 * GB), ("models/gemma-3-4b-it-Q4_K_M.gguf", 3 * GB)]:
    f = HOME / name
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        with open(f, "wb") as fh:
            fh.truncate(size)

sys.path.insert(0, str(TESTS.parent / "app"))
import server  # noqa: E402

FAKE = str(TESTS / "fake_llama.py")
server.installed_backends = lambda: {"cuda": {"exe": "FAKE_LLAMA", "version": "teste"}}
_Popen = subprocess.Popen


def popen(cmd, *a, **kw):
    if isinstance(cmd, list) and cmd and cmd[0] == "FAKE_LLAMA":
        cmd = [sys.executable, FAKE] + cmd[1:]
        kw["cwd"] = str(TESTS)
    return _Popen(cmd, *a, **kw)


server.subprocess.Popen = popen
server.GPU = {"vendor": "nvidia", "name": "teste", "vram_mb": 16303}
server.main()
