#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000486: листы «классика / сейчас / вариант» (все четыре кадра) и крупный лист краёв. В мод не пишет.

    py -3.13 tools/hdart/t486_regen_sheet.py            листы в art/_review/tickets_2026-11-04/
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)
import obj_series as osr                              # noqa: E402
import ticket_scene as ts                             # noqa: E402

REV = os.path.join(ROOT, "art", "_review", "tickets_2026-11-04")
SRC = os.path.join(ROOT, "art", "tickets", "t486_regen")
BG = (58, 64, 72, 255)
VARS = [v for v in ("a", "b") if os.path.exists(os.path.join(SRC, v, "IDT_FARM_19.png"))]


def on(im, bg=BG):
    b = Image.new("RGBA", im.size, bg)
    b.alpha_composite(im.convert("RGBA"))
    return b


def whole(sc, get, k, members):
    """Составной из кадров get(f) (128x160) на полотне 48x48 клеток x4."""
    im = Image.new("RGBA", (48 * 4, 48 * 4), (0, 0, 0, 0))
    pos = {19: (0, 0), 18: (16, 8), 15: (16, 0), 14: (0, 8)}
    for f in k:
        im.alpha_composite(get(f), (pos[f][0] * 4, pos[f][1] * 4))
    return im


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sc = ts.Scene()
    cols = [("классика", lambda f: sc.classic("IDT_FARM", f)), ("сейчас", lambda f: sc.hd("IDT_FARM", f))]
    for v in VARS:
        cols.append(("вариант " + v, (lambda vv: lambda f: Image.open(
            os.path.join(SRC, vv, "IDT_FARM_%d.png" % f)).convert("RGBA"))(v)))
    panels = []
    order = (19, 18, 15, 14)
    for f in order:
        for name, get in cols:
            panels.append(("IDT_FARM:%d %s" % (f, name), on(get(f)).resize((256, 320), Image.NEAREST)))
    ts.sheet(panels, os.path.join(REV, "xp486_regen_sheet.png"), cols=len(cols))
    # целиком: лестница из двух клеток, левая (19+18) и правая зеркальная (15+14), крупно x2
    panels = []
    for name, get in cols:
        panels.append(("лестница 19+18 %s" % name, on(whole(sc, get, (19, 18), None)).resize((384, 384), Image.NEAREST)))
    for name, get in cols:
        panels.append(("лестница 15+14 %s" % name, on(whole(sc, get, (15, 14), None)).resize((384, 384), Image.NEAREST)))
    ts.sheet(panels, os.path.join(REV, "xp486_regen_whole.png"), cols=len(cols))


if __name__ == "__main__":
    main()
