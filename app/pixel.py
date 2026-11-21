"""Pixel art da Arasaka Mikoshi: transforma uma imagem gerada (ou enviada) em sprite de verdade.

Sem dependencias externas (so a biblioteca padrao): le e grava PNG, tira o fundo, recorta o personagem,
reduz para 16/32/64/128 px escolhendo a cor dominante de cada bloco (sem borrar), reduz a paleta (corte
mediano, a mesma paleta para todos os quadros de uma folha), contorno opcional e monta folhas de sprites.

As imagens ficam como Img(w, h, px), px = bytearray RGBA (4 bytes por pixel).
"""
import struct
import zlib
from collections import Counter, deque

SIZES = (16, 24, 32, 48, 64, 96, 128)
PNG_SIG = b"\x89PNG\r\n\x1a\n"


class Img:
    __slots__ = ("w", "h", "px")

    def __init__(self, w, h, px=None):
        self.w, self.h = int(w), int(h)
        self.px = px if px is not None else bytearray(self.w * self.h * 4)

    def get(self, x, y):
        i = (y * self.w + x) * 4
        return tuple(self.px[i:i + 4])

    def put(self, x, y, c):
        i = (y * self.w + x) * 4
        self.px[i:i + 4] = bytes(c)


# ---------------------------------------------------------------- PNG

