#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000443: сцена по карте сейва игрока (CHEMTOWNGHOUL, census/tickets/XP-000443/files/02__autobattle_.asav):
классика | HD сейчас | кандидат (art/tickets/t443/cand). Карта читается как файл, игра не запускается.

    py -3.13 tools\hdart\t443_scene.py   # art/_review/tickets_2026-10-30/t443_cand_scene.png (+ _zoom)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)

import ticket_scene as ts                            # noqa: E402
import map_truth as mt                               # noqa: E402
from PIL import Image                                # noqa: E402

REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
CAND = os.path.join(ROOT, "art", "tickets", "t443", "cand")
SAVE = os.path.join(ROOT, "census", "tickets", "XP-000443", "files", "02__autobattle_.asav")
_SC = ts.Scene()
_BT = mt.Battle(SAVE)
_RC = {}


def render(x0, x1, y0, y1, zmax, mode, k=3, override=None):
    W = (x1 - x0 + y1 - y0) * 16 + 64
    H = (x1 - x0 + y1 - y0) * 8 + zmax * 24 + 80 + 40
    im = Image.new("RGBA", (W * k, H * k), ts.BG + (255,))
    ox = (y1 - y0) * 16 + 16
    oy = zmax * 24 + 20
    for z in range(zmax + 1):
        for y in range(y0, y1):
            for x in range(x0, x1):
                for p in range(4):
                    v = _BT.part(z, y, x, p)
                    if not v or v[0] < 0:
                        continue
                    S = _BT.sets[v[0]]
                    if S not in _RC:
                        try:
                            _RC[S] = _SC.w.records(S)
                        except Exception:
                            _RC[S] = None
                    if _RC[S] is None or v[1] >= len(_RC[S]):
                        continue
                    r = _RC[S][v[1]]
                    f = r["frame"]
                    if mode == "classic":
                        spr = _SC.classic(S, f)
                    else:
                        spr = (override or {}).get((S, f)) or _SC.hd(S, f) or _SC.classic(S, f)
                    if spr is None:
                        continue
                    if spr.width != 32 * k:
                        spr = spr.resize((32 * k, 40 * k), Image.NEAREST if mode == "classic" else Image.LANCZOS)
                    px = ox + ((x - x0) - (y - y0)) * 16
                    py = oy + ((x - x0) + (y - y0)) * 8 - z * 24 - r["p_level"]
                    im.alpha_composite(spr, (px * k, py * k))
    return im


def load_cand():
    ov = {}
    for fn in sorted(os.listdir(CAND)):
        if fn.endswith(".png"):
            s, f = fn[:-4].rsplit("_", 1)
            ov[(s, int(f))] = Image.open(os.path.join(CAND, fn)).convert("RGBA")
    return ov


def main():
    W = 1000
    ov = load_cand()
    ims = {}
    for title, mode, o in (("классика", "classic", None), ("HD сейчас", "hd", None), ("кандидат", "hd", ov)):
        im = render(0, 24, 38, 50, 1, mode, k=3, override=o).convert("RGB")
        im = im.crop((300, 150, 1900, 1000))
        ims[title] = im.resize((W, int(im.height * W / im.width)), Image.LANCZOS)
        # увеличенный кусок: центр сцены, три кадра крупнее
        z = im.crop((330, 160, 1030, 560))
        ims[title + "_z"] = z
    ts.sheet([("1. сцена по карте сейва: классика", ims["классика"]),
              ("2. сцена по карте сейва: HD сейчас", ims["HD сейчас"]),
              ("3. сцена по карте сейва: кандидат", ims["кандидат"])],
             os.path.join(REV, "t443_cand_scene.png"), cols=1)
    ts.sheet([("классика (крупно)", ims["классика_z"]), ("HD сейчас (крупно)", ims["HD сейчас_z"]),
              ("кандидат (крупно)", ims["кандидат_z"])],
             os.path.join(REV, "t443_cand_scene_zoom.png"), cols=3)
    print("листы: t443_cand_scene.png, t443_cand_scene_zoom.png")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
