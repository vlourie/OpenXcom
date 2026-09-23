#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Лист приёмки зеркальных пар: стоит ли рисовать близнеца отдельно.

Кадр и его зеркало - одна и та же вещь, повёрнутая другим боком, и второй заказ модели на
неё уходит впустую. Но "зеркальный" бывает двух разных сортов, и порогом это не решается:
надо смотреть. Лист кладёт в одну строку четыре картинки:

    оригинал i | оригинал j | j, выведенный из нарисованного i | j, нарисованный моделью

Третий столбец - это поворот плюс возврат своего света (mirror_frames.relit_frame). Если он
неотличим от четвёртого, второй заказ был не нужен. Четвёртого может и не быть - тогда
сравнивать не с чем, и это как раз те пары, которые мы ещё не успели потратить.

    py -3 tools/hdart/mirror_sheet.py --set ICEKING_RUINS.PCK
    py -3 tools/hdart/mirror_sheet.py --set POLAR.PCK --thr 40

Фон тёмный нарочно: остаток подложки и потерянная плотность краёв на шахматке не видны
(грабли R-041), а в бою пол именно тёмный.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont             # noqa: E402

import tile_forge as tf                                 # noqa: E402
import mirror_frames as mfr                             # noqa: E402

BG = (18, 18, 20)
FLOOR = (38, 34, 30)
CELL = 168


def font(size=13):
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def on_floor(im, box):
    """Картинка на тёмном полу, вписанная в клетку без искажения пропорций."""
    pad = Image.new("RGBA", (box, box), FLOOR + (255,))
    k = min(box / im.width, box / im.height)
    r = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.NEAREST)
    pad.alpha_composite(r, ((box - r.width) // 2, (box - r.height) // 2))
    return pad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="set_name", required=True)
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--sub", default="lora")
    ap.add_argument("--thr", type=float, default=60.0, help="порог отбора пар")
    ap.add_argument("--out", default=os.path.join("art", "_review", "mirrors"))
    args = ap.parse_args()

    name = args.set_name if args.set_name.endswith(".PCK") else args.set_name + ".PCK"
    sh = tf.Sheet(args.sheets, name)
    d = os.path.join(args.sheets, name, "returned", args.sub)
    pairs = mfr.silhouette_pairs(sh, args.thr)
    if not pairs:
        sys.exit("зеркальных пар не нашлось")

    head, foot = 24, 20
    W = 10 + 4 * (CELL + 6)
    im = Image.new("RGB", (W, head + len(pairs) * (CELL + foot) + 10), BG)
    dr = ImageDraw.Draw(im)
    dr.text((10, 5), "%s - зеркальные пары, %d" % (name, len(pairs)),
            fill=(255, 220, 0), font=font(15))
    names = ["оригинал i", "оригинал j", "j выведен из i", "j нарисован"]
    for k, (i, j, err) in enumerate(pairs):
        y = head + k * (CELL + foot)
        pa = os.path.join(d, "%d.png" % i)
        pb = os.path.join(d, "%d.png" % j)
        drawn_i = Image.open(pa).convert("RGBA") if os.path.exists(pa) else None
        drawn_j = Image.open(pb).convert("RGBA") if os.path.exists(pb) else None
        made = (mfr.relit_frame(drawn_i, sh.frame(i), sh.frame(j))
                if drawn_i is not None else None)
        cells = [sh.frame(i), sh.frame(j), made, drawn_j]
        for c, pic in enumerate(cells):
            x = 10 + c * (CELL + 6)
            if pic is None:
                dr.rectangle([x, y, x + CELL, y + CELL], fill=(30, 26, 26))
                dr.text((x + 8, y + CELL // 2), "нет ответа", fill=(160, 160, 160), font=font())
            else:
                im.paste(on_floor(pic.convert("RGBA"), CELL).convert("RGB"), (x, y))
            dr.text((x + 3, y + 2), names[c], fill=(255, 220, 0), font=font(12))
        diff = ""
        if made is not None and drawn_j is not None and made.size == drawn_j.size:
            a = np.asarray(made, np.float32)[..., :3]
            b = np.asarray(drawn_j, np.float32)[..., :3]
            diff = ", выведенный против нарисованного %.1f из 255" % float(np.abs(a - b).mean())
        dr.text((12, y + CELL + 3),
                "кадры %d и %d, расхождение по свету %.1f%s" % (i, j, err, diff),
                fill=(150, 255, 150), font=font(12))
    os.makedirs(args.out, exist_ok=True)
    p = os.path.join(args.out, "%s_mirrors.png" % name[:-4])
    im.save(p)
    print("пар: %d, лист: %s" % (len(pairs), p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
