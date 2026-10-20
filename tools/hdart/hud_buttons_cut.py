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
    # iron_bone keys5b: the green field's rise outdoes the iron frame round it
    "reserve_none": ("0db812acc1336d73", (33, 38, 335, 232)),
    # iron_bone keys5: a near square plate on the oak, the oak strip on the left passes the rim test
    "options": ("48f9861009734a16", (120, 22, 507, 323)),
}


STYLE = "brass_ship"   # whose metal plate_mask looks for (--style)


def metal_mask(r, g, b, lum):
    """The style's plate metal against its wall (medians measured on the pilot keys, plate | wall)."""
    if STYLE == "space_lilac":
        # lilac alloy (108,83,157) on neutral graphite (40,38,56): red and blue both above green
        return (r * 100 >= g * 115) & (b * 100 >= g * 130) & (lum > 50)
    if STYLE == "silver":
        # sterling (94,104,115) on black lacquer (10,5,4): any light, neutral or cool
        return lum > 60
    if STYLE == "iron_bone":
        # wrought iron (50,36,29) on charred oak (28,15,9): the iron is grey, the oak orange; the iron's lit bevel
        # warms up (176,100,60), the lit oak stays orange (180,84,28)
        return ((b * 100 >= r * 45) & (lum > 18)) | ((g * 100 >= r * 55) & (lum > 80))
    if STYLE == "deep_bronze":
        # verdigris bronze (50,94,71) on the same copper sheets in shadow (18,33,23): only brighter
        return lum > 45
    # brass runs from dark orange in shadow (85,43,8) to near white in the highlights, the engraving is filled with
    # neutral black (10,9,5); the mahogany is red through and through, lit or in shadow (127,31,9), (14,1,0):
    # green under a third of red. So: green at least 0.42 of red, at any brightness
    return g * 100 >= r * 42


# the later styles (keys5 run) ask for the button face filling the picture: the plate nearly fills the frame, with
# a thin margin of whatever surface round it, so its box is the rim and not the colour
RIM_STYLES = ("space_lilac", "silver", "iron_bone", "deep_bronze")
RIM_BAND = 0.2      # how far in from each side of the frame the plate's edge may lie
RIM_STRONG = 0.55   # a rise this strong against the strongest past the dark point counts; the first one wins
RIM_DARK = 0.12     # how near the band's darkest a point counts as dark (rim_side's `nearest`)
RIM_BY_COLOUR = ("space_lilac",)   # whose plate is told from its wall by metal_mask, not by brightness
SKEW_MAX = 0.035    # find_rim's skew above this: the plate is a trapezoid, draw it again (a tall key: by eye -
                    # its sides are too short for the measure)
RIM_FILL = 0.8      # a rim style's plate narrower than this share of the picture stands on the wall: draw it again


def rim_side(profile, n, nearest=False):
    """Where the plate starts in profile[:n] (the profile runs from the frame's side inward). The plate is lighter
    than its dark rim and the shadow it casts, whatever light falls on the wall: from the band's darkest point (or,
    `nearest`, the dark point nearest the plate - a lit strip of wall may lie between the frame's side and the gap
    round the plate) inward, the first strong rise."""
    if STYLE in RIM_BY_COLOUR:
        # the profile is the share of plate-coloured pixels: the plate starts where they are the most
        over = np.where(profile[:n] >= 128)[0]
        return int(over[0]) if len(over) else 0
    if nearest:
        lo, hi = float(profile[:n].min()), float(profile[:n].max())
        v = int(np.where(profile[:n] <= lo + RIM_DARK * (hi - lo))[0][-1])
    else:
        v = int(np.argmin(profile[:n]))
    g = np.diff(profile[v:n + 1])
    if len(g) == 0 or g.max() <= 0:
        return v
    return v + int(np.where(g >= RIM_STRONG * g.max())[0][0]) + 1


def find_rim(img, aspect):
    """The plate's box: on each side where the plate starts (rim_side) in the outer band of the frame, on the
    profile averaged over the middle half of the other axis (so no corner screws and no sign). Top and bottom have
    two guesses each (darkest, nearest dark): the pair that gives the key's own proportions (`aspect`, width to
    height) best wins. Also the skew: how far the left and right edges of the upper part and the lower part
    disagree, of the width - a plate drawn as a trapezoid (seen from below) leaves wall in two corners of any box,
    and is to be drawn again."""
    from PIL import ImageFilter
    lum = np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(1.5))).astype(np.float32)
    if STYLE in RIM_BY_COLOUR:
        # a plate sunk into a grey bezel: the bezel is lighter than the gap round it, the plate's colour alone tells
        rgb = np.asarray(img.filter(ImageFilter.GaussianBlur(1.5))).astype(np.int32)
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        lum = metal_mask(r, g, b, (r + g + b) // 3).astype(np.float32) * 255
    h, w = lum.shape
    bx, by = int(w * RIM_BAND), int(h * RIM_BAND)

    def xs(r0, r1):
        prof = lum[r0:r1].mean(axis=0)
        return rim_side(prof, bx), w - rim_side(prof[::-1], bx)
    x0, x1 = xs(h // 4, 3 * h // 4)
    cols = lum[:, w // 4:3 * w // 4].mean(axis=1)
    tops = {rim_side(cols, by, k) for k in (False, True)}
    bottoms = {h - rim_side(cols[::-1], by, k) for k in (False, True)}
    y0, y1 = min(((t, b) for t in tops for b in bottoms if b - t > h // 3),
                 key=lambda p: abs(np.log((x1 - x0) / float(p[1] - p[0]) / aspect)), default=(0, h))
    ux0, ux1 = xs(y0 + (y1 - y0) // 4, y0 + 3 * (y1 - y0) // 8)
    lx0, lx1 = xs(y0 + 5 * (y1 - y0) // 8, y0 + 3 * (y1 - y0) // 4)
    skew = (abs(ux0 - lx0) + abs(ux1 - lx1)) / float(w)
    return (x0, y0, x1, y1), skew


def plate_mask(rgb, coloured):
    """Where the picture is the button's face: the style's metal (brass: warm, bright), or for a coloured key its
    enamel too."""
    a = rgb.astype(np.int32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = (r * 3 + g * 6 + b) // 10
    brass = metal_mask(r, g, b, lum)
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
    ap.add_argument("--style", default="brass_ship", help="whose plate metal to look for (metal_mask)")
    a = ap.parse_args()
    global STYLE
    STYLE = a.style
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
        skew = 0.0
        if name in BOX and BOX[name][0] == sha:
            box = BOX[name][1]
        elif STYLE in RIM_STYLES:
            box, skew = find_rim(img, kw / float(kh))
            if kh > kw:
                skew = 0.0
        else:
            box = find_framed(img) if name in TINT else find_plate(img, False)
        if box is None:
            print("%s: no plate found" % name)
            continue
        x0, y0, x1, y1 = box
        cut = img.crop(box).resize((kw * SCALE, kh * SCALE), Image.LANCZOS)
        cut.save(os.path.join(a.out, name + ".png"))
        stretch = (kw / kh) / ((x1 - x0) / (y1 - y0))
        # a rim style's plate is to fill the picture: a small one stands on the wall, its proportions are not the
        # key's - draw it again
        small = STYLE in RIM_STYLES and (x1 - x0) < RIM_FILL * img.width
        print("%-13s plate %4d,%4d - %4d,%4d of %dx%d  stretch x%.2f  skew %.3f%s%s" % (
            name, x0, y0, x1, y1, img.width, img.height, stretch, skew, "  TRAPEZOID" if skew > SKEW_MAX else "",
            "  SMALL" if small else ""))
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
