#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Живая база 23.10, «трубы - всё» (docs/research/base-living-2026-10-22.md, раздел 11): маска труб и координата
течения u каждой постройки - заранее, по картинке пака, для вида сцены `flow` (HdBaseScene).

На клетку N пишется <N>.flow.png, RGB 128x128 (пиксели пака):
    R  u * 255 - путь от истока (0) до дальнего конца (255), одна шкала на всю постройку; вне трубы - u ближайшей
       трубы (движок масштабирует карту, края не должны тянуть u к нулю)
    G  тело трубы 0..255 - где светится сама жидкость (середина ярче краёв)
    B  ореол 0..255 - размытое тело (свечение на полу и стенке трубы считается здесь, не в кадре)
и строка сцены (FLOW ниже):
    flow steady 1.00 0.55 0.15 0.25 0.35 0.75 0.90
         вид (steady - сгустки идут всё время, fit - поезд сгустков от истока в приступ постройки), цвет,
         steady: скорость (долей пути в с) и шаг сгустков (долей пути); fit: сгустков за приступ и 0;
         яркость тела и ореола

Маска - правило по картинке (оттенок, светлая труба над окружением, белая тонкая, тёмный кабель) только внутри
коридоров вдоль труб, размеченных руками по сетке (листы art/_review/base_living/flow_*.png): в пробе 23.10
свечение электростанции без коридора задевало пол у баков. u - кратчайший путь по самой маске от истоков; часть,
не связанная с истоком, начинается с расстояния до него.

    py -3.13 tools/hdart/base_flow_bake.py --sheet            листы проверки (маска, u, кадр свечения)
    py -3.13 tools/hdart/base_flow_bake.py --out DIR          карты и строки в DIR/hd/BASEBITS.PCK
