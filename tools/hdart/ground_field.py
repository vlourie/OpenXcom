"""ground_field.py - раскладка вариантов пола, как её делает движок (Canvas32::groundFrameFor, HdCanvas.cpp).

Порт один к одному: groundHash, groundNoise (квинтика), groundLevel (две волны 6 и 2.5 клетки, растяжка x2.4),
groundPure по 9 точкам клетки, на краях пятен - попиксельное смешение двух соседних вариантов по рваной линии
(GROUND_EDGE 0.16, GROUND_RAGGED 0.22). Шкала вариантов: основной кадр посередине, нечётные .v в одну сторону,
чётные в другую (при 4 кадрах - [v3, v1, 0, v2]). Числа - float32, как в движке.

probe_floor.ground_level - приближение со своими константами, для листов, которые обязаны показать то, что
покажет игра, не годится.

    import ground_field as gf
    rgba = gf.frame_for([base, v1, v2, v3], x, y, z, seed)     # кадры HxWx4 uint8, x4
    im = gf.field([base, v1, v2, v3], n=9, seed=..., x0=..., y0=...)   # поле n x n в изометрии

Проверка - tools/test_ground_field.py (контроль: при одном варианте кадр не меняется; шкала [v3, v1, 0, v2]).
"""
import numpy as np

F = np.float32
U = np.uint32
GROUND_WAVE = F(6.0)
GROUND_WAVE2 = F(2.5)
GROUND_EDGE = F(0.16)
GROUND_RAGGED = F(0.22)


def _rotl13(h):
    return (h << U(13)) | (h >> U(19))


def ground_hash(seed, x, y, z):
    with np.errstate(over="ignore"):
        x = np.asarray(x).astype(np.int64).astype(U)
        y = np.asarray(y).astype(np.int64).astype(U)
        h = np.full(x.shape, U(seed) ^ U(0x9E3779B9), U)
        h ^= x * U(0x85EBCA6B)
        h = _rotl13(h) * U(5) + U(0xE6546B64)
        h ^= y * U(0xC2B2AE35)
        h = _rotl13(h) * U(5) + U(0xE6546B64)
        h ^= U(z & 0xFFFFFFFF) * U(0x27D4EB2F)
        h ^= h >> U(16)
        h *= U(0x85EBCA6B)
        h ^= h >> U(13)
        h *= U(0xC2B2AE35)
        h ^= h >> U(16)
    return h


def ground_noise(seed, x, y, z):
    x = np.asarray(x, F)
    y = np.asarray(y, F)
    fx, fy = np.floor(x), np.floor(y)
    ix, iy = fx.astype(np.int64), fy.astype(np.int64)
    tx, ty = x - fx, y - fy
    tx = tx * tx * tx * (tx * (tx * F(6) - F(15)) + F(10))
    ty = ty * ty * ty * (ty * (ty * F(6) - F(15)) + F(10))

    def at(a, b):
        return (ground_hash(seed, a, b, z) & U(0xFFFFFF)).astype(F) / F(16777215.0)
    v00, v10, v01, v11 = at(ix, iy), at(ix + 1, iy), at(ix, iy + 1), at(ix + 1, iy + 1)
    a = v00 + (v10 - v00) * tx
    b = v01 + (v11 - v01) * tx
    return a + (b - a) * ty


def ground_level(seed, u, v, z, count):
    if count < 2:
        return np.zeros(np.shape(u), F)
    u, v = np.asarray(u, F), np.asarray(v, F)
    n = F(0.62) * ground_noise(seed, u / GROUND_WAVE, v / GROUND_WAVE, z) \
        + F(0.38) * ground_noise((seed + 101) & 0xFFFFFFFF, u / GROUND_WAVE2 + F(0.37), v / GROUND_WAVE2 + F(0.71), z)
    n = np.clip((n - F(0.5)) * F(2.4) + F(0.5), F(0), F(1))
    return n * F(count - 1)


def ground_ragged(seed, u, v, z):
    u, v = np.asarray(u, F), np.asarray(v, F)
    return F(0.6) * ground_noise((seed + 7) & 0xFFFFFFFF, u * F(5), v * F(5), z) \
        + F(0.4) * ground_noise((seed + 13) & 0xFFFFFFFF, u * F(13), v * F(13), z)


def battle_seed(X, Y, Z, block_cols):
    """Зерно узора боя - Map::groundSeed: FNV-1a по размеру карты и именам блоков (столбцы x, в столбце по y)."""
    h = 2166136261

    def mix(s):
        nonlocal h
        for c in s.encode("utf-8"):
            h = ((h ^ c) * 16777619) & 0xFFFFFFFF
        h = ((h ^ 0xFF) * 16777619) & 0xFFFFFFFF
    mix("%dx%dx%d" % (X, Y, Z))
    for col in block_cols:
        for name in col:
            mix(name)
    return h


def ground_pure(p, count):
    i = max(0, min(count - 2, int(np.floor(p))))
    t = float(p) - i
    reach = float(GROUND_EDGE) + float(GROUND_RAGGED) * 0.5 + 0.08
    if t <= 0.5 - reach:
        return i
    if t >= 0.5 + reach:
        return i + 1
    return -1


