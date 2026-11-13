#!/usr/bin/env python3
"""Pilot: the battle panel's buttons painted by the image-editing model (Qwen-Image-Edit-2511), one button a call.

The whole panel at once loses its layout (the model moves and adds buttons), so every button of the mod's own panel
(X-Piratez ICONS_xpb.png) goes in alone, with a little of the panel round it, and is told to keep its shape and its
sign; the first finished button is shown to the model with every other one as the style to match. A few styles ->
art/hud_buttons/pilot/<style>/<button>.png and <style>_sheet.png, for Vitali to choose from. Resumable: a button
already painted is not painted again.

    py -3 tools/gpuq.py add --name hud-panel-pilot -- E:/OpenXCom/tools/hdart/.venv/Scripts/python.exe E:/OpenXCom/tools/hdart/hud_panel_pilot.py
"""
import argparse
import os
import sys
import time

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import photo_ui  # noqa: E402

SOURCE = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Resources", "UnitUI", "ICONS_xpb.png")

# the buttons in ICONS_xpb.png (x, y, w, h), as BattlescapeState lays them out (the panel's top at y 144)
BUTTONS = {
    "unit_up": (48, 144, 32, 16), "unit_down": (48, 160, 32, 16),
    "map_up": (80, 144, 32, 16), "map_down": (80, 160, 32, 16),
    "show_map": (112, 144, 32, 16), "kneel": (112, 160, 32, 16),
    "inventory": (144, 144, 32, 16), "center": (144, 160, 32, 16),
    "next_soldier": (176, 144, 32, 16), "next_stop": (176, 160, 32, 16),
    "show_layers": (208, 144, 32, 16), "options": (208, 160, 32, 16),
    "links": (208, 144, 32, 16),   # the Piratez' links key, in the layers key's place when oxceLinks is on
    "end_turn": (240, 144, 32, 16), "abort": (240, 160, 32, 16),
    "reserve_none": (60, 177, 17, 11), "reserve_snap": (78, 177, 17, 11),
    "reserve_aimed": (60, 189, 17, 11), "reserve_auto": (78, 189, 17, 11),
    "reserve_kneel": (96, 177, 10, 23), "zero_tus": (49, 177, 10, 23),
}
PILOT = ["unit_up", "kneel", "end_turn", "reserve_snap"]

KEEP = ("Redraw the single push-button in the middle of this picture as finished, high-detail game interface art. "
        "It stays one button of exactly the same shape and proportions, filling the picture the same way, with "
        "exactly the same symbol on it in the same place and at the same size - do not change, simplify, replace or "
        "add symbols, no text, no letters. A coloured button keeps its colour. The button is seen straight on from "
        "the front, flat, with no perspective and no tilt, its edges parallel to the picture's edges; its face fills "
        "the whole picture edge to edge, cut off exactly at the button's own outer edge, with no console, wall, "
        "mount or background round it. Only change the materials, the lighting and the quality of the rendering: ")
# (the view was added for the styles after brass_ship: the lilac pilot keys came out tilted in perspective, the iron and
# bronze ones small in a wide wall, and neither can be cut to a key by a box; asked for "a thin margin of the console",
# the model still drew a wide one - the styles after brass_ship no longer name a wall to mount the button on)
MATCH = (" The second picture is another button of the same panel, already finished: make this one in exactly the "
         "same materials, colours, lighting, bevel, wear and scale of detail, as if both were made together.")

