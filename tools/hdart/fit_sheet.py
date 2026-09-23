#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Лист приёмки набора: оригинал против того, что реально легло в пак.

Судим по файлу, который читает игра - кадры пака, а не painted_x4.png (грабли R-019).
Фон тёмный, как пол боя, иначе остаток подложки не виден (грабли R-041).

    py -3 tools/hdart/fit_sheet.py --set CAVEBROWN.PCK --pack <мод>/hd/TERRAIN/CAVEBROWN.PCK
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PIL import Image, ImageDraw, ImageFont            # noqa: E402

import tile_forge as tf                                # noqa: E402

BG = (18, 18, 20)
FLOOR = (38, 34, 30)


def font(size):
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--set", dest="set_name", required=True)
    ap.add_argument("--pack", required=True, help="папка пака с кадрами <N>.png")
    ap.add_argument("--cols", type=int, default=6, help="пар в ряд")
    ap.add_argument("--frames", default="", help="только эти кадры")
    ap.add_argument("--out", default=os.path.join("art", "_review", "fit"))
    args = ap.parse_args()

    sh = tf.Sheet(args.sheets, args.set_name)
    want = [int(x) for x in args.frames.replace(" ", "").split(",") if x] if args.frames else None
    nums = []
    for i in sh.frames():
        if want is not None and i not in want:
            continue
        if os.path.exists(os.path.join(args.pack, "%d.png" % i)):
            nums.append(i)
    if not nums:
        sys.exit("в паке нет ни одного кадра: %s" % args.pack)

    probe = Image.open(os.path.join(args.pack, "%d.png" % nums[0]))
    fw, fh = probe.size
    lab, gap = 15, 6
    cell = 2 * fw + 4
    rows = (len(nums) + args.cols - 1) // args.cols
    head = 30
    W = gap + args.cols * (cell + gap)
    H = head + rows * (lab + fh + gap)
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((gap, 7), "%s - %d кадров; в каждой паре слева оригинал, справа пак"
           % (sh.name, len(nums)), fill=(255, 220, 0), font=font(15))

    for k, i in enumerate(nums):
        r, c = divmod(k, args.cols)
        x = gap + c * (cell + gap)
        y = head + r * (lab + fh + gap)
        d.text((x, y), str(i), fill=(160, 200, 255), font=font(12))
        d.rectangle([x, y + lab, x + cell, y + lab + fh], fill=FLOOR)
        o = sh.frame(i).resize((fw, fh), Image.NEAREST)
        im.paste(o, (x, y + lab), o)
        p = Image.open(os.path.join(args.pack, "%d.png" % i)).convert("RGBA")
        im.paste(p, (x + fw + 4, y + lab), p)

    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, "%s_fit.png" % os.path.splitext(sh.name)[0])
    im.save(out)
    print("%s: %d кадров -> %s  (%dx%d)" % (sh.name, len(nums), out, W, H))
    return 0


if __name__ == "__main__":
    sys.exit(main())
