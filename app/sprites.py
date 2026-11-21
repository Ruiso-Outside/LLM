"""Setor Sprites da Arasaka Mikoshi: pixel art e folhas de sprites com IA local.

Gera com o stable-diffusion.cpp (SDXL + LoRA Pixel Art XL, preset media.PIXEL_PRESET), passa pelo pixel.py
(fundo transparente, recorte, reducao sem borrar para 16/32/64..., paleta comum a todos os quadros, contorno) e
monta a folha: uma linha por direcao (frente, esquerda, direita, costas), uma coluna por variacao.

Tambem envia o resultado para o Arasaka Construct (write_image + create_sprite pelo MCP dele) e expoe as
ferramentas generate_sprite / pixelate_image como servidor MCP da propria Mikoshi (POST /mcp), para o Claude
Code, o Cursor ou outro assistente que mexe no Construct gerar sprites aqui.
"""
import base64
import json
import random
import re
import time
from pathlib import Path

import mcp
import media
import pixel

# as direcoes na ordem do Arasaka Construct (uma linha da folha por direcao)
VIEWS = {
    "baixo": "front view, facing the viewer",
    "esquerda": "side view, facing left",
    "direita": "side view, facing right",
    "cima": "back view, facing away",
}
STYLE = "pixel art, {subject}, single game sprite, full body, centered, plain flat white background, crisp pixels, limited palette"
NEGATIVE = ("blurry, smooth, 3d render, photo, realistic, gradient background, scenery, text, watermark, signature, "
            "multiple characters, cropped, cut off, frame, border, shadow on ground")
LIMITS = {"frames": 8, "views": 4, "colors": 64}
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")


def build_prompt(subject, view=""):
    p = STYLE.format(subject=subject.strip().rstrip("."))
    return f"{p}, {VIEWS.get(view, view)}" if view else p


def clean_params(b):
    size = int(b.get("size") or 32)
    if size not in pixel.SIZES:
        raise ValueError(f"Tamanho {size}: use {', '.join(map(str, pixel.SIZES))}.")
    views = [v for v in (b.get("views") or []) if v in VIEWS][:LIMITS["views"]]
    return {"size": size, "colors": max(2, min(LIMITS["colors"], int(b.get("colors") or 16))),
            "frames": max(1, min(LIMITS["frames"], int(b.get("frames") or 1))), "views": views,
            "outline": bool(b.get("outline")), "remove_bg": b.get("remove_bg", True) is not False,
            "tolerance": max(5, min(120, int(b.get("tolerance") or 40))),
            "mode": b.get("mode") if b.get("mode") in ("rapido", "qualidade") else "rapido"}


def _save_png(img):
    fid, out = media.new_media_path("png")
    out.write_bytes(pixel.encode_png(img))
    return fid


