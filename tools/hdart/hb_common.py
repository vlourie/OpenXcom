r"""Общее для листов XP-000510/511/512: сцена блока, подписи, склейка. Только чтение."""
import os
import sys

sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
sys.path.insert(0, r"E:\OpenXCom\tools")
os.chdir(r"E:\OpenXCom")
import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont   # noqa: E402

import map_mockup as mm                 # noqa: E402
import ticket_scene as ts               # noqa: E402

TERRAIN = os.path.join("user", "mods", "hd", "hd", "TERRAIN")
FONT = "C:/Windows/Fonts/arial.ttf"


def font(n):
    return ImageFont.truetype(FONT, n)


def best_blocks(sc, keys, terrain=None, top=3):
    """Блоки карты, где больше всего клеток кадров keys: -> [((террейн, блок), число)]."""
    use = mm.usage(sc.w)
    score = {}
    for k in keys:
        for t, b, n in use.get("%s:%d" % k, []):
            if terrain and t != terrain:
                continue
            score[(t, b)] = score.get((t, b), 0) + n
    return sorted(score.items(), key=lambda kv: -kv[1])[:top]


def scene_panels(sc, terrain, block, keys, override, size=(150, 100), k=4, which=0, titles=("классика", "сейчас", "новое")):
    """Три окна сцены (классика, HD сейчас, HD новое) вокруг клеток keys нижнего этажа."""
    found = ts.find_cells(sc, terrain, block, keys)
    zmin = min(f[3] for f in found)
    found = [f for f in found if f[3] == zmin]
    found.sort(key=lambda f: (f[4][0], f[4][1]))
    pick = found[min(which, len(found) - 1)]
    box = ts.window([(pick[0], pick[1], tuple(v * k for v in pick[2]))], size[0], size[1], k)
    out = []
    for title, mode, o in zip(titles, ("classic", "hd", "hd"), (None, None, override)):
        im, _f = sc.render(terrain, block, mode, override=o, k=k, maxz=zmin)
        out.append((title, ts.crop_pad(im, box)))
    return out, len(found)


def zoom_cell(sc_img, scale=1):
    return sc_img


def title_bar(im, text, size=24):
    im = im.convert("RGB")
    out = Image.new("RGB", (im.width, im.height + size + 14), (15, 15, 18))
    out.paste(im, (0, size + 14))
    ImageDraw.Draw(out).text((8, 6), text, fill=(255, 220, 0), font=font(size))
    return out


def vstack(ims, gap=10, bg=(12, 12, 14)):
    W = max(i.width for i in ims)
    H = sum(i.height for i in ims) + gap * (len(ims) + 1)
    out = Image.new("RGB", (W + 2 * gap, H), bg)
    y = gap
    for i in ims:
        out.paste(i, (gap, y))
        y += i.height + gap
    return out


def hstack(ims, gap=10, bg=(12, 12, 14)):
    H = max(i.height for i in ims)
    W = sum(i.width for i in ims) + gap * (len(ims) + 1)
    out = Image.new("RGB", (W, H + 2 * gap), bg)
    x = gap
    for i in ims:
        out.paste(i, (x, gap))
        x += i.width + gap
    return out


def on_bg(im, bg=(60, 60, 70)):
    base = Image.new("RGBA", im.size, bg + (255,))
    base.alpha_composite(im.convert("RGBA"))
    return base.convert("RGB")
