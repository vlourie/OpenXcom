"""Плита с мелкими полосами и фаской по краю клетки по геометрии классики (09.10, без генерации).

Брак пака у палубы AVENGER_EDIT 37 (и побайтной копии STATIONDECOR 35): у классики цвет середины зависит только
от фазы x + 2y по модулю 4 - мелкие полосы вдоль одной изо-оси, восемь серых и восемь бежевых на клетку (в 32x40
читаются шахматкой 2x1), а по краю клетки фаска: светлая по верхним рёбрам, тёмная по нижним. Пак нарисовал
вместо этого несколько крупных досок поперёк, другой оси и числа; у копии ещё и свой шов.

Что делается:
  1. Поле полос - ridge_roof.build с периодом из классики (поиск по 4, 8, 16, 32): фаза x4 непрерывна, сдвиг
     соседней клетки меняет её на кратное периоду, полосы соседей стыкуются сами.
  2. Фаска - полоса ширины RIM у края ромба (мера dmap), цвет каждой четверти ромба - средний цвет классики
     в той же полосе той же четверти; переход к полосам мягкий (SOFT). Фаска - раскладка классики (палуба из
     плит), её не убирают, как тень края у кровли.
  3. Альфа - силуэт классики x4 плюс точный ромб (ground_seam.classic_alpha).
Проверка - игровой кадр классика | пак установки | новое (R-249).

    py -3.13 tools/hdart/stripe_plate.py --set AVENGER_EDIT --frame 37 --out <папка>/TERRAIN --checker [--copies STATIONDECOR:35]

Поправка 09.10: у AVENGER_EDIT 37 цвет середины зависит от (x+2y) mod 4 и РАВНО от (x-2y) mod 4 - это шашечка
клеток 2x1 базы (квадраты пола по диагонали к краю плиты), а не полосы вдоль одной оси. Полосы (без --checker)
лист классика | новое не подтвердил.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ground_seam as gs          # noqa: E402
import water_build as wb          # noqa: E402
import ridge_roof as rr           # noqa: E402

RIM = 2.0 / 16                    # ширина фаски в мере dmap: два пикселя базы по горизонтали
SOFT = 0.02                       # ширина мягкого перехода фаски к полосам (около пикселя x4)


def quadrant(xx, yy, cx, cy):
    """0 - верх слева, 1 - верх справа, 2 - низ слева, 3 - низ справа."""
    return (yy >= cy).astype(np.int64) * 2 + (xx >= cx).astype(np.int64)


def checker_field(fr, pal, P, seed=7):
    """Шашечка классики: цвет базового пикселя зависит от (x + 2y) mod P и так же от (x - 2y) mod P (при P = 4
    это одно и то же) - клетки 2x1 базы по осям экрана, то есть квадраты пола, положенные по диагонали к краю
    плиты. В HD клетка - тот же прямоугольник x4 (геометрия клетки, а не лесенка), край смягчён на пиксель x4.
    Поле периодично по 128 x 160, поэтому сдвиг np.roll на краях не рвёт рисунок."""
    h, w = fr.shape
    y, x = np.mgrid[0:h, 0:w]
    d = gs.dmap(h * gs.K, w * gs.K)[gs.K // 2::gs.K, gs.K // 2::gs.K]
    mid = (fr > 0) & (d < 1.0 - rr.EDGE)
    ph = (x + 2 * y) % P
    rgb = pal[fr].astype(np.float32)
    col = np.zeros((P, 3), np.float32)
    for k in range(P):
        col[k] = rgb[mid & (ph == k)].mean(0)
    H, W = h * gs.K, w * gs.K
    Y, X = np.mgrid[0:H, 0:W]
    out = col[(X // gs.K + 2 * (Y // gs.K)) % P]
    k3 = (0.25, 0.5, 0.25)
    for ax in (0, 1):
        out = sum(np.roll(out, o, axis=ax) * k3[o + 1] for o in (-1, 0, 1))
    g = gs.grain_noise(W, sig=1.2, seed=seed)
    g = g / (g.std() + 1e-6) * rr.GRAIN
    return np.clip(out + g[..., None], 0, 255), col


def build(s, f, pal, seed=7, checker=False):
    fr = wb.read_set(s)[f]
    (sg, P, q), _ = rr.find_stripes(fr, (4, 8, 16, 32))
    out, al, _, prof = rr.build(s, f, pal, seed=seed, period=P)
    if checker:
        out, prof = checker_field(fr, pal, P, seed=seed)
    h, w = fr.shape
    # фаска классики: пиксели у края ромба, по четвертям
    d0 = gs.dmap(h * gs.K, w * gs.K)[gs.K // 2::gs.K, gs.K // 2::gs.K]
    y0, x0 = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    q0 = quadrant(x0 * gs.K, y0 * gs.K, gs.CX, gs.CY)
    rgb = pal[fr].astype(np.float32)
    rim0 = (fr > 0) & (d0 >= 1.0 - RIM)
    rimc = np.zeros((4, 3), np.float32)
    for k in range(4):
        m = rim0 & (q0 == k)
        rimc[k] = rgb[m].mean(0) if m.any() else prof.mean(0)
    H, W = h * gs.K, w * gs.K
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32) + 0.5
    d = gs.dmap(H, W)
    qq = quadrant(X, Y, gs.CX, gs.CY)
    wgt = np.clip((d - (1.0 - RIM - SOFT / 2)) / SOFT, 0, 1)[..., None]
    out = out * (1 - wgt) + rimc[qq] * wgt
    return out, al, (sg, P, q), prof, rimc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--frame", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--copies", default="", help="НАБОР:кадр через запятую - побайтные копии классики, тот же файл")
    ap.add_argument("--checker", action="store_true", help="шашечка 2x1 базы (цвет и по x+2y, и по x-2y), а не полосы")
    a = ap.parse_args()
    pal = wb.palette()
    rgb, al, (sg, P, q), prof, rimc = build(a.set, a.frame, pal, checker=a.checker)
    print("%s %d: полосы x%s2y, период %d (совпало %.2f); профиль Y %s; фаска Y %s"
          % (a.set, a.frame, "+" if sg > 0 else "-", P, q, (prof @ gs.LUMA).round().astype(int).tolist(),
             (rimc @ gs.LUMA).round().astype(int).tolist()))
    if 32 % P:
        raise SystemExit("период не делит 32 - полосы соседей не сойдутся")
    base = wb.read_set(a.set)[a.frame]
    targets = [(a.set, a.frame)]
    for c in filter(None, a.copies.split(",")):
        s2, f2 = c.split(":")
        if not np.array_equal(wb.read_set(s2)[int(f2)], base):
            raise SystemExit("%s - классика не побайтно та же (R-272), не копирую" % c)
        targets.append((s2, int(f2)))
    for s2, f2 in targets:
        gs.save_rgba(rgb, al, a.out, s2, "%d" % f2)
        print("  записан %s:%d" % (s2, f2))


if __name__ == "__main__":
    main()
