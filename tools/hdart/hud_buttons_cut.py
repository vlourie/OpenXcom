#!/usr/bin/env python3
"""Cuts the painted battle-panel buttons (hud_panel_pilot.py) down to the button alone, for the game.

The model keeps the button's sign but not its place: the brass plate comes out a little smaller and off-centre,
with the wall round it (wood, a lantern). The plate is found by its colour (bright brass, the connected patch
nearest the picture's middle; the engraved sign inside it is part of it), cut to its box and stretched to the key's
own proportions at SCALE times the classic size -> <out>/<name>.png, plus <out>/_cut_sheet.png to look at.

    E:/OpenXCom/tools/hdart/.venv/Scripts/python.exe -I E:/OpenXCom/tools/hdart/hud_buttons_cut.py
"""
import argparse
import hashlib
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from hud_panel_pilot import BUTTONS  # noqa: E402

SCALE = 8    # the cut button: this many times the key's classic size (the game shrinks it to its k, at most 4)

# boxes found by eye, for paintings whose wood is light and warm enough to pass for brass (the colour search walks
# off into it): name -> (the painting's sha256, first 16 hex; the box). A painting drawn again has another hash and
# is searched as usual
BOX = {
    "links": ("86373d92c3847f73", (168, 94, 466, 276)),
    "reserve_auto": ("07c500215c090673", (42, 40, 330, 228)),
}


