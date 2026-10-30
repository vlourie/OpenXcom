#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000435: комната CULTHOUSE08 (этаж z=1) - классика | HD сейчас | кандидаты t435 (art/tickets/t435/cand/435 + семья).
Только чтение, в мод не пишет. Лист - art/_review/tickets_2026-10-30/t435_cand_scene.png.

    py -3.13 tools\hdart\t435_scene.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from PIL import Image                                  # noqa: E402

import ticket_scene as ts                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
CAND = os.path.join(ROOT, "art", "tickets", "t435", "cand", "435")
OUT = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30", "t435_cand_scene.png")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sc = ts.Scene()
    ov = {}
    for fn in sorted(os.listdir(CAND)):
        if fn.endswith(".png"):
            s, f = fn[:-4].rsplit("_", 1)
            ov[(s, int(f))] = Image.open(os.path.join(CAND, fn)).convert("RGBA")
    keys = [("CULTDECOR", 22), ("CULTEXTRA", 31), ("CULTDECOR", 51)]
    found = [f for f in ts.find_cells(sc, "STR_LOC_CRACKHOUSE", "CULTHOUSE08", keys) if f[3] == 1]
    print("клеток на z=1:", [(f[0], f[1], f[4]) for f in found])
    found = [(f[0], f[1], tuple(v * 4 for v in f[2]), f[3], f[4]) for f in found]
    box = ts.window(found, 150, 110, 4)
    panels = []
    for title, mode, o in (("классика x4", "classic", None), ("HD сейчас", "hd", None), ("HD: кандидаты t435", "hd", ov)):
        im, _f = sc.render("STR_LOC_CRACKHOUSE", "CULTHOUSE08", mode, override=o, k=4, maxz=1)
        panels.append((title, ts.crop_pad(im, box)))
    ts.sheet(panels, OUT, cols=1)
    print("лист:", OUT)


if __name__ == "__main__":
    main()
