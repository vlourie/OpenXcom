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
    done = 0
    for c in sorted(x for x in F if x.startswith(prefix) and x.endswith("_NUDECAMO")):
        n = c.replace("_NUDECAMO", "_NUDE")
        hd = np.asarray(Image.open(os.path.join(B.UI, n.lower() + ".png")).convert("RGBA"))
        a, b = db.load_indices(F[n]), db.load_indices(F[c])
        res = camo_layer(hd, db.to_rgba(a, PAL)[..., :3], db.to_rgba(b, PAL)[..., :3], (a != 0) & (b != 0))
        Image.fromarray(res, "RGBA").save(os.path.join(out, c.lower() + ".png"))
        done += 1
    print("камуфляж: %d слоёв в %s" % (done, out))


if __name__ == "__main__":
    main()
