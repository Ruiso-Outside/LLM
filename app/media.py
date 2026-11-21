"""Midia do LLM Local: transcricao de audio (whisper.cpp), geracao de imagem
(stable-diffusion.cpp), arquivos enviados e extracao de texto de documentos.

Sem dependencias externas. As funcoes de rede (download/get_json) e as pastas
sao entregues pelo server.py via configure().
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

ROOT = ENGINE = MODELS = UPLOADS = None
_download = _get_json = None


def configure(root, download, get_json):
    global ROOT, ENGINE, MODELS, UPLOADS, _download, _get_json
    ROOT = Path(root)
    ENGINE, MODELS, UPLOADS = ROOT / "engine", ROOT / "models", ROOT / "data" / "uploads"
    for d in (ENGINE, MODELS, UPLOADS):
        d.mkdir(parents=True, exist_ok=True)
    _download, _get_json = download, get_json


# ---------------------------------------------------------------- arquivos enviados

ID_RE = re.compile(r"^[a-f0-9]{20}\.[a-z0-9]{1,6}$")
MAX_UPLOAD = 2 * 1024 ** 3  # 2 GB


def save_upload(name, data_iter):
    ext = re.sub(r"[^a-z0-9]", "", Path(name).suffix.lower().lstrip("."))[:6] or "bin"
    fid = f"{uuid.uuid4().hex[:20]}.{ext}"
    size = 0
    with open(UPLOADS / fid, "wb") as f:
        for chunk in data_iter:
            size += len(chunk)
            if size > MAX_UPLOAD:
                f.close()
                (UPLOADS / fid).unlink(missing_ok=True)
                raise ValueError("Arquivo grande demais (limite de 2 GB).")
            f.write(chunk)
    return {"id": fid, "name": name, "size": size}


def upload_path(fid):
    if not ID_RE.match(fid or ""):
        raise ValueError("arquivo invalido")
    p = UPLOADS / fid
    if not p.is_file():
        raise ValueError("arquivo nao encontrado")
    return p


def new_media_path(ext):
    fid = f"{uuid.uuid4().hex[:20]}.{ext}"
    return fid, UPLOADS / fid


# ---------------------------------------------------------------- texto de documentos Office

def _xml_text(xml, para_tag):
    xml = re.sub(rf"</{para_tag}>", "\n", xml)
    xml = re.sub(r"<w:tab/>|<a:tab/>", "\t", xml)
    xml = re.sub(r"<w:br/>|<a:br/>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")):
        text = text.replace(a, b)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_text(fid):
    """Extrai texto de .docx, .pptx, .xlsx e .odt enviados pelo usuario."""
    return extract_text_path(upload_path(fid))


def extract_text_path(p):
    """Extrai texto de um arquivo .docx, .pptx, .xlsx ou .odt no disco."""
    p = Path(p)
    ext = p.suffix.lower()
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        if ext == ".docx":
            return _xml_text(z.read("word/document.xml").decode("utf-8", "replace"), "w:p")
        if ext == ".pptx":
            slides = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                            key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
            return "\n\n".join(f"--- Slide {i} ---\n" + _xml_text(z.read(n).decode("utf-8", "replace"), "a:p")
                               for i, n in enumerate(slides, 1))
        if ext == ".xlsx":
            shared = []
            if "xl/sharedStrings.xml" in names:
                xml = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
                shared = [_xml_text(si, "x") for si in re.findall(r"<si>(.*?)</si>", xml, re.S)]
            out = []
            sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
            for i, n in enumerate(sheets, 1):
                xml = z.read(n).decode("utf-8", "replace")
                rows = []
                for row in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
                    cells = []
                    for attrs, inner in re.findall(r"<c([^>]*)>(.*?)</c>", row, re.S):
                        v = re.search(r"<v>(.*?)</v>", inner, re.S)
                        t = re.search(r'\bt="(\w+)"', attrs)
                        if t and t.group(1) == "s" and v:
                            cells.append(shared[int(v.group(1))] if int(v.group(1)) < len(shared) else "")
                        elif t and t.group(1) == "inlineStr":
                            cells.append(_xml_text(inner, "x"))
                        else:
                            cells.append(v.group(1) if v else "")
                    rows.append("\t".join(cells))
                out.append(f"--- Planilha {i} ---\n" + "\n".join(rows))
            return "\n\n".join(out)
        if ext == ".odt":
            return _xml_text(z.read("content.xml").decode("utf-8", "replace"), "text:p")
    raise ValueError("formato nao suportado")


# ---------------------------------------------------------------- instalacao dos motores

LINUX = os.name != "nt"


def host_glibc():
    """Versao da glibc deste Linux, ex.: (2, 39) no Ubuntu 24.04 / Zorin OS 18. None fora do Linux/glibc."""
    try:
        m = re.search(r"(\d+)\.(\d+)", os.confstr("CS_GNU_LIBC_VERSION") or "")
        return (int(m.group(1)), int(m.group(2))) if m else None
    except (AttributeError, ValueError, OSError):
        return None


def ubuntu_glibc(name):
    """glibc exigida por um pacote "...-Ubuntu-24.04-..." (20.04 = 2.31, +2 por ano, +1 nas versoes .10)."""
    m = re.search(r"ubuntu-(\d{2})\.(\d{2})", name, re.I)
    if not m:
        return None
    yy, mm = int(m.group(1)), int(m.group(2))
    return (2, 31 + 2 * (yy - 20) + (1 if mm >= 10 else 0))


def linux_asset_ok(name, glibc=None):
    """O pacote roda aqui? Pacotes feitos num Ubuntu mais novo pedem uma glibc que este sistema nao tem."""
    need, have = ubuntu_glibc(name), glibc or host_glibc()
    return need is None or have is None or have >= need


def _latest_win_release(repo, accept=None):
    """Versao mais nova com binarios deste sistema (Windows, ou Linux quando roda no Linux).
    accept(nome) filtra os pacotes; no Linux, por padrao, so os que rodam com a glibc daqui."""
    key = "linux" if LINUX else "win"
    accept = accept or (lambda n: key in n.lower() and (not LINUX or linux_asset_ok(n)))
    for page in (1, 2, 3):
        rels = _get_json(f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}")
        for r in rels:
            if any(accept(a["name"]) for a in r.get("assets", [])):
                return r
        if len(rels) < 100:
            break
    raise RuntimeError(f"Nenhuma versao com binarios {'Linux' if LINUX else 'Windows'} que rodem neste sistema em {repo}.")


def _pick(assets, pattern):
    cands = []
    for n in assets:
        m = re.match(pattern, n)
        if m:
            ver = tuple(int(x) for x in re.findall(r"\d+", m.group(1) if m.groups() else "0"))
            cands.append((ver, n))
    return max(cands)[1] if cands else None


def _install(task, repo, files, dest_name, exe_names, rel=None):
    rel = rel or _latest_win_release(repo)
    assets = {a["name"]: (a["browser_download_url"], a.get("size", 0)) for a in rel["assets"]}
    files = [f for f in files if f in assets]
    if not files:
        raise RuntimeError("Pacote nao encontrado nesta versao. Tente outra opcao.")
    task["total"] = sum(assets[f][1] for f in files)
    tmp = ENGINE / f"_dl_{dest_name}"
    tmp.mkdir(exist_ok=True)
    done = 0
    for f in files:
        task["detail"] = f"Baixando {f}"
        done += _download(assets[f][0], tmp / f, task, done)
    task["detail"] = "Extraindo..."
    dest = ENGINE / dest_name
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir()
    for f in files:
        with zipfile.ZipFile(tmp / f) as z:
            z.extractall(dest)
    if LINUX:  # o .zip nao guarda a permissao de executar
        for x in dest.rglob("*"):
            if x.is_file() and (x.suffix in ("", ".so") or ".so." in x.name):
                x.chmod(0o755)
    exe = find_exe(dest_name, exe_names)
    if not exe:
        raise RuntimeError("Executavel nao encontrado no pacote baixado.")
    for dll in dest.rglob("*.dll"):  # DLLs do CUDA ao lado do executavel
        if dll.parent != exe.parent and not (exe.parent / dll.name).exists():
            shutil.copy2(dll, exe.parent / dll.name)
    (dest / "version.txt").write_text(f"{rel['tag_name']} ({files[0]})", "utf-8")
    shutil.rmtree(tmp, ignore_errors=True)


def find_exe(dest_name, names):
    d = ENGINE / dest_name
    if not d.is_dir():
        return None
    for n in names:
        exe = next(d.rglob(n), None)
        if exe:
            return exe
    return None


def engine_version(dest_name):
    f = ENGINE / dest_name / "version.txt"
    return f.read_text("utf-8").strip() if f.exists() else ""


def _hf_download(task, items, folder):
    """items: lista de (repo, caminho no repo, tamanho)."""
    folder.mkdir(parents=True, exist_ok=True)
    task["total"] = sum(s for _, _, s in items)
    done = 0
    for repo, path, _ in items:
        dest = folder / Path(path).name
        task["detail"] = Path(path).name
        if dest.exists():
            done += dest.stat().st_size
            task["done"] = done
            continue
        done += _download(f"https://huggingface.co/{repo}/resolve/main/{path}", dest, task, done)


def _hf_size(repo, path):
    try:
        folder = path.rsplit("/", 1)[0] if "/" in path else ""
        items = _get_json(f"https://huggingface.co/api/models/{repo}/tree/main/{folder}")
        it = next(i for i in items if i.get("path") == path)
        return (it.get("lfs") or {}).get("size") or it.get("size", 0)
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------- embeddings (bases de conhecimento)

EMBED_MODEL = ("Qwen/Qwen3-Embedding-0.6B-GGUF", "Qwen3-Embedding-0.6B-Q8_0.gguf")


def embed_model_path():
    d = MODELS / "embed"
    p = d / EMBED_MODEL[1]
    if p.is_file():
        return p
    return next(iter(sorted(d.glob("*.gguf"))), None) if d.is_dir() else None


def install_embed_model(task, _value=""):
    repo, path = EMBED_MODEL
    _hf_download(task, [(repo, path, _hf_size(repo, path))], MODELS / "embed")


# ---------------------------------------------------------------- audio: whisper.cpp

WHISPER_EXE = ("whisper-cli.exe", "main.exe", "whisper-cli")
WHISPER_MODELS = {
    "large-v3-turbo-q5_0": "Large v3 Turbo (melhor, 530 MB)",
    "small-q8_0": "Small (bom e leve, 250 MB)",
    "base-q8_0": "Base (rápido, 80 MB)",
}


def install_whisper(task, backend):
    task["detail"] = "Consultando versao do whisper.cpp..."
    if LINUX:
        raise RuntimeError("O whisper.cpp nao publica o programa pronto para Linux. Por enquanto, a transcricao de audio fica so no Windows.")
    rel = _latest_win_release("ggml-org/whisper.cpp")
    names = [a["name"] for a in rel["assets"]]
    if backend == "cuda":
        f = _pick(names, r"whisper-bin-win-cuda-([\d.]+)-x64\.zip$")
    else:
        f = "whisper-bin-x64.zip" if "whisper-bin-x64.zip" in names else "whisper-bin-Win32.zip"
    _install(task, "ggml-org/whisper.cpp", [f] if f else [], "whisper", WHISPER_EXE)


def install_whisper_model(task, key):
    if key not in WHISPER_MODELS:
        raise ValueError("modelo invalido")
    path = f"ggml-{key}.bin"
    _hf_download(task, [("ggerganov/whisper.cpp", path, _hf_size("ggerganov/whisper.cpp", path))], MODELS / "whisper")


def whisper_status():
    models = sorted(p.name for p in (MODELS / "whisper").glob("ggml-*.bin")) if (MODELS / "whisper").is_dir() else []
    return {"installed": bool(find_exe("whisper", WHISPER_EXE)), "version": engine_version("whisper"),
            "models": models, "available": WHISPER_MODELS}


def transcribe(fid, model_name="", language="auto", threads=0):
    exe = find_exe("whisper", WHISPER_EXE)
    if not exe:
        raise RuntimeError("Motor de audio (Whisper) nao instalado. Instale em Modelos > Midia.")
    models = whisper_status()["models"]
    if not models:
        raise RuntimeError("Nenhum modelo do Whisper baixado. Baixe em Modelos > Midia.")
    model = model_name if model_name in models else next((m for k in WHISPER_MODELS for m in models if k in m), models[0])
    src = upload_path(fid)
    out_base = src.with_suffix("")
    cmd = [str(exe), "-m", str(MODELS / "whisper" / model), "-f", str(src), "-l", language or "auto",
           "-nt", "-otxt", "-of", str(out_base), "-t", str(threads or max(2, (os.cpu_count() or 4) - 2))]
    r = subprocess.run(cmd, capture_output=True, cwd=str(exe.parent), timeout=3600, creationflags=NO_WINDOW)
    txt = out_base.with_suffix(".txt")
    if r.returncode != 0 or not txt.exists():
        tail = r.stderr.decode("utf-8", "replace").strip().splitlines()[-5:]
        raise RuntimeError("Falha na transcricao: " + " | ".join(tail))
    text = txt.read_text("utf-8", "replace").strip()
    txt.unlink(missing_ok=True)
    return text


# ---------------------------------------------------------------- imagem: stable-diffusion.cpp

SD_EXE = ("sd-cli.exe", "sd.exe", "sd-cli", "sd")
IMAGE_PRESETS = {
    "z-image-turbo": {
        "name": "Z-Image Turbo",
        "desc": "Melhor qualidade, ótimo com textos na imagem. 8 passos. ~6,2 GB.",
        "files": {"--diffusion-model": ("leejet/Z-Image-Turbo-GGUF", "z_image_turbo-Q4_K.gguf"),
                  "--vae": ("Comfy-Org/z_image_turbo", "split_files/vae/ae.safetensors"),
                  "--llm": ("unsloth/Qwen3-4B-Instruct-2507-GGUF", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf")},
        "args": ["--diffusion-fa"], "steps": 8, "cfg": 1.0, "width": 1024, "height": 1024, "negative": False,
    },
    "sdxl-turbo": {
        "name": "SDXL Turbo",
        "desc": "Muito rápido (1 a 4 passos), ideal em 512x512. ~6,5 GB.",
        "files": {"-m": ("stabilityai/sdxl-turbo", "sd_xl_turbo_1.0_fp16.safetensors")},
        "args": [], "steps": 4, "cfg": 1.0, "width": 512, "height": 512, "negative": False,
    },
    # Setor Sprites (o resultado passa pelo pixel.py: paleta, reducao sem borrar, fundo). Tres niveis:
    # 1) Qwen-Image-2512 (20B, o mais forte que cabe em 16 GB): GGUF Q4_K_M (13,3 GB) + Qwen2.5-VL 7B como codificador de
    #    texto + LoRA "Pixel Art" (prithivMLmods) + LoRA Lightning de 8 passos (lightx2v). Apache 2.0.
    "pixel-qwen-image": {
        "name": "Pixel Art Qwen-Image 2512 (20B, máximo)",
        "desc": "O mais forte: Qwen-Image 2512 (20 bilhões de parâmetros, Q4_K_M) com a LoRA Pixel Art e a Lightning (8 passos). Segue melhor a descrição e desenha melhor mãos, rostos e objetos. ~20,3 GB. Feito para placas de 16 GB (o codificador de texto vai para a RAM).",
        "files": {"--diffusion-model": ("unsloth/Qwen-Image-2512-GGUF", "qwen-image-2512-Q4_K_M.gguf"),
                  "--vae": ("Comfy-Org/Qwen-Image_ComfyUI", "split_files/vae/qwen_image_vae.safetensors"),
                  "--llm": ("unsloth/Qwen2.5-VL-7B-Instruct-GGUF", "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf")},
        "loras": {"pixel-art-qwen": ("prithivMLmods/Qwen-Image-2512-Pixel-Art-LoRA", "Qwen-Image-2512-Master-Pixel-Art-LoRA.safetensors"),
                  "qwen-lightning-8": ("lightx2v/Qwen-Image-2512-Lightning", "Qwen-Image-2512-Lightning-8steps-V1.0-bf16.safetensors")},
        "modes": {"rapido": {"loras": [("pixel-art-qwen", 1.0), ("qwen-lightning-8", 1.0)], "steps": 8, "cfg": 1.0, "sampler": "euler"},
                  "qualidade": {"loras": [("pixel-art-qwen", 1.0)], "steps": 40, "cfg": 4.0, "sampler": "euler"}},
        "style": "Pixel Art, {subject}",
        "args": ["--diffusion-fa", "--vae-tiling"], "steps": 8, "cfg": 1.0, "width": 1024, "height": 1024, "negative": True,
        "pixel": True,
        # 13.300 + 254 + 4.683 + 1.180 + 850 MB, conferido no Hugging Face em 2026-11-21
        "bytes": 20_267_000_000,
    },
    # 2) Z-Image Turbo inteiro (bf16, 6B, sem quantizar) + Qwen3 4B Q8 + LoRA de pixel art mais baixada (tarn59): 8 passos.
    "pixel-z-image": {
        "name": "Pixel Art Z-Image Turbo (6B, rápido)",
        "desc": "Z-Image Turbo sem quantizar (bf16) com a LoRA Pixel Art Style: ótima qualidade e bem mais rápido que o Qwen-Image (8 passos). ~17,1 GB.",
        "files": {"--diffusion-model": ("Comfy-Org/Z-Image-Turbo", "split_files/diffusion_models/z_image_turbo_bf16.safetensors"),
                  "--vae": ("Comfy-Org/Z-Image-Turbo", "split_files/vae/ae.safetensors"),
                  "--llm": ("unsloth/Qwen3-4B-Instruct-2507-GGUF", "Qwen3-4B-Instruct-2507-Q8_0.gguf")},
        "loras": {"pixel-art-zimage": ("tarn59/pixel_art_style_lora_z_image_turbo", "pixel_art_style_z_image_turbo.safetensors")},
        "modes": {"rapido": {"loras": [("pixel-art-zimage", 1.0)], "steps": 8, "cfg": 1.0, "sampler": "euler"},
                  "qualidade": {"loras": [("pixel-art-zimage", 1.0)], "steps": 14, "cfg": 1.0, "sampler": "euler"}},
        "style": "Pixel art style. {subject}",
        "args": ["--diffusion-fa"], "steps": 8, "cfg": 1.0, "width": 1024, "height": 1024, "negative": False, "pixel": True,
        # 12.310 + 335 + 4.280 + 170 MB
        "bytes": 17_095_000_000,
    },
    # 3) Leve (placas de 8 GB): SDXL base + LoRA Pixel Art XL (nerijs) + LCM LoRA (8 passos).
    "pixel-art-xl": {
        "name": "Pixel Art XL (SDXL, leve)",
        "desc": "Para placas menores: SDXL 1.0 com a LoRA Pixel Art XL e a LCM LoRA (8 passos). ~7,8 GB. Precisa de ~8 GB de VRAM.",
        "files": {"-m": ("stabilityai/stable-diffusion-xl-base-1.0", "sd_xl_base_1.0.safetensors"),
                  "--vae": ("madebyollin/sdxl-vae-fp16-fix", "sdxl_vae.safetensors")},
        "loras": {"pixel-art-xl": ("nerijs/pixel-art-xl", "pixel-art-xl.safetensors"),
                  "lcm-sdxl": ("latent-consistency/lcm-lora-sdxl", "pytorch_lora_weights.safetensors")},
        "modes": {"rapido": {"loras": [("pixel-art-xl", 1.2), ("lcm-sdxl", 1.0)], "steps": 8, "cfg": 1.5, "sampler": "lcm"},
                  "qualidade": {"loras": [("pixel-art-xl", 1.2)], "steps": 30, "cfg": 7.0, "sampler": "euler_a"}},
        "style": "pixel art, {subject}",
        "args": [], "steps": 8, "cfg": 1.5, "width": 1024, "height": 1024, "negative": True, "pixel": True,
        # 6.938 MB (SDXL) + 335 MB (VAE) + 171 MB (Pixel Art XL) + 394 MB (LCM), conferido no Hugging Face em 2026-11-21
        "bytes": 7_838_000_000,
    },
}
PIXEL_PRESETS = ("pixel-qwen-image", "pixel-z-image", "pixel-art-xl")  # do mais forte ao mais leve
PIXEL_PRESET = PIXEL_PRESETS[0]


def pixel_default():
    """O modelo de pixel art usado quando ninguem escolhe: o mais forte ja baixado (ou o mais forte, para baixar)."""
    return next((k for k in PIXEL_PRESETS if preset_installed(k)), PIXEL_PRESET)


def lora_dir(key):
    return MODELS / "image" / key / "loras"


def preset_files(key):
    """(repo, caminho no repo, pasta, nome local) de cada arquivo do modelo."""
    p = IMAGE_PRESETS[key]
    out = [(repo, path, MODELS / "image" / key, Path(path).name) for repo, path in p["files"].values()]
    out += [(repo, path, lora_dir(key), f"{name}.safetensors") for name, (repo, path) in p.get("loras", {}).items()]
    return out


def preset_size(key):
    """Tamanho total do download em bytes (consulta o Hugging Face; 0 se nao der)."""
    return sum(_hf_size(repo, path) for repo, path, _, _ in preset_files(key))


def install_sd(task, backend):
    task["detail"] = "Consultando versao do stable-diffusion.cpp..."
    if LINUX:  # pacotes do Linux: "...-bin-Linux-Ubuntu-24.04-x86_64(-vulkan).zip"; a placa NVIDIA usa o Vulkan
        want_vk = backend in ("vulkan", "cuda")

        def ok(n):
            return (bool(re.search(r"linux", n, re.I)) and n.endswith(".zip") and bool(re.search(r"x86_64|x64", n))
                    and "rocm" not in n.lower() and ("vulkan" in n.lower()) == want_vk and linux_asset_ok(n))
        rel = _latest_win_release("leejet/stable-diffusion.cpp", ok)
        f = next(a["name"] for a in rel["assets"] if ok(a["name"]))
        _install(task, "leejet/stable-diffusion.cpp", [f], "sd", SD_EXE, rel)
        return
    rel = _latest_win_release("leejet/stable-diffusion.cpp")
    names = [a["name"] for a in rel["assets"]]
    if backend == "cuda":
        f = _pick(names, r"sd-.*-bin-win-cuda(\d+)-x64\.zip$")
        files = [f, _pick(names, r"cudart-sd-bin-win-cu(\d+)-x64\.zip$")]
    else:
        f = _pick(names, rf"sd-.*-bin-win-{backend}()-x64\.zip$")
        files = [f]
    _install(task, "leejet/stable-diffusion.cpp", [x for x in files if x], "sd", SD_EXE, rel)


def install_image_preset(task, key):
    p = IMAGE_PRESETS.get(key)
    if not p:
        raise ValueError("modelo invalido")
    files = [(repo, path, folder, name, _hf_size(repo, path)) for repo, path, folder, name in preset_files(key)]
    task["total"] = sum(f[4] for f in files)
    done = 0
    for repo, path, folder, name, _ in files:
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / name
        task["detail"] = name
        if dest.exists():
            done += dest.stat().st_size
            task["done"] = done
            continue
        done += _download(f"https://huggingface.co/{repo}/resolve/main/{path}", dest, task, done)


def preset_installed(key):
    return all((folder / name).exists() for _, _, folder, name in preset_files(key))


_CHECKED = {}


def engine_problem(dest_name, names):
    """Roda o motor uma vez (--help) para ver se ele abre neste sistema. "" = ok.
    Pega o caso do pacote feito para um Linux mais novo (falta GLIBC_2.43, por exemplo)."""
    exe = find_exe(dest_name, names)
    if not exe:
        return ""
    key = (str(exe), exe.stat().st_mtime)
    if key in _CHECKED:
        return _CHECKED[key]
    msg = ""
    try:
        env = dict(os.environ)
        if LINUX:
            env["LD_LIBRARY_PATH"] = str(exe.parent) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        r = subprocess.run([str(exe), "--help"], capture_output=True, timeout=20, cwd=str(exe.parent), env=env,
                           stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
        m = re.search(r"version `(GLIBC_[\d.]+)' not found", out)
        if m:
            msg = f"O motor instalado foi feito para um Linux mais novo (pede {m.group(1)}). Reinstale o motor: a Mikoshi agora escolhe o pacote certo."
        elif r.returncode not in (0, 1) and "usage" not in out.lower():
            msg = "O motor não abriu: " + out.strip()[-300:]
    except (OSError, subprocess.TimeoutExpired) as e:
        msg = f"O motor não abriu: {e}"
    _CHECKED[key] = msg
    return msg


def image_status():
    return {"installed": bool(find_exe("sd", SD_EXE)), "version": engine_version("sd"),
            "problem": engine_problem("sd", SD_EXE),
            "presets": {k: {"name": v["name"], "desc": v["desc"], "installed": preset_installed(k),
                            "steps": v["steps"], "cfg": v["cfg"], "width": v["width"], "height": v["height"],
                            "pixel": bool(v.get("pixel"))}
                        for k, v in IMAGE_PRESETS.items()}}


def generate_image(key, prompt, negative="", width=0, height=0, steps=0, cfg=0, seed=-1, offload=True,
                   on_progress=None, cancel=None, threads=0, loras=None, sampler=""):
    exe = find_exe("sd", SD_EXE)
    if not exe:
        raise RuntimeError("Motor de imagem nao instalado. Instale em Modelos > Midia.")
    p = IMAGE_PRESETS.get(key)
    if not p or not preset_installed(key):
        raise RuntimeError("Modelo de imagem nao baixado. Baixe em Modelos > Midia.")
    fid, out = new_media_path("png")
    cmd = [str(exe)]
    for flag, (_, path) in p["files"].items():
        cmd += [flag, str(MODELS / "image" / key / Path(path).name)]
    if loras:  # <lora:nome:peso> no prompt + --lora-model-dir (o jeito do stable-diffusion.cpp)
        cmd += ["--lora-model-dir", str(lora_dir(key))]
        prompt = prompt + " " + " ".join(f"<lora:{n}:{w:g}>" for n, w in loras)
    if sampler:
        cmd += ["--sampling-method", sampler]
    cmd += ["-p", prompt, "-o", str(out), "-W", str(int(width or p["width"])), "-H", str(int(height or p["height"])),
            "--steps", str(int(steps or p["steps"])), "--cfg-scale", str(cfg or p["cfg"]), "-s", str(int(seed))]
    if negative and p["negative"]:
        cmd += ["-n", negative]
    if offload:
        cmd.append("--offload-to-cpu")
    if threads:
        cmd += ["-t", str(int(threads))]
    cmd += p["args"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            cwd=str(exe.parent), creationflags=NO_WINDOW)
    log, buf = [], b""
    total = int(steps or p["steps"])
    try:
        while True:
            if cancel and cancel():
                proc.kill()
                raise RuntimeError("cancelado")
            chunk = proc.stdout.read1(512) if hasattr(proc.stdout, "read1") else proc.stdout.read(512)
            if not chunk:
                break
            buf += chunk
            parts = re.split(rb"[\r\n]", buf)
            buf = parts.pop()
            for line in parts:
                s = line.decode("utf-8", "replace").strip()
                if not s:
                    continue
                log.append(s)
                m = re.search(r"\|\s*(\d+)/(\d+)\s*-\s*([\d.]+)\s*(s/it|it/s)", s)
                if m and on_progress:
                    on_progress({"step": int(m.group(1)), "total": int(m.group(2)) or total,
                                 "speed": f"{m.group(3)} {m.group(4)}"})
                elif on_progress and re.search(r"loading|load", s, re.I):
                    on_progress({"stage": "loading"})
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError("Falha ao gerar a imagem:\n" + "\n".join(log[-8:]))
    return fid, out
