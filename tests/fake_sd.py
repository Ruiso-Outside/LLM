"""stable-diffusion.cpp falso para os testes: aceita as mesmas opcoes do sd-cli, mostra o progresso e grava um PNG
(um "personagem" redondo sobre fundo branco). Guarda a linha de comando em <saida>.args.json para o teste conferir."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import pixel  # noqa: E402

argv = sys.argv[1:]
if "--help" in argv:
    print("usage: sd-cli [options]\n  --lora-model-dir <string>\n  --sampling-method")
    sys.exit(0)


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


out = Path(opt("-o"))
w, h, steps = min(256, int(opt("-W", 512))), min(256, int(opt("-H", 512))), int(opt("--steps", 4))  # menor: teste rapido
for i in range(1, steps + 1):
    print(f"  |{'=' * i}| {i}/{steps} - 9.99it/s", flush=True)
seed = int(opt("-s", 0))
img = pixel.Img(w, h)
cx, cy, r = w // 2, h // 2 + h // 10, w // 4
color = (40 + seed % 7 * 20, 160, 70)
for y in range(h):
    for x in range(w):
        inside = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
        eye = (x - cx + r // 3) ** 2 + (y - cy + r // 3) ** 2 <= (r // 6) ** 2 or (x - cx - r // 3) ** 2 + (y - cy + r // 3) ** 2 <= (r // 6) ** 2
        img.put(x, y, ((255, 255, 255) if eye else color if inside else (250, 250, 250)) + (255,))
out.write_bytes(pixel.encode_png(img))
Path(str(out) + ".args.json").write_text(json.dumps(argv), "utf-8")