"""
import argparse
import heapq
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PACK = os.path.join(ROOT, "user", "mods", "hd", "hd", "BASEBITS.PCK")
REVIEW = os.path.join(ROOT, "art", "_review", "base_living")
TILE = 128

GREEN = (.55, 1.0, .35)
ORANGE = (1.0, .55, .15)
BLUE = (.30, .70, 1.0)


def line(*pts, w=7):
    return ("line", pts, w)


def box(x0, y0, x1, y1):
    return ("box", (x0, y0, x1, y1))


def hole(x, y, r):
    return ("hole", (x, y, r))


# Постройка: кадры клеток по строкам, колонок; правило маски; где искать (коридоры line - ломаная и ширина, box,
# минус hole); истоки; вид и параметры строки flow. Пиксели - пака картинки всей постройки (128 на клетку).
def pods(y0):
    """Капсулы ферм тел - сетка 4 x 4 с шагом 48, в нижнем ряду две правые: их блики - не трубы."""
    return [hole(50 + 48 * i, y0 + 48 * j, 14) for j in range(4) for i in range(4) if j < 3 or i >= 2]


QUIET = (.12, .30, .45, .55)        # тихое течение: скорость, шаг, тело, ореол
THIN = (.12, .30, 1.0, 1.0)         # то же по трубке в 1-3 px: её мало, ярче на пиксель
FLOW = {
    # декодер: зелёные кабели, сгустки от бака (светящийся шар справа внизу) приступом раз в 60 с (CYCLE 60 10)
    "STR_HYPER_WAVE_DECODER": dict(tiles=[32], cols=1, rule=("hue", 85, 40, .30, .08), where=[box(8, 8, 120, 120)],
                                   src=[(90, 87)], soft=1.6, mode="fit", col=GREEN, par=(2, 0, 1.0, 1.4)),
    # электростанция: светлые трубы от двух оранжевых баков к щиту «$» и к решётке; коридоры обходят баки
    "STR_POWER_PLANT": dict(tiles=[341], cols=1, rule=("tube", 4.5), where=[
        line((30, 51), (30, 62.5), (94, 62.5), (94, 51)), line((66, 62.5), (66, 84), (47, 85)),
        line((30, 62.5), (25, 67), (25, 73)), line((79, 106), (79, 83), (105, 83))],
        src=[(29, 52), (94, 52)], soft=1.6, mode="steady", col=ORANGE, par=(.25, .35, .75, .90)),
    # реактор: стальные трубы от сердца во все стороны
    "STR_FUSION_REACTOR": dict(tiles=[350], cols=1, rule=("bright", .04, .30), where=[
        line((64, 56), (64, 8), w=9), line((66, 44), (74, 39), (90, 38), (90, 16), w=9),
        line((51, 67), (33, 67), w=9), line((32, 49), (32, 74), w=9), line((32, 49), (8, 49), w=9),
        line((32, 74), (8, 74), w=9), line((77, 68), (108, 68), w=9),
        line((57, 84), (57, 110), w=8), line((70, 84), (70, 110), w=8)],
        src=[(64, 56), (51, 67), (77, 68), (57, 82), (70, 82), (64, 56)], soft=2.0, mode="steady", col=ORANGE,
        par=(.25, .35, .75, .90)),
    # нефтезавод: колено светлой трубы и оранжевые трубки в углу
    "STR_REFINERY": dict(tiles=[370], cols=1, rule=("lum", .50, .35), where=[
        line((6, 45), (20, 45), (26, 50), (28, 58), (28, 88), w=15)],
        src=[(6, 45)], soft=3.0, mode="steady", col=(1.0, .68, .28), par=QUIET),
    "STR_HYDROPONICS": dict(tiles=[389, 390, 391, 392], cols=2, rule=("lum", .45, .40), where=[
        line((123, 12), (123, 238), w=20), line((16, 123), (232, 123), w=20)],
        src=[(123, 123)], soft=3.0, mode="steady", col=BLUE, par=(.10, .25, .30, .40), dark=.3),
    "STR_HYDROPONICS_BOOM_HARVEST": dict(tiles=[413, 414, 415, 416], cols=2, rule=("lum", .45, .40), where=[
        line((121, 14), (121, 232), w=18), line((16, 123), (232, 123), w=18)],
        src=[(121, 123)], soft=3.0, mode="steady", col=BLUE, par=(.10, .25, .30, .40), dark=.3),
    "STR_HYDROPONICS_WEED": dict(tiles=[397, 398, 399, 400], cols=2, rule=("lum", .45, .40), where=[
        line((123, 14), (123, 234), w=20), line((18, 125), (230, 125), w=20)],
        src=[(123, 125)], soft=3.0, mode="steady", col=BLUE, par=(.10, .25, .30, .40), dark=.3),
    "STR_HYDROPONICS_WEED_HARVEST": dict(tiles=[405, 406, 407, 408], cols=2, rule=("lum", .40, .50), where=[
        line((121, 12), (121, 234), w=18), line((18, 125), (230, 125), w=18)],
        src=[(121, 125)], soft=3.0, mode="steady", col=BLUE, par=(.10, .25, .30, .40), dark=.3),
    # разрушитель-щит: красные и синие кабели между четырьмя шарами
    "STR_DISRUPTOR_SHROUD": dict(tiles=[515], cols=1, rule=("hue2", (355, 25, .35), (220, 30, .30)), where=[
        box(24, 30, 100, 98), hole(41.5, 40, 12), hole(85, 40, 12), hole(41.5, 85, 12), hole(85, 85, 12)],
        src=[(52, 41)], soft=1.4, mode="steady", col=(.70, .55, 1.0), par=QUIET),
    # клонарий: тёмные кабели между капсулами и вниз к стене
    "STR_CLONING_CENTRE": dict(tiles=[374], cols=1, rule=("tube", 2.6, "dark"), where=[
        line((68, 46), (77, 49), (88, 45)), line((64, 55), (61, 63), (60, 71)), line((94, 55), (97, 63), (98, 71)),
        line((68, 83), (78, 86), (89, 82)), line((62, 94), (62, 106)), line((97, 94), (98, 106))],
        src=[(75, 49)], soft=1.2, mode="steady", col=(1.0, .50, .65), par=THIN),
    # облучатель: белая трубка от зелёного шара к воронке и между воронками
    "STR_IRRADIATOR_TOWER": dict(tiles=[603], cols=1, rule=("tube", 3.0), where=[
        line((32, 34), (32, 56)), line((40, 84), (40, 96), (65, 96), (65.5, 77.5), (86, 76.5), (88, 70))],
        src=[(32, 34), (40, 84)], soft=1.2, mode="steady", col=(.60, 1.0, .40), par=THIN, dark=.4),
    # фермы тел: тонкие белые трубки от вводов в стене к капсулам; угол с белой плиткой и капсулы - мимо
    "STR_BODY_FARM": dict(tiles=[1044, 1045, 1046, 1047], cols=2, rule=("thin", .62, .12, .06),
                          where=[box(14, 12, 238, 238), ("cut", (6, 168, 100, 242))] + pods(50),
                          src=[(24, 14), (168, 14), (232, 120), (232, 170), (20, 157), (122, 236)], soft=1.0,
                          mode="steady", col=(.55, 1.0, .50), par=(.12, .30, .70, .70), dark=.5),
    "STR_BODY_FARM_E": dict(tiles=[1036, 1037, 1038, 1039], cols=2, rule=("thin", .62, .12, .06),
                            where=[box(14, 12, 238, 238), ("cut", (6, 168, 100, 242))] + pods(45),
                            src=[(26, 14), (170, 14), (226, 14), (18, 154), (120, 236)], soft=1.0,
                            mode="steady", col=(.50, .90, 1.0), par=(.12, .30, .70, .70), dark=.5),
}


def load(tiles, cols):
    rows = len(tiles) // cols
    img = np.zeros((rows * TILE, cols * TILE, 4), np.float32)
    for k, i in enumerate(tiles):
        t = np.asarray(Image.open(os.path.join(PACK, "%d.png" % i)).convert("RGBA")).astype(np.float32) / 255
        img[(k // cols) * TILE:(k // cols + 1) * TILE, (k % cols) * TILE:(k % cols + 1) * TILE] = t
    return img


def seg_dist(h, w, pts):
    """Расстояние каждого пикселя до ломаной."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    d = np.full((h, w), np.inf, np.float32)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        vx, vy = x1 - x0, y1 - y0
        L2 = max(vx * vx + vy * vy, 1e-6)
        t = np.clip(((xx - x0) * vx + (yy - y0) * vy) / L2, 0, 1)
        d = np.minimum(d, np.hypot(xx - (x0 + t * vx), yy - (y0 + t * vy)))
    return d


