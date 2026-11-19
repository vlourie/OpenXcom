#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000486: крупный лист краёв кандидата (x8, тёмный и светлый фон: кайма подложки видна на светлом).
Составная лестница 19+18 и зеркальная 15+14, участки: верхние ступени, просветы между ступенями, низ у пола.

    py -3.13 tools/hdart/t486_regen_edges.py a
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)
import ticket_scene as ts                             # noqa: E402

POS = {19: (0, 0), 18: (16, 8), 15: (16, 0), 14: (0, 8)}
Z = 8


def whole(var, order):
    im = Image.new("RGBA", (192, 192), (0, 0, 0, 0))
    for f in order:
        t = Image.open(os.path.join(ROOT, "art", "tickets", "t486_regen", var, "IDT_FARM_%d.png" % f)).convert("RGBA")
        im.alpha_composite(t, (POS[f][0] * 4, POS[f][1] * 4))
    return im


def crop(im, box, bg):
    b = Image.new("RGBA", im.size, bg)
    b.alpha_composite(im)
    return b.crop(box).convert("RGB").resize(((box[2] - box[0]) * Z, (box[3] - box[1]) * Z), Image.NEAREST)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    var = sys.argv[1]
    a, b = whole(var, (19, 18)), whole(var, (15, 14))
    spots = [("19+18 верх", a, (0, 0, 64, 56)), ("19+18 просветы", a, (56, 64, 120, 120)),
             ("19+18 низ у пола", a, (112, 140, 192, 192)),
             ("15+14 верх", b, (128, 0, 192, 56)), ("15+14 просветы", b, (72, 64, 136, 120)),
             ("15+14 низ у пола", b, (0, 140, 80, 192))]
    for tag, bg in (("dark", (40, 44, 52, 255)), ("light", (214, 218, 222, 255))):
        panels = [(n + " " + tag, crop(im, bx, bg)) for n, im, bx in spots]
        ts.sheet(panels, os.path.join(ROOT, "art", "_review", "tickets_2026-11-04",
                                      "xp486_regen_edges_%s_%s.png" % (var, tag)), cols=3, width=560)


if __name__ == "__main__":
    main()
