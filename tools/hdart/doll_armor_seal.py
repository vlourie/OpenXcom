#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Выбранные сиды armor_over -> chosen, край вещи плотнее там, где под ним край тела.

Альфа вещи и тела спадает по одному силуэту: на чёрном экране кожа светится линией вдоль тёмной вещи (R-726). Вещь
расширяется на GROW точек k=4 (меньше точки классики) только у края тел всех внешностей; внутренние края на теле не меняются.
Модель не нужна. В мод ставит doll_race_install.py --race armor_over.

    E:\OpenXCom\tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\doll_armor_seal.py
"""
import glob
import os
import sys

import cv2
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PILOT = os.path.join(ROOT, "art", "doll", "pipe_pilot")
LAYERS = os.path.join(PILOT, "armor_over", "layers")
CHOSEN = os.path.join(PILOT, "armor_over", "chosen")
BODIES = os.path.join(PILOT, "layers")
GROW = 4
BLEND = 6.0                                         # на скольких точках k=4 расширение сходит на нет
RAMP = 2.0                                          # ширина мягкого края вещи, как у слоёв
# выбор Vitali 05.11: GANGER B, CASTAWAY LIGHT A, DARK B, RAGS A, TAC_FULL A (A - сид 0, B - сид 1)
PICK = {"ubergal__3__bra_large_black_lace": 1, "ubergal__7__ganger_main": 1, "ubergal__8__ganger_jacket": 1,
        "ubergal__4__castaway_outfit_light": 0, "ubergal__4__castaway_outfit_dark": 1,
        "ubergal__1__rags_back": 0, "ubergal__9__rags": 0, "ubergal__8__tac_suit": 0, "ubergal__14__tac_helmet": 0}


def body_edge():
    """Полоса полупрозрачного края тела хотя бы одной внешности, расширенная на GROW."""
    band = None
    for fn in glob.glob(os.path.join(BODIES, "ubergal__2__*_nude.png")):
        a = np.asarray(Image.open(fn).convert("RGBA"))[..., 3]
        b = (a > 5) & (a < 250)
        band = b if band is None else band | b
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    return cv2.dilate(band.astype(np.uint8), k) > 0


def seal(rgba, zone):
    """Контур вещи отходит наружу на ширину, плавно спадающую за зоной: резкая граница зоны дала бы зубец (правило 12).
    Цвет новых и полупрозрачных точек - от ближней плотной."""
    px = rgba.copy()
    a = px[..., 3]
    reach = GROW * np.clip(cv2.GaussianBlur(zone.astype(np.float32), (0, 0), BLEND) * 2, 0, 1)
    dist = cv2.distanceTransform((a <= 127).astype(np.uint8), cv2.DIST_L2, 5)
    grown = np.clip(0.5 + (reach - dist) / RAMP, 0, 1) * 255
    grown = np.where(reach > 0.2, np.maximum(a, grown), a).astype(np.uint8)
    solid = a > 230
    if solid.any():
        _d, lab = cv2.distanceTransformWithLabels((~solid).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(solid)
        table = np.zeros((lab.max() + 1, 3), np.uint8)
        table[lab[ys, xs]] = px[ys, xs, :3]
        soft = (reach > 0.2) & (grown > 0) & ~solid
        px[soft, :3] = table[lab[soft]]
    px[..., 3] = grown
    return px


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    zone = body_edge()
    os.makedirs(CHOSEN, exist_ok=True)
    for name, seed in PICK.items():
        px = np.asarray(Image.open(os.path.join(LAYERS, "%s_s%d.png" % (name, seed))).convert("RGBA"))
        if int(name.split("__")[1]) > 2:                    # ниже тела край кожу не открывает
            new = seal(px, zone)
            print("%s: новых точек %d" % (name, int(((new[..., 3] > 128) & (px[..., 3] <= 128)).sum())), flush=True)
            px = new
        Image.fromarray(px, "RGBA").save(os.path.join(CHOSEN, name + ".png"))
    print("chosen:", CHOSEN, len(PICK))


if __name__ == "__main__":
    main()
