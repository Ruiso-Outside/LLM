"""Ajustes por modelo: cada modelo pode ter contexto, camadas na GPU e amostragem proprios.

Ordem de prioridade (do mais fraco ao mais forte):
  configuracoes globais -> recomendados da familia do modelo -> ajustes salvos pelo usuario
"""
import json
import re
from pathlib import Path

FILE = None
LOAD_KEYS = ("ctx_size", "gpu_layers")
SAMPLING_KEYS = ("temperature", "top_p", "top_k", "min_p", "repeat_penalty")
KEYS = LOAD_KEYS + SAMPLING_KEYS


def configure(data_dir):
    global FILE
    FILE = Path(data_dir) / "model_settings.json"


def load_all():
    try:
        return json.loads(FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def get(rel):
    return load_all().get(rel or "", {})


def save(rel, values):
    """values=None apaga os ajustes do modelo (volta aos recomendados/globais)."""
    d = load_all()
    if values is None:
        d.pop(rel, None)
    else:
        clean = {}
        for k in KEYS:
            v = values.get(k)
            if v in (None, ""):
                continue
            clean[k] = int(float(v)) if k in ("ctx_size", "gpu_layers", "top_k") else round(float(v), 4)
        if clean:
            d[rel] = clean
        else:
            d.pop(rel, None)
    FILE.write_text(json.dumps(d, indent=1), "utf-8")
    return d.get(rel, {})


def recommended(rel, caps=None, ctx_max=0, model_size=0, vram_bytes=0):
    """Valores sugeridos pelos autores de cada familia de modelo."""
    name = Path(rel or "").name.lower()
    caps = set(caps or [])
    rec = {"temperature": 0.7, "top_p": 0.95, "top_k": 40, "min_p": 0.05, "repeat_penalty": 1.0}
    family = "Genérico"  # sem recomendação especifica: valem as configuracoes globais
    if re.search(r"qwen3|qwq", name):
        thinking = "reasoning" in caps and not re.search(r"instruct|coder|2507-instruct", name) or "thinking" in name
        if thinking:
            rec.update(temperature=0.6, top_p=0.95, top_k=20, min_p=0.0)
            family = "Qwen3 (modo raciocínio)"
        else:
            rec.update(temperature=0.7, top_p=0.8, top_k=20, min_p=0.0)
            family = "Qwen3 (instruct)"
        if "coder" in name:
            rec.update(temperature=0.7, top_p=0.8, top_k=20, repeat_penalty=1.05)
            family = "Qwen3 Coder"
    elif "gemma" in name:
        rec.update(temperature=1.0, top_p=0.95, top_k=64, min_p=0.0)
        family = "Gemma"
    elif re.search(r"deepseek.*r1|r1-distill", name):
        rec.update(temperature=0.6, top_p=0.95, top_k=40, min_p=0.0)
        family = "DeepSeek R1"
    elif "magistral" in name:
        rec.update(temperature=0.7, top_p=0.95, top_k=40, min_p=0.0)
        family = "Magistral"
    elif re.search(r"mistral|devstral|ministral", name):
        rec.update(temperature=0.15, top_p=1.0, top_k=40, min_p=0.0)
        family = "Mistral / Devstral"
    elif "gpt-oss" in name:
        rec.update(temperature=1.0, top_p=1.0, top_k=0, min_p=0.0)
        family = "gpt-oss"
    elif "llama" in name:
        rec.update(temperature=0.6, top_p=0.9, top_k=40, min_p=0.05)
        family = "Llama"
    elif "phi" in name:
        rec.update(temperature=0.7, top_p=0.95, top_k=40, min_p=0.0)
        family = "Phi"
    # contexto: o maior que cabe com folga na VRAM (o cache de contexto tambem ocupa memoria)
    if vram_bytes and model_size:
        free = vram_bytes * 0.92 - model_size
        ctx = 32768 if free > 4 * 1024 ** 3 else 16384 if free > 2 * 1024 ** 3 else 8192
    else:
        ctx = 8192
    if ctx_max:
        ctx = min(ctx, ctx_max)
    rec.update(ctx_size=ctx, gpu_layers=999, generic=family == "Genérico")
    return rec, family


def effective(base, rel, rec=None, use_recommended=True):
    """Configuracoes efetivas para o modelo `rel`: globais <- recomendados <- salvos."""
    out = dict(base)
    # recomendados so ajustam a amostragem (contexto e GPU continuam vindo das configuracoes globais)
    if use_recommended and rec and not rec.get("generic"):
        out.update({k: rec[k] for k in SAMPLING_KEYS if k in rec})
    out.update(get(rel))
    return out


def sampling_for(rel, rec=None, use_recommended=True):
    """So os parametros de amostragem do modelo (para aplicar sobre o pedido do chat)."""
    vals = {}
    if use_recommended and rec and not rec.get("generic"):
        vals.update({k: rec[k] for k in SAMPLING_KEYS if k in rec})
    vals.update({k: v for k, v in get(rel).items() if k in SAMPLING_KEYS})
    return vals
