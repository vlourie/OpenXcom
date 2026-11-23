#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Ступени MUJUNGLE 22, 23, 28, 29, 62, 63 и семья (XP-000509): силуэт спрямить, материал и цвет прежние, без видеокарты.
Альфа - силуэт классики своего набора, спрямлённый xBRZ x4 (R-121, R-568), у линии ромба - покрытие прямой с перехлёстом
(t_slope_edge.smooth_fixed). Цвет - нынешний HD кадра; где альфа выросла (там, где была лесенка), цвет - тон середины рядом.
В МОД НИЧЕГО НЕ СТАВИТ: заготовки art/tickets/hb_stairs/<НАБОР>_<кадр>.png.

    py -3.13 tools\hdart\hb_stairs.py
"""
import os
import sys

sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
os.chdir(r"E:\OpenXCom")
import numpy as np
from PIL import Image
from scipy import ndimage

import rim_alpha as ra
import probe_object as po
import t_slope_edge as te

TERR = os.path.join("user", "mods", "hd", "hd", "TERRAIN")
OUT = os.path.join("art", "tickets", "hb_stairs")

# члены семьи по ticket_family 05.11: (набор, кадр) -> основа MUJUNGLE
FAMILY = {}
for base in (22, 23, 28, 29, 62, 63):
    mem = [("MUJUNGLE", base), ("CATACOMB", base), ("SIETCH", base), ("SIETCH_DARK", base)]
    if base in (22, 23):
        mem.append(("DOOM_FRN", base - 1))
    else:
        mem.append(("MUCONCRETE", base))
    FAMILY[base] = mem
MEMBERS = [m for b in sorted(FAMILY) for m in FAMILY[b]]


def straight_alpha(op):
    m = Image.fromarray(op.astype(np.uint8) * 255, "L")
    a = np.asarray(po.smooth_silhouette(m, 4), np.float32) / 255.0
    sil4 = np.kron(op, np.ones((4, 4), bool))
    return np.where(ndimage.binary_dilation(sil4, iterations=2), a, 0.0)


def build(s, f):
    frames, _t, fw, fh = ra.classic(s)
    op = frames[f] != 0
    cur = np.asarray(Image.open(os.path.join(TERR, s + ".PCK", "%d.png" % f)).convert("RGBA")).copy()
    a = straight_alpha(op)
    new = cur.copy()
    need = (a > 0) & (cur[..., 3] < ra.OWN_A)
    if need.any():
        rgb = ra.fill(cur)
        new[..., :3][need] = np.clip(np.rint(rgb[need]), 0, 255).astype(np.uint8)
    new[..., 3] = np.rint(np.clip(a, 0, 1) * 255).astype(np.uint8)
    new, _n = te.smooth_fixed(new, op, 4, fw, fh)
    return Image.fromarray(new, "RGBA"), cur, op


def ladder_rows(alpha):
    """Лесенка по краю: рядов, где граница (альфа > 127) слева или справа прыгает на 5 и больше пикселей, и столбцов то же по верху/низу."""
    m = alpha > 127
    n = 0
    for arr in (m, m.T):
        rows = [y for y in range(arr.shape[0]) if arr[y].any()]
        lo = np.array([int(np.argmax(arr[y])) for y in rows])
        hi = np.array([arr.shape[1] - 1 - int(np.argmax(arr[y][::-1])) for y in rows])
        n += int((np.abs(np.diff(lo)) >= 5).sum() + (np.abs(np.diff(hi)) >= 5).sum())
    return n


def main():
    os.makedirs(OUT, exist_ok=True)
    print("%-22s лесенка было -> стало, полупрозр. было -> стало" % "кадр")
    tot = 0
    for s, f in MEMBERS:
        im, cur, op = build(s, f)
        im.save(os.path.join(OUT, "%s_%d.png" % (s, f)))
        a0, a1 = cur[..., 3], np.asarray(im)[..., 3]
        semi0, semi1 = int(((a0 > 0) & (a0 < 255)).sum()), int(((a1 > 0) & (a1 < 255)).sum())
        print("%-22s %4d -> %4d   %5d -> %5d" % ("%s:%d" % (s, f), ladder_rows(a0), ladder_rows(a1), semi0, semi1))
        tot += 1
    print("кадров:", tot, "->", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
