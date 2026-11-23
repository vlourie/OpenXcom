# -*- coding: utf-8 -*-
r"""XP-000351: готовые файлы вариантов пола URBAN_WASTE:80 / URBAN_WASTE_WALLS:74 (вариант S) и лист поля.
Ничего не ставит (установка - t351_install.py).
    py -3.13 tools\hdart\t351_build.py"""
import os
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEEDS = os.path.join(ROOT, "art", "_review", "tickets_2210b_strict", "floor")
OUT = os.path.join(ROOT, "art", "_review", "tickets_2026-10-28")
INST = os.path.join(OUT, "t351_install")
CUR = os.path.join(ROOT, "user", "mods", "hd", "hd", "TERRAIN")
M = 0xFFFFFFFF


def load(p):
    return np.array(Image.open(p).convert("RGBA"))


def build():
    s2 = load(os.path.join(SEEDS, "URBAN_WASTE_80_s22112.png"))
    s3 = load(os.path.join(SEEDS, "URBAN_WASTE_80_s22113.png"))
    base = load(os.path.join(CUR, "URBAN_WASTE.PCK", "80.png"))
    m = base[..., 3] > 0
    for n, a in (("s22112", s2), ("s22113", s3)):
        assert ((a[..., 3] > 0) == m).all(), n + ": маска не совпала с основой"
    res = {}
    for name, f in (("lr", lambda a: a[:, ::-1]), ("ud", lambda a: a[::-1]), ("rot", lambda a: a[::-1, ::-1])):
        res[name] = int((f(m[..., None])[..., 0] != m).sum())
    print("несовпадение маски у зеркал (пикселей):", res)
    v3 = np.ascontiguousarray(s2[:, ::-1])       # зеркало по вертикальной оси ромба
    assert ((v3[..., 3] > 0) == m).all()
    v3[~m] = 0
    return base, [s2, s3, v3]


def save(vs):
    for sub, n in (("URBAN_WASTE.PCK", 80), ("URBAN_WASTE_WALLS.PCK", 74)):
        d = os.path.join(INST, "TERRAIN", sub)
        os.makedirs(d, exist_ok=True)
        for i, v in enumerate(vs, 1):
            Image.fromarray(v, "RGBA").save(os.path.join(d, "%d.v%d.png" % (n, i)), optimize=True)


# ---- повтор Canvas32::groundFrameFor / makeGround (HdCanvas.cpp 2210-2520) ----
def h32(seed, x, y, z):
    h = (seed ^ 0x9E3779B9) & M
    h ^= (x * 0x85EBCA6B) & M
    h = ((((h << 13) | (h >> 19)) & M) * 5 + 0xE6546B64) & M
    h ^= (y * 0xC2B2AE35) & M
    h = ((((h << 13) | (h >> 19)) & M) * 5 + 0xE6546B64) & M
    h ^= (z * 0x27D4EB2F) & M
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & M
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & M
    h ^= h >> 16
    return h


_cache = {}


def lat(seed, a, b, z):
    k = (seed, a, b, z)
    if k not in _cache:
        _cache[k] = (h32(seed, a, b, z) & 0xFFFFFF) / 16777215.0
    return _cache[k]


def noise(seed, x, y, z):
    ix, iy = int(np.floor(x)), int(np.floor(y))
    tx, ty = x - ix, y - iy
    f = lambda t: t * t * t * (t * (t * 6 - 15) + 10)
    tx, ty = f(tx), f(ty)
    v00, v10, v01, v11 = lat(seed, ix, iy, z), lat(seed, ix + 1, iy, z), lat(seed, ix, iy + 1, z), lat(seed, ix + 1, iy + 1, z)
    a = v00 + (v10 - v00) * tx
    b = v01 + (v11 - v01) * tx
    return a + (b - a) * ty


EDGE, RAG = 0.16, 0.22


def level(seed, u, v, z, count):
    n = 0.62 * noise(seed, u / 6.0, v / 6.0, z) + 0.38 * noise((seed + 101) & M, u / 2.5 + 0.37, v / 2.5 + 0.71, z)
    n = max(0.0, min(1.0, (n - 0.5) * 2.4 + 0.5))
    return n * (count - 1)


def ragged(seed, u, v, z):
    return 0.6 * noise((seed + 7) & M, u * 5, v * 5, z) + 0.4 * noise((seed + 13) & M, u * 13, v * 13, z)


