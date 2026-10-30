#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Листы пилота XP-000436/437: t436_cand.png (классика | сейчас | кандидат по кадрам и кластерам) и
t436_cand_scene.png (участок карты POLAR14 с кластерами: было | стало). Читает art/tickets/t436/cand."""
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
os.chdir(ROOT)
import ticket_scene as ts  # noqa: E402

CAND = ROOT / "art" / "tickets" / "t436" / "cand_pilot"
OUT = ROOT / "art" / "_review" / "tickets_2026-10-30"
BG = (90, 110, 150, 255)
OFFS = [(16, 0), (0, 8), (32, 8), (16, 16)]
DRAW = [0, 2, 1, 3]


def cand(f):
    p = CAND / ("%d.png" % f)
    return Image.open(p).convert("RGBA") if p.exists() else None


def cluster_canvas(sc, base, mode, k=4):
    im = Image.new("RGBA", (64 * k, 56 * k), BG)
    for i in DRAW:
        f = base + i
        if mode == "classic":
            t = sc.classic("POLAR", f)
        elif mode == "hd":
            t = sc.hd("POLAR", f)
        else:
            t = cand(f)
        if t.width != 32 * k:
            t = t.resize((32 * k, 40 * k), Image.NEAREST if mode == "classic" else Image.LANCZOS)
        im.alpha_composite(t, (OFFS[i][0] * k, OFFS[i][1] * k))
    return im.crop((0, 14 * k, 64 * k, 56 * k))


def tiles_row(sc, base, mode):
    row = Image.new("RGBA", (4 * 136, 112), BG)
    for n in range(4):
        f = base + n
        t = sc.classic("POLAR", f) if mode == "classic" else (sc.hd("POLAR", f) if mode == "hd" else cand(f))
        t = t.crop((0, 96, 128, 160)).resize((128, 64), Image.LANCZOS if mode != "classic" else Image.NEAREST)
        row.alpha_composite(t, (n * 136 + 4, 40))
    return row


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sc = ts.Scene()
    panels = []
    for base in (52, 40):
        for mode, nm in (("classic", "классика"), ("hd", "HD сейчас"), ("cand", "кандидат")):
            panels.append(("POLAR %d-%d %s (холст 2x2)" % (base, base + 3, nm), cluster_canvas(sc, base, mode)))
    ts.sheet(panels, OUT / "t436_cand.png", cols=3, width=560)
    # по кадрам
    rows = []
    for base in (52, 40):
        for mode, nm in (("classic", "классика"), ("hd", "сейчас"), ("cand", "кандидат")):
            rows.append(("POLAR %d-%d по кадрам: %s" % (base, base + 3, nm), tiles_row(sc, base, mode)))
    ts.sheet(rows, OUT / "t436_cand_frames.png", cols=1)
    # сцена
    ov = {("POLAR", f): cand(f) for f in list(range(52, 56)) + list(range(40, 44))}
    keys = list(ov)
    _x, found = sc.render("POLAR", "POLAR14", mode="classic", k=4, marks=set(keys))
    old, _ = sc.render("POLAR", "POLAR14", mode="hd", k=4)
    new, _ = sc.render("POLAR", "POLAR14", mode="hd", override=ov, k=4)
    cl, _ = sc.render("POLAR", "POLAR14", mode="classic", k=4)
    sp = [f for f in found if f[1] in (52, 53, 54, 55)]
    bk = [f for f in found if f[1] in (40, 41, 42, 43)]
    sheets = []
    for nm, fs in (("шпиль 52-55", sp), ("блок 40-43", bk)):
        box = ts.window(fs, 150, 80, 4)
        for tag, im in (("было", old), ("стало", new)):
            sheets.append(("%s: %s" % (nm, tag), ts.crop_pad(im, box)))
    ts.sheet(sheets, OUT / "t436_cand_scene.png", cols=2, width=1000)
    # одиночные плитки: камушки 33, 35, проталины 1, 4
    sm = []
    for mode, nm in (("classic", "классика"), ("hd", "сейчас"), ("cand", "кандидат")):
        row = Image.new("RGBA", (4 * 264, 172), BG)
        for n, f in enumerate((33, 35, 1, 4)):
            t = sc.classic("POLAR", f) if mode == "classic" else (sc.hd("POLAR", f) if mode == "hd" else cand(f))
            t = t.crop((0, 96, 128, 160)).resize((256, 128), Image.NEAREST if mode == "classic" else Image.LANCZOS)
            row.alpha_composite(t, (n * 264 + 4, 40))
        sm.append(("POLAR 33, 35 (камушки), 1, 4 (проталины): %s" % nm, row))
    ts.sheet(sm, OUT / "t436_cand_small.png", cols=1)
    print("листы готовы")


if __name__ == "__main__":
    main()
