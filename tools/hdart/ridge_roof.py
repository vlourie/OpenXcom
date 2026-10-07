"""Ребристая кровля без сетки: поле рёбер по профилю классики, сплошное через клетки (08.10, без генерации).

Брак пака у кровли из рёбер (URBANLUX 52 и её побайтные копии в 7 наборах): пак нарисовал рёбра короткими
досками с торцами внутри клетки, на поле крыши - кладка кирпичом. У классики ребро идёт через всю крышу:
цвет пикселя зависит только от фазы s = x + 2y (или x - 2y) по модулю периода P, а сдвиг соседней клетки
(16, 8) или (16, -8) меняет s на кратное P - рёбра соседей стыкуются сами.

Что делается:
  1. Направление и период ищутся перебором (x + 2y и x - 2y, P = 8, 16, 32): доля пикселей середины классики,
     чей индекс совпал с самым частым индексом своей фазы.
  2. Профиль фазы - средний цвет классики середины (полосы у края ромба шириной EDGE не берутся: в них
     тень края клетки, на HD-поле она дала бы сетку).
  3. HD: фаза каждого пикселя x4 непрерывна, цвет - периодическая интерполяция Катмулла-Рома по профилю;
     зерно - периодический шум ground_seam.grain_noise (поле бесшовно, как ковёр).
  4. Альфа - силуэт классики x4 плюс точный ромб (ground_seam.classic_alpha); за ромбом то же поле, то есть
     ровно то, что нарисует сосед.
Проверка - игровой кадр классика | пак установки | новое (R-249).

    py -3.13 tools/hdart/ridge_roof.py --set URBANLUX --frame 52 --out <папка>/TERRAIN [--copies COMMS:18,...]
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ground_seam as gs          # noqa: E402
import water_build as wb          # noqa: E402

EDGE = 3.0 / 16                   # полоса у края ромба (в мере dmap, 1 - край), где тень края клетки
OVERLAP = 0.04                    # --exact: перехлёст ромба (в мере dmap), около 2 пикселей x4 по горизонтали
GRAIN = 1.5                      # СКО зерна по яркости


def find_stripes(fr, periods=(8, 16, 32)):
    """(знак, период, доля совпадения) лучшего направления рёбер середины кадра."""
    h, w = fr.shape
    y, x = np.mgrid[0:h, 0:w]
    d = gs.dmap(h * gs.K, w * gs.K)[gs.K // 2::gs.K, gs.K // 2::gs.K]
    mid = (fr > 0) & (d < 1.0 - EDGE)
    best = (0, 0, 0.0)
    for sg in (1, -1):
        for P in periods:
            ph = (x + sg * 2 * y) % P
            hit = 0
            for k in range(P):
                v = fr[mid & (ph == k)]
                if v.size:
                    hit += int(np.bincount(v).max())
            q = hit / max(int(mid.sum()), 1)
            if q > best[2] + 0.02:            # меньший период при равной доле
                best = (sg, P, q)
    return best, mid


def build(s, f, pal, seed=7, period=0, exact=False):
    fr = wb.read_set(s)[f]
    (sg, P, q), mid = find_stripes(fr, (period,) if period else (8, 16, 32))
    h, w = fr.shape
    y, x = np.mgrid[0:h, 0:w]
    ph = (x + sg * 2 * y) % P
    rgb = pal[fr].astype(np.float32)
    prof = np.zeros((P, 3), np.float32)
    for k in range(P):
        m = mid & (ph == k)
        prof[k] = rgb[m].mean(0) if m.any() else np.nan
    bad = np.isnan(prof[:, 0])
    if bad.any():
        ok = np.flatnonzero(~bad)
        for c in range(3):
            prof[bad, c] = np.interp(np.flatnonzero(bad), ok, prof[ok, c], period=P)
    H, W = h * gs.K, w * gs.K
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32) + 0.5
    t = (X / gs.K - 0.5) + sg * 2 * (Y / gs.K - 0.5)
    i0 = np.floor(t).astype(np.int64)
    u = (t - i0)[..., None]
    p = [prof[(i0 + o) % P] for o in (-1, 0, 1, 2)]
    out = 0.5 * (2 * p[1] + (-p[0] + p[2]) * u + (2 * p[0] - 5 * p[1] + 4 * p[2] - p[3]) * u * u
                 + (-p[0] + 3 * p[1] - 3 * p[2] + p[3]) * u * u * u)
    lo, hi = prof.min(0), prof.max(0)
    out = np.clip(out, lo, hi)
    g = gs.grain_noise(W, sig=1.2, seed=seed)
    g = g / (g.std() + 1e-6) * GRAIN
    out = np.clip(out + g[..., None], 0, 255)
    # точный ромб ровно по краю оставляет просветы в вершинах (четыре клетки сходятся в точке) - перехлёст
    # OVERLAP: под ним то же поле, что нарисует сосед
    al = (gs.dmap() <= 1.0 + OVERLAP).astype(np.float32) if exact else gs.classic_alpha(fr)
    return out, al, (sg, P, q), prof


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--frame", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--exact", action="store_true", help="альфа - только точный ромб x4: карниз крыши без лесенки")
    ap.add_argument("--copies", default="", help="НАБОР:кадр через запятую - побайтные копии классики, тот же файл")
    ap.add_argument("--period", type=int, default=0,
                    help="период рёбер вдоль x (делитель 32); 0 - перебор. При 32 рёбра одного кадра бывают разной"
                         " ширины, и на поле они идут парами (URBANLUX 52: ровный шаг - 16)")
    a = ap.parse_args()
    pal = wb.palette()
    rgb, al, (sg, P, q), prof = build(a.set, a.frame, pal, period=a.period, exact=a.exact)
    print("%s %d: рёбра x %s 2y, период %d, совпадение фазы %.2f" % (a.set, a.frame, "+" if sg > 0 else "-", P, q))
    print("  профиль:", " ".join("%d" % v for v in (prof @ gs.LUMA).round()))
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