def plate_mask(rgb, coloured):
    """Where the picture is the button's face: brass (warm, bright), or for a coloured key its enamel too."""
    a = rgb.astype(np.int32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = (r * 3 + g * 6 + b) // 10
    # brass runs from dark orange in shadow (85,43,8) to near white in the highlights, the engraving is filled with
    # neutral black (10,9,5); the mahogany is red through and through, lit or in shadow (127,31,9), (14,1,0):
    # green under a third of red. So: green at least 0.42 of red, at any brightness
    brass = g * 100 >= r * 42
    if coloured:
        brass |= (lum > 30) & ((g > r + 25) | (r > g * 2))             # green or red enamel
    return brass


def run_round(frac, mid, limit):
    """The run of indices round `mid` where the (smoothed) share of brass stays above `limit`."""
    f = np.convolve(frac, np.ones(5) / 5, mode="same")
    lo = hi = mid
    while lo > 0 and f[lo - 1] > limit:
        lo -= 1
    while hi < len(f) - 1 and f[hi + 1] > limit:
        hi += 1
    return lo, hi + 1


def find_plate(img, coloured, limit=0.25):
    """The plate's box: the columns round the middle where the middle band of rows is mostly brass (the dark sign
    only thins it), then the rows round the middle within those columns. A colour flood fill does not do: the
    lamp-lit wood touches the plate, and an engraved ring cuts the middle off it."""
    rgb = np.asarray(img.convert("RGB"))
    h, w = rgb.shape[:2]
    mask = plate_mask(rgb, coloured)
    # the lantern's glass is pale and bluish (brass's highlights are too, but small): out, so the run of columns
    # does not walk from the plate into the lamp
    a = rgb.astype(np.int32)
    glass = (a[..., 2] * 100 > a[..., 1] * 60) & (a[..., 0] + a[..., 1] + a[..., 2] > 450)
    m = (mask & ~glass).astype(np.float32)
    # the columns over most of the height: a broad dark sign (the map's) fills the middle band, not the plate above
    # and below it
    band = m[int(h * 0.15):int(h * 0.85)]
    x0, x1 = run_round(band.mean(axis=0), w // 2, limit)
    y0, y1 = run_round(m[:, x0:x1].mean(axis=1), h // 2, limit)
    if x1 - x0 < w // 8 or y1 - y0 < h // 8:
        return None
    # the shadow the plate casts is neutral black like the engraving, so the box takes it in: trim each edge while
    # its line holds little lit brass (the plate's own rim is lit all along)
    lum = rgb.astype(np.int32) @ np.array([3, 6, 1]) // 10
    lit = (mask & (lum > 40)).astype(np.float32)
    while x1 - x0 > w // 8 and lit[y0:y1, x1 - 1].mean() < limit:
        x1 -= 1
    while x1 - x0 > w // 8 and lit[y0:y1, x0].mean() < limit:
        x0 += 1
    while y1 - y0 > h // 8 and lit[y1 - 1, x0:x1].mean() < limit:
        y1 -= 1
    while y1 - y0 > h // 8 and lit[y0, x0:x1].mean() < limit:
        y0 += 1
    # the lantern's bracket is brass too and can join the run on the left: the plate's left edge is where wood turns
    # to brass down the plate's whole height, which no part of the lamp does
    r0, r1 = y0 + (y1 - y0) // 6, y1 - (y1 - y0) // 6
    step = 6
    edge = (mask[r0:r1, step:w // 2] & ~mask[r0:r1, :w // 2 - step]).mean(axis=0)
    edge = np.convolve(edge, np.ones(3) / 3, mode="same")
    # (only right of the run's own edge; the lamp-lit wood next to the plate passes for brass in places, 0.3 is enough)
    lo = max(x0 - step, 0)
    if lo < len(edge):
        best = lo + int(np.argmax(edge[lo:]))
        if edge[best] > 0.3:
            x0 = best + step - 2
    return x0, y0, x1, y1


def find_framed(img, limit=0.72, cell=4):
    """A coloured key's plate: the biggest box whose four edges run along lit brass - the frame round the enamel.
    Its red can't be told from the mahogany's by colour, the brass frame can. Searched on a grid of `cell` pixels."""
    rgb = np.asarray(img.convert("RGB"))
    a = rgb.astype(np.int32)
    lum = (a[..., 0] * 3 + a[..., 1] * 6 + a[..., 2]) // 10
    glass = (a[..., 2] * 100 > a[..., 1] * 60) & (a[..., 0] + a[..., 1] + a[..., 2] > 450)
    m = plate_mask(rgb, False) & (lum > 40) & ~glass
    h, w = m.shape
    gh, gw = h // cell, w // cell
    g = m[:gh * cell, :gw * cell].reshape(gh, cell, gw, cell).mean(axis=(1, 3)) > 0.3
    gi = g.astype(np.int32)
    rows = np.concatenate([np.zeros((gh, 1), np.int32), np.cumsum(gi, axis=1)], axis=1)   # along x
    cols = np.concatenate([np.zeros((1, gw), np.int32), np.cumsum(gi, axis=0)], axis=0)   # along y
    best, box = 0, None
    min_w, min_h = gw // 3, gh // 3
    x0s = np.arange(gw)[:, None]
    x1s = np.arange(gw)[None, :]
    span = np.maximum(x1s - x0s + 1, 1)   # the cells x0..x1 inclusive
    for y0 in range(gh):
        for y1 in range(y0 + min_h, gh):
            top = (rows[y0][1:][None, :] - rows[y0][:-1][:, None]) / span
            bot = (rows[y1][1:][None, :] - rows[y1][:-1][:, None]) / span
            side = (cols[y1 + 1] - cols[y0]) / (y1 - y0 + 1)
            ok = (top >= limit) & (bot >= limit) & (side[:, None] >= limit) & (side[None, :] >= limit) & (x1s - x0s >= min_w)
            if not ok.any():
                continue
            area = np.where(ok, (x1s - x0s) * (y1 - y0), 0)
            i = int(np.argmax(area))
            if area.flat[i] > best:
                best = area.flat[i]
                box = (i // gw * cell, y0 * cell, (i % gw + 1) * cell, (y1 + 1) * cell)
    if box is None:
        return None
    # the frame's lower edge lies in its own shadow, too dim for the search: lower the box while the row under it
    # is still mostly brass, dim or not (the wood under the frame is not), by at most an eighth of its height
    x0, y0, x1, y1 = box
    dim = plate_mask(rgb, False) & (lum > 18)
    grow = 0
    while y1 < h and grow < (y1 - y0) // 8 and dim[y1, x0:x1].mean() > 0.55:
        y1 += 1
        grow += 1
    return x0, y0, x1, y1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.path.join(ROOT, "art", "hud_buttons", "pilot2", "brass_ship"))
    ap.add_argument("--out", default=os.path.join(ROOT, "art", "hud_buttons", "cut", "brass_ship"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    from hud_panel_pilot import TINT
    rows = []
    for name, (_, _, kw, kh) in BUTTONS.items():
        path = os.path.join(a.src, name + ".png")
        if not os.path.exists(path):
            continue
        img = Image.open(path).convert("RGB")
        with open(path, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()[:16]
        if name in BOX and BOX[name][0] == sha:
            box = BOX[name][1]
        else:
            box = find_framed(img) if name in TINT else find_plate(img, False)
        if box is None:
            print("%s: no plate found" % name)
            continue
        x0, y0, x1, y1 = box
        cut = img.crop(box).resize((kw * SCALE, kh * SCALE), Image.LANCZOS)
        cut.save(os.path.join(a.out, name + ".png"))
        stretch = (kw / kh) / ((x1 - x0) / (y1 - y0))
        print("%-13s plate %4d,%4d - %4d,%4d of %dx%d  stretch x%.2f" % (name, x0, y0, x1, y1, img.width, img.height, stretch))
        rows.append((name, img, box, cut))
    if not rows:
        return
    # the sheet: the painting with the found box, beside the cut
    cw = max(r[1].width for r in rows) + max(r[3].width for r in rows) + 36
    ch = sum(max(r[1].height, r[3].height) + 28 for r in rows)
    sheet = Image.new("RGB", (cw, ch), (12, 12, 12))
    d = ImageDraw.Draw(sheet)
    y = 0
    for name, img, box, cut in rows:
        d.text((6, y + 6), name, fill=(230, 230, 230))
        shown = img.copy()
        ImageDraw.Draw(shown).rectangle(box, outline=(0, 255, 255), width=3)
        sheet.paste(shown, (0, y + 24))
        sheet.paste(cut, (img.width + 24, y + 24))
        y += max(img.height, cut.height) + 28
    sheet.save(os.path.join(a.out, "_cut_sheet.png"))
    print("sheet:", os.path.join(a.out, "_cut_sheet.png"))


if __name__ == "__main__":
    main()
