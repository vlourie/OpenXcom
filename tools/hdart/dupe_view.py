#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Лист близнецов набора: одинаковые кадры рядом, глазами.

dupe_frames.py говорит, СКОЛЬКО кадров повторяется. Этот показывает, ЧТО именно
повторяется: каждая группа - своя строка, в строке все её кадры со своими номерами.
Кадры в группе побайтово равны, поэтому строка обязана выглядеть одинаковой от края
до края; если что-то в строке отличается - сломан не пак, а просмотр (грабли R-043).

    py -3 tools/hdart/dupe_view.py --set FORESTSWAMP.PCK
    py -3 tools/hdart/dupe_view.py --set FORESTSWAMP.PCK --zoom 4 --cols 1

Кладёт art/_review/dupes/<НАБОР>_inside.png.
"""
import argparse
import collections
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont             # noqa: E402

import tile_forge as tf                                 # noqa: E402

BG = (34, 34, 38)
CELL_BG = (52, 52, 58)


def font(size):
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def groups_of(sh):
    """Группы побайтово равных кадров, крупные первыми."""
    h2f = collections.defaultdict(list)
    for i in sh.frames():
        a = np.asarray(sh.frame(i), np.uint8)
        if a.shape[-1] == 4 and a[..., 3].max() < 128:
            continue
        h2f[hashlib.blake2b(a.tobytes(), digest_size=16).hexdigest()].append(i)
    g = [v for v in h2f.values() if len(v) > 1]
    g.sort(key=lambda v: (-len(v), v[0]))
    return g, len(h2f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--set", dest="set_name", default="FORESTSWAMP.PCK")
    ap.add_argument("--zoom", type=int, default=3)
    ap.add_argument("--cols", type=int, default=2, help="сколько групп в ряд")
    ap.add_argument("--out", default=os.path.join("art", "_review", "dupes"))
    args = ap.parse_args()

    sh = tf.Sheet(args.sheets, args.set_name)
    groups, uniq = groups_of(sh)
    if not groups:
        print("повторов в наборе нет: все %d кадров разные" % uniq)
        return 0

    z = args.zoom
    fw, fh = sh.fw * z, sh.fh * z
    wide = max(len(g) for g in groups)
    lab, pad, gap = 20, 6, 10
    blk_w = pad + wide * (fw + pad)
    blk_h = lab + fh + pad
    rows = (len(groups) + args.cols - 1) // args.cols
    head = 34
    W = args.cols * blk_w + (args.cols + 1) * gap
    H = head + rows * (blk_h + gap) + gap
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((gap, 8), "%s - %d групп близнецов, %d кадров лишних из %d; разных картинок %d"
           % (sh.name, len(groups), sum(len(g) - 1 for g in groups), sh.lay["count"], uniq),
           fill=(255, 220, 0), font=font(15))

    for k, g in enumerate(groups):
        r, c = divmod(k, args.cols)
        x0 = gap + c * (blk_w + gap)
        y0 = head + r * (blk_h + gap)
        d.rectangle([x0, y0, x0 + blk_w, y0 + blk_h], fill=CELL_BG)
        d.text((x0 + pad, y0 + 3), "x%d   %s" % (len(g), " = ".join(str(i) for i in g)),
               fill=(150, 255, 150), font=font(13))
        for j, i in enumerate(g):
            fr = sh.frame(i).resize((fw, fh), Image.NEAREST)
            im.paste(fr, (x0 + pad + j * (fw + pad), y0 + lab), fr)

    os.makedirs(args.out, exist_ok=True)
    p = os.path.join(args.out, "%s_inside.png" % os.path.splitext(sh.name)[0])
    im.save(p)
    print("%s: %d групп, %d лишних кадров -> %s" % (sh.name, len(groups),
          sum(len(g) - 1 for g in groups), p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