def scale_order(found):
    """found = [основной, v1, v2, ...] -> шкала узора: основной посередине, нечётные в одну сторону, чётные в другую."""
    count = len(found)
    mid = count // 2
    frames = [None] * count
    frames[mid] = found[0]
    for j in range(1, count):
        frames[mid - (j + 1) // 2 if j % 2 else mid + j // 2] = found[j]
    return frames


_AT = [(0.02, 0.02), (0.5, 0.02), (0.98, 0.02), (0.02, 0.5), (0.5, 0.5), (0.98, 0.5), (0.02, 0.98), (0.5, 0.98), (0.98, 0.98)]


def pick(count, x, y, z, seed):
    """Номер в шкале, если вся клетка одного варианта; -1 - клетка на краю пятна (смешение)."""
    pure = -2
    for sx, sy in _AT:
        p = ground_pure(float(ground_level(seed, F(x + sx), F(y + sy), z, count)), count)
        if p < 0 or (pure != -2 and p != pure):
            return -1
        pure = p
    return pure


def frame_for(found, x, y, z, seed, k=4):
    """Картинка кадра пола в клетке (x, y, z): found = [основной, v1, ...] как HxWx4 uint8 одного размера."""
    count = len(found)
    if count < 2:
        return found[0]
    frames = scale_order(found)
    p = pick(count, x, y, z, seed)
    if p >= 0:
        return frames[p]
    h, w = found[0].shape[:2]
    bw, bh = w // k, h // k
    by, bx = np.mgrid[0:bh, 0:bw].astype(F)
    dx = bx + F(0.5) - F(bw * 0.5)
    ext = np.maximum(F(0), F(8) - np.abs(dx) * F(0.5))
    dy = np.maximum(-ext, np.minimum(ext, by + F(0.5) - (F(bh) - F(8))))
    u = F(x) + F(0.5) + (dx / F(16) + dy / F(8)) * F(0.5)
    v = F(y) + F(0.5) + (dy / F(8) - dx / F(16)) * F(0.5)
    level = ground_level(seed, u, v, z, count)
    ragged = ground_ragged(seed, u, v, z)
    py, px = np.mgrid[0:h, 0:w].astype(F)
    fy = np.clip((py + F(0.5)) / F(k) - F(0.5), F(0), F(bh - 1))
    fx = np.clip((px + F(0.5)) / F(k) - F(0.5), F(0), F(bw - 1))
    x0 = np.minimum(bw - 2, fx.astype(int))
    y0 = np.minimum(bh - 2, fy.astype(int))
    tx, ty = fx - x0, fy - y0

    def sample(g):
        a = g[y0, x0] + (g[y0, x0 + 1] - g[y0, x0]) * tx
        b = g[y0 + 1, x0] + (g[y0 + 1, x0 + 1] - g[y0 + 1, x0]) * tx
        return a + (b - a) * ty
    pp = sample(level)
    i = np.clip(np.floor(pp).astype(int), 0, count - 2)
    t = pp - i + GROUND_RAGGED * (sample(ragged) - F(0.5))
    t = np.clip((t - (F(0.5) - GROUND_EDGE)) / (F(2) * GROUND_EDGE), F(0), F(1))
    t = t * t * (F(3) - F(2) * t)
    wb = np.floor(t * F(255) + F(0.5)).astype(np.int64)
    stack = np.stack([f.astype(np.int64) for f in frames])          # count, h, w, 4
    A = np.take_along_axis(stack, i[None, ..., None].repeat(4, -1), 0)[0]
    B = np.take_along_axis(stack, (i + 1)[None, ..., None].repeat(4, -1), 0)[0]
    fa = (255 - wb) * A[..., 3]
    fb = wb * B[..., 3]
    s = fa + fb
    out = np.zeros((h, w, 4), np.int64)
    ok = s > 0
    for c in range(3):
        out[..., c] = np.where(ok, (A[..., c] * fa + B[..., c] * fb + s // 2) // np.maximum(s, 1), 0)
    out[..., 3] = np.where(ok, (s + 127) // 255, 0)
    out = np.where((wb == 0)[..., None], A, np.where((wb == 255)[..., None], B, out))
    return out.astype(np.uint8)


def field(found, n=9, seed=1, x0=40, y0=40, z=0, k=4, bg=(40, 40, 44)):
    """Поле n x n клеток одного кадра пола с вариантами, в изометрии игры (клетка 32x16 базы, кадр 32x40)."""
    h, w = found[0].shape[:2]
    W = n * 16 * k * 2
    H = n * 8 * k * 2 + h
    canvas = np.zeros((H, W, 4), np.float32)
    canvas[..., :3] = bg
    canvas[..., 3] = 255
    picks = {}
    for yy in range(n):
        for xx in range(n):
            fr = frame_for(found, x0 + xx, y0 + yy, z, seed, k).astype(np.float32)
            picks[(xx, yy)] = pick(len(found), x0 + xx, y0 + yy, z, seed)
            sx = (xx - yy) * 16 * k + (n - 1) * 16 * k
            sy = (xx + yy) * 8 * k
            a = fr[..., 3:4] / 255.0
            canvas[sy:sy + h, sx:sx + w, :3] = canvas[sy:sy + h, sx:sx + w, :3] * (1 - a) + fr[..., :3] * a
    return canvas.clip(0, 255).astype(np.uint8), picks