def process(sources, params, rows=1):
    """sources: caminhos de PNG em ordem de linha (rows linhas). Devolve o resultado salvo (ids dos arquivos)."""
    imgs = [pixel.decode_png(Path(p).read_bytes()) for p in sources]
    cols = max(1, len(imgs) // max(1, rows))
    sprites, sheet, pal = pixel.pixelate(imgs, params["size"], params["colors"], params["remove_bg"], params["outline"],
                                         params["tolerance"], cols)
    return {"size": params["size"], "cols": cols, "rows": max(1, rows), "sprites": [_save_png(s) for s in sprites],
            "sheet": _save_png(sheet), "sheet_w": sheet.w, "sheet_h": sheet.h,
            "palette": ["#%02x%02x%02x" % c for c in pal]}


def generate(subject, params, gen, on_event=None, cancel=None, seed=-1):
    """gen(prompt, negative, seed, mode, on_progress) -> caminho do PNG gerado (o server.py cuida da GPU)."""
    subject = (subject or "").strip()
    if not subject:
        raise ValueError("Descreva o sprite.")
    seed = random.randint(0, 2 ** 31 - 1) if int(seed) < 0 else int(seed)
    views = params["views"] or [""]
    jobs = [(v, f) for v in views for f in range(params["frames"])]
    sources, t0 = [], time.time()
    for n, (view, f) in enumerate(jobs):
        if cancel and cancel():
            raise RuntimeError("cancelado")
        prompt = build_prompt(subject, view)
        if on_event:
            on_event({"stage": "image", "index": n, "total": len(jobs), "view": view, "prompt": prompt})
        # mesma semente para todas as direcoes (o mesmo personagem); +f para cada variacao
        sources.append(gen(prompt, NEGATIVE, seed + f, params["mode"],
                           lambda pr, n=n: on_event and pr.get("step") and on_event(
                               {"stage": "progress", "index": n, "total": len(jobs), "step": pr["step"],
                                "total_steps": pr.get("total"), "speed": pr.get("speed", "")})))
    if on_event:
        on_event({"stage": "pixel"})
    res = process(sources, params, len(views))
    res.update({"subject": subject, "seed": seed, "views": params["views"], "seconds": round(time.time() - t0, 1),
                "sources": [Path(p).name for p in sources]})
    return res


# ---------------------------------------------------------------- Arasaka Construct

def construct_status():
    """Estado da conexao com o Arasaka Construct (para a barra da Mikoshi e o setor Sprites)."""
    srv = mcp.MANAGER.get(mcp.CONSTRUCT_ID)
    if not srv:
        return {"installed": False, "state": "ausente", "tools": 0, "project": "", "recent": mcp.construct_recent()}
    cfg = srv.cfg
    return {"installed": True, "state": srv.state, "error": srv.error, "tools": len(srv.tools),
            "version": (srv.info or {}).get("version", ""), "command": cfg.get("command", ""),
            "project": cfg.get("project", ""), "project_choice": cfg.get("project_choice", ""),
            "recent": cfg.get("recent", []), "enabled": cfg.get("enabled", True),
            "can_sprites": any(t["name"] == "write_image" for t in srv.tools)}


def _text(res):
    return "".join(c.get("text", "") for c in (res or {}).get("content", []) if c.get("type") == "text")


def construct_call(tool, args, timeout=120):
    srv = mcp.MANAGER.get(mcp.CONSTRUCT_ID)
    if not srv:
        raise mcp.MCPError("Arasaka Construct não encontrado neste PC. Instale pela Arasaka Central (aba Apps).")
    res = srv.call(tool, args, timeout=timeout)
    if res.get("isError"):
        raise mcp.MCPError(_text(res) or f"{tool} falhou")
    return _text(res)


def send_to_construct(sheet_id, name, size, cols, rows, views=None, fps=8, folder="assets/mikoshi"):
    """Grava a folha no projeto aberto do Construct e cria o sprite animado (sprites/<nome>.sprite.luau)."""
    if not NAME_RE.match(name or ""):
        raise ValueError("Nome do sprite: use letras, números, _ ou - (sem espaços).")
    srv = mcp.MANAGER.get(mcp.CONSTRUCT_ID)
    if srv:
        srv.connect()
        if not any(t["name"] == "write_image" for t in srv.tools):
            raise mcp.MCPError("Este Arasaka Construct é antigo e não recebe imagens pelo MCP. Atualize-o pela Arasaka Central.")
    if not mcp.construct_project():
        raise mcp.MCPError("Nenhum projeto do Arasaka Construct escolhido. Abra um projeto no editor ou escolha a pasta aqui.")
    png = media.upload_path(sheet_id).read_bytes()
    path = f"{folder.strip('/')}/{name}.png"
    out = [construct_call("write_image", {"path": path, "data": base64.b64encode(png).decode()})]
    # "parado" (1o quadro) e "andando" (todos): os nomes que os modelos do Construct usam no script do jogador
    base = {"texture": path, "frameW": int(size), "frameH": int(size), "loop": True}
    if views and len(views) == rows:
        base["directions"] = list(views)
    anims = [{**base, "name": "parado", "frames": 1, "fps": 4}]
    if cols > 1:
        anims.append({**base, "name": "andando", "frames": int(cols), "fps": fps})
    out.append(construct_call("create_sprite", {"name": name, "animations": anims}))
    return {"path": path, "sprite": f"sprites/{name}.sprite.luau", "log": out}


# ---------------------------------------------------------------- servidor MCP da Mikoshi (POST /mcp)

SERVER_INFO = {"name": "arasaka-mikoshi", "version": "1"}
INSTRUCTIONS = ("Arasaka Mikoshi: IA local no PC. generate_sprite gera pixel art / folhas de sprites com o modelo local "
                "(SDXL + LoRA de pixel art) e pode gravar direto no projeto aberto do Arasaka Construct; pixelate_image "
                "transforma uma imagem PNG em sprite (paleta, fundo transparente, 16/32/64 px).")


def tool_defs():
    common = {
        "size": {"type": "integer", "enum": list(pixel.SIZES), "description": "lado do sprite em pixels (padrão 32)"},
        "colors": {"type": "integer", "description": "cores da paleta (2 a 64, padrão 16)"},
        "outline": {"type": "boolean", "description": "contorno escuro de 1 px"},
        "remove_bg": {"type": "boolean", "description": "fundo transparente (padrão true)"},
        "construct_name": {"type": "string", "description": "se informado, grava no projeto aberto do Arasaka Construct "
                                                            "(assets/mikoshi/<nome>.png) e cria sprites/<nome>.sprite.luau"},
    }
    return [
        {"name": "generate_sprite",
         "description": "Gera um sprite em pixel art com IA local (SDXL + LoRA Pixel Art XL) e devolve o PNG. Com views, "
                        "monta uma folha: uma linha por direção (baixo, esquerda, direita, cima), uma coluna por variação.",
         "inputSchema": {"type": "object", "required": ["prompt"], "properties": {
             "prompt": {"type": "string", "description": "o que desenhar, em inglês de preferência (ex.: 'green slime monster')"},
             "views": {"type": "array", "items": {"type": "string", "enum": list(VIEWS)}, "description": "direções (linhas da folha)"},
             "frames": {"type": "integer", "description": "variações por direção (1 a 8)"},
             "mode": {"type": "string", "enum": ["rapido", "qualidade"], "description": "rapido = 8 passos (LCM); qualidade = 30 passos"},
             "seed": {"type": "integer"}, **common}}},
        {"name": "pixelate_image",
         "description": "Transforma uma imagem PNG em sprite de pixel art: tira o fundo, recorta, reduz sem borrar e limita a paleta.",
         "inputSchema": {"type": "object", "properties": {
             "path": {"type": "string", "description": "caminho de um PNG neste PC"},
             "data": {"type": "string", "description": "ou o PNG em base64"}, **common}}},
        {"name": "sprite_status", "description": "Se o motor e o modelo de pixel art estão instalados e se o Construct está conectado.",
         "inputSchema": {"type": "object", "properties": {}}, "annotations": {"readOnlyHint": True}},
    ]


def _tool_result(res, extra=""):
    png = media.upload_path(res["sheet"]).read_bytes()
    info = (f"Sprite {res['size']}x{res['size']}, folha {res['sheet_w']}x{res['sheet_h']} ({res['cols']} colunas x {res['rows']} linhas), "
            f"{len(res['palette'])} cores: {' '.join(res['palette'])}\nArquivo: {media.upload_path(res['sheet'])}" + extra)
    return {"content": [{"type": "text", "text": info}, {"type": "image", "mimeType": "image/png", "data": base64.b64encode(png).decode()}]}


def call_tool(name, args, gen, status_fn):
    """Executa uma ferramenta do servidor MCP da Mikoshi. gen: igual a generate(); status_fn() -> dict."""
    args = args or {}
    if name == "sprite_status":
        return {"content": [{"type": "text", "text": json.dumps(status_fn(), ensure_ascii=False)}]}
    params = clean_params(args)
    if name == "generate_sprite":
        res = generate(args.get("prompt", ""), params, gen, seed=int(args.get("seed", -1)))
    elif name == "pixelate_image":
        if args.get("data"):
            fid, out = media.new_media_path("png")
            out.write_bytes(base64.b64decode(re.sub(r"^data:[^,]+,", "", args["data"])))
            src = out
        elif args.get("path"):
            src = Path(args["path"]).expanduser()
            if not src.is_file() or src.suffix.lower() != ".png":
                raise ValueError("path precisa ser um arquivo .png existente")
        else:
            raise ValueError("informe path ou data")
        res = process([src], params)
    else:
        raise ValueError(f"ferramenta desconhecida: {name}")
    extra = ""
    if args.get("construct_name"):
        sent = send_to_construct(res["sheet"], args["construct_name"], res["size"], res["cols"], res["rows"], res.get("views"))
        extra = f"\nGravado no Arasaka Construct: {sent['path']} e {sent['sprite']}"
    return _tool_result(res, extra)


def handle_rpc(msg, gen, status_fn):
    """Uma mensagem JSON-RPC do MCP (transporte HTTP em modo JSON). Devolve a resposta ou None (notificacao)."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "pedido inválido"}}
    mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if mid is None:
        return None
    try:
        if method == "initialize":
            r = {"protocolVersion": params.get("protocolVersion") or mcp.PROTOCOL, "serverInfo": SERVER_INFO,
                 "capabilities": {"tools": {}}, "instructions": INSTRUCTIONS}
        elif method == "ping":
            r = {}
        elif method == "tools/list":
            r = {"tools": tool_defs()}
        elif method == "tools/call":
            try:
                r = call_tool(params.get("name", ""), params.get("arguments"), gen, status_fn)
            except (ValueError, RuntimeError, OSError, mcp.MCPError) as e:
                r = {"content": [{"type": "text", "text": str(e)}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"método desconhecido: {method}"}}
    except Exception as e:  # noqa: BLE001
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}
    return {"jsonrpc": "2.0", "id": mid, "result": r}
