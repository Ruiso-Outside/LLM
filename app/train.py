"""Estudio de treino do Piphin LLM: ambiente de treino, conjuntos de dados, execucoes e exportacao.

Tudo fica dentro do app: o ambiente (Python 3.12 + PyTorch CUDA, instalado pelo uv) em engine/train,
os conjuntos de dados e as execucoes em data/train. O treino roda em outro processo (train_worker.py);
este modulo le os eventos dele, guarda as metricas e amostra a GPU (VRAM, uso, temperatura, consumo).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tarfile
import uuid
import zipfile
from collections import deque
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ID_RE = re.compile(r"^[a-f0-9]{10}$")
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"  # CUDA 12.8: suporta as placas novas (RTX 50, sm_120)
PACKAGES = ["transformers>=4.51", "peft>=0.15", "accelerate>=1.6", "bitsandbytes>=0.46", "safetensors", "sentencepiece",
            "protobuf", "numpy", "huggingface_hub"]
CODE_EXT = {".h", ".hpp", ".cpp", ".c", ".cc", ".cs", ".ini", ".md", ".txt", ".py", ".json", ".uplugin", ".uproject", ".usf", ".ush"}
SKIP_DIRS = {"Intermediate", "Binaries", "Saved", "DerivedDataCache", ".git", ".vs", "node_modules", "__pycache__", "Build"}
BASE_MODELS = [
    {"repo": "Qwen/Qwen2.5-Coder-1.5B-Instruct", "params": "1.5B", "download_gb": 3.1, "vram_gb": 4, "note": "o mais leve; treina rápido"},
    {"repo": "Qwen/Qwen2.5-Coder-3B-Instruct", "params": "3B", "download_gb": 6.2, "vram_gb": 6, "note": "bom equilíbrio para C++"},
    {"repo": "Qwen/Qwen2.5-Coder-7B-Instruct", "params": "7B", "download_gb": 15.2, "vram_gb": 10, "note": "mais capaz; treino mais lento"},
    {"repo": "Qwen/Qwen3-1.7B", "params": "1.7B", "download_gb": 4.1, "vram_gb": 4, "note": "uso geral, com raciocínio"},
    {"repo": "Qwen/Qwen3-4B", "params": "4B", "download_gb": 8.1, "vram_gb": 7, "note": "uso geral, com raciocínio"},
    {"repo": "Qwen/Qwen3-8B", "params": "8B", "download_gb": 16.4, "vram_gb": 11, "note": "o mais capaz que cabe com folga em 16 GB"},
]

ENGINE = DATA = MODELS = None
_hooks = {}
RUNS = {}  # id -> Run (execucoes desta sessao)
_lock = threading.Lock()


def configure(engine_dir, data_dir, models_dir, **hooks):
    """hooks: download(url, dest, task), get_json(url), llama_dir() -> pasta do llama.cpp, engine_version() -> 'bNNNN',
    chat(prompt) -> texto (modelo carregado), free_gpu() -> descarrega os modelos, diag(msg)."""
    global ENGINE, DATA, MODELS
    ENGINE, DATA, MODELS = Path(engine_dir) / "train", Path(data_dir) / "train", Path(models_dir)
    _hooks.update(hooks)
    for d in (DATA / "datasets", DATA / "runs"):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- ambiente de treino

def py():
    return ENGINE / "venv" / "Scripts" / "python.exe"


def uv():
    return ENGINE / "uv.exe"


def worker_script():
    return Path(__file__).with_name("train_worker.py")


def env_info():
    try:
        return json.loads((ENGINE / "env.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def env_status():
    info = env_info()
    return {"installed": py().is_file() and bool(info.get("ok")), "probe": info,
            "size": _dir_size(ENGINE) if ENGINE.is_dir() else 0, "path": str(ENGINE)}


def _env():
    e = dict(os.environ)
    e.update(UV_CACHE_DIR=str(ENGINE / "cache"), UV_PYTHON_INSTALL_DIR=str(ENGINE / "python"), UV_NO_PROGRESS="1",
             HF_HOME=str(ENGINE / "hf"), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return e


def _run(cmd, task, label):
    task["detail"] = label
    p = subprocess.Popen([str(c) for c in cmd], cwd=str(ENGINE), env=_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         creationflags=NO_WINDOW)
    tail = deque(maxlen=12)
    for raw in iter(p.stdout.readline, b""):
        line = raw.decode("utf-8", "replace").rstrip()
        if line:
            tail.append(line)
            task["detail"] = f"{label} · {line[:110]}"
        if task.get("cancel"):
            p.kill()
            raise RuntimeError("cancelado")
    if p.wait() != 0:
        raise RuntimeError(f"{label} falhou: " + " | ".join(list(tail)[-4:]))


def install(task):
    """Instala uma vez: uv, Python 3.12, PyTorch CUDA, transformers/peft/bitsandbytes e os conversores do llama.cpp."""
    ENGINE.mkdir(parents=True, exist_ok=True)
    if not uv().is_file():
        task["detail"] = "Baixando o uv (gerenciador de Python)..."
        rel = _hooks["get_json"]("https://api.github.com/repos/astral-sh/uv/releases/latest")
        asset = next(a for a in rel["assets"] if a["name"] == "uv-x86_64-pc-windows-msvc.zip")
        z = ENGINE / "uv.zip"
        _hooks["download"](asset["browser_download_url"], z, task)
        with zipfile.ZipFile(z) as f:
            for n in f.namelist():
                if n.endswith("uv.exe"):
                    uv().write_bytes(f.read(n))
        z.unlink(missing_ok=True)
    task["total"] = task["done"] = 0
    if not py().is_file():
        _run([uv(), "venv", "--python", "3.12", "venv"], task, "Criando o Python 3.12 do treino")
    _run([uv(), "pip", "install", "--python", py(), "torch", "--index-url", TORCH_INDEX], task,
         "Instalando o PyTorch com CUDA (~3 GB)")
    _run([uv(), "pip", "install", "--python", py(), *PACKAGES], task, "Instalando transformers, peft e bitsandbytes")
    install_converters(task)
    try:
        _run([uv(), "cache", "clean"], task, "Limpando os arquivos temporários da instalação")
    except RuntimeError:
        pass
    task["detail"] = "Testando a placa de vídeo com o PyTorch..."
    info = probe()
    (ENGINE / "env.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), "utf-8")
    if not info.get("ok"):
        raise RuntimeError("O PyTorch foi instalado mas não conseguiu usar a GPU: " + str(info.get("error") or info))
    task["detail"] = f"Pronto: PyTorch {info.get('torch')} · {info.get('device')}"


CONVERT_KEEP = ("convert_hf_to_gguf.py", "convert_lora_to_gguf.py", "conversion/", "gguf-py/")


def install_converters(task):
    """Conversores do llama.cpp na mesma versao do motor instalado (o GGUF gerado precisa casar com ele).
    Baixa o codigo-fonte daquela versao num unico arquivo e extrai so os conversores, o pacote conversion/ e o gguf-py."""
    tag = (_hooks["engine_version"]() or "").split()[0] or "master"
    ref = f"refs/tags/{tag}" if tag != "master" else "refs/heads/master"
    tgz = ENGINE / "llama-src.tar.gz"
    task["detail"] = f"Baixando os conversores do llama.cpp {tag}..."
    _hooks["download"](f"https://codeload.github.com/ggml-org/llama.cpp/tar.gz/{ref}", tgz, task)
    conv = ENGINE / "convert"
    shutil.rmtree(conv, ignore_errors=True)
    conv.mkdir(parents=True)
    with tarfile.open(tgz) as tf:
        for m in tf.getmembers():
            rel = m.name.split("/", 1)[1] if "/" in m.name else ""
            if not rel or not m.isfile() or not rel.startswith(CONVERT_KEEP) or ".." in rel.split("/"):
                continue
            dest = conv / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tf.extractfile(m) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    tgz.unlink(missing_ok=True)
    if not (conv / "convert_hf_to_gguf.py").is_file():
        raise RuntimeError("Os conversores do llama.cpp não foram encontrados no pacote baixado.")
    _run([uv(), "pip", "install", "--python", py(), str(conv / "gguf-py")], task, f"Instalando o gguf do llama.cpp {tag}")
    (conv / "versao.txt").write_text(tag, "utf-8")


def probe():
    try:
        out = subprocess.run([str(py()), str(worker_script()), "probe"], capture_output=True, text=True, timeout=180,
                             env=_env(), creationflags=NO_WINDOW)
        line = next((l for l in reversed(out.stdout.splitlines()) if l.startswith("{")), "")
        return json.loads(line) if line else {"ok": False, "error": (out.stderr or out.stdout)[-600:]}
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": str(e)}


def uninstall():
    if ENGINE and ENGINE.exists():
        shutil.rmtree(ENGINE, ignore_errors=True)


# ---------------------------------------------------------------- conjuntos de dados

def _ds_dir(did):
    if not ID_RE.match(did or ""):
        raise ValueError("conjunto invalido")
    return DATA / "datasets" / did


def _read_examples(did):
    f = _ds_dir(did) / "examples.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text("utf-8").splitlines() if l.strip()]


def _write_examples(did, exs):
    f = _ds_dir(did) / "examples.jsonl"
    tmp = f.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in exs), "utf-8")
    tmp.replace(f)


def _tokens(msgs):
    return int(sum(len(m.get("content") or "") for m in msgs) / 3.5)


def ds_meta(did):
    m = json.loads((_ds_dir(did) / "meta.json").read_text("utf-8"))
    exs = _read_examples(did)
    m.update(n=len(exs), approved=sum(1 for e in exs if e.get("status") == "approved"),
             pending=sum(1 for e in exs if e.get("status") == "pending"),
             tokens=sum(_tokens(e["messages"]) for e in exs if e.get("status") == "approved"))
    return m


def ds_list():
    out = []
    for d in sorted((DATA / "datasets").iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            out.append(ds_meta(d.name))
        except (OSError, ValueError):
            continue
    return out


def ds_create(name, system=""):
    did = uuid.uuid4().hex[:10]
    d = DATA / "datasets" / did
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"id": did, "name": (name or "Conjunto")[:80], "system": system[:4000],
                                             "created": time.time()}, ensure_ascii=False), "utf-8")
    (d / "examples.jsonl").write_text("", "utf-8")
    return ds_meta(did)


def ds_update(did, name=None, system=None):
    p = _ds_dir(did) / "meta.json"
    m = json.loads(p.read_text("utf-8"))
    if name is not None:
        m["name"] = name[:80]
    if system is not None:
        m["system"] = system[:4000]
    p.write_text(json.dumps(m, ensure_ascii=False), "utf-8")
    return ds_meta(did)


def ds_delete(did):
    shutil.rmtree(_ds_dir(did), ignore_errors=True)


def ds_examples(did, status="", offset=0, limit=50, q=""):
    exs = _read_examples(did)
    if status:
        exs = [e for e in exs if e.get("status") == status]
    if q:
        ql = q.lower()
        exs = [e for e in exs if ql in json.dumps(e["messages"], ensure_ascii=False).lower()]
    return {"total": len(exs), "items": exs[offset:offset + limit]}


def _example(user, assistant, source="manual", status="approved", system=""):
    msgs = ([{"role": "system", "content": system}] if system else []) + \
        [{"role": "user", "content": user.strip()}, {"role": "assistant", "content": assistant.strip()}]
    return {"id": uuid.uuid4().hex[:12], "messages": msgs, "source": source, "status": status, "created": time.time()}


def ds_save_example(did, ex):
    """Cria ou atualiza um exemplo ({id?, user, assistant, status?})."""
    with _lock:
        exs = _read_examples(did)
        if not (ex.get("user") or "").strip() or not (ex.get("assistant") or "").strip():
            raise ValueError("Preencha o pedido e a resposta.")
        cur = next((e for e in exs if e["id"] == ex.get("id")), None)
        if cur:
            sysm = [m for m in cur["messages"] if m["role"] == "system"]
            cur["messages"] = sysm + [{"role": "user", "content": ex["user"].strip()}, {"role": "assistant", "content": ex["assistant"].strip()}]
            cur["status"] = ex.get("status") or cur.get("status", "approved")
        else:
            cur = _example(ex["user"], ex["assistant"], "manual", ex.get("status") or "approved")
            exs.append(cur)
        _write_examples(did, exs)
        return cur


def ds_review(did, ids, status):
    with _lock:
        exs = _read_examples(did)
        if status == "delete":
            exs = [e for e in exs if e["id"] not in set(ids)]
        else:
            for e in exs:
                if e["id"] in set(ids):
                    e["status"] = "approved" if status == "approved" else "rejected" if status == "rejected" else "pending"
        _write_examples(did, exs)
    return ds_meta(did)


def ds_import_chats(did, chats):
    """chats: lista de conversas (dicts); cada pergunta + resposta final vira um exemplo aprovado."""
    added = []
    for c in chats:
        msgs = c.get("messages") or []
        for i, m in enumerate(msgs):
            if m.get("role") != "user" or i + 1 >= len(msgs):
                continue
            a = msgs[i + 1]
            if a.get("role") != "assistant" or a.get("error") or a.get("mode") == "image":
                continue
            text = re.sub(r"<think>[\s\S]*?(</think>|$)", "", a.get("content") or "").strip()
            if (m.get("content") or "").strip() and text:
                added.append(_example(m["content"], text, f"conversa: {c.get('title', '')[:60]}"))
    with _lock:
        _write_examples(did, _read_examples(did) + added)
    return len(added)


def ds_import_jsonl(did, text):
    """Aceita linhas {"messages": [...]} ou {"prompt"/"instruction", "response"/"output"} (formatos comuns)."""
    added = []
    for line in text.splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if o.get("messages"):
            added.append({"id": uuid.uuid4().hex[:12], "messages": o["messages"], "source": "importado", "status": "approved", "created": time.time()})
        else:
            u = o.get("prompt") or o.get("instruction") or o.get("question") or o.get("pergunta") or ""
            if o.get("input"):
                u = f"{u}\n\n{o['input']}"
            r = o.get("response") or o.get("output") or o.get("answer") or o.get("resposta") or ""
            if u and r:
                added.append(_example(u, r, "importado"))
    with _lock:
        _write_examples(did, _read_examples(did) + added)
    return len(added)


def ds_export_jsonl(did):
    return "".join(json.dumps({"messages": e["messages"]}, ensure_ascii=False) + "\n" for e in _read_examples(did) if e.get("status") == "approved")


def _source_chunks(folders, max_chunks):
    chunks = []
    for folder in folders:
        root = Path(folder)
        for f in sorted(root.rglob("*")):
            if len(chunks) >= max_chunks:
                return chunks
            if not f.is_file() or f.suffix.lower() not in CODE_EXT or any(p in SKIP_DIRS for p in f.relative_to(root).parts):
                continue
            try:
                text = f.read_text("utf-8", errors="replace")
            except OSError:
                continue
            if len(text.strip()) < 200:
                continue
            for i in range(0, min(len(text), 24000), 3500):  # trechos de ~3500 caracteres
                part = text[i:i + 3500]
                if len(part.strip()) > 300:
                    chunks.append((str(f.relative_to(root)), part))
                if len(chunks) >= max_chunks:
                    return chunks
    return chunks


GEN_PROMPT = """Você está criando dados de treino para uma IA especialista em {topic}.
Com base no trecho abaixo (arquivo {file}), escreva {n} exemplos de pergunta e resposta que um desenvolvedor faria.
- Perguntas variadas: como usar, por que funciona assim, como corrigir um erro, como criar algo parecido.
- Respostas completas, corretas e baseadas no trecho, com código C++ quando ajudar.
{extra}
Responda SOMENTE com um JSON no formato: [{{"pergunta": "...", "resposta": "..."}}]