STYLES = {
    "salvage_tech": ("a salvaged sci-fi pirate cockpit console: a chunky worn brass push-button, a thick plate with "
                     "chamfered edges and small bolts in its corners, the symbol engraved deep and inked dark, "
                     "scratches and dents, on dark riveted gunmetal plating; dramatic light from the upper left, "
                     "deep soft shadow under the button, high detail, gritty and expensive-looking."),
    "brass_ship": ("a pirate ship's console: a heavy polished brass push-button with bevelled edges and small screws "
                   "in the corners, the symbol deeply engraved into the brass and filled with black enamel, mounted "
                   "on dark oiled mahogany; warm lantern light from the upper left, crisp specular highlights on the "
                   "edges, soft shadow under the button, rich detail."),
    "space_lilac": ("a starship bridge console: a thick push-button machined from satin lilac-violet anodized alloy, "
                    "bevelled edges and small hex screws in the corners, the symbol deeply engraved into the alloy and "
                    "filled with black enamel; cool violet and white light from the upper left, crisp specular "
                    "highlights on the edges, rich detail."),
    "silver": ("a nobleman's console: a heavy polished sterling silver push-button with bevelled edges, a fine "
               "engraved border and small silver screws in the corners, the symbol deeply engraved into the silver "
               "and filled with black niello; cool white light from the upper left, crisp mirror highlights on the "
               "edges, rich detail."),
    "iron_bone": ("a grim pirate captain's console: a heavy push-button of blackened hammered wrought iron with "
                  "bevelled edges and round rivets in the corners, the symbol carved into the iron and inlaid with old "
                  "yellowed bone, pale and clearly readable; warm firelight from the upper left, dull highlights on "
                  "the iron, rich detail."),
    "deep_bronze": ("a deep-sea diving vessel's console: a heavy cast bronze push-button with bevelled edges and "
                    "round rivets in the corners, its raised parts polished and its hollows crusted with teal "
                    "verdigris patina, the symbol deeply engraved and filled with black enamel; cool sea-green light "
                    "from the upper left, crisp highlights on the bronze, rich detail."),
}
# the metal the coloured keys' enamel sits in, per style
FRAME_METAL = {"brass_ship": "brass", "space_lilac": "lilac alloy", "silver": "silver", "iron_bone": "iron",
               "deep_bronze": "bronze", "salvage_tech": "brass"}

# the reserve keys say their state by colour (green: no reserve, red: the rest); the model turns a red key into brass
# unless told, so a coloured key gets its colour spelt out
TINT = {"reserve_none": "green", "reserve_snap": "red", "reserve_aimed": "red", "reserve_auto": "red",
        "reserve_kneel": "red", "zero_tus": "red"}
TINT_HINT = (" The face of this button is glossy deep %s enamel inside the %s frame, the symbol on it black and "
             "clearly readable; the %s colour must stay strong and obvious.")
# (the first set said "pale": four of the six keys came out with black signs anyway, the redrawn one pale - the
# panel looked patched; black is what most of them have)

NEGATIVE = ("blurry, low resolution, pixelated, jpeg artifacts, text, letters, words, logo, watermark, extra buttons, "
            "different symbol, distorted symbol, deformed, messy, noise, flat, plastic, cartoonish, cropped")

# the panel under the keys (--panel): only the surface - the wells, the cards, the bars and the keys are laid on it
# by the game, so the picture must hold no objects of its own
PANEL = {
    "brass_ship": ("Repaint this picture as the flat front of a pirate ship's control console, seen straight on: dark "
                   "oiled mahogany boards running horizontally, fine wood grain, a slim polished brass trim strip along "
                   "the top edge, a few small brass screws in the trim, warm lantern light from the upper left fading "
                   "to the right, rich high detail. Only the surface: no buttons, no screens, no instruments, no "
                   "objects, no text, nothing standing out of it, the whole picture evenly filled edge to edge."),
    "space_lilac": ("Repaint this picture as the flat front of a starship's bridge console, seen straight on: dark "
                    "graphite hull plating in long horizontal panels with fine seam lines and tiny flush hex screws, a "
                    "slim satin lilac-violet anodized trim strip along the top edge, cool violet light from the upper "
                    "left fading to the right, rich high detail. Only the surface: no buttons, no screens, no lights, "
                    "no instruments, no objects, no text, nothing standing out of it, the whole picture evenly "
                    "filled edge to edge."),
    "silver": ("Repaint this picture as the flat front of a nobleman's console, seen straight on: black lacquered "
               "ebony boards running horizontally with a deep mirror gloss and faint grain, a slim polished silver "
               "trim strip with a fine engraved border along the top edge, a few small silver screws in the trim, "
               "cool white light from the upper left fading to the right, rich high detail. Only the surface: no "
               "buttons, no screens, no instruments, no objects, no text, nothing standing out of it, the whole "
               "picture evenly filled edge to edge."),
    "iron_bone": ("Repaint this picture as the flat front of a grim pirate captain's console, seen straight on: "
                  "charred dark oak boards running horizontally, deep cracked grain, a band of blackened hammered "
                  "wrought iron with round rivets along the top edge, warm firelight from the upper left fading to "
                  "the right, rich high detail. Only the surface: no buttons, no skulls, no instruments, no objects, "
                  "no text, nothing standing out of it, the whole picture evenly filled edge to edge."),
    "deep_bronze": ("Repaint this picture as the flat front of a deep-sea diving vessel's console, seen straight on: "
                    "dark copper plates green with age, joined by rows of round rivets, patches of teal verdigris, a "
                    "slim polished bronze trim strip along the top edge, cool sea-green light from the upper left "
                    "fading to the right, rich high detail. Only the surface: no buttons, no portholes, no gauges, no "
                    "instruments, no objects, no text, nothing standing out of it, the whole picture evenly filled "
                    "edge to edge."),
}
PANEL_BASE = (320, 56)   # the panel's classic size

