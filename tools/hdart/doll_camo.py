#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Камуфляж на теле (NUDECAMO) без модели: к готовому HD-телу прибавляется разница классики NUDECAMO - NUDE, размытая под k=4.

Силуэт NUDECAMO и NUDE совпадает (разница до 4 точек из 2420), рисунок пятен у каждой внешности свой, поэтому кадр на группу не годится,
а карта на 128 тел не нужна. Разница, а не множитель: множитель даёт сиреневые пятна на почти нулевых каналах (R-634). Чёрное бельё
тела `hd` остаётся как есть. В мод не ставит.

    py -3.13 tools\hdart\doll_camo.py --race FHUMAN
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cv2
import numpy as np
from PIL import Image
import doll_armor_batch as B
import doll_b2_render as db

SOFT = 1.5                # размытие разницы, точек k=4: край пятна без лесенки x4 (R-121)
DARK = 40                   # темнее этого на HD-теле - бельё, разница не прибавляется


def camo_layer(hd, nude_rgb, camo_rgb, inside):
    """hd - RGBA тела, *_rgb - классика 320x200, inside - точки классики с телом."""
    k = db.K
    size = (hd.shape[1], hd.shape[0])
    mask = cv2.resize(inside.astype(np.float32), size, interpolation=cv2.INTER_NEAREST)
    delta = cv2.resize((camo_rgb.astype(np.float32) - nude_rgb.astype(np.float32)) * inside[..., None], size, interpolation=cv2.INTER_NEAREST)
    weight = np.maximum(cv2.GaussianBlur(mask, (0, 0), SOFT), 0.05)
    delta = cv2.GaussianBlur(delta, (0, 0), SOFT) / weight[..., None]       # у края тела не тянуть к нулю
    rgb = hd[..., :3].astype(np.float32)
    lum = rgb.mean(axis=2)
    keep = np.clip((lum - DARK) / 20, 0, 1)[..., None]                      # бельё, ресницы и прочее тёмное - как на теле
    out = np.clip(rgb + delta * keep, 0, 255).astype(np.uint8)
    return np.dstack([out, hd[..., 3]])


def paint_layer(hd, nude_rgb, camo_rgb, inside, row):
    """Кошки: разница даёт радугу на чужих окрасах (полосы и кожа HD не совпадают с классикой точка в точку). Ниже шеи цвет берётся из классики, а тени и бугры остаются с HD."""
    k = db.K
    size = (hd.shape[1], hd.shape[0])
    lab = lambda x: cv2.cvtColor((x.astype(np.float32) / 255.0), cv2.COLOR_RGB2Lab)
    mask = cv2.resize(inside.astype(np.float32), size, interpolation=cv2.INTER_NEAREST)

    def smooth(x, s):
        big = cv2.resize(x * (inside[..., None] if x.ndim == 3 else inside), size, interpolation=cv2.INTER_NEAREST)
        w = np.maximum(cv2.GaussianBlur(mask, (0, 0), s), 0.05)
        return cv2.GaussianBlur(big, (0, 0), s) / (w[..., None] if x.ndim == 3 else w)

    lc, ln = lab(camo_rgb), lab(nude_rgb)
    res = lab(hd[..., :3])
    res[..., 0] = np.clip(res[..., 0] + smooth(lc[..., 0] - ln[..., 0], SOFT * 2), 0, 100)
    res[..., 1:] = smooth(lc[..., 1:], SOFT * 2)
    painted = np.clip(cv2.cvtColor(res, cv2.COLOR_Lab2RGB) * 255.0 + 0.5, 0, 255)
    base = camo_layer(hd, nude_rgb, camo_rgb, inside).astype(np.float32)
    t = np.clip((np.arange(size[1], dtype=np.float32) - row * k) / (2 * k), 0, 1)[:, None, None]
    keep = np.clip((hd[..., :3].astype(np.float32).mean(axis=2) - DARK) / 20, 0, 1)[..., None]
    out = base[..., :3] * (1 - t * keep) + painted * t * keep
    return np.dstack([out.astype(np.uint8), hd[..., 3]])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--race", default="FHUMAN")
    ns = ap.parse_args()
    B.set_race(ns.race)
    out = os.path.join(B.OUT, "camo")
    os.makedirs(out, exist_ok=True)
    F, PAL = db.sprite_files(), db.game_palette()
    prefix = ns.race + "__2__"
    bodies = B.UI
    pairs = [(x, x.replace("_NUDECAMO", "_NUDE")) for x in sorted(F) if x.startswith(prefix) and x.endswith("_NUDECAMO")]
    if ns.race == "GNOME":                          # HD-тел GNOME в моде ещё нет; тела без ареол, круги отдельным слоем
        bodies = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", "gnome", "pasties", "bodies")
    if ns.race == "NEKOMIMI":                       # у кошек камуфляж в слое тела, HD-тела в моде ещё нет
        bodies = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", "nekomimi", "heads", "layers")
        pairs = [(x, x.replace("__CAMO_", "__NUDE_")) for x in sorted(F) if x.startswith("NEKOMIMI__4__CAMO_F") or x.startswith("NEKOMIMI__4__CAMO_M")]
    done = 0
    for c, n in pairs:
        hd = np.asarray(Image.open(os.path.join(bodies, n.lower() + ".png")).convert("RGBA"))
        a, b = db.load_indices(F[n]), db.load_indices(F[c])
        if ns.race == "NEKOMIMI":
            res = paint_layer(hd, db.to_rgba(a, PAL)[..., :3], db.to_rgba(b, PAL)[..., :3], (a != 0) & (b != 0), 69)
        else:
            res = camo_layer(hd, db.to_rgba(a, PAL)[..., :3], db.to_rgba(b, PAL)[..., :3], (a != 0) & (b != 0))
        Image.fromarray(res, "RGBA").save(os.path.join(out, c.lower() + ".png"))
        done += 1
    print("камуфляж: %d слоёв в %s" % (done, out))


if __name__ == "__main__":
    main()
