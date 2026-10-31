#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Листы второго круга XP-000436/437: t436_cand2.png (все кадры POLAR: классика | сейчас | кандидат),
t436_cand2_scene.png (+ _zoom) - блок карты POLAR14 целиком, было | стало; t436_cand2_family.png - семья
(BEACH, FORESTSWAMP_SNOW, ASHEN1). Читает art/tickets/t436/cand/<НАБОР>/."""
import os
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
os.chdir(ROOT)
import ticket_scene as ts  # noqa: E402

CAND = ROOT / "art" / "tickets" / "t436" / "cand"
OUT = ROOT / "art" / "_review" / "tickets_2026-10-30"
TMP = ROOT / "art" / "tickets" / "t436" / "_sheets"
BG = (90, 110, 150, 255)
OFFS = [(16, 0), (0, 8), (32, 8), (16, 16)]
DRAW = [0, 2, 1, 3]
SINGLES = [0, 1, 2, 3, 4, 5, 6, 33, 34, 35, 36, 37, 38, 39]


def cand(s, f):
    p = CAND / s / ("%d.png" % f)
    return Image.open(p).convert("RGBA") if p.exists() else None


def tile(sc, s, f, mode):
    if mode == "classic":
        return sc.classic(s, f)
    if mode == "hd":
        return sc.hd(s, f)
    return cand(s, f)


def canvas(sc, s, frames, mode, k=4):
    """frames - 4 номера (None - нет плитки) -> холст 2x2 (низ без пустого верха)"""
    im = Image.new("RGBA", (64 * k, 56 * k), BG)
    for i in DRAW:
        f = frames[i]
        if f is None:
            continue
        t = tile(sc, s, f, mode)
        if t is None:
            continue
        if t.width != 32 * k:
            t = t.resize((32 * k, 40 * k), Image.NEAREST if mode == "classic" else Image.LANCZOS)
        im.alpha_composite(t, (OFFS[i][0] * k, OFFS[i][1] * k))
    return im.crop((0, 14 * k, 64 * k, 56 * k))


def strip(sc, s, frames, mode, w=96, per=14):
    h = w // 2
    row = Image.new("RGBA", (per * (w + 6) + 6, h + 46), BG)
    for n, f in enumerate(frames):
        t = tile(sc, s, f, mode)
        if t is None:
            continue
        t = t.crop((0, 96, 128, 160)).resize((w, h), Image.NEAREST if mode == "classic" else Image.LANCZOS)
        row.alpha_composite(t, (6 + n * (w + 6), 40))
    return row


def stack(paths, out):
    ims = [Image.open(p).convert("RGB") for p in paths]
    W = max(i.width for i in ims)
    H = sum(i.height for i in ims)
    o = Image.new("RGB", (W, H), (12, 12, 14))
    y = 0
    for i in ims:
        o.paste(i, (0, y))
        y += i.height
    o.save(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sc = ts.Scene()
    TMP.mkdir(parents=True, exist_ok=True)
    MODES = (("classic", "классика"), ("hd", "сейчас"), ("cand", "кандидат"))
    # --- cand2: кластеры
    panels = []
    for b in (40, 44, 48, 52, 56):
        for m, nm in MODES:
            panels.append(("POLAR %d-%d %s" % (b, b + 3, nm), canvas(sc, "POLAR", [b, b + 1, b + 2, b + 3], m)))
    ts.sheet(panels, TMP / "c2_clusters.png", cols=3, width=560)
    sp = []
    for m, nm in MODES:
        sp.append(("POLAR 0-6, 33-39 по кадрам: %s" % nm, strip(sc, "POLAR", SINGLES, m)))
    ts.sheet(sp, TMP / "c2_singles.png", cols=1)
    stack([TMP / "c2_clusters.png", TMP / "c2_singles.png"], OUT / "t436_cand2.png")
    # --- сцена
    ov = {("POLAR", f): cand("POLAR", f) for f in list(range(0, 7)) + list(range(33, 60))}
    old, _ = sc.render("POLAR", "POLAR14", mode="hd", k=4)
    new, _ = sc.render("POLAR", "POLAR14", mode="hd", override=ov, k=4)
    W = 1500
    big = [("POLAR14 целиком: было", old), ("POLAR14 целиком: стало (кандидат, все кадры POLAR)", new)]
    ts.sheet([(t, im.resize((W, int(im.height * W / im.width)), Image.LANCZOS)) for t, im in big],
             OUT / "t436_cand2_scene.png", cols=1)
    # увеличенный участок: где кластеры 44-51 и 52-55 и проталины
    keys = list(ov)
    _x, found = sc.render("POLAR", "POLAR14", mode="classic", k=4, marks=set(keys))
    sel = [f for f in found if f[1] in (44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 5, 2)]
    xs = [(f[2][0] + f[2][2]) / 2 for f in sel]
    ys = [(f[2][1] + f[2][3]) / 2 for f in sel]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    box = (int(cx - 700), int(cy - 380), int(cx + 700), int(cy + 380))
    ts.sheet([("участок POLAR14: было", ts.crop_pad(old, box)), ("участок POLAR14: стало", ts.crop_pad(new, box))],
             OUT / "t436_cand2_scene_zoom.png", cols=1)
    # --- семья
    fp = []
    for s, cl in (("BEACH", ((52, 53, 54, 55), (48, 49, 50, 51), (40, 41, 42, 43))),
                  ("FORESTSWAMP_SNOW", ((40, 41, 42, 43), (36, 37, 38, 39), (None, 30, 31, 32))),
                  ("ASHEN1", ((52, 53, 54, 55), (56, 57, 58, 59)))):
        for fr in cl:
            for m, nm in MODES:
                if s == "ASHEN1" and m == "classic":
                    pass
                fp.append(("%s %s %s" % (s, "-".join(str(x) for x in fr if x is not None), nm), canvas(sc, s, list(fr), m)))
    ts.sheet(fp, TMP / "c2_fam_clusters.png", cols=3, width=480)
    fs = []
    for s, frs in (("BEACH", [0, 1, 2, 3, 4, 5, 6, 33, 34, 35, 36, 37, 38, 39]),
                   ("FORESTSWAMP_SNOW", [0, 23, 24, 25, 26, 27, 28, 29]),
                   ("ASHEN1", [5, 6])):
        for m, nm in MODES:
            fs.append(("%s %s: %s" % (s, ",".join(map(str, frs)), nm), strip(sc, s, frs, m, per=len(frs))))
    ts.sheet(fs, TMP / "c2_fam_singles.png", cols=1)
    stack([TMP / "c2_fam_clusters.png", TMP / "c2_fam_singles.png"], OUT / "t436_cand2_family.png")
    print("листы второго круга готовы")


if __name__ == "__main__":
    main()
