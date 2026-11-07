#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Чёрные кружки UBERGAL отдельным слоем, как у LOKNAR (Vitali 06.11, DECISIONS 2026-11-05): 120 тел без кружков и по слою на внешность.
Без видеокарты: наклейка находится по чёрному без цвета, заливается кожей вокруг, свой круг со сглаженным краем (R-705).
Пишет в art/doll/pipe_pilot/pasties_uber: bodies/, layers/, chosen/ (папка установки), where.json. В мод не ставит.

    py -3.13 tools/hdart/doll_ubergal_pasties.py
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cv2
import doll_layers_rul as dl
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(HERE))
UI = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "UI")
OUT = os.path.join(ROOT, "art", "doll", "pipe_pilot", "pasties_uber")
K = 4
W, H = 320 * K, 200 * K
ROWS = (64, 82)                                     # строки и столбцы кадра 320x200, где лежат наклейки: лист 120 тел
SIDES = ((62, 79), (79, 97))
EXPECT = ((69.6, 73.2), (88.8, 73.2))               # обычное место наклеек: медиана по телам
BLACK_L, BLACK_C = 75, 14                           # из 255: блик на наклейке закрывает выпуклая оболочка
MIN_AREA = 40
ROUND_SIDE, ROUND_FILL = 1.5, 0.5                   # стороны рамки и заполнение рамки у наклейки
OPEN_SIZES = (3, 7, 11, 15)
GROW = 13                                           # зона заливки шире наклейки: вокруг неё тёмная кайма и блик
LOOKS = ["%s%d" % (g, n) for g in "FM" for n in range(60)]


def find(px):
    """Наклейки тела: [(x, y, r) слева, справа], маска заливки. Точки кадра k=4."""
    lab = cv2.cvtColor(px[..., :3], cv2.COLOR_RGB2LAB).astype(np.int16)
    black = (lab[..., 0] <= BLACK_L) & (np.hypot(lab[..., 1] - 128, lab[..., 2] - 128) <= BLACK_C) & (px[..., 3] > 230)
    hole = np.zeros(black.shape, np.uint8)
    spots = []
    for (c0, c1), (ex, ey) in zip(SIDES, EXPECT):
        m0 = np.zeros(black.shape, np.uint8)
        m0[ROWS[0] * K:ROWS[1] * K, c0 * K:c1 * K] = black[ROWS[0] * K:ROWS[1] * K, c0 * K:c1 * K]
        for size in OPEN_SIZES:                     # у F59 наклейка срослась с чёрной прядью: шире открытие отрезает прядь
            m = cv2.morphologyEx(m0, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
            n, lb, st, _c = cv2.connectedComponentsWithStats(m, connectivity=8)
            # ближний к обычному месту из круглых: чёрные пряди и подвески тоже попадают в окно (F55, F59)
            round_ = [j for j in range(1, n) if st[j, cv2.CC_STAT_AREA] >= MIN_AREA
                      and max(st[j, cv2.CC_STAT_WIDTH], st[j, cv2.CC_STAT_HEIGHT]) <= ROUND_SIDE * min(st[j, cv2.CC_STAT_WIDTH], st[j, cv2.CC_STAT_HEIGHT])
                      and st[j, cv2.CC_STAT_AREA] >= ROUND_FILL * st[j, cv2.CC_STAT_WIDTH] * st[j, cv2.CC_STAT_HEIGHT]]
            if round_:
                break
        if not round_:
            spots.append(None)
            continue
        i = min(round_, key=lambda j: np.hypot(_c[j][0] / K - ex, _c[j][1] / K - ey))
        ys, xs = np.nonzero(lb == i)
        pts = np.stack([xs, ys], axis=1).astype(np.int32)
        hull = cv2.convexHull(pts)
        cv2.fillConvexPoly(hole, hull, 1)
        (x, y), r = cv2.minEnclosingCircle(pts)
        spots.append((round(float(x), 1), round(float(y), 1), round(float(np.sqrt(cv2.contourArea(hull) / np.pi)), 1)))
    return spots, hole


def blur_in(rgb, known, sigma):
    m = known.astype(np.float32)
    c = cv2.GaussianBlur(m, (0, 0), sigma)
    return cv2.GaussianBlur(rgb * m[..., None], (0, 0), sigma) / np.maximum(c, 1e-3)[..., None], c


def strip(px, hole):
    """Наклейка -> кожа вокруг неё, с мягким переходом."""
    rgb = px[..., :3].astype(np.float32)
    alpha = px[..., 3].astype(np.float32) / 255
    wide = cv2.dilate(hole, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (GROW, GROW))) > 0
    known = (alpha > 0.9) & ~wide
    fill, c = blur_in(rgb, known, 3.0)
    for s in (8.0, 20.0):
        f2, c2 = blur_in(rgb, known, s)
        a = np.clip(c / 0.2, 0, 1)[..., None]
        fill, c = fill * a + f2 * (1 - a), np.maximum(c, c2)
    w = cv2.GaussianBlur(wide.astype(np.float32), (0, 0), 2.0)[..., None]
    w = np.maximum(w, wide[..., None].astype(np.float32))
    out = px.copy()
    out[..., :3] = np.clip(rgb * (1 - w) + fill * w + 0.5, 0, 255).astype(np.uint8)
    return out