def blend_cell(frames, x, y, z, seed, k=4):
    """frames - уже в порядке шкалы [v3, v1, основа, v2]. Возвращает RGBA h x w."""
    h, w = frames[0].shape[:2]
    bw, bh = w // k, h // k
    lv = np.zeros((bh, bw))
    rg = np.zeros((bh, bw))
    count = len(frames)
    for by in range(bh):
        for bx in range(bw):
            dx = bx + 0.5 - bw * 0.5
            ext = max(0.0, 8.0 - abs(dx) * 0.5)
            dy = max(-ext, min(ext, by + 0.5 - (bh - 8.0)))
            u = x + 0.5 + (dx / 16 + dy / 8) * 0.5
            v = y + 0.5 + (dy / 8 - dx / 16) * 0.5
            lv[by, bx] = level(seed, u, v, z, count)
            rg[by, bx] = ragged(seed, u, v, z)

    def samp(g):
        ys = np.clip((np.arange(h) + 0.5) / k - 0.5, 0, bh - 1)
        xs = np.clip((np.arange(w) + 0.5) / k - 0.5, 0, bw - 1)
        y0 = np.minimum(bh - 2, ys.astype(int))
        x0 = np.minimum(bw - 2, xs.astype(int))
        ty = (ys - y0)[:, None]
        tx = (xs - x0)[None, :]
        Y0, X0 = y0[:, None], x0[None, :]
        a = g[Y0, X0] + (g[Y0, X0 + 1] - g[Y0, X0]) * tx
        b = g[Y0 + 1, X0] + (g[Y0 + 1, X0 + 1] - g[Y0 + 1, X0]) * tx
        return a + (b - a) * ty

    p = samp(lv)
    r = samp(rg)
    i = np.clip(np.floor(p).astype(int), 0, count - 2)
    t = p - i + RAG * (r - 0.5)
    t = np.clip((t - (0.5 - EDGE)) / (2 * EDGE), 0, 1)
    t = t * t * (3 - 2 * t)
    st = np.stack(frames).astype(np.float64)
    yy, xx = np.mgrid[0:h, 0:w]
    A = st[i, yy, xx]
    B = st[i + 1, yy, xx]
    fa = (1 - t)[..., None] * A[..., 3:4]
    fb = t[..., None] * B[..., 3:4]
    s = fa + fb
    rgb = np.where(s > 0, (A[..., :3] * fa + B[..., :3] * fb) / np.maximum(s, 1e-9), 0)
    out = np.concatenate([rgb, s], -1)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def field(base, vs, seed, n=8, k=4, z=0):
    """vs - [v1, v2, v3]; порядок шкалы при 4 кадрах: [v3, v1, основа, v2]."""
    frames = [vs[2], vs[0], base, vs[1]]
    h, w = base.shape[:2]
    W = (2 * n) * 16 * k + w
    H = (2 * n) * 8 * k + h
    canvas = np.zeros((H, W, 4), np.uint8)
    for s in range(2 * n - 1):                       # x+y по возрастанию - дальние раньше
        for x in range(n):
            y = s - x
            if not 0 <= y < n:
                continue
            cell = blend_cell(frames, x, y, z, seed, k)
            ox = (x - y) * 16 * k + (n - 1) * 16 * k
            oy = (x + y) * 8 * k
            reg = canvas[oy:oy + h, ox:ox + w]
            a = cell[..., 3:4].astype(np.float64) / 255
            mixed = np.concatenate([cell[..., :3] * a + reg[..., :3] * (1 - a), np.maximum(reg[..., 3:4], cell[..., 3:4])], -1)
            reg[...] = np.where(a > 0, mixed.astype(np.uint8), reg)
    return canvas


def onbg(c):
    bg = np.full(c.shape[:2] + (3,), 40, np.uint8)
    a = c[..., 3:4] / 255.0
    return (c[..., :3] * a + bg * (1 - a)).astype(np.uint8)


def sheet(base, vs):
    cur = [load(os.path.join(CUR, "URBAN_WASTE.PCK", "80.v%d.png" % i)) for i in (1, 2, 3)]
    rows = []
    for seed in (1, 77):
        rows.append(onbg(field(base, cur, seed)))      # до
        rows.append(onbg(field(base, vs, seed)))       # после
    w = rows[0].shape[1]
    h = rows[0].shape[0]
    img = Image.new("RGB", (w * 2 + 10, h * 2 + 10), (20, 20, 20))
    for j, a in enumerate(rows):                       # слева до, справа после; сверху seed 1, снизу seed 77
        img.paste(Image.fromarray(a), ((j % 2) * (w + 10), (j // 2) * (h + 10)))
    img.save(os.path.join(OUT, "t351_field.png"))
    img.resize((img.width // 2, img.height // 2), Image.LANCZOS).save(os.path.join(OUT, "t351_field_half.png"))


if __name__ == "__main__":
    base, vs = build()
    save(vs)
    sheet(base, vs)
    print("готово")
