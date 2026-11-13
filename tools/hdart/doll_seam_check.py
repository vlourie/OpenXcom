"""Шов на границе рамки кадра (R-738): вещь шире рамки, снаружи заготовка B2, вертикальная граница на x=160 и x=480.

Мера: скачок между соседними столбцами на границе против таких же скачков рядом. Обычные слои дают до 1,3, шов RAGS дал 7,5 и 2,8.

    python tools/hdart/doll_seam_check.py [--dir папка] [--race UBERGAL]

Код 1, если нашёлся шов. Слои читает из установленных hd/UI или из указанной папки.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv, ARGV = sys.argv[:1], sys.argv[1:]             # doll_armor_batch разбирает свои аргументы только в main
import doll_armor_batch as B                            # noqa: E402
import doll_b2_render as db                             # noqa: E402

BORDERS = (160, 480)
NEAR = (-12, -8, -4, 4, 8, 12)
LIMIT = 2.0


def ratios(a):
    """[(отношение, x, точек)] по границам, где вещь есть с обеих сторон."""
    rgb, al = a[..., :3].astype(int), a[..., 3] > 200
    out = []
    for x in BORDERS:
        both = al[:, x - 1] & al[:, x]
        if both.sum() < 12:
            continue
        j = np.abs(rgb[:, x] - rgb[:, x - 1]).sum(axis=1)[both].mean()
        near = []
        for d in NEAR:
            b2 = al[:, x + d - 1] & al[:, x + d]
            if b2.sum() >= 6:
                near.append(np.abs(rgb[:, x + d] - rgb[:, x + d - 1]).sum(axis=1)[b2].mean())
        if near:
            out.append((float(j / (np.median(near) + 3)), x, int(both.sum())))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=B.UI, help="папка со слоями, по умолчанию установленные")
    ap.add_argument("--race", default="UBERGAL")
    ns = ap.parse_args(ARGV)
    names = sorted({n for ks in db.armor_layers().values() for st in ks.values() for n in st if n.startswith(ns.race)})
    found, seen = [], 0
    for n in names:
        p = os.path.join(ns.dir, n.lower() + ".png")
        if not os.path.exists(p):
            continue
        seen += 1
        for r, x, c in ratios(np.asarray(Image.open(p).convert("RGBA"))):
            if r >= LIMIT:
                found.append((round(r, 2), n, x, c))
    print("слоёв %d, швов %d" % (seen, len(found)))
    for f in sorted(found, reverse=True):
        print(" ", f)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
