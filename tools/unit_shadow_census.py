#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0 HD-теней: есть ли у HD-юнитов своя (запечённая) тень под ногами.

Проект - docs/research/hd-shadows-ao-2026-10-30.md, §4 «Возможный дубль». Читает pack.hdp наборов юнитов
мода hd (формат - tools/hdart/optimize_hd.py: OXHDPCK1, scale, base_w, base_h, count, затем (кадр, смещение,
размер) и PNG). Только чтение.

Мерка кадра: «мягкие тёмные» пиксели (альфа 16-200, яркость < 80) в нижней полосе кадра - от нижнего
сплошного ряда (альфа >= 230) на 3k рядов вверх и до низа кадра - дальше 2 пикселей от сплошных (края
сглаживания к ним прилегают, пятно тени уходит от них). Пятно - не меньше 6 базовых пикселей площадью.
Мерка - подсказка, решает лист глазами; контроль - тот же кадр с дорисованным эллипсом 7k x 3,5k.

    py -3.13 tools\unit_shadow_census.py
    py -3.13 tools\unit_shadow_census.py --sheet PIR_0,GOV_4,...

Выход - census\ao\unit_shadow.tsv и census\ao\unit_shadow_sheet.png (census в гит не идёт).
"""
import argparse
import io
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ENC = "utf-8-sig"
MAGIC = b"OXHDPCK1"
SHEET = ("PIR_0,PIR_1,GOV_4,ARMY_RUS,BAN_0,MUT_1,XSECT0,XNEKO_008,SOL_0,ZOMBIE_TROOPER_1,CYBORG,SKELETON,"
         "SPIDERGIRL,GIANTRAT,XTANKS,DOGE,HUM_1,NAZ_1,RET_0,MRC_0")


def read_pack(path):
    data = open(path, "rb").read()
    if len(data) < 24 or data[:8] != MAGIC:
        return None, []
    scale, base_w, base_h, count = struct.unpack_from("<4I", data, 8)
    frames = []
    for i in range(count):
        index, off, size = struct.unpack_from("<3I", data, 24 + i * 12)
        if size and off + size <= len(data):
            frames.append((index, data[off:off + size]))
    return scale, frames


def dilate(mask, r):
    out = mask.copy()
    h, w = mask.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            ys, yd = (slice(dy, h), slice(0, h - dy)) if dy >= 0 else (slice(0, h + dy), slice(-dy, h))
            xs, xd = (slice(dx, w), slice(0, w - dx)) if dx >= 0 else (slice(0, w + dx), slice(-dx, w))
            out[yd, xd] |= mask[ys, xs]
    return out


def measure(rgba, k):
    a = rgba[:, :, 3].astype(int)
    lum = (rgba[:, :, 0] * 0.3 + rgba[:, :, 1] * 0.59 + rgba[:, :, 2] * 0.11)
    solid = a >= 230
    solid_rows = np.where(solid.any(axis=1))[0]
    if len(solid_rows) == 0:
        return None
    bottom = int(solid_rows[-1])
    h = rgba.shape[0]
    band = np.zeros_like(solid)
    band[max(0, bottom - 3 * k):h] = True
    # края сглаживания прилегают к сплошным пикселям; пятно тени уходит от них дальше
    soft = (a >= 16) & (a <= 200) & (lum < 80) & band & ~dilate(solid, 2)
    n_soft = int(soft.sum())
    return {"bottom": bottom, "soft": n_soft, "blob": n_soft >= 6 * k * k,
            "legs": int((solid & band).sum()), "feet_low": bottom >= 0.6 * h}


def census(root):
    rows, per_set = [], {}
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name, "pack.hdp")
        if not os.path.isfile(p):
            continue
        k, frames = read_pack(p)
        if not frames:
            continue
        stats = []
        for index, blob in frames:
            im = Image.open(io.BytesIO(blob)).convert("RGBA")
            m = measure(np.asarray(im), k)
            if m:
                stats.append((index, m, im))
        n_blob = sum(1 for _, m, _ in stats if m["blob"])
        per_set[name] = (k, stats)
        rows.append((name, k, len(frames), len(stats), n_blob, round(n_blob / max(1, len(stats)), 3)))
    return rows, per_set


def sheet(per_set, names, path):
    rows = []
    for name in names:
        if name not in per_set:
            continue
        k, stats = per_set[name]
        # кадры со ступнями внизу кадра и с самым большим низом: стойка и ходьба; сначала с пятном, если есть
        low = [s for s in stats if s[1]["feet_low"]] or stats
        best = sorted(low, key=lambda s: (not s[1]["blob"], -s[1]["legs"]))[:4]
        best.sort(key=lambda s: s[0])
        rows.append((name, k, best))
    if not rows:
        return
    cell_w = max(im.width for _, _, b in rows for _, _, im in b)
    k_max = max(k for _, k, _ in rows)
    crop_h = 34 * k_max                           # 26 базовых пикселей над нижним рядом ступней и 8 под ним
    label_w = 260
    try:
        font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"), 16)
    except OSError:
        font = ImageFont.load_default()
    W, H = label_w + 4 * (cell_w + 8), len(rows) * (crop_h + 10) + 10
    out = Image.new("RGB", (W, H), (200, 200, 200))
    d = ImageDraw.Draw(out)
    y = 10
    for name, k, best in rows:
        n_blob = sum(1 for _, m, _ in per_set[name][1] if m["blob"])
        d.text((8, y + 4), name, fill=(0, 0, 0), font=font)
        d.text((8, y + 26), "k=%d  пятно: %d из %d" % (k, n_blob, len(per_set[name][1])), fill=(60, 60, 60), font=font)
        x = label_w
        for index, m, im in best:
            top = m["bottom"] + 8 * k - crop_h
            part = im.crop((0, top, im.width, top + crop_h))
            bg = Image.new("RGBA", part.size, (200, 200, 200, 255))
            bg.alpha_composite(part)
            out.paste(bg.convert("RGB"), (x, y))
            d.text((x + 2, y + 2), "#%d%s" % (index, " *" if m["blob"] else ""), fill=(160, 0, 0), font=font)
            x += cell_w + 8
        y += crop_h + 10
    out.save(path)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd"))
    ap.add_argument("--out", default=os.path.join("census", "ao"))
    ap.add_argument("--sheet", default=SHEET)
    args = ap.parse_args()
    rows, per_set = census(args.root)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "unit_shadow.tsv")
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("set\tk\tframes\tmeasured\tblob_frames\tblob_share\n")
        for r in sorted(rows, key=lambda r: -r[5]):
            f.write("\t".join(str(v) for v in r) + "\n")
    shares = sorted(r[5] for r in rows)
    print("наборов %d; с пятном хотя бы на 10%% кадров: %d, на 50%%: %d, медиана доли %.3f"
          % (len(rows), sum(1 for s in shares if s >= 0.1), sum(1 for s in shares if s >= 0.5), shares[len(shares) // 2]))
    names = [n.strip() + ("" if n.strip().endswith(".PCK") else ".PCK") for n in args.sheet.split(",") if n.strip()]
    sheet_path = os.path.join(args.out, "unit_shadow_sheet.png")
    sheet(per_set, names, sheet_path)
    for n in names:
        r = next((r for r in rows if r[0] == n), None)
        print("  %-22s %s" % (n, "нет набора" if r is None else "кадров %d, с пятном %d (%.0f%%)" % (r[3], r[4], r[5] * 100)))
    print("->", path, sheet_path)


if __name__ == "__main__":
    main()
