# -*- coding: utf-8 -*-
"""XP-000343 вариант A: клеть XBASEN_BITS:0 - xBRZ x4 своей копии классики (pixel_lines.own_render): прорези решётки
остаются сквозными (альфа xBRZ премультиплицированная, края дыр без каймы), лесенки нет, тон - индексы классики.
Основа одна; CYBERWAREAN:96, METRO1:91, RUSTSHACKS2:52 - побайтные копии классики, файл - копия основы.

    py -3.13 t343_A_cage.py --out <папка>
"""
import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, "E:/OpenXCom/tools/hdart")
import water_build as wb          # noqa: E402
import pixel_lines as pl          # noqa: E402

COPIES = [("CYBERWAREAN", 96), ("METRO1", 91), ("RUSTSHACKS2", 52)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    o = ap.parse_args()
    out = Path(o.out)
    pal = wb.palette().astype(np.float32)
    cl = wb.read_set("XBASEN_BITS")[0]
    for s, f in COPIES:
        assert (wb.read_set(s)[f] == cl).all(), "%s:%d не копия XBASEN_BITS:0" % (s, f)
    rgb, a = pl.own_render(cl, pal)
    img = np.dstack([np.clip(rgb, 0, 255), np.clip(a, 0, 1) * 255]).round().astype(np.uint8)
    base = out / "XBASEN_BITS_0.png"
    Image.fromarray(img, "RGBA").save(base)
    for s, f in COPIES:
        shutil.copyfile(base, out / ("%s_%d.png" % (s, f)))
    print("клеть: основа XBASEN_BITS:0 и копии", COPIES)


if __name__ == "__main__":
    main()