Trecho:
```
{chunk}
```"""


def _parse_pairs(text):
    text = re.sub(r"<think>[\s\S]*?(</think>|$)", "", text)
    i, j = text.find("["), text.rfind("]")
    if i < 0 or j <= i:
        return []
    try:
        arr = json.loads(text[i:j + 1])
    except ValueError:
        return []
    out = []
    for o in arr if isinstance(arr, list) else []:
        if isinstance(o, dict):
            q = o.get("pergunta") or o.get("question") or o.get("prompt")
            a = o.get("resposta") or o.get("answer") or o.get("response")
            if isinstance(q, str) and isinstance(a, str) and q.strip() and a.strip():
                out.append((q, a))
    return out


def ds_generate(task, did, folders, per_chunk=3, max_chunks=40, topic="Unreal Engine 5 e C++", extra=""):
    """Gera exemplos sinteticos com o modelo carregado; entram como 'pendentes' para voce revisar."""
    chunks = _source_chunks(folders, max_chunks)
    if not chunks:
        raise RuntimeError("Nenhum arquivo de código ou texto encontrado nessas pastas.")
    task["total"], task["done"] = len(chunks), 0
    made = 0
    for i, (fname, chunk) in enumerate(chunks, 1):
        if task.get("cancel"):
            break
        task["detail"] = f"{i}/{len(chunks)} · {fname} · {made} exemplos"
        try:
            pairs = _parse_pairs(_hooks["chat"](GEN_PROMPT.format(topic=topic, file=fname, n=per_chunk, chunk=chunk,
                                                                   extra=("- " + extra) if extra else "")))
        except RuntimeError as e:
            raise RuntimeError(f"O modelo falhou ao gerar exemplos: {e}") from e
        new = [_example(q, a, f"gerado de {fname}", "pending") for q, a in pairs[:per_chunk * 2]]
        with _lock:
            _write_examples(did, _read_examples(did) + new)
        made += len(new)
        task["done"] = i
    task["detail"] = f"{made} exemplos gerados para revisar"


# ---------------------------------------------------------------- execucoes de treino

def _dir_size(p):
    return sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file())


def gpu_live():
    """Uso da placa NVIDIA agora: VRAM, uso, temperatura, consumo e clock."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,power.limit,clocks.sm",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=8, creationflags=NO_WINDOW).stdout
        v = [x.strip() for x in out.strip().splitlines()[0].split(",")]
        f = lambda x: float(x) if x not in ("[N/A]", "N/A", "") else 0.0  # noqa: E731
        return {"vram_used": f(v[0]), "vram_total": f(v[1]), "util": f(v[2]), "temp": f(v[3]), "power": f(v[4]),
                "power_limit": f(v[5]), "clock": f(v[6])}
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


