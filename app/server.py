"""LLM Local - servidor interno do app desktop.

Iniciado escondido pelo Electron (desktop/main.js); nao e usado sozinho.
Sem dependencias externas (so biblioteca padrao do Python).
Roda apenas em 127.0.0.1: nada sai do seu computador, exceto quando VOCE
pede para baixar o motor, um modelo ou faz uma pesquisa na web.
"""
import atexit
import base64
import json
import os
import random
import re
import socket
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import agent
import agents
import kb
import mcp
import modelsettings
import catalog
import media
import websearch

# LLM_HOME: pasta de dados (modelos, motor, conversas). O app desktop define isso.
ROOT = Path(os.environ.get("LLM_HOME") or Path(__file__).resolve().parent.parent)
WEB = Path(__file__).resolve().parent / "web"
MODELS = ROOT / "models"
ENGINE = ROOT / "engine"
DATA = ROOT / "data"
CHATS = DATA / "chats"
SETTINGS_FILE = DATA / "settings.json"
STATS_FILE = DATA / "stats.json"
MMPROJ_FILE = DATA / "mmproj.json"
MTP_FILE = DATA / "mtp.json"
MODEL_INFO_FILE = DATA / "model_info.json"
CPU_COUNT = os.cpu_count() or 4

HOST = "127.0.0.1"
PORT = int(os.environ.get("LLM_PORT", "8765"))
ENGINE_PORT = PORT + 1
UA = "LLM-Local/1.0"
BACKENDS = ("cuda", "vulkan", "cpu")

for d in (MODELS, ENGINE, CHATS):
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    "system_prompt": "",
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "min_p": 0.05,
    "repeat_penalty": 1.0,
    "max_tokens": 0,  # 0 = sem limite
    "ctx_size": 8192,
    "gpu_layers": 999,  # 999 = tudo na GPU
    "threads": 0,  # (antigo) numero fixo de threads; 0 = usa cpu_percent
    "cpu_percent": 0,  # 0 = automatico (llama.cpp usa os nucleos fisicos, ~50%)
    "backend": "auto",
    "extra_args": "",
    "hf_token": "",
    "last_model": "",
    "auto_load": True,  # carrega o ultimo modelo ao iniciar
    "auto_summarize": True,  # resume a conversa antiga quando o contexto passa de ~80%
    "use_recommended": True,  # aplica a amostragem recomendada da familia de cada modelo
    "quick_model": "",  # modelo da pergunta rapida ("" = o principal)
    "quick_device": "gpu",  # onde roda o modelo da pergunta rapida: gpu | cpu ("auto" antigo = gpu)
    "quick_keep_loaded": True,
    "vram_guard": True,  # VRAM cheia por ~40 s sem nada gerando: descarrega os modelos para o PC nao travar  # deixa o modelo da pergunta rapida sempre carregado (responde na hora)
    "language": "",  # idioma da interface: pt-BR | en | es ("" = o do sistema)
    "reply_language": "auto",  # auto = a IA responde no idioma da pergunta | app = sempre no idioma do app
    "extra_idle_minutes": 10,  # modelos extras (agentes/pergunta rapida) sao descarregados apos X min parados
    "search_provider": "duckduckgo",  # duckduckgo | google | searxng
    "search_region": "br-pt",
    "search_results": 4,
    "google_api_key": "",
    "google_cx": "",
    "searxng_url": "",
    # Codex
    "workspaces": [],
    "agent_confirm_commands": True,
    "agent_confirm_writes": False,
    "agent_max_steps": 40,
    # midia
    "whisper_model": "",
    "whisper_language": "auto",
    "image_preset": "z-image-turbo",
    "image_width": 0,
    "image_height": 0,
    "image_steps": 0,
    "image_offload": True,
    "image_enhance": True,
    "image_unload_llm": False,
}
SECRETS = ("hf_token", "google_api_key")

_settings_lock = threading.Lock()


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text("utf-8")))
    except (OSError, ValueError):
        pass
    return s


def save_settings(new):
    with _settings_lock:
        s = load_settings()
        for k, v in new.items():
            if k in DEFAULT_SETTINGS:
                s[k] = v
        SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), "utf-8")
        return s


REPLY_RULES = {"pt-BR": "Responda sempre em português do Brasil.", "en": "Always answer in English.",
               "es": "Responde siempre en español."}


def reply_rule(s=None):
    """Instrucao extra quando o usuario quer que a IA responda sempre no idioma do app."""
    s = s or load_settings()
    return REPLY_RULES.get(s.get("language") or "pt-BR", "") if s.get("reply_language") == "app" else ""


def with_reply_rule(messages, s=None):
    rule = reply_rule(s)
    if not rule:
        return messages
    if messages and messages[0].get("role") == "system" and isinstance(messages[0].get("content"), str):
        return [{**messages[0], "content": messages[0]["content"] + "\n\n" + rule}] + messages[1:]
    return [{"role": "system", "content": rule}] + messages


def masked(s):
    s = dict(s)
    for k in SECRETS:
        s[k] = "***" if s.get(k) else ""
    return s


# ---------------------------------------------------------------- contador de tokens

_stats_lock = threading.Lock()


def load_stats():
    try:
        return json.loads(STATS_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0, "requests": 0, "searches": 0,
                "since": time.time()}


def add_stats(timings=None, searches=0):
    with _stats_lock:
        st = load_stats()
        if timings:
            st["prompt_tokens"] += int(timings.get("prompt_n") or 0)
            st["cached_tokens"] = st.get("cached_tokens", 0) + int(timings.get("cache_n") or 0)
            st["completion_tokens"] += int(timings.get("predicted_n") or 0)
            st["requests"] += 1
        st["searches"] = st.get("searches", 0) + searches
        STATS_FILE.write_text(json.dumps(st), "utf-8")


# ---------------------------------------------------------------- rede

class _Redirect(urllib.request.HTTPRedirectHandler):
    """Remove o token do Hugging Face quando o redirect vai para outro dominio (CDN)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).netloc != urllib.parse.urlparse(req.full_url).netloc:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


OPENER = urllib.request.build_opener(_Redirect)


def make_request(url, headers=None):
    h = {"User-Agent": UA}
    if "huggingface.co" in url:
        token = load_settings().get("hf_token", "").strip()
        if token:
            h["Authorization"] = f"Bearer {token}"
    h.update(headers or {})
    return urllib.request.Request(url, headers=h)


def get_json(url):
    with OPENER.open(make_request(url), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- tarefas (downloads)

TASKS = {}
_tasks_lock = threading.Lock()


def new_task(kind, label):
    t = {"id": uuid.uuid4().hex[:10], "kind": kind, "label": label, "done": 0, "total": 0,
         "status": "running", "error": "", "detail": "", "cancel": False, "started": time.time()}
    with _tasks_lock:
        TASKS[t["id"]] = t
    return t


def public_tasks():
    with _tasks_lock:
        # remove tarefas concluidas ha mais de 10 min
        now = time.time()
        for tid in [k for k, v in TASKS.items() if v["status"] != "running" and now - v.get("ended", now) > 600]:
            del TASKS[tid]
        return [{k: v for k, v in t.items() if k != "cancel"} for t in TASKS.values()]


class Cancelled(Exception):
    pass


def download(url, dest: Path, task, base_done=0):
    """Baixa com suporte a retomada (.part)."""
    part = dest.with_name(dest.name + ".part")
    start = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={start}-"} if start else {}
    with OPENER.open(make_request(url, headers), timeout=60) as r:
        if start and r.status != 206:
            start = 0
        length = int(r.headers.get("Content-Length") or 0)
        file_total = start + length
        with open(part, "ab" if start else "wb") as f:
            got = start
            while True:
                if task["cancel"]:
                    raise Cancelled()
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                task["done"] = base_done + got
    if length and part.stat().st_size < file_total:
        raise IOError("Download incompleto, tente de novo (ele continua de onde parou).")
    part.replace(dest)
    return dest.stat().st_size


def run_task(task, fn):
    def wrapper():
        try:
            fn(task)
            task["status"] = "done"
        except Cancelled:
            task["status"] = "cancelled"
        except urllib.error.HTTPError as e:
            task["status"] = "error"
            task["error"] = f"HTTP {e.code}: " + (
                "modelo restrito, coloque seu token do Hugging Face nas Configuracoes" if e.code in (401, 403) else e.reason)
        except Exception as e:  # noqa: BLE001
            task["status"] = "error"
            task["error"] = str(e)
        task["ended"] = time.time()

    threading.Thread(target=wrapper, daemon=True).start()


media.configure(ROOT, lambda url, dest, task, base=0: download(url, dest, task, base), get_json)
agents.configure(DATA)
kb.configure(DATA)
modelsettings.configure(DATA)
mcp.configure(DATA)
CHECKPOINTS = DATA / "checkpoints"


# ---------------------------------------------------------------- motor (llama.cpp)

def detect_gpu():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        if out:
            name, mem = out.splitlines()[0].rsplit(",", 1)
            return {"vendor": "nvidia", "name": name.strip(), "vram_mb": int(float(mem))}
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return {"vendor": "other", "name": "", "vram_mb": 0}


GPU = detect_gpu()


# ---------------------------------------------------------------- diagnostico
# Amostra a VRAM real (nvidia-smi) e a RAM a cada 20 s. Quando a VRAM enche, o Windows passa a usar a RAM
# como memoria de video ("sysmem fallback") e o PC inteiro pode travar: isso fica registrado e a interface avisa.
DIAG_FILE = DATA / "diagnostico.log"
DIAG = {"vram_used": 0, "vram_total": 0, "gpu_util": 0, "at": 0, "samples": deque(maxlen=90), "full_since": 0,
        "full_count": 0, "guard": None}


def diag_log(msg):
    try:
        if DIAG_FILE.exists() and DIAG_FILE.stat().st_size > 1024 * 1024:
            DIAG_FILE.replace(DIAG_FILE.with_suffix(".old.log"))
        with open(DIAG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def gpu_sample():
    """Uso real da placa NVIDIA: (MB usados, MB total, % de uso) ou None."""
    if GPU.get("vendor") != "nvidia":
        return None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        used, total, util = (int(float(x)) for x in out.strip().splitlines()[0].split(","))
        return used, total, util
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def diag_snapshot():
    total, avail = ram_info()
    return {"vram_used": DIAG["vram_used"], "vram_total": DIAG["vram_total"], "gpu_util": DIAG["gpu_util"],
            "vram_full": bool(DIAG["full_since"]), "ram_total": total, "ram_avail": avail,
            "engine": {"state": ENGINE_PROC.state, "model": ENGINE_PROC.model, "device": ENGINE_PROC.device},
            "extras": [{"model": m, "device": d, "state": e.state} for (m, d), e in list(POOL.extra.items())],
            "threads": threading.active_count()}


def vram_guard():
    """Protecao contra travar o PC: com a VRAM cheia e nada sendo gerado, descarrega extras e depois o principal."""
    busy = ENGINE_PROC.busy > 0 or any(e.busy > 0 for e in list(POOL.extra.values()))
    if busy:
        return
    gpu_extras = [m for (m, d), e in list(POOL.extra.items()) if d == "gpu" and e.state in ("ready", "loading")]
    if gpu_extras:
        POOL.stop_device("gpu")
        what = "os modelos extras da GPU (" + ", ".join(model_display(m) for m in gpu_extras) + ")"
    elif ENGINE_PROC.state in ("ready", "loading") and ENGINE_PROC.device == "gpu":
        what = "o modelo principal (" + model_display(ENGINE_PROC.model) + ")"
        ENGINE_PROC.stop()
    else:
        return
    POOL.quick_error = "Descarregado pela proteção de VRAM (a placa de vídeo encheu). Carregue de novo quando liberar memória."
    DIAG["guard"] = {"at": time.time(), "what": what}
    DIAG["full_count"] = 0
    diag_log(f"PROTEÇÃO DE VRAM: descarreguei {what}")


def diag_sampler():
    diag_log(f"servidor iniciado | GPU: {GPU.get('name', '-')} {GPU.get('vram_mb', 0)} MB")
    while True:
        g = gpu_sample()
        if g:
            used, total, util = g
            DIAG.update(vram_used=used, vram_total=total, gpu_util=util, at=time.time())
            DIAG["samples"].append((round(time.time()), used, util))
            full = total and used >= total * 0.97
            if full and not DIAG["full_since"]:
                DIAG["full_since"] = time.time()
                diag_log(f"VRAM CHEIA: {used}/{total} MB (o Windows pode começar a usar a RAM e travar) | {json.dumps(diag_snapshot(), ensure_ascii=False)}")
            elif not full and DIAG["full_since"]:
                diag_log(f"VRAM voltou ao normal: {used}/{total} MB (ficou cheia por {time.time() - DIAG['full_since']:.0f}s)")
                DIAG["full_since"] = 0
            DIAG["full_count"] = DIAG["full_count"] + 1 if full else 0
            if full and DIAG["full_count"] >= 2 and load_settings().get("vram_guard", True):
                vram_guard()
        time.sleep(20)


def ram_info():
    """Memoria RAM total e disponivel (MB), pelo Windows."""
    if os.name != "nt":
        return 0, 0
    import ctypes

    class MEMSTAT(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MEMSTAT()
    st.dwLength = ctypes.sizeof(MEMSTAT)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return 0, 0
    return st.ullTotalPhys // 2 ** 20, st.ullAvailPhys // 2 ** 20


def installed_backends():
    found = {}
    for b in BACKENDS:
        d = ENGINE / b
        if d.is_dir():
            exe = next(d.rglob("llama-server.exe" if os.name == "nt" else "llama-server"), None)
            if exe:
                ver = (d / "version.txt").read_text("utf-8").strip() if (d / "version.txt").exists() else ""
                found[b] = {"exe": str(exe), "version": ver}
    return found


def install_engine(task, backend):
    task["detail"] = "Consultando versao mais recente do llama.cpp..."
    # os builds "bNNNN" sao marcados como prerelease; pega o mais novo que tenha binarios Windows
    releases = get_json("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=15")
    rel = next((r for r in releases if any("-bin-win-" in a["name"] for a in r.get("assets", []))), None)
    if not rel:
        raise RuntimeError("Nenhuma versao do llama.cpp com binarios para Windows encontrada.")
    assets = {a["name"]: (a["browser_download_url"], a.get("size", 0)) for a in rel.get("assets", [])}
    tag = rel.get("tag_name", "")
    files = []
    if backend == "cuda":
        cands = []
        for n in assets:
            m = re.match(r"llama-.*-bin-win-cuda-([\d.]+)-x64\.zip$", n)
            if m:
                cands.append((tuple(int(x) for x in m.group(1).split(".")), n, m.group(1)))
        if not cands:
            raise RuntimeError("Nenhum pacote CUDA encontrado nesta versao. Tente Vulkan.")
        _, name, ver = max(cands)
        files.append(name)
        cudart = f"cudart-llama-bin-win-cuda-{ver}-x64.zip"
        if cudart in assets:
            files.append(cudart)
    else:
        pat = {"vulkan": r"llama-.*-bin-win-vulkan-x64\.zip$", "cpu": r"llama-.*-bin-win-cpu-x64\.zip$"}[backend]
        name = next((n for n in assets if re.match(pat, n)), None)
        if not name:
            raise RuntimeError(f"Pacote '{backend}' nao encontrado na versao {tag}.")
        files.append(name)

    task["total"] = sum(assets[f][1] for f in files)
    tmp = ENGINE / "_download"
    tmp.mkdir(exist_ok=True)
    done = 0
    for f in files:
        task["detail"] = f"Baixando {f}"
        done += download(assets[f][0], tmp / f, task, done)

    task["detail"] = "Extraindo..."
    if ENGINE_PROC.backend == backend:
        ENGINE_PROC.stop()
    dest = ENGINE / backend
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir()
    for f in files:
        with zipfile.ZipFile(tmp / f) as z:
            z.extractall(dest)
    # bibliotecas do CUDA precisam ficar na mesma pasta do executavel
    exe = next(dest.rglob("llama-server.exe"), None)
    if exe and exe.parent != dest:
        for dll in dest.glob("*.dll"):
            if not (exe.parent / dll.name).exists():
                shutil.move(str(dll), exe.parent / dll.name)
    (dest / "version.txt").write_text(f"{tag} ({files[0]})", "utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    task["detail"] = f"Motor {backend} instalado ({tag})"


def _job_object():
    """No Windows, garante que o llama-server morra junto com este app."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = ctypes.c_void_p
        k32.SetInformationJobObject.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
        k32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)

        class Basic(ctypes.Structure):
            _fields_ = [("a", ctypes.c_longlong), ("b", ctypes.c_longlong), ("LimitFlags", ctypes.c_uint32),
                        ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", ctypes.c_uint32),
                        ("f", ctypes.c_size_t), ("g", ctypes.c_uint32), ("h", ctypes.c_uint32)]

        class Ext(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", ctypes.c_ulonglong * 6), ("i", ctypes.c_size_t),
                        ("j", ctypes.c_size_t), ("k", ctypes.c_size_t), ("l", ctypes.c_size_t)]

        job = k32.CreateJobObjectW(None, None)
        info = Ext()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        return (k32, job)
    except Exception:  # noqa: BLE001
        return None


