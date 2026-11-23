# -*- coding: utf-8 -*-
"""XP-000343 вариант A: углы ямы крыши башни связи (C_EXT_ROOF_SILVER 40-43, 46, 47 и вся семья) по классике.

Рецепт pixel_lines (xBRZ x4 по полю классики, альфа ромба с перехлестом R-291, выступ своей копией R-326),
но поле - не 5x5 копий одного кадра (они кладут чёрный выступ ямы по рёбрам ромба соседа - чёрная нить), а настоящий
блок COMMS_TOWER_ROOF: яма 4x4 с её настоящими соседями. Кадр вырезается из xBRZ всего блока.

    py -3.13 t343_A_pit.py --out <папка> [--sets C_EXT_ROOF_SILVER,...] [--frames 40,41,42,43,46,47]
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path("E:/OpenXCom")
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402
import pixel_lines as pl          # noqa: E402
import ground_seam as gs          # noqa: E402
import sprite_scale as ss         # noqa: E402
import contour_check as cc        # noqa: E402

K = 4
# блок COMMS_TOWER_ROOF, этаж 1, клетки x,y 2..7 (кадры C_EXT_ROOF_SILVER; (2,7) в блоке LIFTER:0 - тут пол 0)
LAYOUT = {
    (2, 2): 39, (3, 2): 0, (4, 2): 0, (5, 2): 0, (6, 2): 0, (7, 2): 39,
    (2, 3): 1, (3, 3): 43, (4, 3): 46, (5, 3): 46, (6, 3): 42, (7, 3): 1,
    (2, 4): 1, (3, 4): 47, (4, 4): 48, (5, 4): 48, (6, 4): 44, (7, 4): 1,
    (2, 5): 1, (3, 5): 47, (4, 5): 48, (5, 5): 48, (6, 5): 44, (7, 5): 1,
    (2, 6): 1, (3, 6): 40, (4, 6): 45, (5, 6): 45, (6, 6): 41, (7, 6): 1,
    (2, 7): 0, (3, 7): 0, (4, 7): 0, (5, 7): 0, (6, 7): 0, (7, 7): 39,
}
PLEV = {48: 6}
TARGET = {40: (3, 6), 41: (6, 6), 42: (6, 3), 43: (3, 3), 46: (4, 3), 47: (3, 4), 44: (6, 4), 45: (4, 6)}
# край ямы: оба соседа по линии - тот же край, шов нейтрален
EDGE_NB = {46: [(3, 3), (6, 3)], 47: [(3, 3), (3, 6)], 44: [(6, 3), (6, 6)], 45: [(3, 6), (6, 6)]}
PIT = set(range(40, 49))
CE = ["C_EXT_ROOF", "C_EXT_ROOF_BLACK", "C_EXT_ROOF_BLACK2", "C_EXT_ROOF_DBLUE", "C_EXT_ROOF_GOLD", "C_EXT_ROOF_PRPL",
      "C_EXT_ROOF_RED", "C_EXT_ROOF_SILVER"]
OFFSET = {"SPACESTATION_EXTRA": 36 - 40, "STATIONBITS": 16 - 40}      # логический кадр 40..48 -> кадр набора
PAD = 12


def lut_from_silver(member, off):
    """Набор без своих плиток-соседей (0, 1, 39): индексы SILVER -> индексы набора по кадрам ямы 40..47."""
    sil, mem = wb.read_set("C_EXT_ROOF_SILVER"), wb.read_set(member)
    cnt = {}
    for f in range(40, 48):
        a, b = sil[f], mem[f + off]
        m = (a > 0) & (b > 0)
        for i, j in zip(a[m], b[m]):
            cnt.setdefault(int(i), Counter())[int(j)] += 1
    lut = {i: c.most_common(1)[0][0] for i, c in cnt.items()}
    body = lut[Counter(int(v) for v in sil[28][sil[28] > 0]).most_common(1)[0][0]] if False else None
    return lut


def frames_of(setname):
    """Логический кадр (0, 1, 39, 40..48) -> индексы набора 40x32 (с переносом цвета для наборов без соседей)."""
    if setname in CE:
        fr = wb.read_set(setname)
        return {f: fr[f] for f in [0, 1, 39] + list(PIT)}, None
    off = OFFSET[setname]
    fr = wb.read_set(setname)
    sil = wb.read_set("C_EXT_ROOF_SILVER")
    lut = lut_from_silver(setname, off)
    # индексы соседей, которых нет в кадрах ямы: самый частый индекс пола ямы набора (корпус плиты)
    body = Counter(int(v) for f in (40, 43) for v in fr[f + off][fr[f + off] > 0]).most_common(1)[0][0]
    out = {f: fr[f + off] for f in PIT}
    for f in (0, 1, 39):
        a = sil[f]
        b = np.zeros_like(a)
        for i in np.unique(a[a > 0]):
            b[a == i] = lut.get(int(i), body)
        out[f] = b
    return out, lut


def canvas(frames, lay, target, tcell):
    cells = dict(lay)
    ys = [c[1] for c in cells]
    xs = [c[0] for c in cells]
    ox = (max(ys) - min(xs)) * 16 + PAD
    W = (max(xs) - min(ys) + max(ys) - min(xs)) * 16 + 32 + 2 * PAD
    H = (max(xs) + max(ys) - min(xs) - min(ys)) * 8 + 40 + 2 * PAD
    idx = np.zeros((H, W), np.int32)

    def put(c, f):
        x, y = c
        px = ox + (x - y) * 16
        py = PAD + (x + y - min(xs) - min(ys)) * 8 - PLEV.get(f, 0)
        a = frames[f]
        m = a > 0
        idx[py:py + 40, px:px + 32][m] = a[m]
        return px, py

    pos = {}
    for c in sorted(cells, key=lambda c: (c[1], c[0])):
        pos[c] = put(c, cells[c])
    px, py = put(tcell, target)               # свой кадр поверх: соседи его выступ не закрывают (R-326)
    return idx, (px, py)


def build_frame(frames, logical, pal):
    lay = dict(LAYOUT)
    tcell = TARGET[logical]
    for c in EDGE_NB.get(logical, []):
        lay[c] = logical
    lay[tcell] = logical
    idx, (px, py) = canvas(frames, lay, logical, tcell)
    a = (idx > 0).astype(np.float32) * 255.0
    rgba = np.concatenate([pal[idx], a[..., None]], -1)[None]
    up = ss.xbrz_scale(rgba, K)[0]
    rgb = up[py * K:(py + 40) * K, px * K:(px + 32) * K, :3]
    cl = frames[logical]
    dm = gs.dmap()
    al = (dm <= 1.0 + pl.OVERLAP).astype(np.float32)
    rgb2, fa = pl.beyond_diamond(cl, pal, rgb, al, dm)
    return rgb2, fa, cl


def save(rgb, fa, path):
    Image.fromarray(np.dstack([np.clip(rgb, 0, 255), fa * 255]).round().astype(np.uint8), "RGBA").save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sets", default=",".join(CE + list(OFFSET)))
    ap.add_argument("--frames", default="40,41,42,43,46,47")
    o = ap.parse_args()
    pal = wb.palette().astype(np.float32)
    os.makedirs(o.out, exist_ok=True)
    for s in o.sets.split(","):
        frames, _ = frames_of(s)
        for lf in [int(v) for v in o.frames.split(",")]:
            rgb, fa, cl = build_frame(frames, lf, pal)
            v, why = cc.verdict(cl, fa, pal)
            real = lf + OFFSET.get(s, 0)
            save(rgb, fa, os.path.join(o.out, "%s_%d.png" % (s, real)))
            print("%s:%d  контур: %s %s" % (s, real, v, "" if v == "ok" else why))


if __name__ == "__main__":
    main()
