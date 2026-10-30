#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000445: сцена бугра на траве MOUNTGRASS - было (HD сейчас) | стало (кандидат t445_slopes).
Сейва с MOUNTGRASS в тикете нет, поэтому берётся блок карты из сейва тикета 431 (бугор MOUNTTROP: те же MCD склонов 27-39, 41),
и весь пол и склоны подменяются кадрами MOUNTGRASS: пол 0-3 -> трава 0 и варианты 0.v1-0.v7 по клетке (изредка гравий 1, 2),
склоны 27-39, 41 -> MOUNTGRASS (было: HD сейчас; стало: кандидат). Остальное (камни, кусты, деревья) как в сейве.
Только чтение, в мод ничего не пишет.

    py -3.13 tools\hdart\t445_scene.py --name A1 --out art\_review\tickets_2026-10-30\t445_cand_scene.png
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
import t445_slopes as sl               # noqa: E402

ss.SAVE = r"census\tickets\XP-000431\files\02__autobattle_.asav"
VARS = sl.VARIANTS
_CACHE = {}


def img(path_key, loader):
    if path_key not in _CACHE:
        _CACHE[path_key] = loader()
    return _CACHE[path_key]


def mg(frame):
    return img(("MG", frame), lambda: sl.hd_now("MOUNTGRASS", frame))


def pick(nm, fr, mx, my, cand, name):
    """Подмена кадра клетки: MOUNTTROP 0-3, 27-39, 41 -> MOUNTGRASS (пол по клетке, склоны было/стало)."""
    if nm != "MOUNTTROP":
        return None
    if fr in (0, 1, 2, 3):
        h = (mx * 7919 + my * 104729) % 101
        if fr == 0 or fr == 1:
            return mg(VARS[h % len(VARS)])
        if fr == 2:
            return mg("1" if h % 3 == 0 else VARS[h % len(VARS)])
        return mg("2" if h % 4 == 0 else VARS[h % len(VARS)])
    if fr in sl.FRAMES:
        return img(("C", name, fr), lambda: sl.load(name, "MOUNTGRASS", fr)) if cand else mg(str(fr))
    return None


def render_all(x0, y0, w, h, cand, name, k=4, zmax=4):
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
                    pic = pick(nm, fr, mx, my, cand, name)
                    if pic is None:
                        pic = ss.hd_from(ss.CUR, nm, fr)
                    if pic is None:
                        continue
                    px = ox + (xx - yy) * 16 * k
                    py = top + (xx + yy) * 8 * k - recs[i]["yoff"] * k - z * 24 * k
                    im.alpha_composite(pic, (px, py))
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
    ap.add_argument("--out", default=os.path.join(sl.REV, "t445_cand_scene.png"))
    ap.add_argument("--crop", default="", help="x0,y0,x1,y1 в пикселях сцены (крупный план)")
    ap.add_argument("--k", type=int, default=4)
    a = ap.parse_args()
    now = render_all(a.x0, a.y0, a.w, a.h, False, a.name, a.k, a.zmax)
    new = render_all(a.x0, a.y0, a.w, a.h, True, a.name, a.k, a.zmax)
    if a.crop:
        box = tuple(int(v) for v in a.crop.split(","))
        now, new = now.crop(box), new.crop(box)
    W, H = now.size
    sh = Image.new("RGB", (W, 2 * (H + 24)), (12, 12, 14))
    d = ImageDraw.Draw(sh)
    for k, (t, im) in enumerate((("было: HD сейчас (склоны MOUNTGRASS 27-39 и 41 прежние)", now),
                                 ("стало: кандидат " + a.name, new))):
        d.text((6, k * (H + 24) + 4), t, fill=(255, 220, 0), font=sl.FONT)
        sh.paste(im.convert("RGB"), (0, k * (H + 24) + 24))
    sh.save(a.out)
    print("лист:", a.out, sh.size)


if __name__ == "__main__":
    main()