# the wells the items in hand lie in (--well): a brass frame along the picture's edges round a dark floor; the game
# lays the item and its shadow on it, so it stays empty. Two linings of the floor to choose from
WELL = {
    "brass_ship": {
        "leather": "dark worn leather, nearly black, with fine creases",
        "velvet": "deep black-red velvet with a soft sheen",
    },
    "space_lilac": {"carbon": "black carbon fibre weave with a faint violet sheen"},
    "silver": {"velvet": "deep midnight-blue velvet, nearly black, with a soft sheen"},
    "iron_bone": {"leather": "dark oxblood leather, nearly black, scarred and creased"},
    "deep_bronze": {"leather": "dark sea-green leather, nearly black, with fine creases"},
}
# per style: (the frame's metal in one word or two, the frame, the light)
WELL_FRAME = {
    "brass_ship": ("brass", "a thick polished brass frame with bevelled edges and a small brass screw in each corner",
                   "warm light from the upper left, crisp highlights on the brass"),
    "space_lilac": ("anodized alloy", "a thick satin lilac-violet anodized alloy frame with bevelled edges and a "
                    "small hex screw in each corner", "cool violet light from the upper left, crisp highlights on "
                    "the alloy"),
    "silver": ("silver", "a thick polished sterling silver frame with bevelled edges, a fine engraved border and a "
               "small silver screw in each corner", "cool white light from the upper left, crisp mirror highlights on "
               "the silver"),
    "iron_bone": ("iron", "a thick frame of blackened hammered wrought iron with bevelled edges and a round rivet in "
                  "each corner", "warm firelight from the upper left, dull highlights on the iron"),
    "deep_bronze": ("bronze", "a thick cast bronze frame with bevelled edges and a round rivet in each corner, "
                    "polished on top and crusted with teal verdigris in the hollows", "cool sea-green light from the "
                    "upper left, crisp highlights on the bronze"),
}
WELL_PROMPT = ("Repaint this picture as a flat %s picture frame seen exactly straight on, like a scan, with no "
               "perspective and no depth: %s fills the picture right to its edges, nothing outside it, and the flat "
               "area inside the frame is a flat pad of %s, facing the viewer, only a narrow soft shadow along its "
               "upper and left edges; %s, rich high detail. Not a box, not a cabinet, no inner walls, no back wall, "
               "no floor in perspective, no room. The frame and the pad keep exactly the shapes and widths they have "
               "in the picture. Empty: no objects, no items, no text.")
# (the first prompt said "recessed compartment ... sunken floor": all six came out as deep cabinets in perspective,
# a back wall and a floor running away - an item drawn flat can't lie in that)
WELL_BASE = (40, 56)   # the well with its frame, in classic pixels (a hand's 32 x 48 and the frame round it)

MARGIN = 3     # base pixels of the panel kept round a button
SCALE = 16     # the model's input: the button this many times bigger


def crop_button(src, box):
    x, y, w, h = box
    m = MARGIN
    piece = src.crop((x - m, y - m, x + w + m, y + h + m))
    # pixel steps softened a little, so the model reads shapes rather than a grid of squares
    up = piece.resize((piece.width * SCALE, piece.height * SCALE), Image.NEAREST)
    return up.filter(ImageFilter.GaussianBlur(SCALE * 0.35))


