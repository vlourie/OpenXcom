#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000280: листы разбора в art/_review/xp280 - кадры, поле 4x4 вперемешку с 3 и 5, срез салуна WESTOWN_SALOON.
Кадры вариантов берёт из art/tickets/t280/cand (их делает t280_probe.py). В мод ничего не ставится.

    py -3.13 tools\hdart\t280_sheet.py
"""
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)
import ticket_scene as ts  # noqa: E402

REV = ROOT / "art" / "_review" / "xp280"
CAND = ROOT / "art" / "tickets" / "t280" / "cand"
BG = (26, 26, 30)


def cand(n):
    return Image.open(CAND / ("MOUNTSAND_%s.png" % n)).convert("RGBA")


def field(frames, n=4, seed=7, weights=(1, 2, 1)):
    """Поле n x n клеток: на каждую клетку кадр из frames (3, 4, 5) по детерминированному жребию, z-порядок как в движке."""
    rng = np.random.RandomState(seed)
    pick = rng.choice(3, size=(n, n), p=np.array(weights, float) / sum(weights))
    wd, ht = n * 2 * 64 + 128, n * 2 * 32 + 160
    im = Image.new("RGBA", (wd, ht), BG + (255,))
    ox = n * 64
    for s in range(2 * n - 1):
        for y in range(n):
            x = s - y
            if 0 <= x < n:
                im.alpha_composite(frames[pick[y, x]], (ox + (x - y) * 64, 20 + (x + y) * 32))
    return im.crop((0, 20, wd, ht - 20))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sc = ts.Scene()
    REV.mkdir(parents=True, exist_ok=True)
    c = {f: sc.classic("MOUNTSAND", f) for f in (3, 4, 5)}
    h = {f: sc.hd("MOUNTSAND", f) for f in (3, 4, 5)}
    mud5 = sc.hd("MOUNTMUD", 5)
    # --- лист кадров
    names4 = ["4_A_grain3", "4_B_grit_mud5", "4_C_sandv1_tone"]
    names5 = ["5_A_copy_MOUNTMUD5", "5_B_grain3", "5_C_sandv1_tone"]
    panels = [("классика 4", c[4]), ("HD сейчас 4", h[4])] + [("вариант " + n, cand(n)) for n in names4]
    panels += [("классика 5", c[5]), ("HD сейчас 5", h[5])] + [("вариант " + n, cand(n)) for n in names5]
    panels += [("классика 3 (годный)", c[3]), ("HD 3 (годный)", h[3]), ("классика 6", sc.classic("MOUNTSAND", 6)),
               ("HD 6 (годный)", sc.hd("MOUNTSAND", 6))]
    ims = []
    for t, im in panels:
        b = Image.new("RGBA", (128, 160), (110, 110, 116, 255))
        b.alpha_composite(im.resize((128, 160), Image.NEAREST) if im.width != 128 else im)
        ims.append((t, b.crop((0, 92, 128, 160)).resize((384, 204), Image.LANCZOS)))
    ts.sheet([(t, i) for t, i in ims], REV / "t280_frames.png", cols=5)
    # --- поле 4x4: классика / сейчас / варианты (4 и 5 из одного набора вариантов: A,B,C с 5_A)
    sets = [("классика", [c[3], c[4], c[5]]), ("HD сейчас (3, 4, 5)", [h[3], h[4], h[5]])]
    for n4, n5 in zip(names4, ["5_A_copy_MOUNTMUD5", "5_A_copy_MOUNTMUD5", "5_A_copy_MOUNTMUD5"]):
        sets.append(("вариант %s + %s" % (n4, n5), [h[3], cand(n4), cand(n5)]))
    sets.append(("вариант 4_B + 5_B_grain3", [h[3], cand("4_B_grit_mud5"), cand("5_B_grain3")]))
    panels = []
    for t, fr in sets:
        k = 1.0 if t == "классика" else 1.0
        f = field(fr, 4, 7)
        if t == "классика":
            f = field([x.resize((128, 160), Image.NEAREST) for x in fr], 4, 7)
        panels.append((t, f))
    ts.sheet(panels, REV / "t280_field4x4.png", cols=2)
    # --- срез салуна: те же клетки в игровой раскладке
    found = ts.find_cells(sc, "WESTOWN_DESERT", "WESTOWN_SALOON", [("MOUNTSAND", 4)])
    box = tuple(v * 4 for v in ts.window(found, 190, 120, 1))
    over = {}
    pan = []
    for t, ov in [("классика", None), ("HD сейчас", {})] + [("вариант %s + 5_A" % n, {("MOUNTSAND", 4): cand(n), ("MOUNTSAND", 5): cand("5_A_copy_MOUNTMUD5")}) for n in names4]:
        im, _ = sc.render("WESTOWN_DESERT", "WESTOWN_SALOON", "classic" if ov is None else "hd", override=ov, k=4)
        pan.append((t, ts.crop_pad(im, box)))
    ts.sheet(pan, REV / "t280_saloon.png", cols=2)
    print("листы:", REV)


if __name__ == "__main__":
    main()
