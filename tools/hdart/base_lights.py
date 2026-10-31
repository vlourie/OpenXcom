#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Огни постройки базы - автоматически по рисунку (пилот «Живой базы», docs/research/base-living-2026-10-22.md).

На 115 построек лампы руками не расставить. Источник света на рисунке - яркое насыщенное пятно внутри
комнаты (не на раме): экран, лампа, индикатор. Вид огня - по цвету: голубой и синий - экран (ровный, чуть
мерцает), тёплый - лампа (ровная или мерцает, если пламя), красный - сигнальный (мигает), зелёный - индикатор
(дышит). Рама постройки (полоса у силуэта) не смотрится: золото Пираток не лампа.

    py -3.13 tools/hdart/base_lights.py art/base_living/pilot/painted/STR_ACCESS_LIFT@512.png --sheet out.png

Функция lights(rgba) отдаёт список огней в долях постройки - так их берут base_scene_preview.py и
(потом) сборщик пака.
"""
import argparse
import colorsys
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

FRAME = 0.075            # полоса рамы у силуэта, доля клетки
MIN_AREA = 0.00008       # доля площади клетки
MAX_AREA = 0.02


def kind_of(rgb):
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    deg = h * 360
    if s < 0.25:
        return "steady", (1.0, 0.95, 0.85)
    if deg < 18 or deg >= 340:
        return "blink", (1.0, 0.25, 0.15)
    if deg < 65:
        return "steady", (1.0, 0.72, 0.4)
    if deg < 160:
        return "pulse", (0.45, 1.0, 0.45)
    if deg < 260:
        return "screen", (0.45, 0.85, 1.0)
    return "pulse", (0.85, 0.4, 1.0)


def lights(rgba, cols=1, rows=1, limit=24):
    """[(u, v, вид, цвет, радиус в клетках, площадь)] по картинке постройки (float 0..1 или uint8)."""
    a = np.asarray(rgba, np.float32)
    if a.max() > 1.5:
        a = a / 255.0
    h, w = a.shape[:2]
    cell = w / cols
    rgb, alpha = a[..., :3], a[..., 3]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = (mx - mn) / (mx + 1e-4)
    lum = rgb @ np.array([.3, .55, .15], np.float32)
    local = ndimage.uniform_filter(lum, size=max(5, int(cell * 0.12)))
    inside = ndimage.distance_transform_edt(alpha > 0.5) > cell * FRAME
    # светится: заметно ярче окружения и либо очень яркое, либо яркое и насыщенное
    # тон пикселя, градусы (как colorsys, только массивом)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    d = mx - mn + 1e-6
    hue = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    warm = (hue >= 18) & (hue < 65)
    # цветное - ярко и насыщенно; тёплое (золото рам и площадок Пираток - металл, не лампа) - только у самого
    # яркого края; бесцветное - только почти белое и резко ярче окружения (светлый пол не лампа)
    colour = (mx > 0.82) & (sat > 0.3) & (lum > local + 0.12) & ~warm
    lamp = warm & (mx > 0.96) & (sat > 0.08) & (sat < 0.4) & (lum > local + 0.15)    # блик золота насыщеннее 0.4
    white = (mx > 0.97) & (sat < 0.3) & (lum > local + 0.22)
    hot = inside & (colour | lamp | white)
    hot = ndimage.binary_opening(hot, iterations=1)
    lab, n = ndimage.label(hot)
    out = []
    area_cell = cell * cell
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        m = lab[sl] == i
        area = m.sum() / area_cell
        if area < MIN_AREA or area > MAX_AREA:
            continue
        ys, xs = np.nonzero(m)
        cy, cx = ys.mean() + sl[0].start, xs.mean() + sl[1].start
        col = rgb[sl][m].mean(axis=0)
        kind, tint = kind_of(col)
        glow = np.clip(np.array(col) * 0.6 + np.array(tint) * 0.4, 0, 1)
        rad = float(np.clip(0.18 + np.sqrt(area) * 3.0, 0.22, 0.6))
        out.append((cx / w, cy / h, kind, tuple(float(c) for c in glow), rad, float(area)))
    out.sort(key=lambda L: -L[5])
    merged = []                                 # соседние пятна одного вида - один огонь
    for L in out:
        near = [M for M in merged if M[2] == L[2] and abs(M[0] - L[0]) * cols < 0.07 and abs(M[1] - L[1]) * rows < 0.07]
        if not near:
            merged.append(L)
    return merged[:limit]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--cols", type=int, default=1)
    ap.add_argument("--rows", type=int, default=1)
    ap.add_argument("--sheet", default="")
    ns = ap.parse_args()
    im = Image.open(ns.image).convert("RGBA")
    found = lights(np.asarray(im), ns.cols, ns.rows)
    for u, v, kind, col, rad, area in found:
        print("%.3f %.3f %-7s (%.2f %.2f %.2f) r=%.2f area=%.5f" % (u, v, kind, *col, rad, area))
    if ns.sheet:
        bg = Image.new("RGBA", im.size, (20, 20, 24, 255))
        bg.alpha_composite(im)
        d = ImageDraw.Draw(bg)
        for u, v, kind, col, rad, _a in found:
            x, y = u * im.width, v * im.height
            r = 10
            d.ellipse([x - r, y - r, x + r, y + r], outline=tuple(int(c * 255) for c in col) + (255,), width=3)
            d.text((x + r + 2, y - 6), kind, fill=(255, 255, 255, 255))
        bg.convert("RGB").save(ns.sheet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
