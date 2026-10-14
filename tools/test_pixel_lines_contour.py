"""pixel_lines не режет исходную геометрию пола (R-326).

1. Контур: U_BITS_G:3 (прямоугольник над ромбом), URBAN_WASTE:82 и TAVERN:32 (приподнятая плита с боковиной),
   URBAN:52 и MILWARE:70 (крыши), XB3BITZ2:26 (--holes) - contour_check обязан сказать «контур цел».
2. Кромка: на нижних сторонах ромба в полосе перехлёста R-291 нет чужого цвета - где своя копия прозрачна, кадр
   прозрачен (иначе на краю площадки без соседа светлая нитка - верх соседней плиты из поля копий).
3. Поле: участок 4x4 в игровом порядке закрыт внутри целиком (вершины четырёх клеток без просветов, R-291).
4. Решётки XB3BITZ3:23, MADDECOR_WASTE:0, METROBITS:16 (--holes, приняты b05): внутри участка картинка та же,
   что у прежней альфы по ромбу, - правка их не трогает.
Контроль: PIXEL_LINES_DIAMOND_ONLY=1 (прежняя альфа по ромбу) - тест обязан упасть на 1 и 2.
Запуск: py -3.13 tools/test_pixel_lines_contour.py
"""
import os
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent / "hdart"))
import water_build as wb     # noqa: E402
import ground_seam as gs     # noqa: E402
import pixel_lines as pl     # noqa: E402
import contour_check as cc   # noqa: E402

SOLID = ["U_BITS_G:3", "URBAN_WASTE:82", "TAVERN:32", "URBAN:52", "MILWARE:70"]
HOLES = ["XB3BITZ2:26"]
GRATES = ["XB3BITZ3:23", "MADDECOR_WASTE:0", "METROBITS:16"]
N = 4


def frame(g, holes, diamond_only=None):
    s, f = g.split(":")
    cl = wb.read_set(s)[int(f)]
    pal = wb.palette().astype(np.float32)
    old = os.environ.get("PIXEL_LINES_DIAMOND_ONLY")
    if diamond_only:
        os.environ["PIXEL_LINES_DIAMOND_ONLY"] = "1"
    try:
        rgb, fa = pl.build(cl, pal, holes)
    finally:
        if diamond_only:
            if old is None:
                del os.environ["PIXEL_LINES_DIAMOND_ONLY"]
            else:
                os.environ["PIXEL_LINES_DIAMOND_ONLY"] = old
    return cl, pal, rgb, fa


def patch(rgb, fa):
    """участок NxN в порядке x+y: цвет и закрытость, маска ромбов внутренних клеток"""
    dm = gs.dmap()
    W, H = 128 * N + 128, 160 + 64 * N
    col = np.zeros((H, W, 3), np.float32)
    acc = np.zeros((H, W), np.float32)
    inner = np.zeros((H, W), bool)
    for cx, cy in sorted(((i, j) for i in range(N) for j in range(N)), key=lambda t: (t[0] + t[1], t[0])):
        px, py = (cx - cy) * 64 + 64 * (N - 1), (cx + cy) * 32
        a = fa[..., None]
        col[py:py + 160, px:px + 128] = rgb * a + col[py:py + 160, px:px + 128] * (1 - a)
        acc[py:py + 160, px:px + 128] = fa + acc[py:py + 160, px:px + 128] * (1 - fa)
        if 0 < cx < N - 1 and 0 < cy < N - 1:
            inner[py:py + 160, px:px + 128] |= dm <= 1.0
    return col, acc, inner


def main():
    bad = []
    dm = gs.dmap()
    y = np.mgrid[0:160, 0:128][0] + 0.5
    band = (dm > 1.0) & (dm <= 1.0 + pl.OVERLAP) & (y > gs.CY)
    for g in SOLID + HOLES:
        cl, pal, rgb, fa = frame(g, g in HOLES)
        v, why = cc.verdict(cl, fa, pal)
        foreign = int((band & (pl.own_render(cl, pal)[1] < 0.5) & (fa >= 0.5)).sum())
        _c, acc, inner = patch(rgb, fa)
        gaps = int((inner & (acc < 0.99)).sum()) if g not in HOLES else 0
        ok = v == "ok" and foreign == 0 and gaps == 0
        print("%s %-16s %s; чужой кромки %d пикс x4; просветов в поле %d" % (
            "ok  " if ok else "FAIL", g, why, foreign, gaps))
        if not ok:
            bad.append(g)
    for g in GRATES:
        _cl, _pal, rgb, fa = frame(g, True)
        _cl, _pal, rgb0, fa0 = frame(g, True, diamond_only=True)
        c1, a1, inner = patch(rgb, fa)
        c0, a0, _i = patch(rgb0, fa0)
        da = float(np.abs(a1 - a0)[inner].max())
        dc = float(np.abs(c1 - c0)[inner].max())
        ok = da <= 0.01 and dc <= 2.0
        print("%s %-16s решётка внутри участка: альфа %.3f, цвет %.1f против прежней" % (
            "ok  " if ok else "FAIL", g, da, dc))
        if not ok:
            bad.append(g)
    print("\nслучаев %d, не сошлось %d%s" % (len(SOLID + HOLES + GRATES), len(bad),
                                          (": " + ", ".join(bad)) if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