class Run:
    def __init__(self, rid, cfg):
        self.id, self.cfg, self.dir = rid, cfg, DATA / "runs" / rid
        self.proc = None
        self.state = "starting"  # starting | loading | training | done | stopped | error | exporting | exported
        self.setup, self.last, self.result, self.export, self.error = {}, {}, {}, {}, ""
        self.steps, self.evals, self.gpu, self.events = [], [], [], deque(maxlen=200)
        self.energy_wh, self.started, self.finished = 0.0, time.time(), 0

    def summary(self):
        return {"id": self.id, "name": self.cfg.get("name"), "base_repo": self.cfg.get("base_repo"), "state": self.state,
                "started": self.started, "finished": self.finished, "last": self.last, "setup": self.setup,
                "result": self.result, "export": self.export, "error": self.error, "energy_wh": round(self.energy_wh, 2),
                "dataset": self.cfg.get("dataset_name"), "generation": self.cfg.get("generation", 1),
                "parent_name": self.cfg.get("parent_name", ""), "has_adapter": (self.dir / "adapter" / "adapter_config.json").is_file()}

    def detail(self, since=0):
        return {**self.summary(), "cfg": {k: v for k, v in self.cfg.items() if k != "hf_token"},
                "steps": self.steps[since:], "evals": self.evals, "gpu": self.gpu[-900:], "events": list(self.events),
                "n_steps": len(self.steps)}

    def save(self):
        (self.dir / "run.json").write_text(json.dumps({**self.summary(), "cfg": {k: v for k, v in self.cfg.items() if k != "hf_token"},
                                                        "steps": self.steps, "evals": self.evals, "gpu": self.gpu[-900:],
                                                        "events": list(self.events)}, ensure_ascii=False), "utf-8")

    def handle(self, ev):
        t = ev.get("type")
        if t == "setup":
            self.setup, self.state = ev, "training"
        elif t == "step":
            self.last = ev
            self.steps.append({k: ev.get(k) for k in ("step", "loss", "lr", "grad_norm", "tok_s", "mem_alloc", "mem_peak", "elapsed_s")})
        elif t == "eval":
            self.evals.append(ev)
        elif t == "info":
            if ev.get("phase"):
                self.state = "loading"
            self.events.append({"t": time.time(), "msg": ev.get("msg", "")})
        elif t == "checkpoint":
            self.events.append({"t": time.time(), "msg": f"Ponto de salvamento no passo {ev['step']}"})
        elif t == "done":
            self.result = ev
            self.state = "stopped" if ev.get("stopped") else "done"
        elif t == "export":
            self.export.update(ev)
            if ev.get("msg"):
                self.events.append({"t": time.time(), "msg": ev["msg"]})
        elif t == "error":
            self.error, self.state = ev.get("msg", "erro"), "error"
            self.events.append({"t": time.time(), "msg": "Erro: " + self.error})

    def _sample_gpu(self):
        last = time.time()
        while self.proc and self.proc.poll() is None:
            g = gpu_live()
            now = time.time()
            if g:
                self.energy_wh += g["power"] * (now - last) / 3600
                g["t"] = round(now - self.started, 1)
                self.gpu.append(g)
            last = now
            time.sleep(2)

    def _read(self, proc, after=None):
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("{"):
                if line:
                    self.events.append({"t": time.time(), "msg": line[:300]})
                continue
            try:
                self.handle(json.loads(line))
            except ValueError:
                continue
        code = proc.wait()
        if code != 0 and self.state not in ("error",):
            self.state, self.error = "error", self.error or f"o processo de treino terminou com código {code}"
        self.finished = time.time()
        if after:
            after()
        self.save()
        _hooks.get("diag", lambda m: None)(f"treino {self.id}: {self.state} {self.error}")

    def spawn(self, cmd, after=None):
        env = _env()
        if os.environ.get("PIPHIN_TRAIN_FAKE"):
            env["PIPHIN_TRAIN_FAKE"] = os.environ["PIPHIN_TRAIN_FAKE"]
        exe = py() if py().is_file() else Path(sys.executable)  # sem ambiente: so os testes (modo simulado)
        self.proc = subprocess.Popen([str(exe), str(worker_script()), cmd, str(self.dir / "config.json")], cwd=str(self.dir),
                                     env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        threading.Thread(target=self._read, args=(self.proc, after), daemon=True).start()
        threading.Thread(target=self._sample_gpu, daemon=True).start()


def active():
    return next((r for r in RUNS.values() if r.proc and r.proc.poll() is None), None)


def run_start(cfg):
    if active():
        raise RuntimeError("Já existe um treino rodando. Espere terminar ou pare antes.")
    if not env_status()["installed"] and not os.environ.get("PIPHIN_TRAIN_FAKE"):
        raise RuntimeError("Instale o ambiente de treino primeiro (aba Ambiente).")
    meta = ds_meta(cfg["dataset_id"])
    if meta["approved"] < 2:
        raise RuntimeError("O conjunto precisa de pelo menos 2 exemplos aprovados.")
    parent = _parent_info(cfg)  # continuar uma IA ja treinada: parte do adaptador LoRA dela
    rid = uuid.uuid4().hex[:10]
    d = DATA / "runs" / rid
    d.mkdir(parents=True)
    # copia os exemplos aprovados (com o prompt de sistema do conjunto) para a execucao: o treino fica reprodutivel
    sysmsg = meta.get("system", "")
    lines, seen, n_new, n_replay = [], set(), 0, 0

    def push(msgs):
        key = json.dumps([m for m in msgs if m["role"] != "system"], ensure_ascii=False)
        if key in seen:
            return 0
        seen.add(key)
        lines.append(json.dumps({"messages": msgs}, ensure_ascii=False))
        return 1
    for e in _read_examples(cfg["dataset_id"]):
        if e.get("status") == "approved":
            msgs = e["messages"]
            if sysmsg and not any(m["role"] == "system" for m in msgs):
                msgs = [{"role": "system", "content": sysmsg}] + msgs
            n_new += push(msgs)
    old_ds = parent and parent.get("dataset")
    if old_ds and cfg.get("replay", True) and Path(old_ds).is_file():
        # revisa o que a IA ja aprendeu junto com o conteudo novo: sem isso ela tende a esquecer o treino anterior
        for line in Path(old_ds).read_text("utf-8").splitlines():
            if line.strip():
                try:
                    n_replay += push(json.loads(line)["messages"])
                except (ValueError, KeyError):
                    continue
    (d / "dataset.jsonl").write_text("\n".join(lines) + "\n", "utf-8")
    if parent:
        shutil.copytree(parent["adapter"], d / "parent_adapter")  # a execucao nao depende da anterior continuar existindo
    full = {"name": (cfg.get("name") or "Minha IA")[:60], "base_repo": parent["base_repo"] if parent else cfg["base_repo"],
            "dataset": str(d / "dataset.jsonl"),
            "dataset_name": meta["name"], "run_dir": str(d), "lora_r": int(cfg.get("lora_r", 16)), "lora_alpha": int(cfg.get("lora_alpha", 32)),
            "lora_dropout": float(cfg.get("lora_dropout", 0.05)), "lr": float(cfg.get("lr", 2e-4)), "epochs": float(cfg.get("epochs", 2)),
            "max_len": int(cfg.get("max_len", 2048)), "batch_size": int(cfg.get("batch_size", 1)), "grad_accum": int(cfg.get("grad_accum", 4)),
            "warmup_ratio": float(cfg.get("warmup_ratio", 0.05)), "eval_ratio": 0.05, "eval_every": int(cfg.get("eval_every", 25)),
            "save_every": int(cfg.get("save_every", 100)), "seed": int(cfg.get("seed", 42)), "quant4bit": bool(cfg.get("quant4bit", True)),
            "hf_token": cfg.get("hf_token", ""), "new_examples": n_new, "replay_examples": n_replay}
    if parent:
        full.update(parent_adapter=str(d / "parent_adapter"), parent_run=parent.get("run", ""), parent_name=parent["name"],
                    generation=parent["generation"] + 1, lora_r=parent["lora_r"], lora_alpha=parent["lora_alpha"])
    (d / "config.json").write_text(json.dumps(full, ensure_ascii=False, indent=1), "utf-8")
    if cfg.get("free_gpu", True):
        _hooks.get("free_gpu", lambda: None)()  # o treino precisa da VRAM toda
    run = Run(rid, full)
    RUNS[rid] = run
    run.spawn("train")
    return run.summary()


def _parent_info(cfg):
    """De onde continuar: uma execucao anterior (parent_run) ou uma pasta com um adaptador LoRA (parent_adapter)."""
    rid, folder = cfg.get("parent_run") or "", cfg.get("parent_adapter") or ""
    if rid:
        d = DATA / "runs" / rid
        if not ID_RE.match(rid) or not (d / "adapter" / "adapter_config.json").is_file():
            raise RuntimeError("Essa execução não tem um modelo treinado para continuar.")
        pc = json.loads((d / "config.json").read_text("utf-8"))
        return {"run": rid, "adapter": d / "adapter", "dataset": pc.get("dataset"), "base_repo": pc["base_repo"],
                "name": pc.get("name", rid), "generation": int(pc.get("generation", 1)),
                "lora_r": int(pc.get("lora_r", 16)), "lora_alpha": int(pc.get("lora_alpha", 32))}
    if folder:
        f = Path(folder)
        if not (f / "adapter_config.json").is_file():
            raise RuntimeError("A pasta precisa ter um adaptador LoRA (adapter_config.json + adapter_model.safetensors). "
                               "Um arquivo .gguf não pode ser treinado de novo: use a pasta do adaptador.")
        ac = json.loads((f / "adapter_config.json").read_text("utf-8"))
        base = cfg.get("base_repo") or ac.get("base_model_name_or_path") or ""
        if not base:
            raise RuntimeError("O adaptador não diz qual é o modelo base: informe o repositório do modelo base.")
        return {"adapter": f, "dataset": None, "base_repo": base, "name": f.name, "generation": 1,
                "lora_r": int(ac.get("r", 16)), "lora_alpha": int(ac.get("lora_alpha", 32))}
    return None


def run_stop(rid, force=False):
    r = RUNS.get(rid)
    if not r:
        raise ValueError("execução não encontrada")
    (r.dir / "STOP").write_text("1", "utf-8")
    if force and r.proc and r.proc.poll() is None:
        subprocess.run(["taskkill", "/pid", str(r.proc.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
    return r.summary()


def run_get(rid, since=0):
    r = RUNS.get(rid)
    if r:
        return r.detail(since)
    f = DATA / "runs" / rid / "run.json"
    if ID_RE.match(rid or "") and f.exists():
        d = json.loads(f.read_text("utf-8"))
        d["steps"] = d.get("steps", [])[since:]
        d["n_steps"] = len(d.get("steps", [])) + since
        return d
    raise ValueError("execução não encontrada")


def runs_list():
    out, seen = [], set()
    for r in RUNS.values():
        out.append(r.summary())
        seen.add(r.id)
    for d in (DATA / "runs").iterdir():
        if d.name in seen or not (d / "run.json").exists():
            continue
        try:
            j = json.loads((d / "run.json").read_text("utf-8"))
            out.append({**{k: j.get(k) for k in ("id", "name", "base_repo", "state", "started", "finished", "last", "setup",
                                                 "result", "export", "error", "energy_wh", "dataset", "generation", "parent_name")},
                        "has_adapter": (d / "adapter" / "adapter_config.json").is_file()})
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda r: r.get("started") or 0, reverse=True)


def run_delete(rid):
    if active() and active().id == rid:
        raise RuntimeError("Pare o treino antes de apagar.")
    RUNS.pop(rid, None)
    if ID_RE.match(rid or ""):
        shutil.rmtree(DATA / "runs" / rid, ignore_errors=True)


def run_export(rid, name, quant="Q4_K_M"):
    """Junta o LoRA ao modelo base, converte para GGUF e quantiza: o resultado aparece em Meus modelos."""
    if active():
        raise RuntimeError("Espere o treino atual terminar.")
    d = DATA / "runs" / rid
    if not (d / "adapter").is_dir():
        raise RuntimeError("Esta execução não tem um modelo treinado para exportar.")
    r = RUNS.get(rid)
    if not r:
        j = json.loads((d / "run.json").read_text("utf-8"))
        cfg = json.loads((d / "config.json").read_text("utf-8"))
        r = Run(rid, cfg)
        r.setup, r.result, r.steps, r.evals, r.gpu = j.get("setup", {}), j.get("result", {}), j.get("steps", []), j.get("evals", []), j.get("gpu", [])
        r.last = j.get("last", {})
        r.events.extend(j.get("events", []))
        r.started, r.finished, r.energy_wh = j.get("started", 0), j.get("finished", 0), j.get("energy_wh", 0)
        RUNS[rid] = r
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name or r.cfg.get("name", "minha-ia")).strip("-")[:60] or "minha-ia"
    quant = quant if quant in ("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16") else "Q4_K_M"
    out = MODELS / "treinados" / f"{slug}-{quant}.gguf"
    llama = Path(_hooks["llama_dir"]() or ".")
    r.cfg.update(out_path=str(out), quant_type=quant, convert_script=str(ENGINE / "convert" / "convert_hf_to_gguf.py"),
                 quantize_exe=str(llama / "llama-quantize.exe"))
    (d / "config.json").write_text(json.dumps(r.cfg, ensure_ascii=False, indent=1), "utf-8")
    r.state, r.export, r.error = "exporting", {"stage": "start", "quant": quant}, ""

    def after():
        if r.export.get("stage") == "done":
            r.state = "exported"
            _hooks.get("on_model", lambda *a: None)(out, r)
    r.spawn("export", after)
    return r.summary()
