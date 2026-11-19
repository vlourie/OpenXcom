# -*- coding: utf-8 -*-
r"""Общее для листов XP-000509 и куста 510 (исполнитель 509/510 арт): сцена блока, подписи. Только чтение."""
import os
import sys

sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
os.chdir(r"E:\OpenXCom")
import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont   # noqa: E402

import ticket_scene as ts               # noqa: E402

TERRAIN = "JUNGLETEMPLE"
FONT = "C:/Windows/Fonts/arial.ttf"
TERR_DIR = os.path.join("user", "mods", "hd", "hd", "TERRAIN")
_CACHE = {}


def font(n):
    return ImageFont.truetype(FONT, n)


def load_override(d, members):
    ov = {}
    for s, f in members:
        p = os.path.join(d, "%s_%d.png" % (s, f))
        if os.path.exists(p):
            ov[(s, f)] = Image.open(p).convert("RGBA")
    return ov


def render(sc, block, mode, override, k, maxz=None, terrain=TERRAIN):
    key = (block, mode, id(override), k, maxz, terrain)
    if key not in _CACHE:
        _CACHE[key] = sc.render(terrain, block, mode, override=override, k=k, maxz=maxz)[0]
    return _CACHE[key]


def panels(sc, block, keys, override, size=(160, 100), k=4, which=0, titles=("классика", "сейчас", "новое"), maxz=None,
           terrain=TERRAIN, found_sort=True):
    """Три окна сцены вокруг клетки с кадром из keys; which - какую из найденных брать (по порядку этаж, x, y)."""
    found = ts.find_cells(sc, terrain, block, keys)
    if not found:
        raise SystemExit("нет %s в %s" % (keys, block))
    if found_sort:
        found.sort(key=lambda f: (f[3], f[4][0], f[4][1]))
    pick = found[min(which, len(found) - 1)]
    box = ts.window([(pick[0], pick[1], tuple(v * k for v in pick[2]))], size[0], size[1], k)
    out = []
    for title, mode, o in zip(titles, ("classic", "hd", "hd"), (None, None, override)):
        im = render(sc, block, mode, o, k, maxz, terrain)
        out.append((title, ts.crop_pad(im, box)))
    return out, len(found)


def zoom(im, z):
    return im.resize((im.width * z, im.height * z), Image.NEAREST)


def banner(text, width, n=26):
    im = Image.new("RGB", (width, n + 14), (12, 12, 14))
    ImageDraw.Draw(im).text((8, 6), text, fill=(120, 230, 255), font=font(n))
    return im


def stack(parts, gap=8):
    W = max(p.width for p in parts)
    H = sum(p.height for p in parts) + gap * (len(parts) + 1)
    out = Image.new("RGB", (W + 2 * gap, H), (12, 12, 14))
    y = gap
    for p in parts:
        out.paste(p.convert("RGB"), (gap, y))
        y += p.height + gap
    return out
