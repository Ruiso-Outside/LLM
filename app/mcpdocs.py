"""Documentacao de um servidor MCP no prompt do Codex, sem depender de o modelo ir buscar.

Um modelo local pequeno quase nunca para para ler a documentacao antes de agir: ele chuta a API. Para os servidores
que publicam a documentacao como recurso MCP (o Arasaka Construct: demonic://readme), a Mikoshi le esse recurso uma
vez, divide pelos titulos e, a cada pedido, poe no prompt so os trechos que tem a ver com o pedido (busca por palavras,
com peso maior para palavras raras e para o titulo). Sem bibliotecas: funciona no Python do sistema.
"""
import math
import re
import unicodedata
from collections import Counter

# servidor -> recurso com a documentacao inteira em Markdown
DOC_RESOURCES = {"construct": "demonic://readme"}
# paginas que nao ensinam a fazer jogos (instalar, manter a engine, o que foi testado)
SKIP_PAGES = ("instalar e atualizar", "compilar e publicar", "o que foi testado", "criar jogos com ia", "desempenho")
STOP = set("""a o e de da do das dos em no na nos nas um uma uns umas para por com sem que se ao aos as os ou mas
mais menos como quando onde qual quais seu sua seus suas ele ela eles elas isso isto esse essa este esta ja nao sim
the and of to in for on is are be faca fazer faz crie criar cria ponha por coloque colocar adicione adicionar quero
preciso projeto aberto arasaka construct jogo cena main dele dela pelo pela pelos pelas tem ter ser esta estao vai
""".split())
_CACHE = {}  # (servidor, versao) -> lista de trechos
# o pedido usa as palavras de quem joga; a documentacao, as da engine. Sinonimos de jogo (sem acento):
SYNONYMS = {
    "vida": "maxhp hp dano character personagem", "dano": "vida maxhp defense character", "morrer": "vida maxhp",
    "inimigo": "npc inimigos", "monstro": "npc inimigo", "patrulha": "route rota npc wander", "andar": "movement walkspeed",
    "tiro": "spawn pool projetil tiros", "atirar": "spawn pool projetil tiros", "bala": "spawn pool tiros",
    "fase": "cena scenes trocar door porta", "nivel": "cena scenes trocar", "level": "cena scenes",
    "trocar": "scenes go", "moeda": "prefab original moedas", "copia": "prefab original",
    "texto": "text interface hud", "hud": "interface text placar", "placar": "interface text", "interface": "hud text",
    "pular": "jump jumppower platformer", "pulo": "jump jumppower", "gravidade": "gravity platformer",
    "encostar": "overlaps arcade colisao", "tocar": "overlaps", "colisao": "overlaps solid arcade", "bater": "overlaps solid",
    "parede": "solid solids arcade", "tecla": "input bind pressed", "apertar": "input pressed bind", "botao": "input bind",
    "som": "audio play", "musica": "music audio stream", "camera": "follow shake", "animacao": "anim sprite animation",
    "salvar": "datastore storage save", "menu": "interface scenes", "porta": "door scene",
}


def fold(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def terms(text):
    """Palavras de busca: sem acento, sem palavras vazias, cortadas em 6 letras (inimigo/inimigos, moeda/moedas...)."""
    out = []
    for w in re.findall(r"[a-z0-9_]{3,}", fold(text)):
        if w in STOP:
            continue
        out.append(w[:6])
    return out


def query_terms(text):
    """As palavras do pedido mais os sinonimos de jogo (peso menor)."""
    base = terms(text)
    words = re.findall(r"[a-z0-9_]{3,}", fold(text))
    extra = []
    for w in words:
        for key, syn in SYNONYMS.items():
            # mesma palavra, ou mesmo radical para as maiores (salvar/salve, inimigo/inimigos), sem "som" casar com "sombra"
            if w == key or (len(key) >= 5 and len(w) >= 4 and w[:4] == key[:4]):
                extra += terms(syn)
    q = {t: 1.0 for t in base}
    for t in extra:
        q.setdefault(t, 0.6)
    return q


def split_sections(md, max_len=2200):
    """Divide o Markdown pelos titulos (## e ###). Cada trecho leva o titulo da pagina e o proprio."""
    chunks, page, cur_title, cur = [], "", "", []

    def flush():
        body = "\n".join(cur).strip()
        has_text = any(l.strip() and not l.lstrip().startswith("#") for l in cur)  # so o titulo: nada a ensinar
        if body and has_text and not any(p in fold(page) for p in SKIP_PAGES):
            head = f"{page} > {cur_title}" if cur_title and cur_title != page else page
            for i in range(0, len(body), max_len):  # trecho grande: em pedacos com o mesmo titulo
                chunks.append({"title": head, "text": body[i:i + max_len]})
    for line in md.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            flush()
            cur = [line]
            if len(m.group(1)) == 1:
                page, cur_title = m.group(2).strip(), ""
            else:
                cur_title = m.group(2).strip()
            continue
        cur.append(line)
    flush()
    for c in chunks:
        c["terms"] = Counter(terms(c["text"]))
        c["head_terms"] = set(terms(c["title"]))
    return chunks


def retrieve(chunks, query, budget=6000, top=4):
    """Os trechos mais ligados ao pedido (BM25 + titulo), ate `budget` caracteres. Vazio se nada tiver a ver."""
    q = query_terms(query)
    if not q or not chunks:
        return []
    n = len(chunks)
    df = Counter(t for c in chunks for t in set(c["terms"]))
    avg = sum(sum(c["terms"].values()) for c in chunks) / n
    k1, b = 1.4, 0.75
    scored = []
    for c in chunks:
        dl = sum(c["terms"].values()) or 1
        s = 0.0
        for t, wq in q.items():
            f = c["terms"].get(t, 0)
            if not f and t not in c["head_terms"]:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += wq * idf * (f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avg)) + (1.5 if t in c["head_terms"] else 0))
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    out, used = [], 0
    for s, c in scored[:top * 2]:
        if len(out) >= top or used + len(c["text"]) > budget:
            continue
        out.append(c)
        used += len(c["text"])
    return out


def docs_for(srv, ping=None):
    """Os trechos da documentacao de um servidor (lidos uma vez por versao). [] se ele nao publica documentacao."""
    uri = DOC_RESOURCES.get(srv.cfg.get("id"))
    if not uri:
        return []
    key = (srv.cfg["id"], (srv.info or {}).get("version", ""))
    if key not in _CACHE:
        try:
            res = srv.read_resource(uri, ping=ping)
            md = "\n".join(c.get("text", "") for c in res.get("contents") or [])
        except Exception:  # noqa: BLE001  (servidor antigo sem o recurso: segue sem)
            md = ""
        _CACHE[key] = split_sections(md) if md else []
    return _CACHE[key]


def prompt_block(servers, query, ping=None, budget=6000):
    """Bloco para o prompt do sistema com os trechos relevantes de cada servidor (ou "")."""
    parts = []
    for srv in servers:
        found = retrieve(docs_for(srv, ping), query, budget=budget)
        if found:
            parts.append(f"Trechos da documentacao de {srv.cfg['name']} ligados a este pedido (use estas funcoes e campos, "
                         "nao invente outros):\n" + "\n\n".join(f"### {c['title']}\n{c['text']}" for c in found))
    return ("\n\n" + "\n\n".join(parts)) if parts else ""