def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode_png(data):
    """PNG de 8 bits (cinza, RGB, paleta, cinza+alfa, RGBA; 16 bits vira 8), sem entrelacamento -> Img RGBA."""
    if not data.startswith(PNG_SIG):
        raise ValueError("não é um PNG")
    pos, idat, plte, trns = 8, [], None, None
    w = h = depth = ctype = interlace = None
    while pos + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if w is None or not idat:
        raise ValueError("PNG incompleto")
    if interlace:
        raise ValueError("PNG entrelaçado não é suportado")
    if depth not in (8, 16) and not (ctype == 3 and depth in (1, 2, 4)):
        raise ValueError(f"PNG com {depth} bits não é suportado")
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp_bits = chans * depth
    stride = (w * bpp_bits + 7) // 8
    bpp = max(1, bpp_bits // 8)
    raw = zlib.decompress(b"".join(idat))
    out = bytearray(stride * h)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif f == 2:
            line = bytearray((a + b) & 255 for a, b in zip(line, prev))
        elif f == 3:
            for i in range(stride):
                line[i] = (line[i] + ((line[i - bpp] if i >= bpp else 0) + prev[i]) // 2) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                c = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(a, prev[i], c)) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    img = Img(w, h)
    px = img.px
    if depth == 16:  # fica com o byte alto de cada amostra
        out = out[0::2]
        stride //= 2
    if ctype == 6 and depth in (8, 16):
        px[:] = out
        return img
    if ctype == 3:
        alpha = trns or b""
        bits = depth
        for y in range(h):
            row = out[y * stride:(y + 1) * stride]
            for x in range(w):
                if bits == 8:
                    k = row[x]
                else:
                    per = 8 // bits
                    k = (row[x // per] >> (8 - bits * (x % per + 1))) & ((1 << bits) - 1)
                i = (y * w + x) * 4
                px[i:i + 3] = plte[k * 3:k * 3 + 3]
                px[i + 3] = alpha[k] if k < len(alpha) else 255
        return img
    for i in range(w * h):
        if ctype == 2:
            px[i * 4:i * 4 + 3] = out[i * 3:i * 3 + 3]
            px[i * 4 + 3] = 255
        elif ctype == 0:
            v = out[i]
            px[i * 4:i * 4 + 4] = bytes((v, v, v, 255))
        elif ctype == 4:
            v = out[i * 2]
            px[i * 4:i * 4 + 4] = bytes((v, v, v, out[i * 2 + 1]))
    return img


def encode_png(img):
    raw = bytearray()
    row = img.w * 4
    for y in range(img.h):
        raw.append(0)
        raw += img.px[y * row:(y + 1) * row]

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", img.w, img.h, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


# ---------------------------------------------------------------- operacoes

def box_down(img, factor):
    """Reduz pela media de blocos factor x factor (so para preparar; o tamanho final usa dominant_resize)."""
    if factor <= 1:
        return img
    w, h = img.w // factor, img.h // factor
    out = Img(w, h)
    src, dst, sw = img.px, out.px, img.w
    n = factor * factor
    for y in range(h):
        for x in range(w):
            r = g = b = a = 0
            for yy in range(y * factor, y * factor + factor):
                i = (yy * sw + x * factor) * 4
                for _ in range(factor):
                    r += src[i]; g += src[i + 1]; b += src[i + 2]; a += src[i + 3]
                    i += 4
            j = (y * w + x) * 4
            dst[j] = r // n; dst[j + 1] = g // n; dst[j + 2] = b // n; dst[j + 3] = a // n
    return out


def _dist2(c, d):
    return (c[0] - d[0]) ** 2 + (c[1] - d[1]) ** 2 + (c[2] - d[2]) ** 2


def background_color(img):
    """A cor mais comum na borda da imagem (agrupada de 16 em 16 para ignorar ruido)."""
    cnt, sums = Counter(), {}
    for x in range(img.w):
        for y in (0, img.h - 1):
            c = img.get(x, y)
            k = (c[0] >> 4, c[1] >> 4, c[2] >> 4)
            cnt[k] += 1
            s = sums.setdefault(k, [0, 0, 0])
            s[0] += c[0]; s[1] += c[1]; s[2] += c[2]
    for y in range(img.h):
        for x in (0, img.w - 1):
            c = img.get(x, y)
            k = (c[0] >> 4, c[1] >> 4, c[2] >> 4)
            cnt[k] += 1
            s = sums.setdefault(k, [0, 0, 0])
            s[0] += c[0]; s[1] += c[1]; s[2] += c[2]
    k, n = cnt.most_common(1)[0]
    return tuple(v // n for v in sums[k])


def remove_background(img, tolerance=40):
    """Apaga (alfa 0) o fundo ligado as bordas: flood fill a partir da borda com a cor do fundo."""
    out = Img(img.w, img.h, bytearray(img.px))
    w, h, px = out.w, out.h, out.px
    bg = background_color(img)
    tol2 = tolerance * tolerance * 3
    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        q.append((x, 0)); q.append((x, h - 1))
    for y in range(h):
        q.append((0, y)); q.append((w - 1, y))
    while q:
        x, y = q.popleft()
        k = y * w + x
        if seen[k]:
            continue
        seen[k] = 1
        i = k * 4
        if px[i + 3] >= 128 and _dist2((px[i], px[i + 1], px[i + 2]), bg) > tol2:
            continue
        px[i + 3] = 0
        if x > 0: q.append((x - 1, y))
        if x < w - 1: q.append((x + 1, y))
        if y > 0: q.append((x, y - 1))
        if y < h - 1: q.append((x, y + 1))
    # franja: pixels da borda do desenho que ainda puxam para a cor do fundo (mistura do antisserrilhado)
    loose = tol2 * 4
    fringe = []
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 4
            if px[i + 3] < 128 or _dist2((px[i], px[i + 1], px[i + 2]), bg) > loose:
                continue
            if any(0 <= x + dx < w and 0 <= y + dy < h and px[((y + dy) * w + x + dx) * 4 + 3] == 0
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                fringe.append(i)
    for i in fringe:
        px[i + 3] = 0
    return out


def bbox(img, min_alpha=128):
    xs, ys = [], []
    for y in range(img.h):
        for x in range(img.w):
            if img.px[(y * img.w + x) * 4 + 3] >= min_alpha:
                xs.append(x); ys.append(y)
    if not xs:
        return 0, 0, img.w, img.h
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def crop(img, box):
    x0, y0, x1, y1 = box
    out = Img(x1 - x0, y1 - y0)
    for y in range(y0, y1):
        out.px[(y - y0) * out.w * 4:(y - y0 + 1) * out.w * 4] = img.px[(y * img.w + x0) * 4:(y * img.w + x1) * 4]
    return out


def dominant_resize(img, w, h):
    """Reduz escolhendo a cor dominante (moda) de cada bloco: bordas nitidas, sem cores misturadas.
    Um bloco com mais da metade transparente vira transparente."""
    out = Img(w, h)
    sx, sy = img.w / w, img.h / h
    src = img.px
    for y in range(h):
        y0, y1 = int(y * sy), max(int(y * sy) + 1, int((y + 1) * sy))
        for x in range(w):
            x0, x1 = int(x * sx), max(int(x * sx) + 1, int((x + 1) * sx))
            cnt, clear, total = Counter(), 0, 0
            for yy in range(y0, min(y1, img.h)):
                for xx in range(x0, min(x1, img.w)):
                    i = (yy * img.w + xx) * 4
                    total += 1
                    if src[i + 3] < 128:
                        clear += 1
                    else:
                        cnt[(src[i] >> 3, src[i + 1] >> 3, src[i + 2] >> 3)] += 1
            j = (y * w + x) * 4
            if not cnt or clear * 2 > total:
                continue
            k = cnt.most_common(1)[0][0]
            # media das cores daquele grupo (mais fiel que o centro do grupo)
            r = g = b = n = 0
            for yy in range(y0, min(y1, img.h)):
                for xx in range(x0, min(x1, img.w)):
                    i = (yy * img.w + xx) * 4
                    if src[i + 3] >= 128 and (src[i] >> 3, src[i + 1] >> 3, src[i + 2] >> 3) == k:
                        r += src[i]; g += src[i + 1]; b += src[i + 2]; n += 1
            out.px[j:j + 4] = bytes((r // n, g // n, b // n, 255))
    return out


def fit(img, size, margin=1):
    """Recorta o desenho (sem as bordas transparentes) e o encaixa centrado num quadro size x size."""
    sub = crop(img, bbox(img))
    room = max(1, size - 2 * margin)
    scale = room / max(sub.w, sub.h)
    w, h = max(1, round(sub.w * scale)), max(1, round(sub.h * scale))
    small = dominant_resize(sub, w, h)
    out = Img(size, size)
    ox, oy = (size - w) // 2, size - margin - h  # encostado embaixo: os pes ficam na base do quadro
    for y in range(h):
        out.px[((oy + y) * size + ox) * 4:((oy + y) * size + ox + w) * 4] = small.px[y * w * 4:(y + 1) * w * 4]
    return out


def _median_cut(counts, n):
    """counts: {cor: quantidade}. Divide pelas cores distintas (nao pelos pixels), para detalhes pequenos e de cor
    diferente (olhos, boca, brilho) ganharem a propria cor; a cor final de cada caixa e a media pesada."""
    boxes = [list(counts)]
    span = lambda b, i: max(c[i] for c in b) - min(c[i] for c in b)
    while len(boxes) < n:
        boxes.sort(key=lambda b: max(span(b, i) for i in range(3)) if len(b) > 1 else -1)
        b = boxes.pop()
        if len(b) < 2:
            boxes.append(b)
            break
        ch = max(range(3), key=lambda i: span(b, i))
        b.sort(key=lambda c: c[ch])
        mid = len(b) // 2
        boxes += [b[:mid], b[mid:]]
    pal = []
    for b in boxes:
        tot = sum(counts[c] for c in b)
        if tot:
            pal.append(tuple(sum(c[i] * counts[c] for c in b) // tot for i in range(3)))
    return pal


def palette_of(imgs, colors=16):
    """Paleta comum (corte mediano) dos pixels opacos de todas as imagens."""
    counts = Counter()
    for img in imgs:
        p = img.px
        counts.update((p[i], p[i + 1], p[i + 2]) for i in range(0, len(p), 4) if p[i + 3] >= 128)
    if not counts:
        return [(0, 0, 0)]
    if len(counts) <= colors:
        return sorted(counts)
    # junta tons quase iguais (ruido do modelo) antes de cortar
    merged = Counter()
    for c, n in counts.items():
        merged[(c[0] & ~7, c[1] & ~7, c[2] & ~7)] += n
    return _median_cut(merged, max(2, colors))


def apply_palette(img, pal):
    out = Img(img.w, img.h, bytearray(img.px))
    p = out.px
    cache = {}
    for i in range(0, len(p), 4):
        if p[i + 3] < 128:
            p[i:i + 4] = b"\0\0\0\0"
            continue
        c = (p[i], p[i + 1], p[i + 2])
        best = cache.get(c)
        if best is None:
            best = cache[c] = min(pal, key=lambda q: _dist2(c, q))
        p[i:i + 4] = bytes((*best, 255))
    return out


def outline(img, color=(20, 12, 28)):
    """Contorno de 1 px por fora do desenho (nos pixels transparentes vizinhos)."""
    out = Img(img.w, img.h, bytearray(img.px))
    w, h, src = img.w, img.h, img.px
    for y in range(h):
        for x in range(w):
            if src[(y * w + x) * 4 + 3] >= 128:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h and src[(yy * w + xx) * 4 + 3] >= 128:
                    out.put(x, y, (*color, 255))
                    break
    return out


def upscale(img, k):
    """Aumenta sem suavizar (vizinho mais proximo): para ver ou exportar o sprite grande."""
    out = Img(img.w * k, img.h * k)
    for y in range(img.h):
        row = bytearray()
        for x in range(img.w):
            row += img.px[(y * img.w + x) * 4:(y * img.w + x) * 4 + 4] * k
        for j in range(k):
            out.px[((y * k + j) * out.w) * 4:((y * k + j + 1) * out.w) * 4] = row
    return out


def sheet(frames, cols=0):
    """Junta quadros do mesmo tamanho numa folha (cols por linha; 0 = todos numa linha)."""
    if not frames:
        raise ValueError("nenhum quadro")
    fw, fh = frames[0].w, frames[0].h
    cols = cols or len(frames)
    rows = (len(frames) + cols - 1) // cols
    out = Img(fw * cols, fh * rows)
    for n, f in enumerate(frames):
        ox, oy = (n % cols) * fw, (n // cols) * fh
        for y in range(min(fh, f.h)):
            out.px[((oy + y) * out.w + ox) * 4:((oy + y) * out.w + ox + min(fw, f.w)) * 4] = f.px[y * f.w * 4:(y * f.w + min(fw, f.w)) * 4]
    return out


# ---------------------------------------------------------------- caminho completo

def prepare(img, work=256):
    """Leva uma imagem grande (1024 px do modelo) para ~work px pela media, para o resto ser rapido."""
    f = max(1, min(img.w, img.h) // work)
    return box_down(img, f)


def to_sprite(img, size=32, remove_bg=True, tolerance=40, margin=1):
    if size not in SIZES:
        raise ValueError(f"tamanho {size}: use {', '.join(map(str, SIZES))}")
    base = prepare(img, max(128, size * 4))
    if remove_bg:
        base = remove_background(base, tolerance)
    return fit(base, size, margin)


def pixelate(frames, size=32, colors=16, remove_bg=True, add_outline=False, tolerance=40, cols=0):
    """Imagens (Img) -> (lista de sprites, folha, paleta). A paleta e a mesma para todos os quadros."""
    colors = max(2, min(64, int(colors)))
    sprites = [to_sprite(f, size, remove_bg, tolerance) for f in frames]
    pal = palette_of(sprites, colors - (1 if add_outline else 0))
    sprites = [apply_palette(s, pal) for s in sprites]
    if add_outline:
        sprites = [outline(s) for s in sprites]
        pal = pal + [(20, 12, 28)]
    return sprites, sheet(sprites, cols), pal
