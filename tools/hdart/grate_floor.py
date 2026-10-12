"""HD-кадр пола-решётки с прорезями по осям экрана, построенный по геометрии классики (R-298, R-309).

XB2BR 20 (решётка базы, 15 тысяч клеток): тёмные прорези 2x1 пикселя базы с шагом 3 по x и 2 по y, между ними
прутья, на пересечениях прутьев светлый узел, у нижних рёбер бурая кромка. Прежний пак вместо решётки рисовал
фасад здания. Классика рисует узор от левого края кадра, а не от ромба, поэтому соседние клетки сходятся со
сдвигом фазы на пиксель - так же, как в классике (16 не делится на 3).

Узор задан периодом и фазами: прорезь - ряд y % py == hole_row и столбец x % px в hole_cols, узел - ряд
y % py == knot_row и столбец x % px == knot_col. Прорези - прямоугольники x4 с точным краем (оси экрана, лесенки
нет); узел - круг; под прорезью светлая губа прута, над ней тень (свет сверху). Цвета - индексы палитры классики.
Альфа - точный ромб с перехлёстом (R-291), нижние рёбра - кромка шириной rim_w.

    py -3.13 tools/hdart/grate_floor.py --out art/ground/grate-v1/TERRAIN [--frames XB2BR:20]
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

PRESETS = {
    ("XB2BR", 20): dict(px=3, py=2, hole_row=1, hole_cols=(1, 2), knot_row=0, knot_col=0,
                        hole=252, bar=11, knot=10, rim=89, knot_r=0.6, rim_w=0.165,
                        lip=10.0, shade=-8.0),
    # мостки химзавода: прорези сквозные (под ними видно, что ниже), поперечные пруты в классике - чередование
    # 241/243 (в HD - их средний тон), по всему краю ромба кайма прута, на верхних рёбрах болты 4/246
    ("MILEXT", 23): dict(px=3, py=2, hole_row=1, hole_cols=(1, 2), knot_row=0, knot_col=0,
                         hole=None, bar=241, hbar=(241, 243), knot=228, rim=241, rim_all=True, knot_r=0.5,
                         rim_w=0.0625, lip=10.0, shade=-8.0,
                         bolts=((10, 27, 4), (11, 27, 246), (20, 27, 4), (21, 27, 246),
                                (4, 30, 4), (5, 30, 246), (26, 30, 4), (27, 30, 246))),
}


def samples():
    y, x = np.mgrid[0:40 * K * SS, 0:32 * K * SS].astype(np.float32)
    return (x + 0.5) / (K * SS), (y + 0.5) / (K * SS)


def down(c):
    h, w = c.shape[0] // SS, c.shape[1] // SS
    return c.reshape(h, SS, w, SS, -1).mean(axis=(1, 3))


def classes(x, y, p):
    """Класс точки (координаты в пикселях базы): 0 прут, 1 прорезь, 2 узел."""
    ix, iy = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32)
    hole = (iy % p["py"] == p["hole_row"]) & np.isin(ix % p["px"], p["hole_cols"])
    # узел - круг в центре пикселя узла
    kx = np.floor((x - p["knot_col"]) / p["px"] + 0.5) * p["px"] + p["knot_col"] + 0.5
    ky = np.floor((y - p["knot_row"]) / p["py"] + 0.5) * p["py"] + p["knot_row"] + 0.5
    knot = np.hypot(x - kx, y - ky) < p["knot_r"]
    c = np.zeros(x.shape, np.int32)
    c[hole] = 1
    c[knot & ~hole] = 2
    return c


def build(p, pal):
    """rgb (160x128x3), покрытие прорезями (0..1) - для сквозных прорезей альфа, индексы класса и точки."""
    x, y = samples()
    c = classes(x, y, p)
    hole_i = p["hole"] if p["hole"] is not None else p["bar"]
    idx = np.where(c == 1, hole_i, np.where(c == 2, p["knot"], p["bar"]))
    rgb = pal[idx].astype(np.float32)
    if p.get("hbar"):
        # поперечный прут (ряд узлов между узлами) - средний тон чередования классики
        iy = np.floor(y).astype(np.int32)
        hb = (c == 0) & (iy % p["py"] == p["knot_row"])
        rgb[hb] = pal[list(p["hbar"])].astype(np.float32).mean(axis=0)
    # свет сверху: губа прута под прорезью светлее, прут над прорезью в тени (четверть пикселя базы)
    below = classes(x, y - 0.25, p) == 1
    above = classes(x, y + 0.25, p) == 1
    rgb[(c == 0) & below] += p["lip"]
    rgb[(c == 0) & above] += p["shade"]
    # кромка рёбер ромба: нижних или всех
    u = (x - 16.0) / 16.0
    v = (y - 32.5) / 8.0
    if p.get("rim_all"):
        m = 1.0 - np.abs(u) - np.abs(v)
        rim = (m >= -OVERLAP) & (m < p["rim_w"] - OVERLAP)
    else:
        m = np.minimum(1.0 + u - v, 1.0 - u - v)
        rim = (v >= 0) & (m >= -OVERLAP) & (m < p["rim_w"] - OVERLAP)
    rgb[rim] = pal[p["rim"]]
    for bx, by, bi in p.get("bolts", ()):
        rgb[np.hypot(x - bx - 0.5, y - by - 0.5) < 0.5] = pal[bi]
    hole = ((c == 1) & ~rim).astype(np.float32)[..., None]
    idx = idx.copy()
    idx[rim] = p["rim"]
    return down(np.clip(rgb, 0, 255)), down(hole)[..., 0], idx, (x, y)


def agree(p, cl):
    """Доля пикселей классики, у которых класс правила совпал с классом по индексу. Считается внутри ромба
    (дальше 2 пикселей базы от края): у самого края классика ставит прут на месте прорези и лишний узел."""
    y, x = np.mgrid[0:40, 0:32].astype(np.float32)
    c = classes(x + 0.5, y + 0.5, p)
    hole_i = p["hole"] if p["hole"] is not None else 0
    want = np.where(c == 1, hole_i, np.where(c == 2, p["knot"], p["bar"]))
    u = (x + 0.5 - 16.0) / 16.0
    v = (y + 0.5 - 32.5) / 8.0
    inner = (1.0 - np.abs(u) - np.abs(v)) > 0.125
    if p["hole"] is None:
        # сквозная прорезь - прозрачный пиксель классики; прут и кромка одного индекса, их не вычитать
        m = inner & ~((cl == 0) & (c != 1))
        ok = cl[m] == want[m]
    else:
        m = (cl > 0) & (cl != p["rim"]) & inner
        ok = cl[m] == want[m]
    if p.get("hbar"):
        hb = (c == 0) & (np.floor(y).astype(np.int32) % p["py"] == p["knot_row"])
        ok = ok | (hb[m] & np.isin(cl[m], p["hbar"]))
    return float(ok.mean()), int(m.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default="XB2BR:20")
    a = ap.parse_args()
    pal = wb.palette().astype(np.float32)
    al = (gs.dmap() <= 1.0 + OVERLAP).astype(np.float32)
    for it in a.frames.split(","):
        s, f = it.split(":")
        p = PRESETS.get((s, int(f)))
        if p is None:
            raise SystemExit("%s: решётка не задана" % it)
        cl = wb.read_set(s)[int(f)]
        ok, n = agree(p, cl)
        print("%s %s: правило совпало с классикой на %.3f из %d пикселей (внутри ромба)" % (s, f, ok, n))
        if ok < 0.95:
            raise SystemExit("правило узора не совпадает с классикой - фазы или период не те")
        rgb, hole, idx, _ = build(p, pal)
        alf = al * (1.0 - hole) if p["hole"] is None else al
        gs.save_rgba(rgb, alf, a.out, s, f)
        if p["hole"] is None:
            inner = gs.dmap() < 0.85
            c4 = np.repeat(np.repeat(cl, K, 0), K, 1)
            print("%s %s: прозрачно внутри ромба %.3f, у классики %.3f" % (
                s, f, (alf[inner] < 0.5).mean(), (c4[inner] == 0).mean()))
        print("%s %s: средний цвет нового %s, классики %s" % (
            s, f, np.round(rgb[alf > 0.5].mean(axis=0)).astype(int).tolist(),
            np.round(pal[cl[cl > 0]].mean(axis=0)).astype(int).tolist()))


if __name__ == "__main__":
    main()