class EngineProcess:
    def __init__(self, port=ENGINE_PORT):
        self.port = port
        self.device = "gpu"  # gpu | cpu
        self.busy = 0
        self.last_used = time.time()
        self.proc = None
        self.model = ""
        self.backend = ""
        self.state = "stopped"  # stopped | loading | ready | error
        self.error = ""
        self.n_ctx = 0
        self.modalities = {}
        self.mtp = self.mtp_error = False  # acelerador MTP em uso / recusado pelo motor
        self.log = deque(maxlen=400)
        self.lock = threading.Lock()
        self.job = _job_object()

    def stop(self):
        with self.lock:
            p, self.proc = self.proc, None
            self.state, self.model, self.error = "stopped", "", ""
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()

    def start(self, model_rel, s, device=None, embed=False, no_mtp=False):
        self._args = (model_rel, dict(s), device, embed)
        if not no_mtp:
            self.mtp_error = False
        model_path = (MODELS / model_rel).resolve()
        if not embed:
            s = model_effective(model_rel, s)  # ajustes proprios do modelo (contexto, GPU)
        if MODELS.resolve() not in model_path.parents or not model_path.is_file():
            raise ValueError("Modelo nao encontrado.")
        backs = installed_backends()
        if not backs:
            raise ValueError("Nenhum motor instalado. Va em Modelos > Motor e instale.")
        backend = s.get("backend", "auto")
        if backend not in backs:
            backend = next(b for b in BACKENDS if b in backs)
        self.stop()
        if self is ENGINE_PROC:
            POOL.stop(model_rel)  # se ja estava carregado como extra, libera antes
        on_cpu = device == "cpu"
        if self is ENGINE_PROC and not on_cpu:
            POOL.make_room_for_main(model_rel)  # o principal tem prioridade na VRAM
        ngl = "0" if on_cpu else str(int(s["gpu_layers"]))
        if device == "gpu" and self is not ENGINE_PROC and int(s["gpu_layers"]) >= 999:
            ngl = "auto"  # extra na GPU: tudo que couber na VRAM livre de verdade (o resto fica na RAM)
        cmd = [backs[backend]["exe"], "-m", str(model_path), "--host", "127.0.0.1", "--port", str(self.port),
               "-c", str(int(s["ctx_size"])), "-ngl", ngl, "--jinja"]
        if on_cpu:
            cmd += ["--device", "none"]  # CPU e RAM apenas, sem tocar na GPU
        if embed:
            # motor so de embeddings (bases de conhecimento); o Qwen3-Embedding usa o ultimo token
            cmd += ["--embedding", "-b", "4096", "-ub", "4096"]
            if "qwen3-embedding" in model_rel.lower():
                cmd += ["--pooling", "last"]
        mm = mmproj_for(model_rel)
        if mm:
            cmd += ["--mmproj", str(mm)]
        mt = None if (embed or on_cpu or no_mtp) else mtp_for(model_rel)
        if mt:  # decodificacao especulativa: a cabeca MTP adivinha os proximos tokens e o modelo confere
            cmd += ["--spec-type", "draft-mtp", "-md", str(mt), "-ngld", "all"]
        threads = cpu_threads(s)
        if threads:
            cmd += ["-t", str(threads), "-tb", str(threads)]
        if s.get("extra_args", "").strip():
            cmd += [a.strip('"') for a in shlex.split(s["extra_args"], posix=False)]
        self.log.clear()
        self.log.append("> " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                cwd=str(Path(cmd[0]).parent),
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if self.job:
            try:
                self.job[0].AssignProcessToJobObject(self.job[1], int(proc._handle))
            except Exception:  # noqa: BLE001
                pass
        with self.lock:
            self.proc, self.model, self.backend, self.state, self.error = proc, model_rel, backend, "loading", ""
            self.mtp = bool(mt)
            self.device = "cpu" if on_cpu or backend == "cpu" or int(s["gpu_layers"]) == 0 else "gpu"
        threading.Thread(target=self._read_output, args=(proc,), daemon=True).start()
        threading.Thread(target=self._wait_ready, args=(proc,), daemon=True).start()

    def _read_output(self, proc):
        for raw in iter(proc.stdout.readline, b""):
            self.log.append(raw.decode("utf-8", "replace").rstrip())

    def _wait_ready(self, proc):
        while proc is self.proc and proc.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                    if r.status == 200:
                        self.n_ctx, self.modalities = self._read_props()
                        self.state = "ready"
                        return
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        if proc is self.proc and getattr(self, "mtp", False):
            # o motor nao aceitou o acelerador MTP (versao antiga ou arquivo incompativel): tenta sem ele
            model_rel, s, device, embed = self._args
            note = "[LLM Local] O motor falhou com o acelerador MTP; carregando sem ele."
            try:
                self.start(model_rel, s, device, embed, no_mtp=True)
                self.log.append(note)
                self.mtp_error = True
                return
            except (ValueError, OSError):
                pass
        if proc is self.proc:
            tail = [l for l in list(self.log)[-15:] if l]
            diag_log(f"motor fechou ao carregar {self.model}: " + " | ".join(tail[-4:]))
            self.state = "error"
            self.error = "O motor fechou. Ultimas linhas do log:\n" + "\n".join(tail)

    def _read_props(self):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/props", timeout=3) as r:
                p = json.loads(r.read().decode("utf-8"))
            n_ctx = int((p.get("default_generation_settings") or {}).get("n_ctx") or p.get("n_ctx") or 0)
            return n_ctx, {k: bool(v) for k, v in (p.get("modalities") or {}).items()}
        except (OSError, ValueError):
            return 0, {}

    def status(self):
        if self.state == "ready" and self.proc and self.proc.poll() is not None:
            self.state, self.error = "error", "O motor fechou inesperadamente (veja o log)."
        return {"state": self.state, "model": self.model, "backend": self.backend, "error": self.error,
                "port": self.port, "n_ctx": self.n_ctx, "mtp": self.mtp, "mtp_error": self.mtp_error,
                "vision": self.state == "ready" and self.modalities.get("vision", False),
                "audio": self.state == "ready" and self.modalities.get("audio", False)}


ENGINE_PROC = EngineProcess()


def model_display(rel):
    return Path(rel).stem if rel else "modelo principal"


def model_bytes(rel):
    """Tamanho em disco do modelo (com partes e arquivo de visao)."""
    p = MODELS / rel
    if not p.is_file():
        return 0
    m = SPLIT_RE.match(p.name)
    size = sum(q.stat().st_size for q in p.parent.glob(f"{m.group(1)}-*-of-{m.group(3)}.gguf")) if m else p.stat().st_size
    mm, mt = mmproj_for(rel), mtp_for(rel)
    return size + (mm.stat().st_size if mm else 0) + (mt.stat().st_size if mt else 0)


class EnginePool:
    """Modelos extras: cada agente ou a pergunta rapida pode usar um modelo diferente do principal.
    Cada modelo extra roda num llama-server proprio (porta propria) enquanto couber na VRAM;
    os menos usados sao descarregados quando falta memoria ou depois de ficarem parados."""

    def __init__(self):
        self.extra = {}  # caminho do modelo -> EngineProcess
        self.lock = threading.Lock()
        threading.Thread(target=self._reaper, daemon=True).start()

    def _free_port(self):
        used = {ENGINE_PORT} | {e.port for e in self.extra.values()}
        for port in range(ENGINE_PORT + 1, ENGINE_PORT + 60):
            if port in used:
                continue
            with socket.socket() as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        raise RuntimeError("Sem portas livres para outro modelo.")

    OVERHEAD = 1.3 * 1024 ** 3  # contexto + buffers por modelo (aproximado)

    def _used(self, device):
        """Memoria ocupada pelos modelos carregados no dispositivo (bytes)."""
        alive = ("ready", "loading")
        total = model_bytes(ENGINE_PROC.model) + self.OVERHEAD if ENGINE_PROC.state in alive and ENGINE_PROC.device == device else 0
        return total + sum(model_bytes(e.model) + self.OVERHEAD for e in self.extra.values() if e.state in alive and e.device == device)

    @staticmethod
    def _capacity(device):
        if device == "gpu":
            return GPU.get("vram_mb", 0) * 2 ** 20 * 0.95
        total, _ = ram_info()
        return total * 2 ** 20 * 0.70  # deixa RAM para o Windows e outros programas

    def _fits(self, device, need):
        return self._used(device) + need + self.OVERHEAD <= self._capacity(device)

    @staticmethod
    def kept_model():
        """Modelo da pergunta rapida que deve ficar sempre carregado ("" se nenhum)."""
        s = load_settings()
        return s.get("quick_model", "") if s.get("quick_keep_loaded") else ""

    def make_room_for_main(self, model_rel):
        """Antes de carregar o principal na GPU, descarrega extras da GPU se ele nao couber junto."""
        need = model_bytes(model_rel)
        with self.lock:
            for key, e in sorted(self.extra.items(), key=lambda kv: (kv[0][0] == self.kept_model(), kv[1].last_used)):
                if self._used("gpu") + need + self.OVERHEAD <= self._capacity("gpu"):
                    break
                if e.busy == 0 and e.device == "gpu" and key[0] != model_rel:
                    e.stop()
                    self.extra.pop(key, None)

    def _make_room(self, device, need):
        """Descarrega extras do dispositivo (do menos usado para o mais usado) ate o novo modelo caber.
        O modelo mantido da pergunta rapida e o ultimo a sair."""
        kept = self.kept_model()
        for key, e in sorted(self.extra.items(), key=lambda kv: (kv[0][0] == kept, kv[1].last_used)):
            if self._fits(device, need):
                break
            if e.busy == 0 and e.device == device:
                e.stop()
                self.extra.pop(key, None)

    def _resolve(self, device, need):
        """Escolhe onde rodar: 'auto' = GPU se couber, senao CPU (RAM), senao libera espaco na GPU.
        'gpu' = sempre GPU; se nao couber inteiro, o llama.cpp divide entre VRAM e RAM (-ngl auto)."""
        if not GPU.get("vram_mb"):
            return "cpu"
        if device in ("gpu", "cpu"):
            self._make_room(device, need)
            return device
        if self._fits("gpu", need):
            return "gpu"
        if self._fits("cpu", need):
            return "cpu"
        self._make_room("gpu", need)
        return "gpu"

    def use(self, model_rel, s, on_wait=None, device="auto", embed=False):
        return _PoolLease(self, model_rel, s, on_wait, device, embed)

    def acquire(self, model_rel, s, on_wait=None, device="auto", embed=False):
        """Garante o modelo pronto e devolve o motor (o principal se model_rel for vazio ou igual a ele).
        device: 'auto' (GPU se couber, senao CPU), 'gpu' ou 'cpu'."""
        device = device if device in ("gpu", "cpu") else "auto"
        if not model_rel or (model_rel == ENGINE_PROC.model and device in ("auto", ENGINE_PROC.device)):
            eng = ENGINE_PROC
            if not model_rel and eng.state != "ready":
                raise RuntimeError("Nenhum modelo carregado. Carregue um modelo no topo do app.")
        else:
            if not (MODELS / model_rel).is_file():
                raise RuntimeError(f"O modelo \"{model_display(model_rel)}\" não foi encontrado. Escolha outro.")
            with self.lock:
                def alive(e):
                    return e.state in ("ready", "loading") and not (e.proc and e.proc.poll() is not None)
                cands = [e for (m, d), e in self.extra.items() if m == model_rel and alive(e) and device in ("auto", d)]
                eng = sorted(cands, key=lambda e: e.state != "ready")[0] if cands else None
                if not eng:
                    where = self._resolve(device, model_bytes(model_rel))
                    old = self.extra.pop((model_rel, where), None)
                    if old:
                        old.stop()
                    eng = EngineProcess(self._free_port())
                    eng.start(model_rel, s, device=where, embed=embed)
                    self.extra[(model_rel, where)] = eng
        eng.busy += 1
        eng.last_used = time.time()
        announced = False
        t0 = time.time()
        while eng.state == "loading":
            if on_wait and not on_wait(model_display(model_rel or eng.model), not announced):
                eng.busy -= 1
                raise ConnectionError("cliente desconectou")
            announced = True
            if time.time() - t0 > 600:
                break
            time.sleep(0.5)
        if eng.state != "ready":
            eng.busy -= 1
            err = eng.error or "não carregou"
            if "out of memory" in err.lower() or "failed to allocate" in err.lower():
                err = "Sem memória de vídeo para carregar este modelo junto com o principal. Escolha um modelo menor ou descarregue o principal."
            raise RuntimeError(f"Falha ao carregar \"{model_display(model_rel)}\": {err}")
        return eng

    def release(self, eng):
        eng.busy = max(0, eng.busy - 1)
        eng.last_used = time.time()

    def stop_device(self, device):
        with self.lock:
            for key in [k for k in list(self.extra) if k[1] == device and self.extra[k].busy == 0]:
                e = self.extra.pop(key, None)
                if e:
                    e.stop()

    def stop(self, model_rel=None):
        with self.lock:
            for key in [k for k in list(self.extra) if not model_rel or k[0] == model_rel]:
                e = self.extra.pop(key, None)
                if e:
                    e.stop()

    def status(self):
        return [{"model": m, "name": model_display(m), "device": d, "state": e.status()["state"], "port": e.port,
                 "busy": e.busy, "idle": round(time.time() - e.last_used)} for (m, d), e in self.extra.items()]

    def memory(self):
        total, avail = ram_info()
        return {"vram_used": round(self._used("gpu") / 2 ** 20), "vram_total": GPU.get("vram_mb", 0),
                "ram_used": round(self._used("cpu") / 2 ** 20), "ram_total": total, "ram_avail": avail}

    def quick_status(self):
        s = load_settings()
        model = s.get("quick_model", "")
        e = next((e for (m, d), e in self.extra.items() if m == model and e.state in ("ready", "loading")), None)
        if not e and model and model == ENGINE_PROC.model and ENGINE_PROC.state in ("ready", "loading"):
            e = ENGINE_PROC
        loading = getattr(self, "_quick_loading", False) and not getattr(self, "_quick_cancel", False)
        state = e.state if e else ("loading" if loading else "stopped")
        return {"model": model, "name": model_display(model) if model else "", "keep": bool(s.get("quick_keep_loaded")),
                "device": quick_device(s), "state": state, "on": e.device if e else "",
                "error": getattr(self, "quick_error", "")}

    def load_quick(self):
        """Carrega o modelo da pergunta rapida em segundo plano (se houver um e ainda nao estiver carregado)."""
        s = load_settings()
        model = s.get("quick_model", "")
        if not model or getattr(self, "_quick_loading", False):
            return
        if not (MODELS / model).is_file() or not installed_backends():
            return
        if self.quick_status()["state"] in ("ready", "loading"):
            return

        def run():
            self._quick_loading, self._quick_cancel, self.quick_error = True, False, ""
            for _ in range(600):  # o principal carrega primeiro (prioridade na VRAM)
                if ENGINE_PROC.state != "loading":
                    break
                time.sleep(0.5)
            try:
                self.release(self.acquire(model, s, None, quick_device(s)))
            except (RuntimeError, ValueError, OSError) as e:
                if not self._quick_cancel:  # descarregado de proposito no meio da carga: nao e erro
                    self.quick_error = str(e)
            finally:
                self._quick_loading = False
        threading.Thread(target=run, daemon=True).start()

    def _reaper(self):
        while True:
            time.sleep(30)
            if self.kept_model() and not getattr(self, "quick_error", ""):
                self.load_quick()  # volta a carregar se foi descarregado (ex.: para abrir espaco ao principal)
            limit = int(load_settings().get("extra_idle_minutes") or 0) * 60
            if limit <= 0:
                continue
            kept = self.kept_model()
            with self.lock:
                for key, e in list(self.extra.items()):
                    if e.busy == 0 and time.time() - e.last_used > limit and key[0] != kept:
                        e.stop()
                        self.extra.pop(key, None)


def quick_device(s):
    """Onde roda o modelo da pergunta rapida: GPU, a menos que o usuario escolha CPU."""
    return "cpu" if s.get("quick_device") == "cpu" else "gpu"


class _PoolLease:
    def __init__(self, pool, model_rel, s, on_wait, device="auto", embed=False):
        self.pool, self.model_rel, self.s, self.on_wait, self.device, self.eng = pool, model_rel, s, on_wait, device, None
        self.embed = embed

    def __enter__(self):
        self.eng = self.pool.acquire(self.model_rel, self.s, self.on_wait, self.device, self.embed)
        return self.eng

    def __exit__(self, *exc):
        self.pool.release(self.eng)


POOL = EnginePool()
atexit.register(ENGINE_PROC.stop)
atexit.register(POOL.stop)
atexit.register(mcp.MANAGER.stop)


# ---------------------------------------------------------------- modelos

SPLIT_RE = re.compile(r"^(.*)-(\d{5})-of-(\d{5})\.gguf$", re.I)


MEDIA_DIRS = ("image", "whisper", "mmproj", "embed", "mtp")


def model_recommended(rel):
    info = load_model_info().get(rel) or catalog.model_caps({"id": Path(rel).name})
    return modelsettings.recommended(rel, [c["key"] for c in info.get("caps", [])], info.get("ctx_n", 0),
                                     model_bytes(rel), GPU.get("vram_mb", 0) * 2 ** 20)


def model_effective(rel, s):
    rec, _ = model_recommended(rel)
    return modelsettings.effective(s, rel, rec, s.get("use_recommended", True))


def apply_model_sampling(payload, rel, agent_temperature=None):
    """Aplica a amostragem do modelo (recomendada/salva) sobre o pedido; a temperatura do agente vence."""
    if rel:
        s = load_settings()
        rec, _ = model_recommended(rel)
        payload.update(modelsettings.sampling_for(rel, rec, s.get("use_recommended", True)))
    if agent_temperature is not None:
        payload["temperature"] = agent_temperature
    return payload


def embed_texts(texts, on_wait=None):
    """Vetores (embeddings) dos textos, com o modelo de embeddings rodando num motor proprio."""
    path = media.embed_model_path()
    if not path:
        raise RuntimeError("Modelo de embeddings não baixado. Baixe em Conhecimento.")
    rel = path.relative_to(MODELS).as_posix()
    with POOL.use(rel, load_settings(), on_wait, "auto", embed=True) as eng:
        req = urllib.request.Request(f"http://127.0.0.1:{eng.port}/v1/embeddings",
                                     data=json.dumps({"input": texts, "model": "embed"}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError("Falha ao gerar embeddings: " + e.read().decode("utf-8", "replace")[:200]) from None
    return [d["embedding"] for d in sorted(data["data"], key=lambda d: d.get("index", 0))]


def cleanup_checkpoints(days=30):
    if not CHECKPOINTS.exists():
        return
    limit = time.time() - days * 86400
    for chat_dir in CHECKPOINTS.iterdir():
        for run in list(chat_dir.iterdir()) if chat_dir.is_dir() else []:
            if run.stat().st_mtime < limit:
                shutil.rmtree(run, ignore_errors=True)
        if chat_dir.is_dir() and not any(chat_dir.iterdir()):
            chat_dir.rmdir()


def cpu_threads(s):
    """Threads da CPU pela porcentagem escolhida (0 = deixa o motor decidir)."""
    if int(s.get("threads") or 0) > 0:
        return int(s["threads"])
    pct = int(s.get("cpu_percent") or 0)
    return max(1, round(CPU_COUNT * min(pct, 100) / 100)) if pct > 0 else 0


def load_model_info():
    try:
        return json.loads(MODEL_INFO_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_model_info(model_rel, info):
    d = load_model_info()
    d[model_rel] = info
    MODEL_INFO_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")


def hf_model_info(repo):
    m = get_json(f"https://huggingface.co/api/models/{urllib.parse.quote(repo, safe='/')}?{catalog.HF_EXPAND}")
    return {"repo": repo, **catalog.model_caps(m)}


def list_models():
    out = []
    mm = load_mmproj_map()
    mtps = load_mtp_map()
    infos = load_model_info()
    for p in sorted(MODELS.rglob("*.gguf"), key=lambda x: x.name.lower()):
        rel_parts = p.relative_to(MODELS).parts
        if is_aux_file(p.relative_to(MODELS).as_posix()) or (len(rel_parts) > 1 and rel_parts[0] in MEDIA_DIRS):
            continue
        m = SPLIT_RE.match(p.name)
        size = p.stat().st_size
        if m:
            if m.group(2) != "00001":
                continue
            size = sum(q.stat().st_size for q in p.parent.glob(f"{m.group(1)}-*-of-{m.group(3)}.gguf"))
        rel = p.relative_to(MODELS).as_posix()
        info = infos.get(rel) or {"repo": "", **catalog.model_caps({"id": p.name})}
        out.append({"name": p.stem if not m else m.group(1), "path": rel, "size": size,
                    "mmproj": mm.get(rel, "") if (MODELS / mm.get(rel, "_")).is_file() else "",
                    "mtp": mtps.get(rel, "") if (MODELS / mtps.get(rel, "_")).is_file() else "",
                    "custom": bool(modelsettings.get(rel)),
                    "info": info, "quant": catalog.quant_info(p.name)})
    return out


def load_mmproj_map():
    try:
        return json.loads(MMPROJ_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def set_mmproj(model_rel, mm_rel):
    m = load_mmproj_map()
    if mm_rel:
        m[model_rel] = mm_rel
    else:
        m.pop(model_rel, None)
    MMPROJ_FILE.write_text(json.dumps(m, indent=1), "utf-8")


def mmproj_for(model_rel):
    rel = load_mmproj_map().get(model_rel)
    p = (MODELS / rel).resolve() if rel else None
    return p if p and p.is_file() and MODELS.resolve() in p.parents else None


def list_mmproj():
    return sorted(p.relative_to(MODELS).as_posix() for p in MODELS.rglob("*.gguf") if "mmproj" in p.name.lower())


MTP_RE = re.compile(r"(^|[-_.])(fast)?mtp([-_.]|$)", re.I)


def is_mtp(path):
    """Cabeca MTP (Multi-Token Prediction): acelerador do modelo grande, nao funciona sozinho."""
    p = path.replace("\\", "/").lower()
    return p.startswith("mtp/") or "/mtp/" in p or bool(MTP_RE.search(p.rsplit("/", 1)[-1][:-5]))


def is_aux_file(path):
    """Arquivos .gguf que nao sao modelos de conversa (visao, MTP, matriz de importancia)."""
    name = path.rsplit("/", 1)[-1].lower()
    return "mmproj" in name or "imatrix" in name or is_mtp(path)


def pick_mtp(files, model_path=""):
    """Melhor arquivo MTP do repositorio: mesma quantizacao do modelo, senao Q8_0, Q4_0 e o menor."""
    mtp = [f for f in files if is_mtp(f["path"])]
    if not mtp:
        return None
    q = (catalog.quant_info(model_path.rsplit("/", 1)[-1]) or {}).get("quant", "").lower() if model_path else ""

    def score(f):
        n = f["path"].lower()
        return (0 if q and q in n else 1, 0 if "q8_0" in n else 1 if "q4_0" in n else 3 if re.search(r"bf16|f16|f32", n) else 2,
                f["size"])
    return min(mtp, key=score)


def load_mtp_map():
    try:
        return json.loads(MTP_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def set_mtp(model_rel, mtp_rel):
    m = load_mtp_map()
    if mtp_rel:
        m[model_rel] = mtp_rel
    else:
        m.pop(model_rel, None)
    MTP_FILE.write_text(json.dumps(m, indent=1), "utf-8")


def mtp_for(model_rel):
    rel = load_mtp_map().get(model_rel)
    p = (MODELS / rel).resolve() if rel else None
    return p if p and p.is_file() and MODELS.resolve() in p.parents else None


def list_mtp():
    return sorted(p.relative_to(MODELS).as_posix() for p in MODELS.rglob("*.gguf") if is_mtp(p.relative_to(MODELS).as_posix()))


def hf_tree(repo):
    items = get_json(f"https://huggingface.co/api/models/{urllib.parse.quote(repo, safe='/')}/tree/main?recursive=true")
    return [{"path": it["path"], "size": (it.get("lfs") or {}).get("size") or it.get("size", 0)}
            for it in items if it.get("type") == "file" and it["path"].lower().endswith(".gguf")]


def hf_files(repo, tree=None):
    files = [f for f in (tree if tree is not None else hf_tree(repo)) if not is_aux_file(f["path"])]
    # agrupa arquivos divididos
    groups = {}
    for f in files:
        m = SPLIT_RE.match(f["path"])
        key = m.group(1) + ".gguf" if m else f["path"]
        g = groups.setdefault(key, {"path": f["path"], "size": 0, "parts": 0})
        g["size"] += f["size"]
        g["parts"] += 1
        if m and m.group(2) == "00001":
            g["path"] = f["path"]
    return sorted(groups.values(), key=lambda g: g["size"])


def pick_mmproj(files):
    mm = [f for f in files if "mmproj" in f["path"].lower()]
    for pref in ("f16", "bf16", "q8", ""):
        for f in mm:
            if pref in f["path"].lower():
                return f
    return None


def download_model(task, repo, path, with_mmproj=False, with_mtp=False):
    files = hf_tree(repo)
    try:
        info = hf_model_info(repo)
    except Exception:  # noqa: BLE001
        info = None
    m = SPLIT_RE.match(path)
    if m:
        parts = sorted((f["path"], f["size"]) for f in files
                       if SPLIT_RE.match(f["path"]) and SPLIT_RE.match(f["path"]).group(1) == m.group(1))
    else:
        parts = [(path, next((f["size"] for f in files if f["path"] == path), 0))]
    task["total"] = sum(s for _, s in parts)
    folder = MODELS / repo.split("/")[-1] if m else MODELS
    if info:
        save_model_info((folder / Path(parts[0][0]).name).relative_to(MODELS).as_posix(), info)
    folder.mkdir(parents=True, exist_ok=True)
    done = 0
    for p, _ in parts:
        dest = folder / Path(p).name
        task["detail"] = Path(p).name
        if dest.exists():
            done += dest.stat().st_size
            task["done"] = done
            continue
        url = f"https://huggingface.co/{repo}/resolve/main/{urllib.parse.quote(p)}"
        done += download(url, dest, task, done)
    mm = pick_mmproj(files) if with_mmproj else None
    if mm:
        mm_dest = MODELS / "mmproj" / f"{repo.split('/')[-1]}__{Path(mm['path']).name}"
        mm_dest.parent.mkdir(parents=True, exist_ok=True)
        task["detail"] = "arquivo de visao (mmproj)"
        task["total"] += mm["size"]
        if not mm_dest.exists():
            download(f"https://huggingface.co/{repo}/resolve/main/{urllib.parse.quote(mm['path'])}", mm_dest, task, done)
        set_mmproj((folder / Path(parts[0][0]).name).relative_to(MODELS).as_posix(),
                   mm_dest.relative_to(MODELS).as_posix())
    mt = pick_mtp(files, path) if with_mtp else None
    if mt:
        mt_dest = MODELS / "mtp" / f"{repo.split('/')[-1]}__{Path(mt['path']).name}"
        mt_dest.parent.mkdir(parents=True, exist_ok=True)
        task["detail"] = "acelerador MTP"
        task["total"] += mt["size"]
        if not mt_dest.exists():
            download(f"https://huggingface.co/{repo}/resolve/main/{urllib.parse.quote(mt['path'])}", mt_dest, task, done)
        set_mtp((folder / Path(parts[0][0]).name).relative_to(MODELS).as_posix(), mt_dest.relative_to(MODELS).as_posix())


# ---------------------------------------------------------------- conversas

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def list_chats():
    out = []
    for f in CHATS.glob("*.json"):
        try:
            c = json.loads(f.read_text("utf-8"))
            out.append({"id": c["id"], "title": c.get("title", ""), "updated": c.get("updated", 0)})
        except (OSError, ValueError, KeyError):
            pass
    return sorted(out, key=lambda c: c["updated"], reverse=True)


# ---------------------------------------------------------------- anexos -> mensagens do modelo

IMG_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}


def _image_part(fid):
    p = media.upload_path(fid)
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{IMG_MIME.get(p.suffix.lower(), 'image/png')};base64,{b64}"}}


def _audio_part(fid):
    p = media.upload_path(fid)
    return {"type": "input_audio", "input_audio": {"data": base64.b64encode(p.read_bytes()).decode("ascii"),
                                                   "format": "mp3" if p.suffix.lower() == ".mp3" else "wav"}}


def build_content(m, mod):
    atts = m.get("attachments") or []
    if not atts:
        return m.get("content", "")
    texts, parts = [], []
    for a in atts:
        kind, name = a.get("kind"), a.get("name", "arquivo")
        try:
            if kind == "text":
                texts.append(f"[Conteudo do arquivo {name}]\n{a.get('text', '')}\n[Fim do arquivo {name}]")
            elif kind == "image":
                if mod.get("vision"):
                    parts.append(_image_part(a["id"]))
                else:
                    texts.append(f"[Imagem anexada '{name}': o modelo carregado nao tem visao e nao pode ve-la]")
            elif kind == "audio":
                if mod.get("audio") and a.get("id"):
                    parts.append(_audio_part(a["id"]))
                elif a.get("transcript"):
                    texts.append(f"[Transcricao do audio {name}]\n{a['transcript']}")
                else:
                    texts.append(f"[Audio anexado '{name}' sem transcricao disponivel]")
            elif kind == "video":
                frames = a.get("frames") or []
                if frames and mod.get("vision"):
                    stamps = ", ".join(f"{f.get('t', 0):.0f}s" for f in frames)
                    texts.append(f"[Video '{name}' ({a.get('duration', 0):.0f}s): {len(frames)} quadros anexados em ordem, "
                                 f"nos tempos {stamps}]")
                    parts += [_image_part(f["id"]) for f in frames]
                if a.get("transcript"):
                    texts.append(f"[Transcricao do audio do video {name}]\n{a['transcript']}")
                if not (frames and mod.get("vision")) and not a.get("transcript"):
                    texts.append(f"[Video anexado '{name}': o modelo nao tem visao e nao ha transcricao]")
        except ValueError:
            texts.append(f"[Anexo '{name}' nao encontrado]")
    text = "\n\n".join(texts + ([m["content"]] if m.get("content") else []))
    return parts + [{"type": "text", "text": text or "(veja os anexos)"}] if parts else text


def text_of(content):
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if p.get("type") == "text")
    return content or ""


def build_history(msgs, mod, agent_mode=False):
    out, n = [], len(msgs)
    for i, m in enumerate(msgs):
        role = m.get("role")
        if role == "system":
            out.append({"role": "system", "content": m.get("content", "")})
        elif role == "user":
            out.append({"role": "user", "content": build_content(m, mod)})
        elif role == "assistant":
            if m.get("trace") and agent_mode:
                out += agent.compact_history(m["trace"], keep_full=i >= n - 2)
            elif m.get("image"):
                out.append({"role": "assistant", "content": f"[Imagem gerada com o prompt: {m['image'].get('prompt', '')}]"})
            elif m.get("content"):
                out.append({"role": "assistant", "content": m["content"]})
    return out


# ---------------------------------------------------------------- backup das conversas

BACKUP_FORMAT = 1


def backup_info():
    chats = list(CHATS.glob("*.json"))
    ids = set()
    for f in chats:
        try:
            ids |= upload_ids(json.loads(f.read_text("utf-8")))
        except (OSError, ValueError):
            pass
    files = [media.UPLOADS / i for i in ids if (media.UPLOADS / i).is_file()]
    return {"chats": len(chats), "chats_size": sum(f.stat().st_size for f in chats),
            "files": len(files), "files_size": sum(f.stat().st_size for f in files)}


def build_backup(dest, with_files):
    chats = sorted(CHATS.glob("*.json"))
    ids = set()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in chats:
            z.write(f, f"chats/{f.name}")
            try:
                ids |= upload_ids(json.loads(f.read_text("utf-8")))
            except (OSError, ValueError):
                pass
        n_files = 0
        if with_files:
            for i in sorted(ids):
                fp = media.UPLOADS / i
                if fp.is_file():
                    # midia ja comprimida nao precisa de nova compressao
                    z.write(fp, f"uploads/{i}", compress_type=zipfile.ZIP_STORED if fp.suffix in (".png", ".jpg", ".jpeg", ".webp", ".mp3") else zipfile.ZIP_DEFLATED)
                    n_files += 1
        s = {k: v for k, v in load_settings().items() if k not in SECRETS}
        z.writestr("settings.json", json.dumps(s, ensure_ascii=False, indent=1))
        if agents.FILE.exists():
            z.write(agents.FILE, "agents.json")
        z.writestr("manifest.json", json.dumps({"app": "LLM Local", "format": BACKUP_FORMAT, "created": time.time(),
                                                "chats": len(chats), "files": n_files}, indent=1))


def restore_backup(src, with_settings=False):
    added = updated = skipped = files = 0
    with zipfile.ZipFile(src) as z:
        try:
            manifest = json.loads(z.read("manifest.json"))
        except (KeyError, ValueError):
            raise ValueError("Este arquivo nao e um backup do LLM Local.")
        if manifest.get("app") != "LLM Local":
            raise ValueError("Este arquivo nao e um backup do LLM Local.")
        for name in z.namelist():
            m = re.match(r"^chats/([A-Za-z0-9_-]{1,64})\.json$", name)
            if m:
                try:
                    chat = json.loads(z.read(name).decode("utf-8"))
                except ValueError:
                    skipped += 1
                    continue
                chat["id"] = m.group(1)
                dest = CHATS / f"{m.group(1)}.json"
                if dest.exists():
                    try:
                        cur = json.loads(dest.read_text("utf-8"))
                    except (OSError, ValueError):
                        cur = {}
                    if float(chat.get("updated") or 0) <= float(cur.get("updated") or 0):
                        skipped += 1
                        continue
                    updated += 1
                else:
                    added += 1
                dest.write_text(json.dumps(chat, ensure_ascii=False, indent=1), "utf-8")
                continue
            m = re.match(r"^uploads/([a-f0-9]{20}\.[a-z0-9]{1,6})$", name)
            if m and not (media.UPLOADS / m.group(1)).exists():
                with z.open(name) as fsrc, open(media.UPLOADS / m.group(1), "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
                files += 1
        if with_settings and "settings.json" in z.namelist():
            try:
                s = json.loads(z.read("settings.json"))
                s.pop("workspaces", None)  # pastas do outro PC podem nao existir aqui
                save_settings({k: v for k, v in s.items() if k not in SECRETS})
            except ValueError:
                pass
        n_agents = 0
        if "agents.json" in z.namelist():
            try:
                incoming, cur = json.loads(z.read("agents.json")), agents.load()
                have_a, have_g = {a["id"] for a in cur["agents"]}, {g["id"] for g in cur["groups"]}
                new_a = [a for a in incoming.get("agents", []) if a.get("id") not in have_a]
                new_g = [g for g in incoming.get("groups", []) if g.get("id") not in have_g]
                if new_a or new_g:
                    agents.save({"agents": cur["agents"] + new_a, "groups": cur["groups"] + new_g})
                n_agents = len(new_a) + len(new_g)
            except (ValueError, KeyError, TypeError):
                pass
    return {"added": added, "updated": updated, "skipped": skipped, "files": files, "agents": n_agents}


def upload_ids(obj):
    return set(re.findall(r'"([a-f0-9]{20}\.[a-z0-9]{1,6})"', json.dumps(obj)))


# ---------------------------------------------------------------- HTTP

MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".mjs": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".wav": "audio/wav",
        ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".json": "application/json", ".txt": "text/plain; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    server_version = "LLMLocal"

    def log_message(self, fmt, *args):
        pass

    # helpers
    def send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def check_origin(self):
        # bloqueia sites externos de usarem seu servidor local
        origin = self.headers.get("Origin")
        return not origin or origin in (f"http://{HOST}:{PORT}", f"http://localhost:{PORT}")

    # rotas
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        p, q = url.path, urllib.parse.parse_qs(url.query)
        try:
            if p == "/api/status":
                return self.send_json({"engine": ENGINE_PROC.status() | {"device": ENGINE_PROC.device}, "extras": POOL.status(),
                                       "memory": POOL.memory(), "backends": installed_backends(), "quick": POOL.quick_status(),
                                       "gpu_live": {k: DIAG[k] for k in ("vram_used", "vram_total", "gpu_util", "guard")} | {"full": bool(DIAG["full_since"])},
                                       "gpu": GPU | {"cpu_count": CPU_COUNT},
                                       "models": list_models(), "tasks": public_tasks(),
                                       "settings": masked(load_settings()), "chats": list_chats(),
                                       "stats": load_stats()})
            if p == "/api/diag":
                return self.send_json(diag_snapshot())
            if p == "/api/log":
                return self.send_json({"log": list(ENGINE_PROC.log)})
            if p == "/api/agents":
                return self.send_json(agents.load())
            if p == "/api/mcp":
                return self.send_json(self.mcp_status())
            if p == "/api/models/settings":
                rel = q.get("model", [""])[0]
                rec, family = model_recommended(rel)
                return self.send_json({"settings": modelsettings.get(rel), "recommended": rec, "family": family})
            if p == "/api/codex/diff":
                d = self.checkpoint_dir(q.get("chat_id", [""])[0], q.get("run_id", [""])[0])
                if not d:
                    return self.send_json({"error": "ponto de restauração não encontrado"}, 404)
                return self.send_json(agent.diff_checkpoint(d))
            if p == "/api/kb":
                ep = media.embed_model_path()
                return self.send_json({"bases": kb.list_kbs(), "embed_model": ep.name if ep else ""})
            if p == "/api/kb/pending":
                return self.send_json(kb.load_meta(q.get("id", [""])[0]).get("pending_pdfs", []))
            if p == "/api/kb/file":
                meta = kb.load_meta(q.get("id", [""])[0])
                path = Path(q.get("path", [""])[0])
                if path.suffix.lower() != ".pdf" or not kb.inside_folders(meta, path) or not path.is_file():
                    return self.send_json({"error": "arquivo inválido"}, 400)
                return self.send_file(path)
            if p == "/api/backup/info":
                return self.send_json(backup_info())
            if p == "/api/backup":
                return self.send_backup(q.get("attachments", ["1"])[0] == "1")
            if p == "/api/media":
                return self.send_json({"whisper": media.whisper_status(), "image": media.image_status(),
                                       "mmproj": list_mmproj(), "mtp": list_mtp()})
            if p.startswith("/api/uploads/"):
                try:
                    return self.send_file(media.upload_path(p.rsplit("/", 1)[-1]))
                except ValueError:
                    return self.send_json({"error": "nao encontrado"}, 404)
            if p == "/api/chats":
                return self.send_json(list_chats())
            if p.startswith("/api/chats/"):
                cid = p.rsplit("/", 1)[-1]
                f = CHATS / f"{cid}.json"
                if not ID_RE.match(cid) or not f.exists():
                    return self.send_json({"error": "nao encontrado"}, 404)
                return self.send_json(json.loads(f.read_text("utf-8")))
            if p == "/api/hf/search":
                term = q.get("q", [""])[0]
                res = get_json("https://huggingface.co/api/models?" + urllib.parse.urlencode(
                    {"search": term, "filter": "gguf", "sort": "downloads", "direction": "-1", "limit": "40"})
                    + "&" + catalog.HF_EXPAND)
                return self.send_json([{"id": r["id"], "downloads": r.get("downloads", 0), "likes": r.get("likes", 0),
                                        "updated": r.get("lastModified", ""), **catalog.model_caps(r)} for r in res])
            if p == "/api/hf/files":
                repo = q.get("repo", [""])[0]
                tree = hf_tree(repo)
                mm = pick_mmproj(tree)
                files = [f | catalog.quant_info(f["path"].rsplit("/", 1)[-1]) for f in hf_files(repo, tree)]
                mt = pick_mtp(tree)
                try:
                    info = hf_model_info(repo)
                except (urllib.error.URLError, OSError, ValueError):
                    info = None
                return self.send_json({"files": files, "mmproj": mm["path"] if mm else "", "info": info,
                                       "mtp": mt["path"] if mt else "", "mtp_size": mt["size"] if mt else 0})
            return self.static(p)
        except urllib.error.HTTPError as e:
            self.send_json({"error": f"HTTP {e.code}: {e.reason}"}, 502)
        except (urllib.error.URLError, OSError) as e:
            self.send_json({"error": f"Sem conexao: {e}"}, 502)

    def static(self, p):
        if p == "/":
            p = "/index.html"
        f = (WEB / p.lstrip("/")).resolve()
        if WEB.resolve() not in f.parents or not f.is_file():
            return self.send_json({"error": "nao encontrado"}, 404)
        self.send_file(f)

    def send_file(self, f):
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(f.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self.check_origin():
            return self.send_json({"error": "origem bloqueada"}, 403)
        p = urllib.parse.urlparse(self.path).path
        if p == "/api/upload":
            return self.handle_upload()
        if p == "/api/restore":
            return self.handle_restore(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
        try:
            b = self.body()
            if p == "/api/chat":
                return self.proxy_chat(b)
            if p == "/api/agent":
                return self.run_agent(b)
            if p == "/api/summarize":
                return self.summarize(b)
            if p == "/api/codex/undo":
                d = self.checkpoint_dir(b.get("chat_id", ""), b.get("run_id", ""))
                if not d:
                    return self.send_json({"error": "ponto de restauração não encontrado"}, 404)
                try:
                    return self.send_json({"restored": agent.undo_checkpoint(d)})
                except agent.ToolError as e:
                    return self.send_json({"error": str(e)}, 400)
            if p == "/api/kb/create":
                return self.send_json(kb.create(b.get("name", ""), b.get("folders", [])))
            if p == "/api/kb/index":
                kid = b.get("id", "")
                meta = kb.load_meta(kid)
                t = new_task("kb", f"Indexando \"{meta['name']}\"")
                run_task(t, lambda task: kb.index(kid, task, lambda texts: embed_texts(texts), media.extract_text_path))
                return self.send_json({"id": t["id"]})
            if p == "/api/kb/add_text":
                try:
                    return self.send_json({"chunks": kb.add_text(b.get("id", ""), b.get("path", ""), b.get("text", ""), embed_texts)})
                except RuntimeError as e:
                    return self.send_json({"error": str(e)}, 400)
            if p == "/api/kb/search":
                try:
                    return self.send_json(kb.search(b.get("id", ""), b.get("query", ""), embed_texts))
                except RuntimeError as e:
                    return self.send_json({"error": str(e)}, 400)
            if p == "/api/group/run":
                return self.run_group(b)
            if p == "/api/mcp/test":
                srv = mcp.MANAGER.get(b.get("id", ""))
                if not srv:
                    return self.send_json({"error": "servidor não encontrado"}, 404)
                srv.close()
                try:
                    srv.connect()
                except mcp.MCPError as e:
                    return self.send_json({"error": str(e), **self.mcp_status()}, 400)
                return self.send_json(self.mcp_status())
            if p == "/api/mcp/stop":
                srv = mcp.MANAGER.get(b.get("id", ""))
                if srv:
                    srv.close()
                return self.send_json(self.mcp_status())
            if p == "/api/mcp/preset":
                try:
                    cfg = mcp.preset(b.get("kind", ""))
                except mcp.MCPError as e:
                    return self.send_json({"error": str(e)}, 400)
                servers = mcp.load()
                if any(s.get("id") == cfg["id"] or (s.get("command") == cfg["command"] and s.get("args") == cfg["args"]) for s in servers):
                    return self.send_json({"error": "Esse servidor já foi adicionado."}, 400)
                mcp.save(servers + [cfg])
                return self.send_json(self.mcp_status())
            if p == "/api/agents/template":
                doc, gid = agents.template(b.get("kind", ""))
                return self.send_json({"doc": doc, "group_id": gid})
            if p == "/api/agent/approve":
                return self.send_json({"ok": agent.AgentRun.answer(b.get("id"), bool(b.get("ok")), bool(b.get("always")))})
            if p == "/api/image/generate":
                return self.image_generate(b)
            if p == "/api/transcribe":
                s = load_settings()
                try:
                    text = media.transcribe(b.get("id", ""), s.get("whisper_model", ""), s.get("whisper_language", "auto"),
                                            cpu_threads(s))
                except RuntimeError as e:
                    return self.send_json({"error": str(e)}, 400)
                return self.send_json({"text": text})
            if p == "/api/extract":
                try:
                    return self.send_json({"text": media.extract_text(b.get("id", ""))})
                except (KeyError, zipfile.BadZipFile) as e:
                    return self.send_json({"error": f"Nao foi possivel ler o documento: {e}"}, 400)
            if p == "/api/media/install":
                what, value = b.get("what"), b.get("value", "")
                jobs = {
                    "whisper": (("cuda", "cpu"), "Motor de audio Whisper", media.install_whisper),
                    "whisper_model": (tuple(media.WHISPER_MODELS), "Modelo Whisper", media.install_whisper_model),
                    "sd": (("vulkan", "cuda", "cpu"), "Motor de imagem", media.install_sd),
                    "image_preset": (tuple(media.IMAGE_PRESETS), "Modelo de imagem", media.install_image_preset),
                    "embed_model": (("qwen3-embedding",), "Modelo de embeddings", media.install_embed_model),
                }
                if what not in jobs or value not in jobs[what][0]:
                    return self.send_json({"error": "opcao invalida"}, 400)
                t = new_task("engine" if what in ("whisper", "sd") else "model", f"{jobs[what][1]} ({value})")
                run_task(t, lambda task: jobs[what][2](task, value))
                return self.send_json({"id": t["id"]})
            if p == "/api/quick/load":
                upd = {k: b[k] for k in ("quick_model", "quick_device", "quick_keep_loaded") if k in b}
                if upd:
                    save_settings(upd)
                POOL.quick_error = ""
                s = load_settings()
                POOL.stop(s.get("quick_model") or None) if "quick_device" in upd and s.get("quick_model") else None
                POOL.load_quick()
                return self.send_json(POOL.quick_status())
            if p == "/api/quick/unload":
                s = load_settings()
                save_settings({"quick_keep_loaded": False})
                POOL._quick_cancel = True
                if s.get("quick_model") and s["quick_model"] != ENGINE_PROC.model:
                    POOL.stop(s["quick_model"])
                return self.send_json(POOL.quick_status())
            if p == "/api/models/mtp":
                mt = b.get("mtp") or ""
                if mt and mt not in list_mtp():
                    return self.send_json({"error": "acelerador MTP inválido"}, 400)
                set_mtp(b.get("model", ""), mt)
                return self.send_json({"ok": True})
            if p == "/api/models/mmproj":
                mm = b.get("mmproj") or ""
                if mm and mm not in list_mmproj():
                    return self.send_json({"error": "arquivo de visao invalido"}, 400)
                set_mmproj(b.get("model", ""), mm)
                return self.send_json({"ok": True})
            if p == "/api/load":
                s = load_settings()
                s.update({k: v for k, v in b.items() if k in DEFAULT_SETTINGS})
                save_settings({"last_model": b.get("model", "")})
                ENGINE_PROC.start(b.get("model", ""), s)
                return self.send_json({"ok": True})
            if p == "/api/unload":
                if b.get("extra"):
                    POOL.stop(None if b["extra"] == "all" else b["extra"])
                else:
                    ENGINE_PROC.stop()
                    if b.get("all"):
                        POOL.stop()
                return self.send_json({"ok": True})
            if p == "/api/engine/install":
                backend = b.get("backend")
                if backend not in BACKENDS:
                    return self.send_json({"error": "backend invalido"}, 400)
                t = new_task("engine", f"Motor llama.cpp ({backend.upper()})")
                run_task(t, lambda task: install_engine(task, backend))
                return self.send_json({"id": t["id"]})
            if p == "/api/models/download":
                repo, path = b.get("repo", ""), b.get("path", "")
                if not re.match(r"^[\w.-]+/[\w.-]+$", repo) or ".." in path:
                    return self.send_json({"error": "repositorio invalido"}, 400)
                t = new_task("model", f"{repo} / {Path(path).name}")
                with_mm, with_mtp = bool(b.get("mmproj")), bool(b.get("mtp"))
                run_task(t, lambda task: download_model(task, repo, path, with_mm, with_mtp))
                return self.send_json({"id": t["id"]})
            if p == "/api/models/delete":
                f = (MODELS / b.get("path", "")).resolve()
                if MODELS.resolve() not in f.parents or not f.is_file():
                    return self.send_json({"error": "modelo nao encontrado"}, 404)
                if ENGINE_PROC.model == b.get("path"):
                    ENGINE_PROC.stop()
                m = SPLIT_RE.match(f.name)
                targets = list(f.parent.glob(f"{m.group(1)}-*-of-{m.group(3)}.gguf")) if m else [f]
                for t in targets:
                    t.unlink()
                if f.parent != MODELS.resolve() and not any(f.parent.iterdir()):
                    f.parent.rmdir()
                return self.send_json({"ok": True})
            if p == "/api/stats/reset":
                with _stats_lock:
                    STATS_FILE.unlink(missing_ok=True)
                return self.send_json(load_stats())
            if p == "/api/tasks/cancel":
                t = TASKS.get(b.get("id"))
                if t:
                    t["cancel"] = True
                return self.send_json({"ok": True})
            if p == "/api/open-folder":
                folder = {"models": MODELS, "data": DATA, "engine": ENGINE}.get(b.get("which"), ROOT)
                if os.name == "nt":
                    os.startfile(folder)  # noqa: S606
                return self.send_json({"ok": True})
            return self.send_json({"error": "rota desconhecida"}, 404)
        except ValueError as e:
            self.send_json({"error": str(e)}, 400)

    def do_PUT(self):
        if not self.check_origin():
            return self.send_json({"error": "origem bloqueada"}, 403)
        p = urllib.parse.urlparse(self.path).path
        b = self.body()
        if p == "/api/agents":
            return self.send_json(agents.save(b))
        if p == "/api/mcp":
            try:
                mcp.save(b.get("servers", []))
            except mcp.MCPError as e:
                return self.send_json({"error": str(e)}, 400)
            return self.send_json(self.mcp_status())
        if p == "/api/models/settings":
            return self.send_json({"settings": modelsettings.save(b.get("model", ""), b.get("settings"))})
        if p.startswith("/api/kb/"):
            try:
                return self.send_json(kb.update(p.rsplit("/", 1)[-1], b.get("name"), b.get("folders")))
            except (ValueError, OSError) as e:
                return self.send_json({"error": str(e)}, 400)
        if p == "/api/settings":
            for k in SECRETS:
                if b.get(k) == "***":
                    b.pop(k)
            if "workspaces" in b:
                b["workspaces"] = sorted({str(Path(w).resolve()) for w in b["workspaces"] if w and Path(w).is_dir()})
            return self.send_json(masked(save_settings(b)))
        if p.startswith("/api/chats/"):
            cid = p.rsplit("/", 1)[-1]
            if not ID_RE.match(cid):
                return self.send_json({"error": "id invalido"}, 400)
            b["id"] = cid
            b["updated"] = time.time()
            (CHATS / f"{cid}.json").write_text(json.dumps(b, ensure_ascii=False, indent=1), "utf-8")
            return self.send_json({"ok": True, "updated": b["updated"]})
        self.send_json({"error": "rota desconhecida"}, 404)

    def do_DELETE(self):
        if not self.check_origin():
            return self.send_json({"error": "origem bloqueada"}, 403)
        p = urllib.parse.urlparse(self.path).path
        if p.startswith("/api/kb/"):
            try:
                kb.delete(p.rsplit("/", 1)[-1])
            except ValueError:
                pass
            return self.send_json({"ok": True})
        if p.startswith("/api/chats/"):
            cid = p.rsplit("/", 1)[-1]
            f = CHATS / f"{cid}.json"
            if ID_RE.match(cid):
                shutil.rmtree(CHECKPOINTS / cid, ignore_errors=True)
            if ID_RE.match(cid) and f.exists():
                try:
                    for fid in upload_ids(json.loads(f.read_text("utf-8"))):
                        (media.UPLOADS / fid).unlink(missing_ok=True)
                except (OSError, ValueError):
                    pass
                f.unlink()
            return self.send_json({"ok": True})
        self.send_json({"error": "rota desconhecida"}, 404)

    # ---- chat (stream SSE) ----
    def sse(self, obj):
        self.wfile.write(b"data: " + json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n\n")
        self.wfile.flush()

    def engine_call(self, payload, stream):
        port = getattr(self, "engine_port", ENGINE_PORT)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=3600)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            try:
                msg = json.loads(msg)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            raise RuntimeError(msg) from None
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"Motor nao respondeu: {e}") from None

    def make_query(self, messages):
        """Pede ao proprio modelo uma consulta curta para o buscador."""
        convo = [m for m in messages if m["role"] in ("user", "assistant")][-5:]
        hist = "\n".join(f"{'Usuario' if m['role'] == 'user' else 'Assistente'}: {text_of(m['content'])[:600]}"
                         for m in convo[:-1])
        last = text_of(convo[-1]["content"]) if convo else ""
        prompt = (f"Data de hoje: {datetime.now():%d/%m/%Y}.\n"
                  + (f"Conversa anterior:\n{hist}\n\n" if hist else "")
                  + f"Mensagem atual do usuario:\n{last[:1500]}\n\n"
                  "Escreva UMA consulta curta para um buscador da web que encontre as informacoes necessarias "
                  "para responder a mensagem atual. Responda somente com a consulta, sem aspas e sem explicacao.")
        try:
            with self.engine_call({"messages": [{"role": "user", "content": prompt}], "stream": False,
                                   "temperature": 0.2, "max_tokens": 600,
                                   "chat_template_kwargs": {"enable_thinking": False}}, False) as r:
                data = json.loads(r.read().decode("utf-8"))
            add_stats(data.get("timings"))
            q = data["choices"][0]["message"].get("content") or ""
            q = re.sub(r"<think>[\s\S]*?(</think>|$)", "", q).strip().splitlines()
            q = q[0].strip().strip('"\'`').strip() if q else ""
            if q.lower().startswith(("consulta:", "query:")):
                q = q.split(":", 1)[1].strip()
            if 2 <= len(q) <= 200:
                return q
        except (RuntimeError, ValueError, KeyError, IndexError, OSError):
            pass
        return re.sub(r"\s+", " ", last)[:200]

    def web_augment(self, messages):
        s = load_settings()
        self.sse({"llmlocal": {"stage": "query"}})
        query = self.make_query(messages)
        self.sse({"llmlocal": {"stage": "search", "query": query}})
        try:
            results = websearch.search(query, s)
        except Exception as e:  # noqa: BLE001
            self.sse({"llmlocal": {"stage": "error", "query": query, "text": f"Falha na pesquisa: {e}"}})
            return messages
        add_stats(searches=1)
        if not results:
            self.sse({"llmlocal": {"stage": "error", "query": query, "text": "A pesquisa nao retornou resultados."}})
            return messages
        self.sse({"llmlocal": {"stage": "read", "query": query,
                               "sources": [{"title": r["title"], "url": r["url"]} for r in results]}})
        n_ctx = ENGINE_PROC.n_ctx or int(s["ctx_size"])
        budget = max(2500, min(24000, int(n_ctx * 0.45 * 3.2)))  # ~3,2 caracteres por token
        texts = websearch.fetch_pages(results, budget // len(results))
        blocks = []
        for i, (r, t) in enumerate(zip(results, texts), 1):
            blocks.append(f"[{i}] {r['title']}\nURL: {r['url']}\n{t or r['snippet']}")
        self.sse({"llmlocal": {"stage": "done", "query": query,
                               "sources": [{"title": r["title"], "url": r["url"], "snippet": r["snippet"]} for r in results]}})
        ctx = (f"[Resultados de pesquisa na web, feita agora ({datetime.now():%d/%m/%Y %H:%M}) com a consulta \"{query}\"]\n\n"
               + "\n\n---\n\n".join(blocks)
               + "\n\n[Fim dos resultados]\n\nUse os resultados acima para responder com informacoes atuais. "
               "Cite as fontes no texto com o numero entre colchetes, ex.: [1], [2]. "
               "Se os resultados nao forem suficientes, diga isso.\n\nMensagem do usuario:\n")
        out = [dict(m) for m in messages]
        for m in reversed(out):
            if m["role"] == "user":
                if isinstance(m["content"], list):
                    m["content"] = [dict(x) for x in m["content"]]
                    for part in m["content"]:
                        if part.get("type") == "text":
                            part["text"] = ctx + part["text"]
                            break
                else:
                    m["content"] = ctx + m["content"]
                break
        return out

    def sse_safe(self, obj):
        """Envia um evento SSE; obj=None manda so um ping. Retorna False se o cliente desconectou."""
        try:
            if obj is None:
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
            else:
                self.sse(obj)
            return True
        except OSError:
            return False

    def start_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    # ---- arquivos enviados ----
    def handle_upload(self):
        if not self.check_origin():
            return self.send_json({"error": "origem bloqueada"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        name = urllib.parse.unquote(self.headers.get("X-Filename") or "arquivo.bin")

        def chunks():
            left = n
            while left > 0:
                data = self.rfile.read(min(1 << 20, left))
                if not data:
                    break
                left -= len(data)
                yield data
        try:
            return self.send_json(media.save_upload(name, chunks()))
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)

    # ---- grupos de agentes ----
    def reply_rule(self):
        return reply_rule()

    def apply_model_sampling(self, payload, rel, agent_temperature=None):
        return apply_model_sampling(payload, rel, agent_temperature)

    def split_content(self, m, modalities=None):
        """Separa o texto e as partes de midia (imagens/audio) de uma mensagem do usuario."""
        c = build_content(m, ENGINE_PROC.modalities if modalities is None else modalities)
        if isinstance(c, list):
            return text_of(c), [x for x in c if x.get("type") != "text"]
        return c, []

    def run_group(self, b):
        self.start_sse()
        sampling = {k: b[k] for k in ("temperature", "top_p", "top_k", "min_p", "repeat_penalty") if k in b}
        if int(b.get("max_tokens") or 0) > 0:
            sampling["max_tokens"] = int(b["max_tokens"])
        msgs = [m for m in b.get("messages", []) if m.get("role") != "system"]
        if not msgs or msgs[-1].get("role") != "user":
            return self.sse_safe({"error": {"message": "Mensagem vazia."}})
        history = build_history(msgs[:-1], ENGINE_PROC.modalities)
        try:
            timings = agents.run_group(self, b.get("group_id", ""), msgs[-1], history, sampling)
            if timings:
                add_stats(timings)
        except RuntimeError as e:
            self.sse_safe({"error": {"message": str(e)}})
        except ConnectionError:
            pass

    # ---- backup ----
    def send_backup(self, with_files):
        tmp = DATA / f"_backup_{uuid.uuid4().hex[:8]}.zip"
        try:
            build_backup(tmp, with_files)
            name = f"LLM-Local-backup-{datetime.now():%Y-%m-%d_%H%M}.zip"
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(tmp.stat().st_size))
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.end_headers()
            with open(tmp, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 1 << 20)
        except OSError:
            pass
        finally:
            tmp.unlink(missing_ok=True)

    def handle_restore(self, q):
        if not self.check_origin():
            return self.send_json({"error": "origem bloqueada"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        tmp = DATA / f"_restore_{uuid.uuid4().hex[:8]}.zip"
        try:
            with open(tmp, "wb") as f:
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            return self.send_json(restore_backup(tmp, q.get("settings", ["0"])[0] == "1"))
        except (ValueError, zipfile.BadZipFile) as e:
            return self.send_json({"error": str(e) if isinstance(e, ValueError) else "Arquivo de backup invalido ou corrompido."}, 400)
        finally:
            tmp.unlink(missing_ok=True)

    # ---- geracao de imagem ----
    def enhance_prompt(self, prompt):
        """Usa o LLM carregado para transformar o pedido num prompt detalhado em ingles."""
        req = ("Rewrite the user's image request as ONE detailed English prompt for an image generation model: "
               "subject, style, composition, lighting, colors, details. Keep any text that must appear in the image "
               "in its original language, inside quotes. Answer with the prompt only.\n\nRequest: " + prompt)
        try:
            with self.engine_call({"messages": [{"role": "user", "content": req}], "stream": False, "temperature": 0.6,
                                   "max_tokens": 400, "chat_template_kwargs": {"enable_thinking": False}}, False) as r:
                data = json.loads(r.read().decode("utf-8"))
            add_stats(data.get("timings"))
            out = data["choices"][0]["message"].get("content") or ""
            out = re.sub(r"<think>[\s\S]*?(</think>|$)", "", out).strip().strip('"')
            return out if len(out) > 8 else prompt
        except (RuntimeError, ValueError, KeyError, IndexError, OSError):
            return prompt

    def image_generate(self, b):
        s = load_settings()
        preset = b.get("preset") or s.get("image_preset") or "z-image-turbo"
        prompt = (b.get("prompt") or "").strip()
        if not prompt:
            return self.send_json({"error": "Descreva a imagem."}, 400)
        self.start_sse()
        alive = {"ok": True}

        def emit(obj):
            if alive["ok"]:
                alive["ok"] = self.sse_safe(obj)
            return alive["ok"]

        reload_model = None
        try:
            final = prompt
            if b.get("enhance", s.get("image_enhance")) and ENGINE_PROC.state == "ready":
                emit({"image": {"stage": "enhance"}})
                final = self.enhance_prompt(prompt)
            if s.get("image_unload_llm") and ENGINE_PROC.state in ("ready", "loading"):
                reload_model = ENGINE_PROC.model
                emit({"image": {"stage": "unload"}})
                ENGINE_PROC.stop()
            seed = int(b.get("seed", -1))
            if seed < 0:
                seed = random.randint(0, 2 ** 31 - 1)
            emit({"image": {"stage": "loading", "prompt": final, "seed": seed}})
            t0 = time.time()
            fid, out = media.generate_image(
                preset, final, b.get("negative", ""), b.get("width") or s.get("image_width"),
                b.get("height") or s.get("image_height"), b.get("steps") or s.get("image_steps"), 0, seed,
                s.get("image_offload", True), threads=cpu_threads(s),
                on_progress=lambda pr: emit({"image": {"stage": "progress", **pr}}),
                cancel=lambda: not alive["ok"])
            emit({"image": {"stage": "done", "id": fid, "path": str(out), "prompt": prompt, "final_prompt": final,
                            "seed": seed, "preset": preset, "seconds": round(time.time() - t0, 1)}})
        except RuntimeError as e:
            emit({"error": {"message": str(e)}})
        finally:
            if reload_model:
                try:
                    ENGINE_PROC.start(reload_model, load_settings())
                except (ValueError, OSError):
                    pass

    def image_for_agent(self, prompt, width, height, dest):
        s = load_settings()
        fid, out = media.generate_image(s.get("image_preset") or "z-image-turbo", prompt, "", width or 0, height or 0,
                                        0, 0, random.randint(0, 2 ** 31 - 1), s.get("image_offload", True))
        shutil.copy2(out, dest)
        return fid

    # ---- Codex ----
    def run_agent(self, b):
        if ENGINE_PROC.state != "ready":
            return self.send_json({"error": "Nenhum modelo carregado."}, 503)
        s = load_settings()
        mcp_ids = [x.cfg["id"] for x in mcp.MANAGER.all() if x.cfg.get("enabled")]
        if b.get("mcp_only"):
            if not mcp_ids:
                return self.send_json({"error": "Nenhum servidor MCP ativo. Adicione um em Configurações > Ferramentas MCP."}, 400)
            ws = None
        else:
            ws = str(Path(b.get("workspace") or "_").resolve())
            if ws not in s.get("workspaces", []):
                return self.send_json({"error": "Pasta nao liberada. Adicione-a nas Configuracoes > Codex."}, 403)
        self.start_sse()
        sampling = {k: b[k] for k in ("temperature", "top_p", "top_k", "min_p", "repeat_penalty") if k in b}
        if int(b.get("max_tokens") or 0) > 0:
            sampling["max_tokens"] = int(b["max_tokens"])
        history = build_history(b.get("messages", []), ENGINE_PROC.modalities, agent_mode=True)
        image_fn = self.image_for_agent if (media.find_exe("sd", media.SD_EXE)
                                            and media.preset_installed(s.get("image_preset") or "z-image-turbo")) else None
        s["_reply_rule"] = reply_rule(s)
        apply_model_sampling(sampling, ENGINE_PROC.model)
        chat_id = b.get("chat_id", "") if ID_RE.match(b.get("chat_id", "")) else "sem-conversa"
        ckpt = CHECKPOINTS / chat_id / uuid.uuid4().hex[:10]
        run = agent.AgentRun(lambda payload: self.engine_call(payload, True), self.sse_safe, s, image_fn if ws else None,
                             ckpt, mcp_ids, self.save_tool_image)
        try:
            trace, timings = run.run(ws, history, b.get("chat_id", ""), sampling)
            run.send({"agent": {"type": "trace", "trace": trace}})
            if timings:
                add_stats(timings)
        except (RuntimeError, agent.ToolError) as e:
            run.send({"error": {"message": str(e)}})

    def save_tool_image(self, data, mime):
        """Guarda uma imagem devolvida por uma ferramenta MCP (ex.: print da tela) e devolve o id do arquivo."""
        ext = {"image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}.get(mime, "png")
        fid, path = media.new_media_path(ext)
        path.write_bytes(data)
        return fid

    def mcp_status(self):
        return {"servers": [x.public() for x in mcp.MANAGER.all()], "roblox_detected": bool(mcp.roblox_bat())}

    def checkpoint_dir(self, chat_id, run_id):
        if not re.match(r"^[A-Za-z0-9_-]{1,64}$", chat_id or "") or not re.match(r"^[a-f0-9]{10}$", run_id or ""):
            return None
        d = CHECKPOINTS / chat_id / run_id
        return d if (d / "manifest.json").is_file() else None

    def summarize(self, b):
        """Resume a parte antiga de uma conversa para ela caber no contexto."""
        msgs = [m for m in b.get("messages", []) if m.get("role") in ("user", "assistant")]
        if not msgs:
            return self.send_json({"error": "nada para resumir"}, 400)
        try:
            with self.engine_for(b.get("model", "")) as eng:
                self.engine_port = eng.port
                budget = int((eng.n_ctx or 8192) * 0.55 * 3)  # ~3 caracteres por token, deixando espaço para o resumo
                per = max(300, budget // len(msgs))
                lines = []
                for m in msgs:
                    t = text_of(m.get("content", ""))
                    if len(t) > per:
                        t = t[:per * 2 // 3] + "\n[...]\n" + t[-per // 3:]
                    lines.append(("Usuário" if m["role"] == "user" else "Assistente") + ": " + t)
                prompt = ("Resuma a conversa a seguir para que ela possa continuar sem o histórico completo. Preserve: "
                          "o objetivo do usuário, fatos, decisões, nomes, números, trechos de código importantes e o que "
                          "ainda está pendente. Seja conciso e use tópicos. Escreva no idioma da conversa.\n\n" + "\n\n".join(lines))
                with self.engine_call({"messages": [{"role": "user", "content": prompt}], "stream": False, "temperature": 0.3,
                                       "max_tokens": 1200, "chat_template_kwargs": {"enable_thinking": False}}, False) as r:
                    data = json.loads(r.read().decode("utf-8"))
            add_stats(data.get("timings"))
            text = re.sub(r"<think>[\s\S]*?(</think>|$)", "", data["choices"][0]["message"].get("content") or "").strip()
            return self.send_json({"summary": text})
        except (RuntimeError, KeyError, IndexError, ValueError) as e:
            return self.send_json({"error": str(e)}, 400)

    def kb_augment(self, messages, kid):
        """Busca na base de conhecimento os trechos mais parecidos com a pergunta e os junta à mensagem."""
        try:
            meta = kb.load_meta(kid)
        except (ValueError, OSError):
            return messages
        users = [text_of(m["content"]) for m in messages if m.get("role") == "user"]
        if not users:
            return messages
        query = users[-1] if len(users[-1]) > 40 or len(users) < 2 else users[-2] + "\n" + users[-1]
        self.sse({"kb": {"stage": "searching", "name": meta["name"]}})
        try:
            hits = kb.search(kid, query[-2000:], lambda texts: embed_texts(texts, self.loading_notifier(
                lambda n: {"kb": {"stage": "loading", "name": meta["name"], "model": n}})))
        except RuntimeError as e:
            self.sse({"kb": {"stage": "error", "name": meta["name"], "text": str(e)}})
            return messages
        sources = [{"n": i, "path": h["path"], "file": Path(h["path"]).name, "lines": h["lines"], "score": h["score"]}
                   for i, h in enumerate(hits, 1)]
        self.sse({"kb": {"stage": "done", "name": meta["name"], "sources": sources}})
        if not hits:
            return messages
        blocks = [f"[D{i}] {Path(h['path']).name} (linhas {h['lines']})\n{h['text']}" for i, h in enumerate(hits, 1)]
        ctx = (f"[Trechos da base de conhecimento \"{meta['name']}\" relacionados à pergunta]\n\n" + "\n\n---\n\n".join(blocks)
               + "\n\n[Fim dos trechos]\n\nUse os trechos acima quando forem relevantes e cite as fontes no texto como "
               "[D1], [D2]. Se eles não bastarem para responder, diga isso.\n\nMensagem do usuario:\n")
        out = [dict(m) for m in messages]
        for m in reversed(out):
            if m["role"] == "user":
                if isinstance(m["content"], list):
                    m["content"] = [dict(x) for x in m["content"]]
                    for part in m["content"]:
                        if part.get("type") == "text":
                            part["text"] = ctx + part["text"]
                            break
                else:
                    m["content"] = ctx + m["content"]
                break
        return out

    def engine_for(self, model_rel, on_wait=None, device="auto"):
        """Motor para esta requisicao: o principal ou um modelo extra (carregado sob demanda, na GPU ou CPU)."""
        return POOL.use(model_rel or "", load_settings(), on_wait, device)

    def loading_notifier(self, make_event):
        """on_wait do POOL: avisa a interface uma vez e depois so manda pings (detecta desconexao)."""
        return lambda name, first: self.sse_safe(make_event(name) if first else None)

    def proxy_chat(self, b):
        ag = agents.get_agent(b["agent_id"]) if b.get("agent_id") else None
        model = (ag or {}).get("model") or b.get("model") or ""
        device = (ag or {}).get("device") if (ag or {}).get("model") else b.get("device", "auto")
        if not model and ENGINE_PROC.state != "ready":
            return self.send_json({"error": "Nenhum modelo carregado."}, 503)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        upstream = lease = None
        try:
            lease = self.engine_for(model, self.loading_notifier(lambda n: {"engine": {"stage": "loading", "model": n}}), device or "auto")
            eng = lease.__enter__()
            self.engine_port = eng.port
            if model:
                self.sse({"engine": {"stage": "ready", "model": model_display(eng.model), "device": eng.device}})
            msgs = b.get("messages", [])
            if ag:
                msgs = [{"role": "system", "content": (ag["instructions"] or "Você é um assistente útil.")
                         + f"\n\nVocê é o agente \"{ag['name']}\". Responda no idioma do usuário."}] + \
                       [m for m in msgs if m.get("role") != "system"]
                if ag["temperature"] is not None:
                    b["temperature"] = ag["temperature"]
                if ag["web"]:
                    b["web"] = True
            messages = with_reply_rule(build_history(msgs, eng.modalities))
            kid = (ag or {}).get("kb") or b.get("kb")
            if kid:
                messages = self.kb_augment(messages, kid)
            if b.get("web"):
                messages = self.web_augment(messages)
            payload = {"messages": messages, "stream": True, "cache_prompt": True, "timings_per_token": True}
            for k in ("temperature", "top_p", "top_k", "min_p", "repeat_penalty"):
                if k in b:
                    payload[k] = b[k]
            if int(b.get("max_tokens") or 0) > 0:
                payload["max_tokens"] = int(b["max_tokens"])
            apply_model_sampling(payload, eng.model, (ag or {}).get("temperature"))
            upstream = self.engine_call(payload, True)
            last_timings = None
            for line in iter(upstream.readline, b""):
                self.wfile.write(line)
                self.wfile.flush()
                if b'"timings"' in line:
                    last_timings = line
        except RuntimeError as e:
            try:
                self.sse({"error": {"message": str(e)}})
            except OSError:
                pass
        except (ConnectionError, OSError):
            pass  # usuario clicou em Parar: fechar a conexao interrompe a geracao
        finally:
            if upstream:
                upstream.close()
                try:
                    add_stats(json.loads(last_timings.decode("utf-8")[5:])["timings"]) if last_timings else None
                except (ValueError, KeyError):
                    pass
            if lease and lease.eng:
                lease.__exit__(None, None, None)


def watch_parent():
    """Encerra o servidor quando o app desktop que o abriu fecha (mesmo se fechar a forca)."""
    pid = int(os.environ.get("LLM_PARENT_PID") or 0)
    if not pid or os.name != "nt":
        return
    import ctypes
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    handle = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return

    def wait():
        k32.WaitForSingleObject(handle, 0xFFFFFFFF)
        mcp.MANAGER.stop()
        POOL.stop()
        ENGINE_PROC.stop()
        os._exit(0)

    threading.Thread(target=wait, daemon=True).start()


def auto_load():
    s = load_settings()
    if s.get("quick_keep_loaded") and s.get("quick_model"):
        def later():
            for _ in range(240):  # espera o principal terminar de carregar (ele tem prioridade na VRAM)
                if ENGINE_PROC.state != "loading":
                    break
                time.sleep(0.5)
            time.sleep(2)
            POOL.load_quick()
        threading.Thread(target=later, daemon=True).start()
    if s.get("auto_load") and s.get("last_model") and installed_backends() and (MODELS / s["last_model"]).is_file():
        try:
            ENGINE_PROC.start(s["last_model"], s)
        except (ValueError, OSError) as e:
            print("Nao foi possivel carregar o ultimo modelo:", e)


def main():
    url = f"http://{HOST}:{PORT}"
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        sys.exit(f"A porta {PORT} ja esta em uso (o LLM Local ja esta aberto?).")
    httpd.daemon_threads = True
    watch_parent()
    threading.Thread(target=auto_load, daemon=True).start()
    threading.Thread(target=cleanup_checkpoints, daemon=True).start()
    threading.Thread(target=diag_sampler, daemon=True).start()
    print(f"Servidor em {url} | API OpenAI do motor: http://127.0.0.1:{ENGINE_PORT}/v1", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        mcp.MANAGER.stop()
        POOL.stop()
        ENGINE_PROC.stop()


if __name__ == "__main__":
    main()
