"""HD-кадры пола виртуальной базы U_BASE_VR, построенные по геометрии классики (R-042, R-298).

У кадров 64-67 нет HD в паке: на картах VR это около 38 тысяч клеток классики. Кадры - векторная графика:
тёмная заливка 126, линия по двум ВЕРХНИМ рёбрам ромба (нижние рисует сосед, который ложится позже),
у 67 ещё перекрестие с рамкой и засечками. Кадр 63 - куб (20 тысяч клеток): верх - ромб пола, поднятый
на 24 пикселя, линии по нижним рёбрам верха, трём вертикалям и нижним рёбрам низа, как в классике. Кадр 58 - статический шум трёх цветов: пятна классики,
сглаженные по классам, без лесенки.

Альфа - точный ромб с перехлёстом OVERLAP (R-291). Линия ребра стоит в полосе [-OVERLAP, W - OVERLAP]
меры до ребра: у соседа под нами та же полоса, общая толщина линии - один пиксель базы по вертикали (W).
Цвет считается по 4x4 отсчётам на пиксель x4, альфа - по центру пикселя.

    py -3.13 tools/hdart/vr_floor.py --out art/ground/vr-v1/TERRAIN [--frames 58,64,65,66,67]
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402
import ground_seam as gs          # noqa: E402

SET = "U_BASE_VR"
K = 4
SS = 4                     # отсчётов на пиксель x4 по каждой оси
OVERLAP = 0.04             # как ridge_roof.OVERLAP
W = 0.125                  # толщина линии ребра в мере ромба: один пиксель базы по вертикали
FILL = 126
EDGE = {64: 163, 65: 65, 66: 67, 67: 227}
MOTIF = 227
NOISE_SIG = 0.4            # зерно шума 58, пикселей базы


def samples():
    """Координаты отсчётов в пикселях базы: (160*SS, 128*SS)."""
    y, x = np.mgrid[0:40 * K * SS, 0:32 * K * SS].astype(np.float32)
    return (x + 0.5) / (K * SS), (y + 0.5) / (K * SS)


def edge_line(x, y):
    """Полоса линии по верхним рёбрам ромба (центр 16, 32.5, полуоси 16 x 8)."""
    u = (x - 16.0) / 16.0
    v = (y - 32.5) / 8.0
    m = np.minimum(1.0 + u + v, 1.0 - u + v)          # мера до верхнего левого / правого ребра
    return (v <= 0.0) & (m >= -OVERLAP) & (m < W - OVERLAP)


def motif67(x, y):
    """Перекрестие кадра 67 по пикселям классики, сдвинуто на +0.5 по x (центр ромба 16)."""
    inner = (x > 13.5) & (x < 18.5) & (y > 31.0) & (y < 33.0)
    box = (x >= 12.5) & (x <= 19.5) & (y >= 30.0) & (y <= 34.0) & ~inner
    vert = (np.abs(x - 16.0) < 0.5) & (y >= 27.0) & (y <= 38.0) & ~inner
    horz = (y >= 32.0) & (y <= 33.0) & (x >= 5.0) & (x <= 27.0) & ~inner
    tl = (x >= 10.5) & (x <= 13.5) & (np.abs(y - (29.5 + (x - 11.5) / 2)) < 0.5)
    tr = (x >= 18.5) & (x <= 21.5) & (np.abs(y - (29.5 - (x - 20.5) / 2)) < 0.5)
    bl = (x >= 10.5) & (x <= 13.5) & (np.abs(y - (34.5 - (x - 11.5) / 2)) < 0.5)
    br = (x >= 18.5) & (x <= 21.5) & (np.abs(y - (34.5 + (x - 20.5) / 2)) < 0.5)
    return box | vert | horz | tl | tr | bl | br


BLOCK = 63
BLOCK_LIFT = 24.0          # верх куба 63 - ромб пола, поднятый на 24 пикселя базы


def diamond(x, y, cy):
    """u, v и меры до верхних (mu) и нижних (md) рёбер ромба с центром (16, cy), полуоси 16 x 8."""
    u = (x - 16.0) / 16.0
    v = (y - cy) / 8.0
    return u, v, np.minimum(1.0 + u + v, 1.0 - u + v), np.minimum(1.0 + u - v, 1.0 - u - v)


def block_mask(x, y, ov):
    """Силуэт куба 63: верхняя половина верхнего ромба, бока x 0..32, нижняя половина ромба пола."""
    cy_top, cy_bot = 32.5 - BLOCK_LIFT, 32.5
    _, vt, mut, _ = diamond(x, y, cy_top)
    _, vb, _, mdb = diamond(x, y, cy_bot)
    return (((vt <= 0) & (mut >= -ov)) | ((y >= cy_top) & (y <= cy_bot))
            | ((vb >= 0) & (mdb >= -ov)))


def block_lines(x, y):
    """Рёбра куба 63 по классике: нижние рёбра верха (внутри силуэта), три вертикали, нижние рёбра низа."""
    cy_top, cy_bot = 32.5 - BLOCK_LIFT, 32.5
    _, vt, _, mdt = diamond(x, y, cy_top)
    _, vb, _, mdb = diamond(x, y, cy_bot)
    top = (vt >= 0) & (mdt >= 0) & (mdt < W)
    bot = (vb >= 0) & (mdb >= -OVERLAP) & (mdb < W)
    side = (y >= cy_top) & (y <= cy_bot) & ((x < 1.0) | (x > 31.0))
    mid = (np.abs(x - 16.0) < 0.5) & (y >= cy_top + 8.0) & (y <= cy_bot + 8.0)
    return top | bot | side | mid


def block_frame(pal):
    x, y = samples()
    idx = np.full(x.shape, FILL, np.int32)
    idx[block_lines(x, y)] = EDGE[64]
    return down(pal[idx].astype(np.float32))


def block_alpha():
    y, x = np.mgrid[0:40 * K, 0:32 * K].astype(np.float32)
    return block_mask((x + 0.5) / K, (y + 0.5) / K, OVERLAP).astype(np.float32)


def down(c):
    """Среднее по блокам SSxSS: (160*SS, 128*SS, 3) -> (160, 128, 3)."""
    h, w = c.shape[0] // SS, c.shape[1] // SS
    return c.reshape(h, SS, w, SS, -1).mean(axis=(1, 3))


def alpha():
    return (gs.dmap() <= 1.0 + OVERLAP).astype(np.float32)


def line_frame(f, pal):
    x, y = samples()
    idx = np.full(x.shape, FILL, np.int32)
    if f == 67:
        idx[motif67(x, y)] = MOTIF
    idx[edge_line(x, y)] = EDGE[f]
    return down(pal[idx].astype(np.float32))


def noise_frame(fr, pal, sig=NOISE_SIG, seed=58):
    """Статический шум: классика - случайная россыпь трёх цветов, и её пятна, перенесённые как есть, на поле
    выстраиваются по клеткам (R-265). Здесь зерно своё, размером с пиксель базы, доли цветов - как в классике."""
    a = fr.astype(np.int32)
    cls, cnt = np.unique(a[a > 0], return_counts=True)
    order = np.argsort(-cnt)                       # самый частый (заливка) - самые низкие значения поля
    cls, share = cls[order], cnt[order] / cnt.sum()
    n = 8                                          # сетка поля x8, потом вверх до отсчётов
    rng = np.random.default_rng(seed)
    g = wb.gauss(rng.standard_normal((40 * n, 32 * n)).astype(np.float32), sig * n)
    edges = np.quantile(g, np.cumsum(share)[:-1])
    lab = cls[np.digitize(g, edges)]
    r = K * SS // n
    lab = np.kron(lab, np.ones((r, r), np.int32))
    return down(pal[lab].astype(np.float32)), [(int(c), round(float(s), 2)) for c, s in zip(cls, share)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default="58,64,65,66,67")
    ap.add_argument("--sig", type=float, default=NOISE_SIG)
    a = ap.parse_args()
    pal = wb.palette().astype(np.float32)
    frames = wb.read_set(SET)
    al = alpha()
    for f in [int(s) for s in a.frames.split(",")]:
        fa = al
        if f == BLOCK:
            rgb = block_frame(pal)
            fa = block_alpha()
            note = "block, edge %d" % EDGE[64]
        elif f in EDGE:
            rgb = line_frame(f, pal)
            note = "edge %d" % EDGE[f]
        elif f == 58:
            rgb, cls = noise_frame(frames[f], pal, a.sig)
            note = "noise %s" % cls
        else:
            raise SystemExit("кадр %d: построение не задано" % f)
        gs.save_rgba(rgb, fa, a.out, SET, str(f))
        print("%s %d: %s, opaque %d" % (SET, f, note, int(fa.sum())))


if __name__ == "__main__":
    main()
