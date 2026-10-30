#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000431: сцена бугра из сейва игрока (Паучьи угодья, MOUNTTROP) - было (HD сейчас) | стало (кандидат t431_slopes).
Рисует блок карты из сейва, как art/tickets/scene_save.render, но по всем этажам (z сдвигает на 24 пикселя) и с подменой кадров.
Только чтение, в мод ничего не пишет.

    py -3.13 tools\hdart\t431_scene.py --name A1 --x0 20 --y0 10 --w 20 --h 20 --out art\_review\tickets_2026-10-30\t431_cand_scene.png
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "art", "tickets"))
sys.path.insert(0, os.path.join(ROOT, "tools", "hdart"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from PIL import Image, ImageDraw       # noqa: E402
import scene_save as ss                # noqa: E402
import t431_slopes as sl               # noqa: E402

ss.SAVE = r"census\tickets\XP-000431\files\02__autobattle_.asav"


def render_all(x0, y0, w, h, over=None, k=4, zmax=4, mode="hd"):
    """Все этажи z=0..zmax и четыре части клетки; over - подмена кадров {(набор, кадр): RGBA 128x160}."""
    b, d = ss.battle()
    top = zmax * 24 * k
    W = (w + h) * 16 * k + 32 * k
    H = (w + h) * 8 * k + 40 * k + 8 * k + top
    im = Image.new("RGBA", (W, H), (30, 56, 20, 255))
    ox = h * 16 * k
    for z in range(zmax + 1):
        for yy in range(h):
            for xx in range(w):
                mx, my = x0 + xx, y0 + yy
                for p in (0, 1, 2, 3):
                    st = b.SET[z, my, mx, p]
                    i = int(b.ID[z, my, mx, p])
                    if st < 0 or i < 0:
                        continue
                    nm = b.sets[st]
                    if nm == "BLANKS":
                        continue
                    recs = d.mcd(nm)
                    if i >= len(recs):
                        continue
                    fr = recs[i]["frames"][0]
                    if over and (nm, fr) in over:
                        img = over[(nm, fr)]
                    elif mode == "classic":
                        img = ss.classic(nm, fr, k)
                    else:
                        img = ss.hd_from(ss.CUR, nm, fr)
                        if img is None:
                            continue
                    px = ox + (xx - yy) * 16 * k
                    py = top + (xx + yy) * 8 * k - recs[i]["yoff"] * k - z * 24 * k
                    im.alpha_composite(img, (px, py))
    return im


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="A1")
    ap.add_argument("--x0", type=int, default=20)
    ap.add_argument("--y0", type=int, default=10)
    ap.add_argument("--w", type=int, default=20)
    ap.add_argument("--h", type=int, default=20)
    ap.add_argument("--zmax", type=int, default=4)
    ap.add_argument("--out", default=os.path.join(sl.REV, "t431_cand_scene.png"))
    ap.add_argument("--crop", default="", help="x0,y0,x1,y1 в пикселях сцены (для крупного плана)")
    ap.add_argument("--k", type=int, default=4)
    a = ap.parse_args()
    over = {("MOUNTTROP", f): sl.load(a.name, "MOUNTTROP", f) for f in sl.FRAMES}
    now = render_all(a.x0, a.y0, a.w, a.h, k=a.k, zmax=a.zmax)
    new = render_all(a.x0, a.y0, a.w, a.h, over=over, k=a.k, zmax=a.zmax)
    if a.crop:
        box = tuple(int(v) for v in a.crop.split(","))
        now, new = now.crop(box), new.crop(box)
    W, H = now.size
    sh = Image.new("RGB", (W, 2 * (H + 24)), (12, 12, 14))
    d = ImageDraw.Draw(sh)
    for k, (t, im) in enumerate((("было: HD сейчас (склоны 27-39 и 41 прежние)", now), ("стало: кандидат " + a.name, new))):
        d.text((6, k * (H + 24) + 4), t, fill=(255, 220, 0), font=sl.b.FONT)
        sh.paste(im.convert("RGB"), (0, k * (H + 24) + 24))
    sh.save(a.out)
    print("лист:", a.out, sh.size)


if __name__ == "__main__":
    main()
