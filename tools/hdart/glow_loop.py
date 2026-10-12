"""HD-петля анимированного пола со светящимися клетками по неподвижной тёмной решётке (R-071, R-298).

XOPSUFOSMFLOOR 0-7 (пол малого НЛО, запись MCD 0 - петля из восьми кадров): тёмная решётка индексом 31 стоит
на месте всю петлю (расходятся 0-15 пикселей из 256), а клетки между ней светятся и меняют цвет по рампе.
Прежний пак рисовал каждый кадр своей формой: 0-3 скалами, 4-7 вафельными панелями - в игре пол мигал.

Что делается:
  1. Форма решётки одна на всю петлю: пиксель тёмный, если тёмный в половине кадров и больше. Маска
     решётки на поле копий классики (pixel_lines.build_field) - xBRZ x4: лесенка спрямлена, углы держатся.
  2. Цвет свечения - свой у каждого кадра: цвета классики вне решётки, решётка дозалита цветом соседних
     светящихся пикселей, поле - xBRZ x4.
  3. Кадр = свечение под маской, цвет решётки - её индекс классики. Альфа - точный ромб с перехлёстом (R-291).

    py -3.13 tools/hdart/glow_loop.py --out art/ground/xops-v1/TERRAIN --set XOPSUFOSMFLOOR --frames 0-7 --dark 31
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402
import ground_seam as gs          # noqa: E402
import sprite_scale as ss         # noqa: E402
import pixel_lines as pl          # noqa: E402

K = pl.K
PAD = pl.PAD
OVERLAP = pl.OVERLAP


def crop(fld, o):
    ox, oy = o
    return fld[oy - PAD:oy + 40 + PAD, ox - PAD:ox + 32 + PAD]


def up(rgb):
    rgba = np.concatenate([rgb, np.full(rgb.shape[:2] + (1,), 255.0, np.float32)], -1)[None]
    return ss.xbrz_scale(rgba, K)[0][..., :3][PAD * K:-PAD * K, PAD * K:-PAD * K]


def fill(rgb, known):
    """Неизвестные пиксели - среднее известных соседей 3x3, по кольцам наружу."""
    rgb, known = rgb.copy(), known.copy()
    while not known.all():
        acc = np.zeros_like(rgb)
        n = np.zeros(known.shape, np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                k = np.roll(np.roll(known, dy, 0), dx, 1)
                acc += np.roll(np.roll(rgb, dy, 0), dx, 1) * k[..., None]
                n += k
        new = ~known & (n > 0)
        if not new.any():
            raise SystemExit("дозаливка не сходится")
        rgb[new] = acc[new] / n[new][..., None]
        known |= new
    return rgb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--set", required=True)
    ap.add_argument("--frames", required=True, help="0-7")
    ap.add_argument("--dark", type=int, required=True, help="индекс решётки")
    a = ap.parse_args()
    lo, hi = (int(v) for v in a.frames.split("-"))
    frames = list(range(lo, hi + 1))
    pal = wb.palette().astype(np.float32)
    sets = wb.read_set(a.set)
    cls = [sets[f] for f in frames]
    if any((c > 0).sum() != (cls[0] > 0).sum() or ((c > 0) != (cls[0] > 0)).any() for c in cls):
        raise SystemExit("силуэт кадров петли разный - это не петля одного пола")
    dark = sum((c == a.dark).astype(int) for c in cls) * 2 >= len(cls)
    for f, c in zip(frames, cls):
        print("кадр %d: тёмных %d, расходится с общей решёткой %d" % (f, int((c == a.dark).sum()),
                                                                     int(((c == a.dark) != dark)[c > 0].sum())))
    # 1. форма решётки
    mimg = np.where(cls[0] > 0, np.where(dark, 2, 1), 0).astype(np.int32)
    mf, o = pl.build_field(mimg)
    msub = crop(mf, o)
    mrgb = np.where(msub[..., None] == 1, 255.0, 0.0).repeat(3, -1).astype(np.float32)
    m4 = up(mrgb)[..., 0] / 255.0
    darkfld = crop(mf, o) == 2
    al = (gs.dmap() <= 1.0 + OVERLAP).astype(np.float32)
    dcol = pal[a.dark]
    for f, c in zip(frames, cls):
        fld, o2 = pl.build_field(c)
        if o2 != o:
            raise SystemExit("поле кадра сдвинуто")
        sub = crop(fld, o)
        known = (sub > 0) & ~darkfld & (sub != a.dark)
        glow = up(fill(pal[sub].astype(np.float32), known))
        rgb = glow * m4[..., None] + dcol * (1.0 - m4[..., None])
        gs.save_rgba(rgb, al, a.out, a.set, str(f))
        print("кадр %d: средний цвет нового %s, классики %s" % (
            f, np.round(rgb[al > 0].mean(axis=0)).astype(int).tolist(),
            np.round(pal[c[c > 0]].mean(axis=0)).astype(int).tolist()))


if __name__ == "__main__":
    main()