def region(h, w, where):
    m = np.zeros((h, w), bool)
    yy, xx = np.mgrid[0:h, 0:w]
    for item in where:
        if item[0] == "line":
            m |= seg_dist(h, w, item[1]) <= item[2] / 2
        elif item[0] == "box":
            x0, y0, x1, y1 = item[1]
            m |= (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)
    for item in where:
        if item[0] == "hole":
            x, y, r = item[1]
            m &= np.hypot(xx - x, yy - y) > r
        elif item[0] == "cut":
            x0, y0, x1, y1 = item[1]
            m &= ~((xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1))
    return m


def hsv(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    hi = a[..., :3].max(-1)
    lo = a[..., :3].min(-1)
    d = hi - lo + 1e-6
    h = np.where(hi == r, ((g - b) / d) % 6, np.where(hi == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    return h, d / (hi + 1e-6), hi


def hue_w(a, hue0, tol, sat, vmin=.2):
    h, s, v = hsv(a)
    off = np.abs(h - hue0)
    off = np.minimum(off, 360 - off)
    return np.clip((tol - off) / (tol * .5), 0, 1) * np.clip((s - sat) / .15, 0, 1) * np.clip((v - vmin) / .1, 0, 1)


def pick(a, rule):
    """Пиксели трубы по правилу, 0..1."""
    Y = .3 * a[..., 0] + .59 * a[..., 1] + .11 * a[..., 2]
    _h, s, _v = hsv(a)
    kind = rule[0]
    if kind == "hue":
        return hue_w(a, *rule[1:])
    if kind == "hue2":
        return np.maximum(hue_w(a, *rule[1]), hue_w(a, *rule[2]))
    if kind == "bright":
        # светлая узкая полоса над окружением (стальной цилиндр), а не просто серое (pipes_grey.py)
        top = Y - ndimage.grey_opening(Y, size=(11, 11))
        return ((top > rule[1]) & (s < rule[2])).astype(np.float32)
    if kind == "lum":
        return ((Y > rule[1]) & (s < rule[2])).astype(np.float32)
    if kind == "white":
        return ((Y > rule[1]) & (s < rule[2])).astype(np.float32)
    if kind == "thin":
        top = Y - ndimage.grey_opening(Y, size=(5, 5))
        m = (Y > rule[1]) & (s < rule[2]) & (top > rule[3])
        # блик капсулы - пятно толще трубки: что переживает размыкание 3x3, с каймой - не труба
        blob = ndimage.binary_opening(m, structure=np.ones((3, 3)))
        return (m & ~ndimage.binary_dilation(blob, iterations=2)).astype(np.float32)
    if kind == "dark":
        return ((Y < rule[1]) & (s < rule[2])).astype(np.float32)
    raise ValueError(kind)


def snap(Y, pts, reach=4.0):
    """Ломаная, подвинутая на светлую трубу: каждый отрезок сдвигается по нормали (до reach px), где средняя
    светлота вдоль него больше; вершина - сумма сдвигов соседних отрезков (у прямого угла - каждый по своей оси)."""
    pts = [np.array(p, np.float32) for p in pts]
    offs = []
    for p0, p1 in zip(pts, pts[1:]):
        v = p1 - p0
        L = float(np.hypot(*v))
        nrm = np.array([-v[1], v[0]], np.float32) / max(L, 1e-6)
        ts = np.linspace(0.15, 0.85, max(4, int(L)))
        best = (-1.0, 0.0)
        for o in np.arange(-reach, reach + .01, .5):
            q = p0[None] + ts[:, None] * v[None] + o * nrm[None]
            score = float(ndimage.map_coordinates(Y, [q[:, 1] - .5, q[:, 0] - .5], order=1).mean())
            if score > best[0] + 1e-4 or (abs(score - best[0]) <= 1e-4 and abs(o) < abs(best[1])):
                best = (score, o)
        offs.append(nrm * best[1])
    out = []
    for i, p in enumerate(pts):
        near = [offs[j] for j in (i - 1, i) if 0 <= j < len(offs)]
        if len(near) == 2 and abs(float(np.dot(near[0], near[1]))) > 1e-3 * (np.hypot(*near[0]) * np.hypot(*near[1]) + 1e-6) \
                and abs(abs(float(np.dot(near[0], near[1]))) - np.hypot(*near[0]) * np.hypot(*near[1])) < 1e-3:
            shift = (near[0] + near[1]) / 2       # соседи параллельны - середина
        else:
            shift = sum(near)
        out.append(tuple(p + shift))
    return out


def tube(a, where, width, dark=False):
    """Труба по размеченным осям (подвинутым на светлое, у тёмного кабеля - на тёмное), профиль - ярче середина."""
    Y = .3 * a[..., 0] + .59 * a[..., 1] + .11 * a[..., 2]
    if dark:
        Y = 1 - Y
    h, w = Y.shape
    d = np.full((h, w), np.inf, np.float32)
    for item in where:
        if item[0] == "line":
            d = np.minimum(d, seg_dist(h, w, snap(Y, item[1])))
    return np.clip(1 - (d / (width / 2)) ** 2, 0, 1)


def geodesic(mask, seeds):
    h, w = mask.shape
    d = np.full((h, w), np.inf, np.float32)
    pq = []
    for dd, y, x in seeds:
        if dd < d[y, x]:
            d[y, x] = dd
            pq.append((dd, y, x))
    heapq.heapify(pq)
    steps = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1), (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
    while pq:
        dd, y, x = heapq.heappop(pq)
        if dd > d[y, x]:
            continue
        for oy, ox, c in steps:
            ny, nx = y + oy, x + ox
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and dd + c < d[ny, nx]:
                d[ny, nx] = dd + c
                heapq.heappush(pq, (dd + c, ny, nx))
    return d


def bake(t):
    F = FLOW[t]
    a = load(F["tiles"], F["cols"])
    h, w = a.shape[:2]
    where = region(h, w, F["where"]) & (a[..., 3] > .5)
    if F["rule"][0] == "tube":
        prof = tube(a, F["where"], F["rule"][1], len(F["rule"]) > 2 and F["rule"][2] == "dark") * (a[..., 3] > .5)
        m = prof > .05
        where = m
    else:
        raw = pick(a, F["rule"]) * where
        m = ndimage.binary_closing(raw > .4, iterations=1) & where
    # крошки по 1-3 пикселя - не труба
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n:
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        keep = np.zeros(n + 1, bool)
        keep[1:] = sizes >= 12
        m = keep[lab]
    # путь: каждая связная часть (с перемычками в 1 px) - от пикселя, ближайшего к истоку, плюс зазор до него
    reach = ndimage.binary_dilation(m, iterations=1)
    lab, n = ndimage.label(reach, structure=np.ones((3, 3)))
    seeds = []
    ys, xs = np.nonzero(m)
    for k in range(1, n + 1):
        part = (lab == k) & m
        py, px = np.nonzero(part)
        if not len(py):
            continue
        best = None
        for sx, sy in F["src"]:
            j = int(np.argmin((px - sx) ** 2 + (py - sy) ** 2))
            gap = math.hypot(px[j] - sx, py[j] - sy)
            if best is None or gap < best[0]:
                best = (gap, py[j], px[j])
        seeds.append(best)
    d = geodesic(reach, seeds)
    ok = np.isfinite(d) & m
    far = float(d[ok].max()) if ok.any() else 1.0
    u = np.where(ok, d / max(far, 1.0), 0)
    if F["rule"][0] == "tube":
        core = prof * ok
    else:
        core = np.clip(ndimage.distance_transform_edt(m) / F["soft"], 0, 1) * ok
        core = ndimage.gaussian_filter(core, .6) * reach
    halo = ndimage.gaussian_filter(core, 2.5)
    halo = halo / max(halo.max(), 1e-6) * min(1.0, halo.max() * 2.5)
    # u вне трубы - от ближайшего пикселя трубы
    if ok.any():
        _dist, (iy, ix) = ndimage.distance_transform_edt(~ok, return_indices=True)
        u = u[iy, ix]
    return a, m, u, core, halo, far


def emission(F, u, core, halo, t):
    """Свечение в кадре - как HdBaseScene::draw (вид flow): (добавка, затемнение тела)."""
    col = np.array(F["col"], np.float32)
    a1, a2, gc, gh = F["par"]
    if F["mode"] == "steady":
        ph = (u - a1 * t) / a2
        pulse = (.5 + .5 * np.cos(2 * math.pi * ph)) ** 6
        e = .18 + .82 * pulse
        add = (e * (core * gc + halo * gh))[..., None] * col
        return add, F.get("dark", .15) * core
    # приступ: 10 с, a1 поездов; t - секунда приступа
    length = 10.0
    span = length / a1
    local = t % span
    fade = min(1.0, local / .6, max(0.0, (span - local) / .8))
    head = local / (span * .75) * 1.35 - .05
    slug = sum(np.exp(-((u - (head - .11 * i)) / .045) ** 2) * (1 - .25 * i) for i in range(3))
    behind = head - u
    trail = np.where(behind > 0, np.exp(-np.maximum(behind, 0) / .35) * .35, 0)
    e = (slug + trail) * fade
    add = (e * (core * gc + halo * gh))[..., None] * col + ((core * slug * fade) ** 2 * .6)[..., None] * np.array([.85, 1.0, .75])
    return add, F.get("dark", .30) * core * fade


def sheet(names):
    os.makedirs(REVIEW, exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
    for t in names:
        F = FLOW[t]
        a, m, u, core, halo, far = bake(t)
        rgb = a[..., :3] * a[..., 3:4] + .08 * (1 - a[..., 3:4])
        # маска: тело красным, ореол жёлтым, u - от синего (исток) к белому
        ov = rgb * .45
        ov = ov + halo[..., None] * np.array([.35, .30, 0])
        uc = np.stack([u, u * .6 + .2, 1 - u * .8], -1)
        ov = ov * (1 - core[..., None]) + uc * core[..., None]
        frames = []
        for tt in (0.0, 1.3, 2.6) if F["mode"] == "steady" else (1.0, 2.2, 3.4):
            add, dark = emission(F, u, core, halo, tt)
            frames.append(np.clip(rgb * (1 - dark[..., None]) + add, 0, 1))
        z = 4 if F["cols"] == 1 else 2
        panels = [rgb, ov] + frames
        labels = ["картинка", "маска: тело (u: синий исток - белый конец), ореол жёлтым"] + ["t=%.1f" % v for v in ((0, 1.3, 2.6) if F["mode"] == "steady" else (1, 2.2, 3.4))]
        ims = []
        for p, lb in zip(panels, labels):
            im = Image.fromarray((np.clip(p, 0, 1) * 255).astype(np.uint8)).resize((a.shape[1] * z, a.shape[0] * z), Image.NEAREST)
            dr = ImageDraw.Draw(im)
            dr.rectangle([0, 0, im.width, 22], fill=(0, 0, 0))
            dr.text((6, 1), lb, fill=(255, 255, 255), font=font)
            ims.append(im)
        W = sum(i.width for i in ims)
        out = Image.new("RGB", (W, ims[0].height + 26), (10, 10, 10))
        x = 0
        for i in ims:
            out.paste(i, (x, 26))
            x += i.width
        ImageDraw.Draw(out).text((6, 3), "%s  %s  путь %.0f px, тело %d px" % (t, F["mode"], far, int((core > .3).sum())),
                                 fill=(255, 220, 120), font=font)
        p = os.path.join(REVIEW, "flow_%s.png" % t.replace("STR_", "").lower())
        out.save(p)
        print(p)


def write(names, out):
    dest = os.path.join(out, "hd", "BASEBITS.PCK")
    os.makedirs(dest, exist_ok=True)
    lines = {}
    for t in names:
        F = FLOW[t]
        _a, _m, u, core, halo, _far = bake(t)
        rgb = np.stack([u, core, halo], -1)
        img = (np.clip(rgb, 0, 1) * 255 + .5).astype(np.uint8)
        for k, n in enumerate(F["tiles"]):
            cy, cx = k // F["cols"], k % F["cols"]
            tile = img[cy * TILE:(cy + 1) * TILE, cx * TILE:(cx + 1) * TILE]
            if tile[..., 1].max() == 0 and tile[..., 2].max() == 0:
                continue
            Image.fromarray(tile, "RGB").save(os.path.join(dest, "%d.flow.png" % n), optimize=True)
            c = F["col"]
            p = F["par"]
            lines[n] = "flow %s %.2f %.2f %.2f %.3f %.3f %.2f %.2f %.2f" % (F["mode"], c[0], c[1], c[2], p[0], p[1], p[2], p[3],
                                                                          F.get("dark", .15 if F["mode"] == "steady" else .30))
    return lines


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="типы через запятую (по умолчанию все из FLOW)")
    ap.add_argument("--sheet", action="store_true", help="листы проверки в art/_review/base_living")
    ap.add_argument("--out", default="", help="папка пака: карты <N>.flow.png")
    a = ap.parse_args()
    names = [s for s in a.only.split(",") if s] or list(FLOW)
    if a.sheet:
        sheet(names)
    if a.out:
        for n, ln in sorted(write(names, a.out).items()):
            print(n, ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
