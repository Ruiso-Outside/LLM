"""Setor Sprites: pixel art (pixel.py), escolha do pacote do motor no Linux e a conexao com o Arasaka Construct."""
import base64
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "app"))
import mcp  # noqa: E402
import media  # noqa: E402
import pixel  # noqa: E402
import sprites  # noqa: E402


def blob(w=64, h=64, bg=(250, 250, 250), fg=(30, 140, 60), eye=(255, 255, 255), mouth=(150, 20, 30)):
    """Um 'personagem' redondo com olhos e boca sobre fundo liso."""
    img = pixel.Img(w, h)
    cx, cy, r = w / 2, h / 2, w / 3
    for y in range(h):
        for x in range(w):
            c = bg
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                c = fg
                if abs(y - (cy - r / 3)) < r / 8 and (abs(x - (cx - r / 3)) < r / 8 or abs(x - (cx + r / 3)) < r / 8):
                    c = eye
                if abs(y - (cy + r / 3)) < r / 12 and abs(x - cx) < r / 3:
                    c = mouth
            img.put(x, y, c + (255,))
    return img


def png_filtered(img, filt):
    """PNG RGBA com um filtro fixo em todas as linhas (para testar o decodificador)."""
    raw, prev, bpp, stride = bytearray(), bytearray(img.w * 4), 4, img.w * 4
    for y in range(img.h):
        line = img.px[y * stride:(y + 1) * stride]
        f = bytearray(stride)
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            pred = {0: 0, 1: a, 2: b, 3: (a + b) // 2, 4: pixel._paeth(a, b, c)}[filt]
            f[i] = (line[i] - pred) & 255
        raw += bytes([filt]) + f
        prev = line

    def chunk(k, d):
        return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d) & 0xFFFFFFFF)
    return pixel.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", img.w, img.h, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


class Png(unittest.TestCase):
    def test_roundtrip_and_all_filters(self):
        img = blob(37, 23)
        self.assertEqual(bytes(pixel.decode_png(pixel.encode_png(img)).px), bytes(img.px))
        for f in range(5):
            self.assertEqual(bytes(pixel.decode_png(png_filtered(img, f)).px), bytes(img.px), f"filtro {f}")

    def test_rejects_other_files(self):
        with self.assertRaises(ValueError):
            pixel.decode_png(b"GIF89a....")


