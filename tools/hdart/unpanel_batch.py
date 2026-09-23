#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Снять серую подложку с того, что вернула модель, и поставить прозрачность.

Ответ DiffSynth приходит непрозрачным RGB на ровном сером поле (PANEL): альфы в нём нет
вообще. Полы это переживают - tile_forge режет их по ромбу оригинала, - а предметы нет:
серый прямоугольник запекается в кадр и в игре виден рамкой вокруг рисунка (R-041).

Пересчитывать генерацию для этого не нужно: подложка ровная, снимается арифметикой
из уже сохранённых кадров (gen_fire.unpanel), а остаток гасится порогом (R-041).

    py -3 tools/hdart/unpanel_batch.py --in art/TERRAIN/CAVEBROWN.PCK/returned/lora
    py -3 tools/hdart/unpanel_batch.py --all           все наборы с папкой returned/lora

Кладёт рядом: <...>/returned/lora_cut/<N>.png. Исходные кадры не трогает.
"""
import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                      # noqa: E402
from PIL import Image                                   # noqa: E402

import gen_fire as gf                                   # noqa: E402
import gen_cursor as gc                                 # noqa: E402
import gen_lora_test as glt                             # noqa: E402


def cut_dir(src, dst, panel, soft, floor):
    os.makedirs(dst, exist_ok=True)
    n = 0
    spill = []
    for p in sorted(glob.glob(os.path.join(src, "*.png"))):
        rgba = gf.unpanel(Image.open(p).convert("RGB"), panel, soft)
        rgba = gc.alpha_floor(rgba, floor)
        rgba.save(os.path.join(dst, os.path.basename(p)))
        spill.append(float((np.asarray(rgba)[..., 3] < 32).mean()))
        n += 1
    return n, (100.0 * sum(spill) / max(1, len(spill)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", default="")
    ap.add_argument("--all", action="store_true", help="все наборы art/TERRAIN/*/returned/lora")
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--soft", type=int, default=48, help="порог снятия подложки")
    ap.add_argument("--floor", type=float, default=0.30, help="порог остатка альфы (R-041)")
    ap.add_argument("--out-name", default="lora_cut")
    args = ap.parse_args()

    panel = tuple(glt.PANEL)
    dirs = ([args.in_dir] if args.in_dir else
            sorted(glob.glob(os.path.join(args.sheets, "*.PCK", "returned", "lora"))))
    if not dirs:
        sys.exit("нечего резать")
    total = 0
    for d in dirs:
        dst = os.path.join(os.path.dirname(d), args.out_name)
        n, pct = cut_dir(d, dst, panel, args.soft, args.floor)
        total += n
        name = os.path.basename(os.path.dirname(os.path.dirname(d)))
        print("  %-22s %3d кадров, прозрачного стало %.0f%%" % (name, n, pct), flush=True)
    print("итого: %d кадров" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
