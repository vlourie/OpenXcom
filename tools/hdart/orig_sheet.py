#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Лист оригинала набора: все кадры увеличенными, с номерами.

Нужен, чтобы глазами разобрать набор целиком - что в нём есть, что повторяется, что
зеркально. Кадры увеличиваются ближайшим соседом: это ПРОСМОТР оригинала, здесь важно
видеть каждый пиксель как он есть, а не сглаженную картинку (в конвейер генерации
nearest подавать нельзя - R-004, но это не конвейер).

    py -3 tools/hdart/orig_sheet.py --set ICEKING_RUINS.PCK
    py -3 tools/hdart/orig_sheet.py --set POLAR.PCK --scale 4 --cols 8

Фон тёмный, как пол в бою: на шахматке не видно ни остатка подложки, ни потери
плотности по краю (R-041).
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


def font(size=13):
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="set_name", required=True)
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--out", default=os.path.join("art", "_review", "orig"))
    args = ap.parse_args()

    name = args.set_name if args.set_name.endswith(".PCK") else args.set_name + ".PCK"
    sh = tf.Sheet(args.sheets, name)
    n = sh.lay["count"]
    cw, ch = sh.fw * args.scale, sh.fh * args.scale
    cols = args.cols
    rows = (n + cols - 1) // cols
    head, foot, gap = 26, 17, 6

    im = Image.new("RGB", (10 + cols * (cw + gap), head + rows * (ch + foot) + 10), BG)
    dr = ImageDraw.Draw(im)
    dr.text((10, 6), "%s - %d кадров, оригинал x%d" % (name, n, args.scale),
            fill=(255, 220, 0), font=font(15))
    empty = 0
    for i in range(n):
        r, c = divmod(i, cols)
        x = 10 + c * (cw + gap)
        y = head + r * (ch + foot)
        cell = Image.new("RGBA", (cw, ch), FLOOR + (255,))
        fr = sh.frame(i).convert("RGBA")
        cell.alpha_composite(fr.resize((cw, ch), Image.NEAREST))
        im.paste(cell.convert("RGB"), (x, y))
        blank = tf.alpha_box(sh.frame(i)) is None
        if blank:
            empty += 1
        dr.text((x + 2, y + ch + 2), "%d%s" % (i, "  пусто" if blank else ""),
                fill=(120, 120, 120) if blank else (255, 220, 0), font=font(12))
    os.makedirs(args.out, exist_ok=True)
    p = os.path.join(args.out, "%s_x%d.png" % (name[:-4], args.scale))
    im.save(p)
    print("кадров %d (пустых %d), размер кадра %dx%d -> %dx%d"
          % (n, empty, sh.fw, sh.fh, cw, ch))
    print("лист: %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