def paint_panel(a):
    """Variants of the panel's surface (seeds a.seed, a.seed + 1, ...) -> <out>/<style>/panel_<seed>.png and
    <out>/<style>_panel_sheet.png. The input is a flat dark brown with the light falling from the upper left."""
    pw, ph = PANEL_BASE[0] * 6, PANEL_BASE[1] * 6
    inp = Image.new("RGB", (pw, ph))
    d = ImageDraw.Draw(inp)
    for x in range(pw):
        t = 1.0 - x / pw
        d.line([(x, 0), (x, ph)], fill=(int(40 + 34 * t), int(18 + 14 * t), int(10 + 6 * t)))
    d.rectangle([0, 0, pw, ph // 14], fill=(150, 112, 50))
    painter = None
    for style in [s for s in a.styles.split(",") if s in PANEL]:
        sdir = os.path.join(a.out, style)
        os.makedirs(sdir, exist_ok=True)
        inp.save(os.path.join(sdir, "panel_input.png"))
        paths = []
        for seed in range(a.seed, a.seed + a.panel):
            path = os.path.join(sdir, "panel_%d.png" % seed)
            paths.append(path)
            if os.path.exists(path):
                continue
            if painter is None:
                painter = photo_ui.Painter(a.models, False, a.steps, photoreal=False)
            W, H = photo_ui.target_size(pw, ph, 0.6)
            t0 = time.time()
            rgb = painter.edit([inp.resize((W, H), Image.LANCZOS)], PANEL[style], NEGATIVE, seed, a.steps, a.cfg, W, H)
            Image.fromarray(rgb).resize((pw, ph), Image.LANCZOS).save(path)
            print("%s / panel %d: %.0f s -> %s" % (style, seed, time.time() - t0, path), flush=True)
        sheet = Image.new("RGB", (pw, (ph + 28) * len(paths)), (12, 12, 12))
        dd = ImageDraw.Draw(sheet)
        for i, p in enumerate(paths):
            dd.text((6, i * (ph + 28) + 6), os.path.basename(p), fill=(230, 230, 230))
            sheet.paste(Image.open(p).convert("RGB"), (0, i * (ph + 28) + 24))
        sheet.save(os.path.join(a.out, style + "_panel_sheet.png"))
        print("sheet:", os.path.join(a.out, style + "_panel_sheet.png"), flush=True)


def paint_well(a):
    """Variants of a hand's well, every lining x seeds a.seed .. a.seed + a.well - 1 -> <out>/<style>/well_<lining>_
    <seed>.png and <out>/<style>_well_sheet.png. The input: a brass band along the edges round a near black floor."""
    S = 12
    pw, ph = WELL_BASE[0] * S, WELL_BASE[1] * S
    band = 4 * S
    inp = Image.new("RGB", (pw, ph), (150, 112, 50))
    d = ImageDraw.Draw(inp)
    d.rectangle([band, band, pw - band - 1, ph - band - 1], fill=(22, 14, 10))
    painter = None
    for style in [s for s in a.styles.split(",") if s in WELL]:
        sdir = os.path.join(a.out, style)
        os.makedirs(sdir, exist_ok=True)
        inp.save(os.path.join(sdir, "well_input.png"))
        paths = []
        for lining, words in WELL[style].items():
            for seed in range(a.seed, a.seed + a.well):
                path = os.path.join(sdir, "well_%s_%d.png" % (lining, seed))
                paths.append(path)
                if os.path.exists(path):
                    continue
                if painter is None:
                    painter = photo_ui.Painter(a.models, False, a.steps, photoreal=False)
                W, H = photo_ui.target_size(pw, ph, 0.6)
                t0 = time.time()
                rgb = painter.edit([inp.resize((W, H), Image.LANCZOS)],
                                   WELL_PROMPT % (WELL_FRAME[style][0], WELL_FRAME[style][1], words, WELL_FRAME[style][2]),
                                   NEGATIVE, seed, a.steps,
                                   a.cfg, W, H)
                Image.fromarray(rgb).resize((pw, ph), Image.LANCZOS).save(path)
                print("%s / well %s %d: %.0f s -> %s" % (style, lining, seed, time.time() - t0, path), flush=True)
        sheet = Image.new("RGB", ((pw + 12) * len(paths), ph + 28), (12, 12, 12))
        dd = ImageDraw.Draw(sheet)
        for i, p in enumerate(paths):
            dd.text((i * (pw + 12) + 6, 6), os.path.basename(p), fill=(230, 230, 230))
            sheet.paste(Image.open(p).convert("RGB"), (i * (pw + 12), 24))
        sheet.save(os.path.join(a.out, style + "_well_sheet.png"))
        print("sheet:", os.path.join(a.out, style + "_well_sheet.png"), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=r"E:\models")
    ap.add_argument("--out", default=os.path.join(ROOT, "art", "hud_buttons", "pilot"))
    ap.add_argument("--styles", default=",".join(STYLES))
    ap.add_argument("--buttons", default=",".join(PILOT), help="comma-separated, or `all`")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--clean", default=os.path.join(ROOT, "art", "hud_buttons", "clean"),
                    help="the keys drawn clean and big by the engine's own code (<name>.png); empty = the mod's pixels")
    ap.add_argument("--match", action="store_true", help="show the first finished button with every other one (R-378: copies its sign)")
    ap.add_argument("--panel", type=int, default=0, help="paint this many variants of the panel's surface instead of keys")
    ap.add_argument("--well", type=int, default=0, help="paint this many variants of a hand's well (per lining) instead")
    a = ap.parse_args()
    if a.panel:
        paint_panel(a)
        return
    if a.well:
        paint_well(a)
        return
    names = list(BUTTONS) if a.buttons == "all" else [b for b in a.buttons.split(",") if b]

    src = Image.open(SOURCE).convert("RGB")
    painter = None
    for style in [s for s in a.styles.split(",") if s]:
        sdir = os.path.join(a.out, style)
        os.makedirs(sdir, exist_ok=True)
        ref = None
        done = []
        for name in names:
            path = os.path.join(sdir, name + ".png")
            clean = os.path.join(a.clean, name + ".png") if a.clean else ""
            inp = Image.open(clean).convert("RGB") if clean and os.path.exists(clean) else crop_button(src, BUTTONS[name])
            inp.save(os.path.join(sdir, name + "_input.png"))
            if not os.path.exists(path):
                if painter is None:
                    painter = photo_ui.Painter(a.models, False, a.steps, photoreal=False)
                W, H = photo_ui.target_size(inp.width, inp.height, 0.6)
                images = [inp.resize((W, H), Image.LANCZOS)]
                prompt = KEEP + STYLES[style]
                if name in TINT:
                    prompt += TINT_HINT % (TINT[name], FRAME_METAL.get(style, "brass"), TINT[name])
                if ref is not None and a.match:
                    # R-378: the finished button as the second picture makes the model copy its sign
                    images.append(ref)
                    prompt += MATCH
                t0 = time.time()
                rgb = painter.edit(images, prompt, NEGATIVE, a.seed, a.steps, a.cfg, W, H)
                Image.fromarray(rgb).resize(inp.size, Image.LANCZOS).save(path)
                print("%s / %s: %.0f s -> %s" % (style, name, time.time() - t0, path), flush=True)
            if ref is None:
                ref = Image.open(path).convert("RGB")
            done.append(name)
        # the sheet: every button's input beside its painting
        tiles = [(Image.open(os.path.join(sdir, n + "_input.png")).convert("RGB"), Image.open(os.path.join(sdir, n + ".png")).convert("RGB")) for n in done]
        cw = max(i.width for i, _ in tiles) * 2 + 24
        ch = sum(i.height + 28 for i, _ in tiles)
        sheet = Image.new("RGB", (cw, ch), (12, 12, 12))
        d = ImageDraw.Draw(sheet)
        y = 0
        for n, (i, p) in zip(done, tiles):
            d.text((6, y + 6), n, fill=(230, 230, 230))
            sheet.paste(i, (0, y + 24))
            sheet.paste(p, (i.width + 24, y + 24))
            y += i.height + 28
        sheet.save(os.path.join(a.out, style + "_sheet.png"))
        print("sheet:", os.path.join(a.out, style + "_sheet.png"), flush=True)


if __name__ == "__main__":
    main()
