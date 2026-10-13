"""Etiquetas dos modelos: o que cada modelo do Hugging Face sabe fazer.

Tudo e deduzido dos metadados publicos do Hugging Face (pipeline, tags,
cabecalho GGUF e chat template) e do nome do repositorio/arquivo.
"""
import re

HF_EXPAND = "&".join(f"expand[]={k}" for k in ("pipeline_tag", "tags", "gguf", "downloads", "likes", "cardData", "lastModified"))

VISION_PIPES = {"image-text-to-text", "any-to-any", "video-text-to-text", "visual-question-answering"}
AUDIO_PIPES = {"audio-text-to-text", "automatic-speech-recognition", "any-to-any"}
IMAGE_GEN_PIPES = {"text-to-image", "image-to-image"}
EMBED_PIPES = {"feature-extraction", "sentence-similarity"}
IMAGE_GEN_ARCH = re.compile(r"flux|sd3|sdxl|stable.?diffusion|z.?image|wan|hunyuan.?video|ltx|chroma|qwen.?image", re.I)


def _fmt_params(n):
    if not n:
        return ""
    return f"{n / 1e9:.0f}B" if n >= 9.5e9 else f"{n / 1e9:.1f}B".replace(".0B", "B") if n >= 1e9 else f"{n / 1e6:.0f}M"


def _fmt_ctx(n):
    if not n:
        return ""
    return f"{round(n / 1024)}k" if n >= 1024 else str(n)


def model_caps(m):
    """Recebe um item da API de modelos do HF e devolve as etiquetas."""
    rid = m.get("id", "")
    name = rid.lower()
    tags = {t.lower() for t in m.get("tags") or []}
    pipe = (m.get("pipeline_tag") or "").lower()
    g = m.get("gguf") or {}
    arch = (g.get("architecture") or "").lower()
    tmpl = g.get("chat_template") or ""
    if isinstance(tmpl, list):  # alguns modelos tem varios templates
        tmpl = " ".join(t.get("template", "") if isinstance(t, dict) else str(t) for t in tmpl)
    is_clip = arch in ("clip", "mllama") or "mmproj" in arch

    caps = []

    def add(key, icon, label, tip):
        caps.append({"key": key, "icon": icon, "label": label, "tip": tip})

    image_gen = pipe in IMAGE_GEN_PIPES or "text-to-image" in tags or "diffusers" in tags or bool(IMAGE_GEN_ARCH.search(arch))
    if image_gen:
        add("imagegen", "🎨", "Gera imagens", "Modelo de GERAR imagens, não de conversa. Use-o pelo modo 🎨 Imagem (Modelos → Mídia), não aqui.")
    embed = pipe in EMBED_PIPES or "embedding" in name or "sentence-transformers" in tags
    if embed:
        add("embed", "🔎", "Embedding", "Modelo de busca semântica (embeddings). Não serve para conversar.")

    vision = pipe in VISION_PIPES or tags & {"vision", "multimodal", "image-text-to-text", "video-text-to-text"} \
        or re.search(r"(^|[-_/.])(vl|vision|omni|llava|pixtral|minicpm-v|gemma-?3n?)([-_.]|$)", name) is not None
    audio = pipe in AUDIO_PIPES or tags & {"audio", "speech", "asr", "audio-text-to-text"} \
        or re.search(r"omni|voxtral|ultravox|audio|whisper|qwen2-audio", name) is not None
    if vision and not image_gen:
        add("vision", "👁", "Visão", "Enxerga imagens. Ao baixar, deixe marcado \"Incluir visão\" para baixar o arquivo mmproj.")
        add("video", "🎬", "Vídeo", "Entende vídeos pelos quadros que o app extrai (precisa da visão).")
    if audio and not image_gen:
        add("audio", "🎧", "Áudio", "Entende áudio direto. Sem isso, o app transcreve com o Whisper.")
    if re.search(r"\btools\b|tool_call", tmpl) or "tool-use" in tags or "function-calling" in tags:
        add("tools", "🛠️", "Ferramentas", "Sabe usar ferramentas (tool calling): funciona no modo Codex.")
    if re.search(r"<think>|enable_thinking", tmpl) or tags & {"reasoning", "thinking"} \
            or re.search(r"(^|[-_/])(r1|qwq|thinking|reason\w*)([-_.]|$)", name):
        add("reasoning", "🧠", "Raciocínio", "Pensa antes de responder (mais inteligente, mais lento). O pensamento aparece num bloco recolhível.")
    if "code" in tags or re.search(r"coder|code|devstral|starcoder|codestral|granite-.*code", name):
        add("code", "💻", "Programação", "Especializado em código.")
    if re.search(r"abliterat|uncensor|heretic|obliterat|unfilter|amoral|dolphin", name) or tags & {"uncensored", "abliterated"}:
        add("uncensored", "🔓", "Sem censura", "Ajustado para recusar menos pedidos.")
    if "moe" in tags or arch.endswith("moe") or re.search(r"[-_]a\d+(\.\d+)?b([-_.]|$)", name) or "mixtral" in name:
        add("moe", "⚡", "MoE rápido", "Mistura de especialistas: usa só parte dos parâmetros por vez, então roda bem mais rápido que o tamanho sugere.")
    if "imatrix" in tags or re.search(r"[-_]i1[-_]|imatrix", name) or "unsloth" in name:
        add("optimized", "✨", "Otimizado", "Quantização otimizada (imatrix/dinâmica): mais qualidade no mesmo tamanho de arquivo.")

    params = 0 if is_clip else int(g.get("total") or 0)
    # o HF as vezes informa o tamanho de um arquivo auxiliar (mmproj, rascunho MTP); o nome costuma ser mais confiavel
    mm = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*b(?![a-z])", re.sub(r"-a\d+(\.\d+)?b", "", name.split("/")[-1]))
    name_params = int(float(mm.group(1)) * 1e9) if mm else 0
    if name_params and params < name_params * 0.5:
        params = name_params
    ctx = 0 if is_clip else int(g.get("context_length") or 0)
    license_ = ((m.get("cardData") or {}).get("license") or next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), ""))
    return {"caps": caps, "params": _fmt_params(params), "params_n": params, "ctx": _fmt_ctx(ctx), "ctx_n": ctx,
            "license": license_, "chat": not image_gen and not embed}


