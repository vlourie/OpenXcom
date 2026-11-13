#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Серый клин в паху слоя тела куклы: остаток серой основы между стрингами и просветом между ног.

Без видеокарты. Серое пятно и его кайма заполняются кожей с соседних бёдер (диффузия от кожи, стринги и прозрачное
в источник не идут), чуть темнее - внутренняя сторона бедра. Альфа не меняется: силуэт и сборка с бронёй те же.
Прежний слой копируется в <папка>_before_wedge. Без --write только мерка и лист до/после.

    py -3.13 tools/hdart/doll_wedge_fix.py --dir art/doll/pipe_pilot/layers
    py -3.13 tools/hdart/doll_wedge_fix.py --dir art/doll/pipe_pilot/layers --write
"""
import argparse
import glob
import os
import shutil
import sys

import numpy as np
from PIL import Image

# Пах у всех тел в одном месте кадра 1280x800, серая основа светлее стрингов и почти без цвета
BOX = (300, 366, 334, 404)
MIN_PX = 40
SHADE = 0.84
RAMP = 5
STEPS = 300


def gray_mask(a):
    """Самое большое серое пятно в BOX, связное. Пусто, если меньше MIN_PX."""
    rgb = a[..., :3].astype(int)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    m = (a[..., 3] > 128) & (sat < 22) & (rgb.max(axis=2) > 70)
    x0, y0, x1, y1 = BOX
    seen = np.zeros(m.shape, bool)
    best = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            if not m[y, x] or seen[y, x]:
                continue
            stack, pts = [(y, x)], []
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                pts.append((cy, cx))
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if y0 <= ny < y1 and x0 <= nx < x1 and m[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(pts) > len(best):
                best = pts
    out = np.zeros(m.shape, bool)
    if len(best) >= MIN_PX:
        ys, xs = zip(*best)
        out[ys, xs] = True
    return out


def dilate(m, n):
    for _ in range(n):
        d = m.copy()
        d[1:] |= m[:-1]
        d[:-1] |= m[1:]
        d[:, 1:] |= m[:, :-1]
        d[:, :-1] |= m[:, 1:]
        m = d
    return m


def fix(a, mask):
    """Новые цвета на месте пятна и каймы: альфа прежняя."""
    rgb = a[..., :3].astype(float)
    v = rgb.max(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    # кайма: переход серого в кожу и в прозрачное, стринги (тёмное) не трогаем
    region = dilate(mask, 3) & (a[..., 3] > 0) & ((v > 55) | mask)
    skin = (a[..., 3] > 200) & ~region & (v > 70) & (sat >= 22)
    near = dilate(region, 12)
    known = skin & near
    if not known.any():
        raise SystemExit("нет кожи рядом с пятном")
    ys, xs = np.where(near)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    cur = rgb[y0:y1, x0:x1].copy()
    r = region[y0:y1, x0:x1]
    k = known[y0:y1, x0:x1]
    w = k.astype(float)
    val = cur * k[..., None]
    for _ in range(STEPS):
        pad_v = np.pad(val, ((1, 1), (1, 1), (0, 0)))
        pad_w = np.pad(w, 1)
        s = pad_v[:-2, 1:-1] + pad_v[2:, 1:-1] + pad_v[1:-1, :-2] + pad_v[1:-1, 2:]
        n = pad_w[:-2, 1:-1] + pad_w[2:, 1:-1] + pad_w[1:-1, :-2] + pad_w[1:-1, 2:]
        have = n > 0
        new_v = np.zeros_like(val)
        new_v[have] = s[have] / n[have][..., None]
        new_w = (n > 0).astype(float)
        new_v[k] = cur[k]
        new_w[k] = 1
        val, w = new_v, new_w
    # край вровень с кожей, к середине темнее: иначе видна заплатка
    depth = np.zeros(r.shape)
    cur_r = r.copy()
    while cur_r.any():
        depth[cur_r] += 1
        e = np.pad(cur_r, 1)
        cur_r = e[:-2, 1:-1] & e[2:, 1:-1] & e[1:-1, :-2] & e[1:-1, 2:] & cur_r
    shade = 1 - (1 - SHADE) * np.clip((depth - 1) / RAMP, 0, 1)
    fill = np.clip(val * shade[..., None], 0, 255)
    out = a.copy()
    sub = out[y0:y1, x0:x1]
    # холодный ободок стрингов на границе с серым: светлота прежняя, оттенок кожи
    bx = sub[..., :3].astype(float)
    bv = bx.max(axis=2)
    rim = dilate(mask, 3)[y0:y1, x0:x1] & ~r & (sub[..., 3] > 0) & (bv >= 20) & (bx[..., 2] >= bx[..., 0])
    sub[..., :3][rim] = np.clip(val[rim] * (bv[rim] / np.maximum(val[rim].max(axis=1), 1))[..., None], 0, 255).round().astype("uint8")
    sub[..., :3][r] = fill[r].round().astype("uint8")
    return out, region


def crop(im):
    x0, y0, x1, y1 = BOX
    return im.crop((x0 - 34, y0 - 34, x1 + 34, y1 + 26))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--glob", default="*__2__*_nude.png")
    ap.add_argument("--sheet", default="art/doll/pipe_pilot/ingame_check/wedge_fix.png")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.dir, a.glob)))
    pairs = []
    for f in files:
        src = np.asarray(Image.open(f).convert("RGBA")).copy()
        m = gray_mask(src)
        if not m.any():
            continue
        new, region = fix(src, m)
        if (new[..., 3] != src[..., 3]).any():
            raise SystemExit("альфа изменилась: " + f)
        print("%s: серых %d, заменено %d" % (os.path.basename(f), int(m.sum()), int(region.sum())))
        pairs.append((f, src, new))
    print("тел %d, с клином %d" % (len(files), len(pairs)))
    if pairs:
        S = 4
        cell = crop(Image.fromarray(pairs[0][1])).size
        sh = Image.new("RGB", (cell[0] * S * len(pairs), cell[1] * S * 2), (0, 0, 0))
        for i, (_, s, n) in enumerate(pairs):
            for j, arr in enumerate((s, n)):
                c = crop(Image.fromarray(arr)).resize((cell[0] * S, cell[1] * S), Image.LANCZOS)
                sh.paste(c, (i * cell[0] * S, j * cell[1] * S), c)
        sh.save(a.sheet)
    if a.write:
        keep = a.dir.rstrip("/\\") + "_before_wedge"
        os.makedirs(keep, exist_ok=True)
        for f, _, n in pairs:
            shutil.copy2(f, os.path.join(keep, os.path.basename(f)))
            Image.fromarray(n).save(f)
        print("записано", len(pairs), "прежние в", keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
