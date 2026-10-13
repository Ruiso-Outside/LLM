"""Bases de conhecimento do LLM Local: a IA responde com base em pastas de documentos do usuario.

Os arquivos sao divididos em trechos, cada trecho vira um vetor (embedding) gerado localmente
pelo llama.cpp com um modelo de embeddings, e a busca encontra os trechos mais parecidos com a
pergunta. Tudo fica em data/kb/<id>/ (um JSON por arquivo indexado, para reindexar so o que mudou).
"""
import array
import base64
import hashlib
import json
import math
import operator
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

ROOT = None
ID_RE = re.compile(r"^[a-f0-9]{10}$")
TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".html", ".htm", ".css", ".js", ".mjs",
            ".ts", ".tsx", ".jsx", ".py", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php",
            ".lua", ".luau", ".sh", ".ps1", ".bat", ".sql", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log", ".vue",
            ".svelte", ".swift", ".dart", ".r", ".tex", ".srt", ".vtt", ".rst", ".gd", ".rbxlx", ".rbxmx"}
OFFICE_EXT = {".docx", ".pptx", ".xlsx", ".odt"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".idea", ".vs", "bin", "obj"}
MAX_FILE = 5 * 1024 * 1024
CHUNK = 1200        # caracteres por trecho
OVERLAP = 200
DIM = 512           # o Qwen3-Embedding aceita reduzir a dimensao (MRL); 512 e um bom equilibrio
QUERY_PREFIX = "Instruct: Given a user question, retrieve relevant passages that answer the question\nQuery: "
_cache = {}         # id -> (chunks, vetores) para a busca
_lock = threading.Lock()


def configure(data_dir):
    global ROOT
    ROOT = Path(data_dir) / "kb"
    ROOT.mkdir(parents=True, exist_ok=True)


def _dir(kid):
    if not ID_RE.match(kid or ""):
        raise ValueError("base invalida")
    return ROOT / kid


def _meta_path(kid):
    return _dir(kid) / "meta.json"


def load_meta(kid):
    return json.loads(_meta_path(kid).read_text("utf-8"))


def save_meta(meta):
    _meta_path(meta["id"]).write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")


def list_kbs():
    out = []
    for d in sorted(ROOT.iterdir()) if ROOT.exists() else []:
        try:
            m = load_meta(d.name)
            out.append({k: m.get(k) for k in ("id", "name", "folders", "updated", "indexed", "n_files", "n_chunks", "status")}
                       | {"pending_pdfs": len(m.get("pending_pdfs", []))})
        except (OSError, ValueError):
            continue
    return out


def create(name, folders):
    kid = uuid.uuid4().hex[:10]
    _dir(kid).mkdir(parents=True)
    (_dir(kid) / "files").mkdir()
    meta = {"id": kid, "name": (name or "Base").strip()[:60], "folders": [str(Path(f).resolve()) for f in folders if Path(f).is_dir()],
            "created": time.time(), "updated": time.time(), "indexed": 0, "files": {}, "n_files": 0, "n_chunks": 0,
            "pending_pdfs": [], "status": "nova"}
    save_meta(meta)
    return meta


def update(kid, name=None, folders=None):
    meta = load_meta(kid)
    if name is not None:
        meta["name"] = name.strip()[:60] or meta["name"]
    if folders is not None:
        meta["folders"] = [str(Path(f).resolve()) for f in folders if Path(f).is_dir()]
    meta["updated"] = time.time()
    save_meta(meta)
    return meta


def delete(kid):
    shutil.rmtree(_dir(kid), ignore_errors=True)
    _cache.pop(kid, None)


def inside_folders(meta, path):
    p = Path(path).resolve()
    return any(p == Path(f) or Path(f) in p.parents for f in meta["folders"])


# ---------------------------------------------------------------- texto e trechos

def read_text_file(p):
    data = p.read_bytes()
    if b"\0" in data[:4000]:
        return ""
    for enc in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def chunk_text(text):
    """Divide em trechos de ~CHUNK caracteres respeitando linhas; devolve (linha_ini, linha_fim, texto)."""
    lines = text.replace("\r\n", "\n").split("\n")
    chunks, buf, size, start = [], [], 0, 1
    for i, line in enumerate(lines, 1):
        if size + len(line) > CHUNK and buf:
            body = "\n".join(buf).strip()
            if body:
                chunks.append((start, i - 1, body))
            # sobreposicao: repete as ultimas linhas para nao cortar ideias ao meio
            keep, kept = [], 0
            for prev in reversed(buf):
                if kept + len(prev) > OVERLAP:
                    break
                keep.insert(0, prev)
                kept += len(prev)
            buf, size, start = keep, kept, i - len(keep)
        while len(line) > CHUNK:  # linha enorme (ex.: JSON minificado)
            chunks.append((i, i, line[:CHUNK]))
            line = line[CHUNK - OVERLAP:]
        buf.append(line)
        size += len(line) + 1
    body = "\n".join(buf).strip()
    if body:
        chunks.append((start, len(lines), body))
    return chunks


def _file_key(path):
    return hashlib.sha1(str(path).lower().encode()).hexdigest()[:16]


def _normalize(vec):
    v = vec[:DIM]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _pack(vectors):
    a = array.array("f")
    for v in vectors:
        a.extend(v)
    return base64.b64encode(a.tobytes()).decode("ascii")