# ---------------------------------------------------------------- qualidade dos arquivos (quantizacao)

QUANT_RE = re.compile(r"(UD-)?(IQ\d_[A-Z]+|Q\d_K_[SMLX]{1,2}|Q\d_K|Q\d_[01]|MXFP4(?:_MOE)?|NVFP4|BF16|F16|F32)", re.I)


def quant_info(filename):
    m = QUANT_RE.search(filename.upper())
    if not m:
        return {"quant": "", "stars": 0, "quality": "", "tip": ""}
    dyn, q = bool(m.group(1)), m.group(2).upper()
    level = int(re.search(r"\d+", q).group()) if re.search(r"\d+", q) else 16
    if q in ("F16", "BF16", "F32"):
        stars, quality = 5, "Original (sem perda, pesado)"
    elif q.startswith(("MXFP4", "NVFP4")):
        stars, quality = 4, "Formato FP4 otimizado"
    elif level >= 8:
        stars, quality = 5, "Quase idêntico ao original"
    elif level == 6:
        stars, quality = 5, "Ótima"
    elif level == 5:
        stars, quality = 4, "Muito boa"
    elif level == 4:
        stars, quality = 4 if ("K_M" in q or q.startswith("IQ4")) else 3, "Boa (melhor equilíbrio)"
    elif level == 3:
        stars, quality = 2, "Razoável (perde um pouco)"
    else:
        stars, quality = 1, "Baixa (só se não couber outra)"
    tip = quality + (" · Quantização dinâmica Unsloth (mais precisa)" if dyn else "") + (" · IQ: versão compacta com imatrix" if q.startswith("IQ") else "")
    return {"quant": ("UD-" if dyn else "") + q, "stars": stars, "quality": quality, "tip": tip, "dynamic": dyn}