def circles(spots, radius):
    """Слой кружков: круг со сглаженным краем, верх чуть светлее, как у LOKNAR."""
    s = 4
    out = np.zeros((H, W, 4), np.float32)
    for sp in spots:
        if sp is None:
            continue
        cx, cy, r = sp[0], sp[1], radius
        x0, y0, x1, y1 = int(cx - r - 3), int(cy - r - 3), int(cx + r + 4), int(cy + r + 4)
        yy, xx = np.mgrid[y0:y1:1.0 / s, x0:x1:1.0 / s]
        inside = np.hypot(xx + 0.125 - cx, yy + 0.125 - cy) <= r
        cov = cv2.resize(inside.astype(np.float32), (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
        tone = np.clip(1 - (np.arange(y0, y1) - (cy - r)) / (2 * r), 0, 1)[:, None, None]
        out[y0:y1, x0:x1, :3] = np.array((16, 16, 19), np.float32) + tone * 12
        out[y0:y1, x0:x1, 3] = cov * 255
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def chosen():
    """Папка установки: 120 тел и круги под слотами из рулсета; один круг - столько копий, сколько слотов у его внешности."""
    dst = os.path.join(OUT, "chosen")
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(os.path.join(OUT, "bodies")):
        shutil.copyfile(os.path.join(OUT, "bodies", f), os.path.join(dst, f))
    for n in dl.layer_names():
        race, slot, name = n.split("__", 2)
        if race == "UBERGAL":
            src = "ubergal__3__%s.png" % name.lower()
            shutil.copyfile(os.path.join(OUT, "layers", src), os.path.join(dst, n.lower() + ".png"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(os.path.join(OUT, "bodies"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "layers"), exist_ok=True)
    where = {}
    for look in LOOKS:
        name = "ubergal__2__%s_nude.png" % look.lower()
        px = np.asarray(Image.open(os.path.join(UI, name)).convert("RGBA"))
        spots, hole = find(px)
        where[look] = spots
        Image.fromarray(strip(px, hole), "RGBA").save(os.path.join(OUT, "bodies", name))
    rs = [sp[2] for v in where.values() for sp in v if sp]
    radius = round(float(np.median(rs)), 1)
    for look, spots in where.items():
        Image.fromarray(circles(spots, radius), "RGBA").save(os.path.join(OUT, "layers", "ubergal__3__pasties_%s.png" % look.lower()))
    with open(os.path.join(OUT, "where.json"), "w", encoding="utf-8-sig") as f:
        json.dump({"radius": radius, "where": where}, f, ensure_ascii=False, indent=0)
    chosen()
    miss = [k for k, v in where.items() if None in v]
    print("тел %d, радиус %.1f (мин %.1f, макс %.1f), не найдено %s" % (len(where), radius, min(rs), max(rs), miss))
    print("самые большие:", sorted(((sp[2], k) for k, v in where.items() for sp in v if sp), reverse=True)[:12])
    print("самые маленькие:", sorted((sp[2], k) for k, v in where.items() for sp in v if sp)[:12])


if __name__ == "__main__":
    main()