def store_file(kid, path, mtime, size, text, embed_fn, cancel=None):
    """Divide, gera os embeddings e grava o arquivo indexado. embed_fn(lista de textos) -> lista de vetores."""
    chunks = chunk_text(text)
    vectors = []
    for i in range(0, len(chunks), 16):
        if cancel and cancel():
            raise InterruptedError
        vectors += [_normalize(v) for v in embed_fn([c[2] for c in chunks[i:i + 16]])]
    rec = {"path": str(path), "mtime": mtime, "size": size, "chunks": [{"a": a, "b": b, "t": t} for a, b, t in chunks],
           "vecs": _pack(vectors)}
    (_dir(kid) / "files" / f"{_file_key(path)}.json").write_text(json.dumps(rec, ensure_ascii=False), "utf-8")
    return len(chunks)


def scan(meta):
    """Arquivos atuais das pastas: {caminho: (mtime, tamanho, tipo)}."""
    found = {}
    for folder in meta["folders"]:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for f in files:
                p = Path(root) / f
                ext = p.suffix.lower()
                kind = "text" if ext in TEXT_EXT else "office" if ext in OFFICE_EXT else "pdf" if ext == ".pdf" else None
                if not kind:
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_size > MAX_FILE * (6 if kind != "text" else 1):
                    continue
                found[str(p)] = (st.st_mtime, st.st_size, kind)
    return found


def index(kid, task, embed_fn, office_text_fn):
    """Indexa (ou atualiza) a base. PDFs ficam pendentes: a interface extrai o texto com o pdf.js."""
    meta = load_meta(kid)
    meta["status"] = "indexando"
    save_meta(meta)
    found = scan(meta)
    known = meta.get("files", {})
    # remove arquivos que sumiram
    for path in [p for p in known if p not in found]:
        (_dir(kid) / "files" / f"{_file_key(path)}.json").unlink(missing_ok=True)
        known.pop(path, None)
    todo = [(p, v) for p, v in found.items() if p not in known or known[p]["mtime"] != v[0] or known[p]["size"] != v[1]]
    pending = [p for p, (m, s, kind) in todo if kind == "pdf"]
    todo = [t for t in todo if t[1][2] != "pdf"]
    task["total"] = len(todo)
    for n, (path, (mtime, size, kind)) in enumerate(todo, 1):
        if task.get("cancel"):
            break
        task["done"], task["detail"] = n - 1, Path(path).name
        try:
            text = read_text_file(Path(path)) if kind == "text" else office_text_fn(path)
        except Exception:  # noqa: BLE001
            text = ""
        if not text.strip():
            known[path] = {"mtime": mtime, "size": size, "chunks": 0}
            continue
        nchunks = store_file(kid, path, mtime, size, text, embed_fn, lambda: task.get("cancel"))
        known[path] = {"mtime": mtime, "size": size, "chunks": nchunks}
    task["done"] = len(todo)
    meta = load_meta(kid)
    meta["files"] = known
    meta["pending_pdfs"] = sorted(set(pending) | {p for p in meta.get("pending_pdfs", []) if p in found and p not in known})
    meta["n_files"] = sum(1 for v in known.values() if v["chunks"])
    meta["n_chunks"] = sum(v["chunks"] for v in known.values())
    meta["indexed"] = time.time()
    meta["status"] = "pronta" if not meta["pending_pdfs"] else "pdfs_pendentes"
    save_meta(meta)
    _cache.pop(kid, None)
    return meta


def add_text(kid, path, text, embed_fn):
    """Recebe o texto de um PDF (extraido na interface) e indexa."""
    meta = load_meta(kid)
    if not inside_folders(meta, path):
        raise ValueError("arquivo fora das pastas da base")
    st = Path(path).stat()
    n = store_file(kid, path, st.st_mtime, st.st_size, text, embed_fn) if text.strip() else 0
    meta = load_meta(kid)
    meta["files"][str(Path(path))] = {"mtime": st.st_mtime, "size": st.st_size, "chunks": n}
    meta["pending_pdfs"] = [p for p in meta.get("pending_pdfs", []) if p != str(Path(path))]
    meta["n_files"] = sum(1 for v in meta["files"].values() if v["chunks"])
    meta["n_chunks"] = sum(v["chunks"] for v in meta["files"].values())
    meta["status"] = "pronta" if not meta["pending_pdfs"] else "pdfs_pendentes"
    save_meta(meta)
    _cache.pop(kid, None)
    return n


# ---------------------------------------------------------------- busca

def _load_index(kid):
    with _lock:
        if kid in _cache:
            return _cache[kid]
        chunks, vecs = [], array.array("f")
        for f in (_dir(kid) / "files").glob("*.json"):
            try:
                rec = json.loads(f.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            a = array.array("f")
            a.frombytes(base64.b64decode(rec["vecs"]))
            if len(a) != len(rec["chunks"]) * DIM:
                continue
            for c in rec["chunks"]:
                chunks.append({"path": rec["path"], "a": c["a"], "b": c["b"], "t": c["t"]})
            vecs.extend(a)
        _cache[kid] = (chunks, vecs)
        return chunks, vecs


def search(kid, query, embed_fn, k=6, min_score=0.15, relative=0.6):
    chunks, vecs = _load_index(kid)
    if not chunks:
        return []
    q = _normalize(embed_fn([QUERY_PREFIX + query])[0])
    scores = []
    mul = operator.mul
    for i in range(len(chunks)):
        off = i * DIM
        scores.append((sum(map(mul, q, vecs[off:off + DIM])), i))
    scores.sort(reverse=True)
    # corte: nota minima absoluta e relativa ao melhor trecho (descarta o claramente irrelevante)
    cut = max(min_score, scores[0][0] * relative) if scores else min_score
    out, seen = [], set()
    for s, i in scores:
        if s < cut or len(out) >= k:
            break
        c = chunks[i]
        key = (c["path"], c["a"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"path": c["path"], "lines": f"{c['a']}-{c['b']}", "score": round(s, 3), "text": c["t"]})
    return out
