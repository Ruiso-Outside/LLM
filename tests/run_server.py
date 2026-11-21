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
for name, size in [("models/Qwen3-8B-Q4_K_M.gguf", 5 * GB), ("models/gemma-3-4b-it-Q4_K_M.gguf", 3 * GB),
                   ("models/embed/Qwen3-Embedding-0.6B-Q8_0.gguf", 600 * 1024 ** 2)]:
    f = HOME / name
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        with open(f, "wb") as fh:
            fh.truncate(size)

sys.path.insert(0, str(TESTS.parent / "app"))
import server  # noqa: E402

FAKE = str(TESTS / "fake_llama.py")
FAKE_SD = str(TESTS / "fake_sd.py")
if os.environ.get("FAKE_SD") == "1":  # setor Sprites: motor de imagem falso e o modelo de pixel art "baixado"
    exe = HOME / "engine" / "sd" / ("sd-cli.exe" if os.name == "nt" else "sd-cli")
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("falso", "utf-8")
    (exe.parent / "version.txt").write_text("teste", "utf-8")
    import media  # noqa: E402
    media.configure(HOME, None, None)
    for _, _, folder, name in media.preset_files(media.PIXEL_PRESET):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(b"falso")
server.installed_backends = lambda: {"cuda": {"exe": "FAKE_LLAMA", "version": "teste"}}
_Popen = subprocess.Popen


def popen(cmd, *a, **kw):
    if isinstance(cmd, list) and cmd and cmd[0] == "FAKE_LLAMA":
        cmd = [sys.executable, FAKE] + cmd[1:]
        kw["cwd"] = str(TESTS)
    elif isinstance(cmd, list) and cmd and Path(str(cmd[0])).name.startswith("sd-cli"):
        cmd = [sys.executable, FAKE_SD] + cmd[1:]
    return _Popen(cmd, *a, **kw)


server.subprocess.Popen = popen
server.GPU = {"vendor": "nvidia", "name": "teste", "vram_mb": 16303}
server.gpu_sample = lambda: None  # nao le a placa de verdade (a protecao de VRAM nao age nos testes)
server.main()
