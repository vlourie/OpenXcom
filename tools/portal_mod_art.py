"""Pictures for the mod pages of the site (portal/src/Xp.Portal/wwwroot/img/mods), made from the game's own files.

Nothing here is generated: every picture is cut from the mods as players get them, so a page never shows art
the game does not have.
  hd-ship.jpg, hd-forest.jpg   classic above, HD below: the same block of a map, laid out from its tiles the way
                               the game draws them (tools/hdart/map_mockup.py --k 4, panels 0 and 2)
  tank-turret.jpg (+@2x)       card: the pirate tank with its turret turned three ways (piratez_tank_turret)
  tank-turret-turn.png         one hull, the turret in all 8 directions
  apple-processing.jpg (+@2x)  card: apple, tube of puree, jar of jam (Piratez + Apple_Processing sprites)
  apple-processing-recipe.png  3 apples -> tube, 5 apples -> jar
  kisya-brysya.jpg             card: the sisters from their UFOpaedia picture in HD (hd/UI/Pumas.png)
  kisya-brysya-pedia.png       the two UFOpaedia portraits the mod brings (Resources/Awards)
  kisya-brysya-event.png       the event scene «Сёстры Кися и Брыся» (Puma_sisters.png, x3)

    tools\\hdart\\.venv\\Scripts\\python.exe tools\\portal_mod_art.py --ship <CARGO_LINER__CARGO00 at k4> --forest <FOREST__FOREST05 at k4>
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "hdart"))
import tank_turret as tt  # noqa: E402

MODS = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods")
OUT = os.path.join(ROOT, "portal", "src", "Xp.Portal", "wwwroot", "img", "mods")
SITE_BG = (16, 0, 16)
GROUND = (84, 104, 84)


def save(im, name, **kw):
    p = os.path.join(OUT, name)
    if name.endswith(".jpg"):
        im.convert("RGB").save(p, quality=kw.get("quality", 86), optimize=True, progressive=True)
    else:
        im.save(p, optimize=True)
    print("%-32s %5dx%-5d %4d KB" % (name, im.width, im.height, os.path.getsize(p) // 1024))


def card(im, name):
    """A 16:9 card: 1280x720 as @2x and 640x360 as the plain one (the site picks by srcset)."""
    big = im.resize((1280, 720), Image.LANCZOS) if im.size != (1280, 720) else im
    root, ext = os.path.splitext(name)
    save(big, root + "@2x" + ext)
    save(big.resize((640, 360), Image.LANCZOS), name)


def stacked(sheet, box, name, width=1000):
    """Classic (panel 0) above HD now (panel 2) of a map_mockup sheet, the same box of both."""
    im = Image.open(sheet).convert("RGB")
    pw = im.width // 3
    x0, y0, x1, y1 = box
    top = im.crop((x0, y0, x1, y1))
    bottom = im.crop((2 * pw + x0, y0, 2 * pw + x1, y1))
    gap = 10
    out = Image.new("RGB", (top.width, top.height * 2 + gap), SITE_BG)
    out.paste(top, (0, 0))
    out.paste(bottom, (0, top.height + gap))
    out = out.resize((width, round(out.height * width / out.width)), Image.LANCZOS)
    save(out, name, quality=88)


def rgba_of(path):
    """An indexed sprite as RGBA, index 0 clear."""
    im = Image.open(path)
    a = np.array(im)
    rgb = np.array(im.convert("RGB"))
    alpha = np.where(a == 0, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


def trim(im):
    return im.crop(im.getbbox())


# ---------------------------------------------------------------- tank

def tank(hull, turret, z):
    """The standing tank of hull direction `hull` with its turret turned to `turret`, as the game puts them."""
    d = os.path.join(MODS, "piratez_tank_turret", "Resources", "TankTurret")
    sheet = tt.Sheet(os.path.join(d, "PIR_TANK.png"))
    cv, _, _ = tt.assemble(sheet, hull)
    big = np.array(Image.open(os.path.join(d, "PIR_TANK_turret", "%02d.png" % (hull * 8 + turret))))
    rgb = np.array(tt.show_big(cv, big, sheet.palette, 1))
    # show_big paints the empty pixels with its preview ground; make them clear instead
    clear = (rgb == np.array(GROUND)).all(axis=2)
    alpha = np.where(clear, 0, 255).astype(np.uint8)
    im = trim(Image.fromarray(np.dstack([rgb, alpha]), "RGBA"))
    return im.resize((im.width * z, im.height * z), Image.NEAREST)


def tank_pictures():
    z = 6
    canvas = Image.new("RGBA", (1280, 720), GROUND + (255,))
    shots = [tank(2, t, z) for t in (1, 3, 5)]   # the same hull, the gun to the right, at the viewer, to the left
    xs = [70, 470, 870]
    for im, x in zip(shots, xs):
        canvas.alpha_composite(im, (x + (340 - im.width) // 2, 360 - im.height // 2 + 30))
    card(canvas, "tank-turret.jpg")

    z = 4
    frames = [tank(2, t, z) for t in range(8)]
    cw = max(f.width for f in frames) + 24
    ch = max(f.height for f in frames) + 24
    grid = Image.new("RGBA", (cw * 4, ch * 2), GROUND + (255,))
    for i, f in enumerate(frames):
        r, c = divmod(i, 4)
        grid.alpha_composite(f, (c * cw + (cw - f.width) // 2, r * ch + (ch - f.height) // 2))
    save(grid.convert("RGB"), "tank-turret-turn.png")


# ---------------------------------------------------------------- apples

def inventory(w, h, cell):
    """The dark backpack grid the items lie on."""
    im = Image.new("RGBA", (w, h), (20, 12, 28, 255))
    d = ImageDraw.Draw(im)
    for x in range(0, w + 1, cell):
        d.line((x, 0, x, h), fill=(52, 40, 64, 255), width=2)
    for y in range(0, h + 1, cell):
        d.line((0, y, w, y), fill=(52, 40, 64, 255), width=2)
    return im


def arrow(im, x, y, size, color=(200, 220, 120, 255)):
    d = ImageDraw.Draw(im)
    d.rectangle((x, y - size // 6, x + size, y + size // 6), fill=color)
    d.polygon([(x + size, y - size // 2), (x + size + size * 2 // 3, y), (x + size, y + size // 2)], fill=color)


def apple_pictures():
    res = os.path.join(MODS, "Piratez", "Resources", "Apple.png")
    mine = os.path.join(MODS, "Apple_Processing", "Resources", "AppleProcessing")
    apple = trim(rgba_of(res))
    puree = trim(rgba_of(os.path.join(mine, "apple_puree_big.png")))
    jam = trim(rgba_of(os.path.join(mine, "apple_jam_big.png")))

    def big(im, z):
        return im.resize((im.width * z, im.height * z), Image.NEAREST)

    z = 8
    canvas = inventory(1280, 720, 16 * z // 2)
    items = [big(apple, z), big(puree, z), big(jam, z)]
    slots = [(90, 380), (530, 380), (970, 380)]
    # no arrows: puree and jam are both made of apples, the jam not of the puree
    for im, (x, y) in zip(items, slots):
        canvas.alpha_composite(im, (x + (220 - im.width) // 2, y - im.height // 2))
    card(canvas, "apple-processing.jpg")

    z = 5
    a = big(apple, z)
    rows = [(3, big(puree, z)), (5, big(jam, z))]
    step = a.width + 14
    w = 5 * step + 120 + 40 + max(r[1].width for r in rows) + 40
    rh = max(max(r[1].height for r in rows), a.height) + 40
    out = inventory(w, rh * 2, 16 * z // 2)
    for i, (n, item) in enumerate(rows):
        cy = i * rh + rh // 2
        for k in range(n):
            out.alpha_composite(a, (20 + k * step, cy - a.height // 2))
        arrow(out, 5 * step + 30, cy, 60)
        out.alpha_composite(item, (5 * step + 160, cy - item.height // 2))
    save(out.convert("RGB"), "apple-processing-recipe.png")


# ---------------------------------------------------------------- sisters

def sister_pictures():
    hd = Image.open(os.path.join(MODS, "hd", "hd", "UI", "Pumas.png")).convert("RGB")
    art = hd.crop((hd.width // 2 + 8, 0, hd.width, hd.height))      # the left half is the text field of the page
    face = art.crop((0, 30, art.width, 30 + art.width * 9 // 16))
    save(face, "kisya-brysya.jpg")
    # the mod's own UFOpaedia pictures: the art is the right part of the 320x200 page, the left is the text field
    awards = os.path.join(MODS, "XPZ_Kisya_Brysya_Sisters", "Resources", "Awards")
    pics = [Image.open(os.path.join(awards, n)).convert("RGB").crop((192, 4, 316, 196)) for n in ("ANNA_PUMA.png", "UNI_PUMA.png")]
    pics = [p.resize((p.width * 3, p.height * 3), Image.NEAREST) for p in pics]
    both = Image.new("RGB", (pics[0].width * 2 + 12, pics[0].height), SITE_BG)
    both.paste(pics[0], (0, 0))
    both.paste(pics[1], (pics[0].width + 12, 0))
    save(both, "kisya-brysya-pedia.png")
    scene = Image.open(os.path.join(MODS, "Piratez", "Resources", "Backgrounds", "Puma_sisters.png")).convert("RGB")
    save(scene.resize((scene.width * 3, scene.height * 3), Image.NEAREST), "kisya-brysya-event.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ship", help="map_mockup sheet CARGO_LINER__CARGO00 at --k 4")
    ap.add_argument("--forest", help="map_mockup sheet FOREST__FOREST05 at --k 4")
    o = ap.parse_args()
    if o.ship:
        stacked(o.ship, (1550, 1320, 2650, 2000), "hd-ship.jpg")
    if o.forest:
        stacked(o.forest, (40, 400, 1376, 1080), "hd-forest.jpg")
    tank_pictures()
    apple_pictures()
    sister_pictures()


if __name__ == "__main__":
    main()
