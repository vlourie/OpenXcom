"""HD-кадр пола с правильной решёткой, построенный по геометрии классики (R-042, R-298).

A_BASE 64 (пол базы пришельцев, 29 тысяч клеток): светлые линии по двум изо-осям, шаг - четверть клетки,
в узлах заклёпка с ореолом, ячейки тёмные. Прежний пак вместо решётки рисовал тёмное поле с точками.
Решётка задана узлом и двумя векторами A, B в пикселях базы: клетка (16, 8) = 4A, (-16, 8) = 4B, поэтому
кадр периодичен и стыкуется сам с собой. Классика рисует узор ровно этими векторами (замер по пикселям 'g').

Цвета - индексы палитры классики: ячейка, ореол узла, линия, узел и светлая кромка верхних рёбер
(нижние рёбра классики закрывает сосед, он ложится позже). Цвет считается по 4x4 отсчётам на пиксель x4,
альфа - точный ромб с перехлёстом (R-291).

    py -3.13 tools/hdart/lattice_floor.py --out art/ground/abase-v1/TERRAIN [--frames A_BASE:64]
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402
import ground_seam as gs          # noqa: E402

K = 4
SS = 4
OVERLAP = 0.04

# узел - центр пикселя 'g' классики; линия - полоса по вертикали в рядах базы; радиусы - пиксели базы
PRESETS = {
    ("A_BASE", 64): dict(node=(7.5, 30.5), a=(4.0, 2.0), b=(-4.0, 2.0),
                         fill=242, halo=241, line=6, knot=5, rim=240,
                         line_rows=1.0, knot_r=0.55, halo_r=1.6, rim_w=0.0625),
}


def samples():
    y, x = np.mgrid[0:40 * K * SS, 0:32 * K * SS].astype(np.float32)
    return (x + 0.5) / (K * SS), (y + 0.5) / (K * SS)


def down(c):
    h, w = c.shape[0] // SS, c.shape[1] // SS
    return c.reshape(h, SS, w, SS, -1).mean(axis=(1, 3))


def lattice_coords(x, y, p):
    """(alpha, beta): точка = узел + alpha*A + beta*B."""
    (nx, ny), (ax, ay), (bx, by) = p["node"], p["a"], p["b"]
    dx, dy = x - nx, y - ny
    det = ax * by - ay * bx
    return (dx * by - dy * bx) / det, (ax * dy - ay * dx) / det


def build(p, pal):
    x, y = samples()
    al, be = lattice_coords(x, y, p)
    fa, fb = al - np.round(al), be - np.round(be)          # до ближайшей линии, в долях шага
    # вертикальное расстояние до линии в рядах базы: шаг A по y - ay рядов на единицу alpha, у обеих осей
    rows_a = np.abs(fb) * (p["a"][1] + p["b"][1])
    rows_b = np.abs(fa) * (p["a"][1] + p["b"][1])
    line = (rows_a < p["line_rows"] / 2) | (rows_b < p["line_rows"] / 2)
    # расстояние до ближайшего узла в пикселях базы
    (ax, ay), (bx, by) = p["a"], p["b"]
    ra, rb = np.round(al), np.round(be)
    best = np.full(x.shape, np.inf, np.float32)
    for da in (-1, 0, 1):
        for db in (-1, 0, 1):
            ka, kb = ra + da, rb + db
            nx = p["node"][0] + ka * ax + kb * bx
            ny = p["node"][1] + ka * ay + kb * by
            best = np.minimum(best, np.hypot(x - nx, y - ny))
    idx = np.full(x.shape, p["fill"], np.int32)
    idx[best < p["halo_r"]] = p["halo"]
    idx[line] = p["line"]
    idx[best < p["knot_r"]] = p["knot"]
    # светлая кромка верхних рёбер ромба
    u = (x - 16.0) / 16.0
    v = (y - 32.5) / 8.0
    m = np.minimum(1.0 + u + v, 1.0 - u + v)
    idx[(v <= 0) & (m >= -OVERLAP) & (m < p["rim_w"] - OVERLAP)] = p["rim"]
    return down(pal[idx].astype(np.float32)), idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default="A_BASE:64")
    a = ap.parse_args()
    pal = wb.palette().astype(np.float32)
    al = (gs.dmap() <= 1.0 + OVERLAP).astype(np.float32)
    for it in a.frames.split(","):
        s, f = it.split(":")
        p = PRESETS.get((s, int(f)))
        if p is None:
            raise SystemExit("%s: решётка не задана" % it)
        rgb, idx = build(p, pal)
        gs.save_rgba(rgb, al, a.out, s, f)
        cl = wb.read_set(s)[int(f)]
        share = {k: round(float((idx == p[k]).mean()), 3) for k in ("fill", "halo", "line", "knot", "rim")}
        cls = {k: round(float((cl == p[k]).sum() / max(1, (cl > 0).sum())), 3)
               for k in ("fill", "halo", "line", "knot", "rim")}
        print("%s %s: доли нового %s" % (s, f, share))
        print("%s %s: доли классики %s" % (s, f, cls))
        print("%s %s: средний цвет нового %s, классики %s" % (
            s, f, np.round(rgb[al > 0].mean(axis=0)).astype(int).tolist(),
            np.round(pal[cl[cl > 0]].mean(axis=0)).astype(int).tolist()))


if __name__ == "__main__":
    main()
