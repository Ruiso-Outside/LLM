"""Pesquisa na web para o LLM Local (so biblioteca padrao).

Provedores:
- duckduckgo: gratis, sem chave (padrao)
- google: API oficial "Programmable Search" (precisa de chave + ID do mecanismo)
- searxng: sua propria instancia SearXNG (com formato JSON habilitado)
"""
import html
import ipaddress
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/141.0 Safari/537.36")


def _get(url, data=None, timeout=10, accept="text/html,application/xhtml+xml,*/*;q=0.8"):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": BROWSER_UA, "Accept": accept, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        raw = r.read(3_000_000)
        charset = r.headers.get_content_charset() or "utf-8"
        return ctype, raw.decode(charset, "replace")


def _clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


# ---------------------------------------------------------------- provedores

def _ddg_url(href):
    if href.startswith("//"):
        href = "https:" + href
    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    return q["uddg"][0] if "uddg" in q else href


def search_duckduckgo(query, region="br-pt", n=5):
    body = urllib.parse.urlencode({"q": query, "kl": region}).encode()
    _, page = _get("https://html.duckduckgo.com/html/", data=body)
    results = []
    for chunk in page.split('class="result__title"')[1:]:
        a = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', chunk, re.S)
        if not a or "duckduckgo.com/y.js" in a.group(1):  # anuncio
            continue
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', chunk, re.S)
        results.append({"title": _clean(a.group(2)), "url": _ddg_url(html.unescape(a.group(1))),
                        "snippet": _clean(snip.group(1)) if snip else ""})
    if not results:
        # versao "lite" como reserva
        _, page = _get("https://lite.duckduckgo.com/lite/", data=body)
        links = re.findall(r"<a([^>]*class=['\"]result-link['\"][^>]*)>(.*?)</a>", page, re.S)
        snips = re.findall(r"class=['\"]result-snippet['\"][^>]*>(.*?)</td>", page, re.S)
        for i, (attrs, title) in enumerate(links):
            href = re.search(r"href=['\"]([^'\"]+)['\"]", attrs)
            if href and "duckduckgo.com/y.js" not in href.group(1):
                results.append({"title": _clean(title), "url": _ddg_url(html.unescape(href.group(1))),
                                "snippet": _clean(snips[i]) if i < len(snips) else ""})
    if not results and ("anomaly" in page or "captcha" in page.lower()):
        raise RuntimeError("O DuckDuckGo bloqueou temporariamente as buscas. Espere alguns minutos "
                           "ou configure outro provedor.")
    return results[:n]


def search_google(query, api_key, cx, n=5):
    if not api_key or not cx:
        raise RuntimeError("Para usar o Google, preencha a chave da API e o ID do mecanismo nas Configuracoes.")
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(
        {"key": api_key, "cx": cx, "q": query, "num": min(n, 10), "hl": "pt-BR"})
    try:
        _, txt = _get(url, accept="application/json")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8"))["error"]["message"]
        except Exception:  # noqa: BLE001
            msg = e.reason
        raise RuntimeError(f"Google API: {msg}") from None
    data = json.loads(txt)
    return [{"title": it.get("title", ""), "url": it.get("link", ""), "snippet": it.get("snippet", "")}
            for it in data.get("items", [])][:n]


def search_searxng(query, base_url, n=5):
    if not base_url:
        raise RuntimeError("Preencha o endereco da sua instancia SearXNG nas Configuracoes.")
    url = base_url.rstrip("/") + "/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
    _, txt = _get(url, accept="application/json")
    data = json.loads(txt)
    return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in data.get("results", [])][:n]


def search(query, settings):
    n = max(1, min(int(settings.get("search_results") or 4), 8))
    provider = settings.get("search_provider", "duckduckgo")
    if provider == "google":
        return search_google(query, settings.get("google_api_key", ""), settings.get("google_cx", ""), n)
    if provider == "searxng":
        return search_searxng(query, settings.get("searxng_url", ""), n)
    return search_duckduckgo(query, settings.get("search_region", "br-pt"), n)


# ---------------------------------------------------------------- leitura das paginas

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "iframe", "button", "select"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _is_public(url):
    try:
        u = urllib.parse.urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname or u.hostname == "localhost":
            return False
        try:
            return ipaddress.ip_address(u.hostname).is_global
        except ValueError:
            return True  # nome de dominio
    except ValueError:
        return False


def page_text(url, max_chars):
    if not _is_public(url):
        return ""
    ctype, body = _get(url, timeout=8)
    if "html" not in ctype and "text/plain" not in ctype:
        return ""
    if "html" in ctype:
        p = _TextExtractor()
        p.feed(body)
        body = "".join(p.parts)
    lines = [re.sub(r"\s+", " ", l).strip() for l in body.splitlines()]
    text = "\n".join(l for l in lines if len(l) >= 30)  # descarta menus e rodapes curtos
    return text[:max_chars]


def fetch_pages(results, max_chars_each):
    texts = [""] * len(results)
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(page_text, r["url"], max_chars_each): i for i, r in enumerate(results)}
        try:
            for f in as_completed(futs, timeout=15):
                try:
                    texts[futs[f]] = f.result()
                except Exception:  # noqa: BLE001
                    pass
        except TimeoutError:
            pass
    return texts
