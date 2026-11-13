"""Тикет XP-000564: лист клетки репульсионного щита и график яркости узла по той же формуле, что в HdBaseScene.cpp
(flashWave и ветка glow с flash). Без игры: берёт 29.png из мода, выбирает пиксели узлов как bake (оттенок, насыщенность,
рамки из 29.scene.txt), рисует покой / пик вспышки / паузу между вспышками, и график яркости узла за 60 с (приступ раз
в 50 с по 8 с).

    tools/hdart/.venv/Scripts/python.exe tools/hdart/t564_shield_sheet.py [выходная_папка]
"""
import colorsys
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACK = os.path.join(ROOT, "user", "mods", "hd", "hd", "BASEBITS.PCK")
OUT = sys.argv[1] if len(sys.argv) > 1 else r"E:\tmp\t564"
S = 4                      # мир-пикселей на пиксель пака (k = 4 в игре: клетка 512)
FLASH, GAP, COUNT, LENGTH = 2.0, 1.0, 3, 8.0
PEAK = 1.9
LILAC_CORE = np.array([235.0, 205.0, 255.0])
LILAC_HALO = np.array([190.0, 140.0, 255.0])
HALO_SIGMA, HALO_GAIN = 2.5, 0.6


def flash_wave(t):
    """как flashWave в HdBaseScene.cpp: sin^2 на каждую вспышку, нули в паузах"""
    if t < 0 or t > LENGTH:
        return 0.0
    k = int(t // (FLASH + GAP))
    u = t - k * (FLASH + GAP)
    if k >= COUNT or u >= FLASH:
        return 0.0
    return math.sin(math.pi * u / FLASH) ** 2


def boxblur(v, r):
    for axis in (0, 1):
        for _ in range(3):
            c = np.cumsum(np.pad(v, [(r + 1, r) if a == axis else (0, 0) for a in (0, 1)], mode="edge"), axis=axis)
            n = 2 * r + 1
            if axis == 0:
                v = (c[n:, :] - c[:-n, :]) / n
            else:
                v = (c[:, n:] - c[:, :-n]) / n
    return v


def boxes():
    out = []
    with open(os.path.join(PACK, "29.scene.txt"), encoding="utf-8-sig") as f:
        for line in f:
            w = line.split()
            if w and w[0] == "glow":
                out.append([float(x) for x in w[1:11]])
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    im = Image.open(os.path.join(PACK, "29.png")).convert("RGBA")
    big = im.resize((im.width * S // (im.width // 128), im.height * S // (im.height // 128)), Image.BICUBIC) \
        if im.width != 128 else im.resize((128 * S, 128 * S), Image.BICUBIC)
    alb = np.asarray(big).astype(np.float64)
    H, W = alb.shape[:2]
    rgb = alb[..., :3]
    taken = np.zeros((H, W), bool)
    core = np.zeros((H, W), bool)
    for x, y, w, h, hue, tol, sat, peak, pulses, groups in boxes():
        x0, y0, x1, y1 = max(0, int(x * S)), max(0, int(y * S)), min(W, math.ceil((x + w) * S)), min(H, math.ceil((y + h) * S))
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                if taken[yy, xx]:
                    continue
                # вспышка: только круг 0.38 ширины рамки (узел ~4.7 px; у крайнего узла в рамку попадает лавандовая кайма, до 7.7)
                if ((xx + 0.5) / S - (x + w / 2)) ** 2 + ((yy + 0.5) / S - (y + h / 2)) ** 2 > (0.38 * w) ** 2:
                    continue
                r, g, b = rgb[yy, xx] / 255.0
                hi, lo = max(r, g, b), min(r, g, b)
                d = hi - lo
                if hi < 0.3 or d <= 0.0001 or d / hi < sat:
                    continue
                hh = colorsys.rgb_to_hsv(r, g, b)[0] * 360
                off = abs(hh - hue)
                if min(off, 360 - off) > tol:
                    continue
                taken[yy, xx] = True
                core[yy, xx] = True
    mask = boxblur(core.astype(np.float64), max(1, round((math.sqrt(4 * (HALO_SIGMA * S) ** 2 + 1) - 1) / 2)))
    mask /= max(mask.max(), 1e-9)

    def frame(a):
        out = rgb.copy()
        if a > 0.004:
            m = (mask * HALO_GAIN * a)[..., None]
            out = out * (1 - m) + LILAC_HALO * m
            g = 1 + (PEAK - 1) * a
            c = np.minimum(255.0, rgb * g)
            c = c * (1 - 0.45 * a) + LILAC_CORE * 0.45 * a
            out[core] = c[core]
        return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))

    moments = [("rest, t = 0 (between fits)", 0.0), ("flash 1 peak, t = 1.0 s", 1.0), ("pause between flashes, t = 2.5 s", 2.5),
               ("flash 2 peak, t = 4.0 s", 4.0)]
    pad = 26
    sheet = Image.new("RGB", (W * len(moments) + 10 * (len(moments) - 1), H + pad), (20, 20, 20))
    dr = ImageDraw.Draw(sheet)
    for i, (name, t) in enumerate(moments):
        a = flash_wave(t)
        sheet.paste(frame(a), (i * (W + 10), pad))
        dr.text((i * (W + 10) + 6, 6), "%s  a=%.2f" % (name, a), fill=(230, 230, 230))
    sheet.save(os.path.join(OUT, "sheet_new.png"))

    # график яркости узла за 60 с: два приступа (0..8 с и 50..58 с)
    GW, GH = 1200, 300
    g = Image.new("RGB", (GW, GH + 40), (20, 20, 20))
    d = ImageDraw.Draw(g)
    mean = rgb[core].mean(axis=0)
    lum = lambda a: float(np.dot(np.minimum(255, mean * (1 + (PEAK - 1) * a)) * (1 - 0.45 * a) + LILAC_CORE * 0.45 * a,
                                 [0.299, 0.587, 0.114]))
    base = lum(0)
    top = max(lum(1), base) * 1.05
    pts = []
    for i in range(GW + 1):
        t = i / GW * 60
        a = flash_wave(t) if t < 8 else flash_wave(t - 50)
        pts.append((i, 20 + GH - lum(a) / top * GH))
    d.line(pts, fill=(200, 150, 255), width=2)
    for s in range(0, 61, 10):
        x = s / 60 * GW
        d.line([(x, 20), (x, 20 + GH)], fill=(60, 60, 60))
        d.text((x + 2, GH + 24), "%d s" % s, fill=(200, 200, 200))
    d.text((6, 4), "node brightness (luma of the mean node pixel), rest = %.0f, peak = %.0f; fit every 50 s: 3 flashes x 2 s, gap 1 s" % (base, lum(1)),
           fill=(230, 230, 230))
    g.save(os.path.join(OUT, "graph_new.png"))
    print("pixels:", int(core.sum()), "of", H * W, "-> ", OUT)


main()