class PixelArt(unittest.TestCase):
    def test_background_becomes_transparent(self):
        out = pixel.remove_background(blob())
        self.assertEqual(out.get(0, 0)[3], 0)
        self.assertEqual(out.get(32, 32)[3], 255)

    def test_sprite_sizes_feet_on_base_and_palette(self):
        for size in (16, 32, 64):
            sprites_, sheet, pal = pixel.pixelate([blob(256, 256)], size, 6)
            s = sprites_[0]
            self.assertEqual((s.w, s.h), (size, size))
            self.assertEqual(s.get(0, 0)[3], 0)
            x0, y0, x1, y1 = pixel.bbox(s)
            self.assertEqual(y1, size - 1, "o desenho encosta na base (margem de 1 px)")
            colors = {s.get(x, y)[:3] for y in range(size) for x in range(size) if s.get(x, y)[3]}
            self.assertLessEqual(len(colors), 6)
            self.assertTrue(colors <= set(pal))
            alphas = {s.get(x, y)[3] for y in range(size) for x in range(size)}
            self.assertEqual(alphas, {0, 255}, "pixel art: alfa so 0 ou 255")

    def test_small_details_keep_their_color(self):
        s = pixel.pixelate([blob(256, 256)], 32, 6)[0][0]
        colors = {s.get(x, y)[:3] for y in range(32) for x in range(32) if s.get(x, y)[3]}
        self.assertTrue(any(r > 120 and g < 60 for r, g, b in colors), f"a boca vermelha sumiu: {colors}")
        self.assertTrue(any(min(c) > 200 for c in colors), "os olhos brancos sumiram")

    def test_outline_and_sheet(self):
        frames = [blob(128, 128, fg=(30, 140, 60)), blob(128, 128, fg=(40, 60, 160))]
        sprites_, sheet, pal = pixel.pixelate(frames, 16, 8, add_outline=True, cols=1)
        self.assertEqual((sheet.w, sheet.h), (16, 32))
        self.assertIn((20, 12, 28), pal)
        s = sprites_[0]
        x0, y0, x1, y1 = pixel.bbox(s)
        self.assertEqual(s.get((x0 + x1) // 2, y0)[:3], (20, 12, 28), "contorno no topo")

    def test_upscale_nearest(self):
        s = pixel.upscale(blob(8, 8), 4)
        self.assertEqual((s.w, s.h), (32, 32))
        self.assertEqual(s.get(0, 0), s.get(3, 3))

    def test_invalid_size(self):
        with self.assertRaises(ValueError):
            pixel.to_sprite(blob(), 33)


class EnginePackage(unittest.TestCase):
    def test_glibc_of_ubuntu_packages(self):
        self.assertEqual(media.ubuntu_glibc("sd-master-x-bin-Linux-Ubuntu-24.04-x86_64-vulkan.zip"), (2, 39))
        self.assertEqual(media.ubuntu_glibc("sd-bin-Linux-Ubuntu-26.04-x86_64.zip"), (2, 43))
        self.assertEqual(media.ubuntu_glibc("llama-b1-bin-ubuntu-22.04-x64.zip"), (2, 35))
        self.assertIsNone(media.ubuntu_glibc("sd-bin-win-cuda12-x64.zip"))

    def test_zorin18_skips_ubuntu_2604_build(self):
        # o caso real: o pacote do Ubuntu 26.04 pede GLIBC_2.43 e o Zorin OS 18 tem a 2.39
        self.assertFalse(media.linux_asset_ok("sd-master-532d2c1-bin-Linux-Ubuntu-26.04-x86_64-vulkan.zip", (2, 39)))
        self.assertTrue(media.linux_asset_ok("sd-master-3be2378-bin-Linux-Ubuntu-24.04-x86_64-vulkan.zip", (2, 39)))
        self.assertTrue(media.linux_asset_ok("algo-linux-x64.zip", (2, 39)))

    def test_release_picker_walks_back(self):
        rels = [{"tag_name": "novo", "assets": [{"name": "sd-a-bin-Linux-Ubuntu-26.04-x86_64-vulkan.zip"}]},
                {"tag_name": "velho", "assets": [{"name": "sd-b-bin-Linux-Ubuntu-24.04-x86_64-vulkan.zip"}]}]
        old_get, old_linux = media._get_json, media.LINUX
        media._get_json, media.LINUX = (lambda url: rels), True
        try:
            r = media._latest_win_release("x/y", lambda n: "vulkan" in n and media.linux_asset_ok(n, (2, 39)))
            self.assertEqual(r["tag_name"], "velho")
        finally:
            media._get_json, media.LINUX = old_get, old_linux

    def test_pixel_preset_files(self):
        with tempfile.TemporaryDirectory() as d:
            media.configure(d, None, None)
            names = [n for _, _, _, n in media.preset_files(media.PIXEL_PRESET)]
            self.assertEqual(names, ["sd_xl_base_1.0.safetensors", "sdxl_vae.safetensors", "pixel-art-xl.safetensors", "lcm-sdxl.safetensors"])
            self.assertFalse(media.preset_installed(media.PIXEL_PRESET))
            for _, _, folder, n in media.preset_files(media.PIXEL_PRESET):
                folder.mkdir(parents=True, exist_ok=True)
                (folder / n).write_bytes(b"x")
            self.assertTrue(media.preset_installed(media.PIXEL_PRESET))


class Construct(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.proj = self.root / "MeuJogo"
        self.proj.mkdir()
        (self.proj / "project.luau").write_text("return {}", "utf-8")
        self.recent = self.root / "recentes.txt"
        self.recent.write_text(f"{self.root / 'apagado'}\n{self.proj}\n", "utf-8")
        self.env = {k: os.environ.get(k) for k in ("ARASAKA_CONSTRUCT_EDITOR", "ARASAKA_CONSTRUCT_RECENT")}
        os.environ["ARASAKA_CONSTRUCT_EDITOR"] = str(TESTS / "fake_construct.py")
        os.environ["ARASAKA_CONSTRUCT_RECENT"] = str(self.recent)
        (self.root / "data").mkdir()
        mcp.configure(self.root / "data")
        media.configure(self.root, None, None)
        mcp.MANAGER.sync()

    def tearDown(self):
        mcp.MANAGER.stop()
        mcp.MANAGER.servers = {}
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def test_discovered_without_config(self):
        srv = mcp.MANAGER.get(mcp.CONSTRUCT_ID)
        self.assertIsNotNone(srv)
        self.assertEqual(srv.cfg["project"], str(self.proj), "usa o projeto recente que ainda existe")
        self.assertEqual(srv.cfg["args"][-2:], [str(self.proj), "--mcp"])
        srv.connect()
        st = sprites.construct_status()
        self.assertEqual((st["state"], st["tools"], st["version"], st["can_sprites"]), ("pronto", 4, "9.9.9", True))
        self.assertIn("MeuJogo", sprites.construct_call("project_info", {}))

    def test_missing_editor(self):
        os.environ["ARASAKA_CONSTRUCT_EDITOR"] = str(self.root / "nao-existe")
        mcp.MANAGER.sync()
        self.assertIsNone(mcp.MANAGER.get(mcp.CONSTRUCT_ID))
        self.assertEqual(sprites.construct_status()["state"], "ausente")

    def test_prefs_are_kept_apart_from_custom_servers(self):
        srv = mcp.MANAGER.get(mcp.CONSTRUCT_ID).public()
        mcp.save([{**srv, "enabled": False, "allowed": ["write_image"]}, {"name": "Outro", "command": "x"}])
        data = json.loads((self.root / "data" / "mcp.json").read_text("utf-8"))
        self.assertEqual([s["id"] for s in data["servers"]], ["outro"])
        self.assertEqual((data["construct"]["enabled"], data["construct"]["tools"]), (False, ["write_image"]))
        cfg = mcp.MANAGER.get(mcp.CONSTRUCT_ID).cfg
        self.assertEqual((cfg["enabled"], cfg["tools"]), (False, ["write_image"]))

    def test_choose_project(self):
        with self.assertRaises(mcp.MCPError):
            mcp.set_construct_project(str(self.root))
        other = self.root / "Outro"
        other.mkdir()
        (other / "project.luau").write_text("return {}", "utf-8")
        mcp.set_construct_project(str(other))
        self.assertEqual(mcp.MANAGER.get(mcp.CONSTRUCT_ID).cfg["args"][-2], str(other))
        mcp.set_construct_project("")  # volta para o mais recente
        self.assertEqual(mcp.MANAGER.get(mcp.CONSTRUCT_ID).cfg["project"], str(self.proj))

    def test_send_sprite_sheet(self):
        res = sprites.process([self._png(blob(128, 128)), self._png(blob(128, 128, fg=(200, 120, 20)))], sprites.clean_params({"size": 16}), rows=2)
        self.assertEqual((res["cols"], res["rows"], res["sheet_w"], res["sheet_h"]), (1, 2, 16, 32))
        out = sprites.send_to_construct(res["sheet"], "slime", 16, res["cols"], res["rows"], ["baixo", "cima"])
        self.assertEqual(out["path"], "assets/mikoshi/slime.png")
        self.assertEqual((self.proj / "assets/mikoshi/slime.png").read_bytes(), media.upload_path(res["sheet"]).read_bytes())
        spr = json.loads((self.proj / "sprites/slime.sprite.luau").read_text("utf-8")[7:])
        self.assertEqual(spr["animations"][0]["directions"], ["baixo", "cima"])
        self.assertEqual([(a["name"], a["frameW"], a["frames"]) for a in spr["animations"]], [("parado", 16, 1)])
        with self.assertRaises(ValueError):
            sprites.send_to_construct(res["sheet"], "nome com espaço", 16, 1, 2)

    def _png(self, img):
        fid, p = media.new_media_path("png")
        p.write_bytes(pixel.encode_png(img))
        return p


class MikoshiMcpServer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        media.configure(self._tmp.name, None, None)

    def tearDown(self):
        self._tmp.cleanup()

    def rpc(self, method, params=None, mid=1):
        return sprites.handle_rpc({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}},
                                  self.gen, lambda: {"ok": True})

    def gen(self, prompt, negative, seed, mode, on_progress=None):
        self.prompts.append((prompt, seed, mode))
        fid, p = media.new_media_path("png")
        p.write_bytes(pixel.encode_png(blob(96, 96)))
        return p

    def test_protocol_and_tools(self):
        self.prompts = []
        r = self.rpc("initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(r["serverInfo"]["name"], "arasaka-mikoshi")
        names = [t["name"] for t in self.rpc("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["generate_sprite", "pixelate_image", "sprite_status"])
        self.assertIsNone(sprites.handle_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, None, None))
        res = self.rpc("tools/call", {"name": "generate_sprite", "arguments": {"prompt": "slime", "views": ["baixo", "esquerda"],
                                                                                 "frames": 2, "size": 16, "seed": 5}})["result"]
        self.assertFalse(res.get("isError"), res)
        self.assertIn("folha 32x32", res["content"][0]["text"])
        self.assertTrue(base64.b64decode(res["content"][1]["data"]).startswith(pixel.PNG_SIG))
        self.assertEqual([s for _, s, _ in self.prompts], [5, 6, 5, 6], "mesma semente por direcao, +1 por variacao")
        self.assertIn("front view", self.prompts[0][0])
        self.assertIn("side view, facing left", self.prompts[2][0])
        data = base64.b64encode(pixel.encode_png(blob(64, 64))).decode()
        res = self.rpc("tools/call", {"name": "pixelate_image", "arguments": {"data": data, "size": 24}})["result"]
        self.assertIn("24x24", res["content"][0]["text"])
        bad = self.rpc("tools/call", {"name": "pixelate_image", "arguments": {"size": 33, "data": data}})["result"]
        self.assertTrue(bad["isError"])
        self.assertEqual(self.rpc("nada")["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
