"""Гладкая плитка без чужого цвета: кадр из ровных цветов и линий строится по самой классике (08.10, без генерации).

Брак пака у ровной плитки (URBANWAR 40 и её 11 побайтных копий, URBANWAR 80): пак залил клетку одним тоном,
теплее и светлее классики (137,135,130 против 112,115,119; 49 против 64 по яркости у 80), и потерял линии
плитки - светлую кромку слева, тёмную справа, ромб внутри. Классика здесь - три-пять ровных цветов без
фактуры, и рисовать в ней нечего, кроме ровных линий.

Что делается:
  1. Маска каждого индекса классики x4 размывается гауссом SIG (пикс x4) - лесенка 8x4 линий 2:1 сходит
     в прямую; цвет пикселя - смесь цветов индексов с весами размытых масок (нормированная свёртка).
     Цвет берётся из палитры как есть: средний тон кадра - тон классики.
  2. Там, где масок рядом нет (за силуэтом классики, внутри точного ромба), - та же свёртка с FAR.
  3. Зерно - периодический шум ground_seam.grain_noise, СКО GRAIN по яркости (ровный цвет на k=4 мёртвый).
  4. Альфа - силуэт классики x4 плюс точный ромб (ground_seam.classic_alpha).
Проверка - игровой кадр классика | пак установки | новое (R-249).

    py -3.13 tools/hdart/flat_tile.py --set URBANWAR --frame 40 --out <папка>/TERRAIN [--copies GOVT:40,...]
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ground_seam as gs          # noqa: E402
import water_build as wb          # noqa: E402

SIG = 2.5                         # размытие масок, пикс x4: лесенка линий уходит, линия в 2 пикселя базы остаётся
FAR = 8.0                         # размытие для мест без своих масок рядом
GRAIN = 1.2                       # СКО зерна по яркости


def build(s, f, pal, seed=7):
    fr = wb.read_set(s)[f]
    up = np.repeat(np.repeat(fr, gs.K, 0), gs.K, 1)
    acc = np.zeros(up.shape + (3,), np.float32)
    wt = np.zeros(up.shape, np.float32)
    acc2 = np.zeros_like(acc)
    wt2 = np.zeros_like(wt)
    for v in np.unique(fr[fr > 0]):
        m = (up == v).astype(np.float32)
        c = pal[v].astype(np.float32)
        g = wb.gauss(m, SIG)
        acc += g[..., None] * c
        wt += g
        g2 = wb.gauss(m, FAR)
        acc2 += g2[..., None] * c
        wt2 += g2
    near = acc / np.maximum(wt, 1e-6)[..., None]
    far = acc2 / np.maximum(wt2, 1e-6)[..., None]
    k = np.clip(wt / 0.25, 0, 1)[..., None]           # где своих масок мало - запасной цвет
    out = k * near + (1 - k) * far
    g = gs.grain_noise(up.shape[1], sig=1.2, seed=seed)
    g = g / (g.std() + 1e-6) * GRAIN
    out = np.clip(out + g[..., None], 0, 255)
    return out, gs.classic_alpha(fr), fr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--frame", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--copies", default="", help="НАБОР:кадр через запятую - побайтные копии классики, тот же файл")
    a = ap.parse_args()
    pal = wb.palette()
    rgb, al, base = build(a.set, a.frame, pal)
    m = al > 0.5
    print("%s %d: средний цвет классики %s, нового %s" % (
        a.set, a.frame, pal[base[base > 0]].mean(0).round().astype(int).tolist(),
        rgb[m].mean(0).round().astype(int).tolist()))
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
