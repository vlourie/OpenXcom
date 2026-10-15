"""Видимые плоскости классического HANDOB по восьми кадрам одного предмета - опора для пробы ракурса.

Только чтение классики (census HANDOB.PCK.png через grip_matrix), без видеокарты и без модели.
По каждому кадру handSprite+0..7: лист x8 и столбцовая мера «светлый верх - тёмный низ»
(яркость верхнего пикселя столбца предмета против нижнего). Это диагностика, а не цель:
по 2-3 пикселям классики угол плоскости не мерится, мерится только, с какой стороны свет.

py -3.13 tools/hdart/handob_planes.py 1640 --out art/items/weapons100-v1/grip_pilot/tommy1642/edit_plan
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grip_matrix as gm  # noqa: E402

# какой кадр что значит (grip-contract §9.1): стойка d = hs+d, прицел d = hs+d+2
USE = {d: "стойка d%d, прицел d%d" % (d, (d - 2) % 8) for d in range(8)}


def lum(c):
    return 0.299 * c[..., 0] + 0.587 * c[..., 1] + 0.114 * c[..., 2]


def planes(idx, pal):
    m = idx > 0
    L = lum(pal[idx].astype(float))
    cols = []
    for x in range(idx.shape[1]):
        ys = np.nonzero(m[:, x])[0]
        if len(ys) < 3:
            continue
        cols.append((x, float(L[ys[0], x] - L[ys[-1], x]), len(ys)))
    d = np.array([c[1] for c in cols]) if cols else np.zeros(0)
    return {
        "px": int(m.sum()),
        "columns": len(cols),
        "top_lighter_share": round(float((d > 8).mean()), 3) if len(d) else None,
        "bottom_lighter_share": round(float((d < -8).mean()), 3) if len(d) else None,
        "top_minus_bottom_mean": round(float(d.mean()), 1) if len(d) else None,
        "mean_luma": round(float(L[m].mean()), 1) if m.any() else None,
        "dark_share": round(float((L[m] < 40).mean()), 3) if m.any() else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hs", type=int)
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    rep, tiles = {}, []
    for d in range(8):
        f = a.hs + d
        idx = gm.hob(f)
        rep[f] = dict(planes(idx, gm.hpal), use=USE[d])
        rgb = gm.hpal[idx].astype(np.uint8)
        im = Image.new("RGB", (32 * a.k, 40 * a.k + 40), (90, 92, 98))
        cell = Image.fromarray(np.where((idx > 0)[..., None], rgb, np.array([90, 92, 98], np.uint8)))
        im.paste(cell.resize((32 * a.k, 40 * a.k), Image.NEAREST), (0, 40))
        dr = ImageDraw.Draw(im)
        r = rep[f]
        dr.text((4, 2), "%d  %s" % (f, r["use"]), fill=(255, 255, 255), font=font)
        dr.text((4, 20), "верх светлее %s, низ светлее %s" % (r["top_lighter_share"], r["bottom_lighter_share"]),
                fill=(220, 220, 160), font=font)
        tiles.append(im)
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * 4 + 30, h * 2 + 20), (20, 22, 28))
    for i, t in enumerate(tiles):
        sheet.paste(t, (6 + (i % 4) * (w + 6), 6 + (i // 4) * (h + 6)))
    sheet.save(os.path.join(a.out, "planes_%d.png" % a.hs))
    with open(os.path.join(a.out, "planes_%d.json" % a.hs), "w", encoding="utf-8-sig") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1)
    for f, r in rep.items():
        print(f, r["use"], "| пикс", r["px"], "| верх светлее", r["top_lighter_share"], "| низ светлее",
              r["bottom_lighter_share"], "| верх-низ", r["top_minus_bottom_mean"], "| яркость", r["mean_luma"],
              "| тёмных", r["dark_share"])


if __name__ == "__main__":
    main()
