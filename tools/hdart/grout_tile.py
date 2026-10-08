"""Плитка со швами по геометрии классики: сетка швов сплошная через клетки (08.10, без генерации).

Брак пака у плитки MADDECOR 0 (и побайтных копий CYBERWAREAN 97, DECORLUX 0, SEAMADDECOR 0): пак нарисовал
плиты своего размера и числа - у MADDECOR/CYBERWAREAN крупные плиты с волнистыми швами, у DECORLUX/SEAMADDECOR
мелкая бежевая сетка втрое гуще. Раскладка классики (2x2 плиты на клетку) потеряна. Ковром это не лечится (R-298):
сетка швов и есть материал.

Как ridge_roof, только по двум изо-осям сразу:
  1. Для каждой оси (x + 2y и x - 2y) период P ищется перебором, профиль - средний цвет классики по фазе
     (середина кадра, без тени края клетки).
  2. Тон плиты T - медиана профилей. Отклонения профиля вниз (шов) объединяются максимумом по осям, вверх
     (фаска, блик) складываются: цвет = T + блик_a + блик_b - max(шов_a, шов_b). На перекрестье швов не
     темнее, чем шов, - как у классики.
  3. HD: фазы непрерывны, профили - периодический Катмулл-Ром. Внутри плиты профиль сводится к тону плиты:
     дизеринг классики с шагом 4, растянутый по фазе, встаёт вафлей вдоль швов (проба r10); мотлинг камня
     даёт зерно ground_seam.grain_noise.
  4. Альфа - силуэт классики x4 плюс точный ромб (ground_seam.classic_alpha), за ромбом то же поле.
Сдвиг соседней клетки (16, +-8) меняет каждую фазу на кратное 32, поэтому швы соседей стыкуются сами, если
P делит 32. Проверка - игровой кадр классика | пак установки | новое (R-249).

    py -3.13 tools/hdart/grout_tile.py --set MADDECOR --frame 0 --out <папка>/TERRAIN [--copies DECORLUX:0,...]
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

GRAIN = 4.0
GRAIN_SIG = 2.0
SEAM_DROP = 20


def axis_profile(fr, rgb, mid, sg, periods=(8, 16, 32)):
    """(период, профиль P x 3) оси sg: лучший по контрасту среди периодов, делящих 32."""
    h, w = fr.shape
    y, x = np.mgrid[0:h, 0:w]
    best = None
    for P in periods:
        ph = (x + sg * 2 * y) % P
        prof = np.full((P, 3), np.nan, np.float32)
        for k in range(P):
            m = mid & (ph == k)
            if m.any():
                prof[k] = rgb[m].mean(0)
        bad = np.isnan(prof[:, 0])
        if bad.all():
            continue
        if bad.any():
            ok = np.flatnonzero(~bad)
            for c in range(3):
                prof[bad, c] = np.interp(np.flatnonzero(bad), ok, prof[ok, c], period=P)
        # доля дисперсии яркости, объяснённая фазой; меньший период при равной доле
        L = rgb @ gs.LUMA
        ph_m = ph[mid]
        fit = (prof @ gs.LUMA)[ph_m]
        r2 = 1 - ((L[mid] - fit) ** 2).mean() / max(L[mid].var(), 1e-6)
        if best is None or r2 > best[2] + 0.03:
            best = (P, prof, r2)
    return best


def cubic(prof, t):
    P = len(prof)
    i0 = np.floor(t).astype(np.int64)
    u = (t - i0)[..., None]
    p = [prof[(i0 + o) % P] for o in (-1, 0, 1, 2)]
    out = 0.5 * (2 * p[1] + (-p[0] + p[2]) * u + (2 * p[0] - 5 * p[1] + 4 * p[2] - p[3]) * u * u
                 + (-p[0] + 3 * p[1] - 3 * p[2] + p[3]) * u * u * u)
    return np.clip(out, prof.min(0), prof.max(0))


def build(s, f, pal, seed=7):
    fr = wb.read_set(s)[f]
    h, w = fr.shape
    d = gs.dmap(h * gs.K, w * gs.K)[gs.K // 2::gs.K, gs.K // 2::gs.K]
    mid = (fr > 0) & (d < 1.0 - rr.EDGE)
    rgb = pal[fr].astype(np.float32)
    Pa, pa, ra = axis_profile(fr, rgb, mid, 1)
    Pb, pb, rb = axis_profile(fr, rgb, mid, -1)
    T = np.median(np.concatenate([pa, pb]), axis=0)
    # внутри плиты профиль несёт дизеринг классики с шагом 4 - в HD он встаёт вафлей вдоль швов;
    # оставить только шов (фазы темнее плиты на SEAM_DROP), остальное - тон плиты, мотлинг даёт зерно
    for p in (pa, pb):
        p[(p @ gs.LUMA) > (T @ gs.LUMA) - SEAM_DROP] = T
    H, W = h * gs.K, w * gs.K
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32) + 0.5
    xa, ya = X / gs.K - 0.5, Y / gs.K - 0.5
    A = cubic(pa, xa + 2 * ya) - T
    B = cubic(pb, xa - 2 * ya) - T
    out = T + np.maximum(A, 0) + np.maximum(B, 0) + np.minimum(np.minimum(A, 0), np.minimum(B, 0))
    g = gs.grain_noise(W, sig=GRAIN_SIG, seed=seed)
    g = g / (g.std() + 1e-6) * GRAIN
    out = np.clip(out + g[..., None], 0, 255)
    al = gs.classic_alpha(fr)
    return out, al, (Pa, ra, Pb, rb), T, (pa, pb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--frame", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--copies", default="", help="НАБОР:кадр через запятую - побайтные копии классики, тот же файл")
    a = ap.parse_args()
    pal = wb.palette()
    rgb, al, (Pa, ra, Pb, rb), T, (pa, pb) = build(a.set, a.frame, pal)
    print("%s %d: ось x+2y период %d (объяснено %.2f), ось x-2y период %d (%.2f), тон плиты %s"
          % (a.set, a.frame, Pa, ra, Pb, rb, T.round().astype(int).tolist()))
    print("  профиль x+2y:", " ".join("%d" % v for v in (pa @ gs.LUMA).round()))
    print("  профиль x-2y:", " ".join("%d" % v for v in (pb @ gs.LUMA).round()))
    if 32 % Pa or 32 % Pb:
        raise SystemExit("период не делит 32 - швы соседей не сойдутся")
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
