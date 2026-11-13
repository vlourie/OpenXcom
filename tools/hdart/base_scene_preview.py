#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Ролик «Живой базы» без игры (docs/research/base-living-2026-10-22.md, шаг 0).

Склеивает витринную базу 6x6 из картинок пилота (gen_base_paint.py) и прогоняет все слои, которые потом
будет рисовать движок: карта высоты и свет от ламп (в том числе на соседей и скалу), смена дня и ночи,
рябь воды, частицы (пар, пузыри, искры сварки, угольки, пыль стройки), вращение (радар, турели), огни
по состоянию (вторая лаборатория загорается, когда в неё приходят учёные), экипаж по коридорам
(ночью - с фонариками), стройка с проявлением, подсветка под мышью и голограмма новой постройки.

Всё - функции от времени ролика t и своего генератора чисел (numpy, seed); ГСЧ игры здесь нет вообще.
Нет картинки стиля - берётся нынешний пак (user/mods/hd/hd/BASEBITS.PCK), так и снимается «до».

    py -3.13 tools/hdart/base_scene_preview.py --style painted
    py -3.13 tools/hdart/base_scene_preview.py --style before --seconds 4       нынешний пак, для сравнения
    py -3.13 tools/hdart/base_scene_preview.py --style painted --still 5,14      только кадры (секунды)
Выход art/base_living/preview/<стиль>/: living_base.mp4, frame_<сек>.png, poster.png.
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

C = 128                                     # пикселей на клетку (k = 4)
N = 6
S = C * N
BAR = 72                                    # полоса подписи под базой
PILOT = os.path.join(ROOT, "art", "base_living", "pilot")
PACK = os.path.join(ROOT, "user", "mods", "hd", "hd", "BASEBITS.PCK")
OUT = os.path.join(ROOT, "art", "base_living", "preview")
FPS = 30
T_TOTAL = 24.0

# Витринная база: (тип, x, y). Мастерская в (4,5) строится, клетка (5,5) - место для голограммы.
LAYOUT = [
    ("STR_HANGAR", 0, 0), ("STR_LABORATORY", 2, 0), ("STR_LABORATORY", 3, 0),
    ("STR_SMALL_RADAR_SYSTEM", 4, 0), ("STR_LASER_DEFENSES", 5, 0),
    ("STR_CORRIDOR", 2, 1), ("STR_WORKSHOP", 3, 1), ("STR_GENERAL_STORES", 4, 1), ("STR_GENERAL_STORES", 5, 1),
    ("STR_LIVING_QUARTERS", 0, 2), ("STR_CORRIDOR", 1, 2), ("STR_ACCESS_LIFT", 2, 2), ("STR_CORRIDOR", 3, 2),
    ("STR_HELLERIUM_PLANT", 4, 2),
    ("STR_LIVING_QUARTERS", 0, 3), ("STR_MED_BAY", 1, 3), ("STR_CORRIDOR", 2, 3), ("STR_GYM_ROOM", 3, 3),
    ("STR_PRISON", 0, 4), ("STR_ONSEN", 2, 4), ("STR_SUMMONING_CIRCLE", 3, 4), ("STR_CORRIDOR", 4, 4),
    ("STR_LASER_DEFENSES", 5, 4),
    ("STR_BURROW", 2, 5), ("STR_CORRIDOR", 3, 5), ("STR_WORKSHOP", 4, 5),
]
BUILDING = (4, 5)                           # клетка стройки
GHOST = ("STR_ONSEN", 5, 5)                 # голограмма
HOVER = (3, 0)                              # подсветка под мышью (вторая лаборатория)
LAB2_ON = 4.6                               # в вторую лабораторию пришли учёные

# Огни по типу: (x, y) в долях постройки, вид, цвет, радиус в клетках, параметры.
# Виды: steady, blink, pulse, flicker, tv, chase, weld, night (дежурный, только ночью), screen.
LIGHTS = {
    "STR_ACCESS_LIFT": [((.36, .36), "blink", (1, .2, .1), .45, {"period": 1.6, "phase": 0}),
                        ((.64, .64), "blink", (1, .2, .1), .45, {"period": 1.6, "phase": .5}),
                        ((.5, .5), "pulse", (1, .85, .6), .55, {"period": 5.0})],
    "STR_HANGAR": [((.62 + .27 * math.cos(a * math.pi / 6), .48 + .27 * math.sin(a * math.pi / 6)), "chase",
                    (.4, 1, .5), .28, {"i": a, "n": 12, "period": 2.4}) for a in range(12)]
                  + [((.15, .15), "steady", (1, .8, .55), .9, {}), ((.15, .85), "steady", (1, .8, .55), .9, {})],
    "STR_LABORATORY": [((.33, .35), "screen", (.45, .85, 1), .5, {}), ((.33, .62), "screen", (.45, .85, 1), .5, {}),
                       ((.63, .36), "screen", (.5, 1, .8), .5, {}), ((.63, .63), "screen", (.45, .85, 1), .5, {}),
                       ((.5, .5), "steady", (.9, .85, .75), .55, {})],
    "STR_WORKSHOP": [((.35, .14), "steady", (1, .78, .45), .8, {}), ((.5, .52), "weld", (.7, .85, 1), .7, {})],
    "STR_GENERAL_STORES": [((.5, .5), "flicker", (1, .8, .5), .75, {"seed": 3})],
    "STR_SMALL_RADAR_SYSTEM": [((.5, .5), "pulse", (.4, 1, .55), .6, {"period": 4.0}),
                               ((.25, .25), "blink", (1, .3, .2), .3, {"period": 2.0, "phase": .2})],
    "STR_LASER_DEFENSES": [((.5, .5), "pulse", (1, .3, .3), .45, {"period": 3.0}),
                           ((.5, .2), "blink", (1, .9, .8), .3, {"period": 1.2, "phase": .3})],
    "STR_LIVING_QUARTERS": [((.2, .22), "steady", (1, .75, .45), .45, {"home": 1}),
                            ((.5, .2), "steady", (1, .75, .45), .45, {"home": 1}),
                            ((.8, .22), "tv", (.5, .65, 1), .45, {}),
                            ((.2, .8), "steady", (1, .75, .45), .45, {"home": 1}),
                            ((.8, .8), "steady", (1, .75, .45), .45, {"home": 1}),
                            ((.5, .55), "night", (1, .6, .35), .5, {})],
    "STR_CORRIDOR": [((.5, .5), "night", (1, .7, .4), .7, {})],
    "STR_MED_BAY": [((.5, .38), "pulse", (1, .35, .35), .55, {"period": 1.1}),
                    ((.5, .75), "steady", (.85, 1, .9), .8, {})],
    "STR_PRISON": [((.88, .9), "pulse", (.4, 1, .4), .35, {"period": 2.5})]
                  + [((x, y), "flicker", (1, .6, .4), .22, {"seed": int(x * 10 + y * 100)})
                     for x in (.3, .55) for y in (.25, .5, .75)],
    "STR_GYM_ROOM": [((.18, .1), "steady", (1, .85, .4), .55, {}), ((.4, .1), "steady", (1, .85, .4), .55, {})],
    "STR_ONSEN": [((.55, .1), "flicker", (1, .7, .35), .45, {"seed": 7}),
                  ((.9, .1), "flicker", (1, .7, .35), .45, {"seed": 8}),
                  ((.75, .6), "pulse", (.3, .8, 1), .6, {"period": 6.0})],
    "STR_SUMMONING_CIRCLE": [((.5, .5), "pulse", (1, .15, .35), 1.1, {"period": 3.2})]
                            + [((.5 + .33 * math.cos(a * math.pi / 4), .5 + .33 * math.sin(a * math.pi / 4)),
                                "flicker", (1, .55, .2), .25, {"seed": 20 + a}) for a in range(8)],
    "STR_HELLERIUM_PLANT": [((.45, .5), "pulse", (.6, 1, .25), 1.0, {"period": 2.7}),
                            ((.07, .07), "flicker", (1, .6, .25), .45, {"seed": 30}),
                            ((.93, .07), "flicker", (1, .6, .25), .45, {"seed": 31}),
                            ((.5, .88), "screen", (.4, .7, 1), .4, {})],
    "STR_BURROW": [((.5, .5), "flicker", (1, .55, .2), .7, {"seed": 40})],
}
# У нарисованной постройки огни ищутся по рисунку (base_lights.py); руками - только то, чего на рисунке
# не видно как лампы: свечение воды и круга, кольцо огней ангара, сварка, дежурный свет, лампы жилья.
SPECIAL = {"STR_HANGAR": ("chase", "steady"), "STR_HELLERIUM_PLANT": ("pulse",), "STR_SUMMONING_CIRCLE": ("pulse", "flicker"),
           "STR_ONSEN": ("pulse",), "STR_WORKSHOP": ("weld",), "STR_CORRIDOR": ("night",), "STR_LIVING_QUARTERS": ("night", "tv"),
           "STR_MED_BAY": ("pulse",), "STR_BURROW": ("flicker",), "STR_SMALL_RADAR_SYSTEM": ("pulse",)}


def lights_of(f, style):
    """Огни постройки: найденные на рисунке + особые из LIGHTS; у старого пака - LIGHTS целиком."""
    manual = LIGHTS.get(f.type, [])
    if not getattr(f, "painted", False):
        return manual
    import base_lights
    master = os.path.join(PILOT, style, f.type + "@512.png")
    rgba = np.asarray(Image.open(master).convert("RGBA")) if os.path.exists(master) else f.rgba
    out = [L for L in manual if L[1] in SPECIAL.get(f.type, ())]
    home = f.type in ("STR_LIVING_QUARTERS", "STR_BURROW")
    for u, v, kind, col, rad, _area in base_lights.lights(rgba, f.cols, f.rows):
        prm = {"period": 1.4 + (u * 7 + v * 3) % 1.2, "phase": (u * 13 + v * 5) % 1} if kind in ("blink", "pulse") else {}
        if kind == "steady" and home:
            prm["home"] = 1
        if kind == "steady" and f.type in ("STR_BURROW", "STR_ONSEN", "STR_SUMMONING_CIRCLE"):
            kind, prm = "flicker", {"seed": int(u * 100 + v * 10)}
        out.append(((u, v), kind, col, rad, prm))
    return out


# Вращение: центр и радиус в долях постройки, скорость (оборотов в секунду) или качание (градусы, период).
SPIN = {"STR_SMALL_RADAR_SYSTEM": ((.5, .5), .26, {"rps": .18}),
        "STR_LASER_DEFENSES": ((.5, .5), .2, {"swing": 40, "period": 7.0})}
WATER = {"STR_ONSEN": ("blue", (.75, 1, 1)), "STR_HELLERIUM_PLANT": ("green", (.8, 1, .4))}


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def night(t):
    """0 день, 1 ночь: сумерки 8-11 с, рассвет 18-21 с."""
    if t < 8:
        return 0.0
    if t < 11:
        return float(smooth((t - 8) / 3))
    if t < 18:
        return 1.0
    if t < 21:
        return float(1 - smooth((t - 18) / 3))
    return 0.0


def clock(t):
    """Часы базы для подписи: 14:00 днём, полночь ночью."""
    h = 14 + (t / T_TOTAL) * 24
    return "%02d:%02d" % (int(h) % 24, int((h % 1) * 60))


def hash1(*a):
    v = 0
    for x in a:
        v = (v * 1103515245 + int(x) * 2654435761 + 12345) & 0xFFFFFFFF
    return ((v >> 8) & 0xFFFF) / 65535.0


def noise1(t, seed):
    return (math.sin(t * 7.1 + seed * 1.7) * .5 + math.sin(t * 13.3 + seed * 3.1) * .3
            + math.sin(t * 29.7 + seed * .7) * .2)


# ---------------------------------------------------------------- сцена

class Fac:
    def __init__(self, t, x, y, cols, rows, rgba):
        self.type, self.x, self.y, self.cols, self.rows = t, x, y, cols, rows
        self.rgba = rgba                        # float32 h, w, 4 (0..1)

    def px(self, u, v):
        return (self.x * C + u * self.cols * C, self.y * C + v * self.rows * C)


def load_art(style, rules, sprites):
    """{тип: (cols, rows, rgba 0..1, нарисована ли)}; картинка стиля или нынешний пак."""
    from gen_base_anim import Facility
    out = {}
    for t in sorted({t for t, _x, _y in LAYOUT} | {GHOST[0]}):
        fac = Facility(rules[t], sprites)
        p = os.path.join(PILOT, style, t + ".png")
        painted = style != "before" and os.path.exists(p)
        if painted:
            im = np.asarray(Image.open(p).convert("RGBA"), np.float32) / 255
        else:
            im = np.zeros((fac.rows * C, fac.cols * C, 4), np.float32)
            for n, idx in enumerate(fac.indices):
                f = os.path.join(PACK, "%d.png" % idx)
                cx, cy = (n % fac.cols) * C, (n // fac.cols) * C
                if os.path.exists(f):
                    tile = np.asarray(Image.open(f).convert("RGBA").resize((C, C), Image.NEAREST), np.float32) / 255
                else:
                    a = fac.alpha[cy:cy + C, cx:cx + C]
                    tile = np.dstack([fac.rgb[cy:cy + C, cx:cx + C], a])
                im[cy:cy + C, cx:cx + C] = tile
        out[t] = (fac.cols, fac.rows, im, painted)
    return out


def rock_image(style, sprites):
    p = os.path.join(PILOT, style, "_rock.png")
    if style != "before" and os.path.exists(p):
        r = np.asarray(Image.open(p).convert("RGB").resize((S, S), Image.LANCZOS), np.float32) / 255
        return r * 0.62
    from gen_craft_lights import load_frame
    from gen_base import scale2x
    idx, pal = load_frame(0, sprites)
    tile = pal[scale2x(scale2x(idx[:32, :32]))].astype(np.float32) / 255
    tile = np.asarray(Image.fromarray((tile * 255).astype(np.uint8)).resize((C, C), Image.NEAREST), np.float32) / 255
    return np.tile(tile, (N, N, 1))


class Scene:
    """Всё неподвижное: альбедо, высота, нормали, карты света, вода, кадры экипажа."""

    def __init__(self, style, seed=1):
        from facility_sheet import load_rules, sprites_map
        rules, _ = load_rules()
        sprites = sprites_map()
        self.style = style
        self.before = style == "before"
        art = load_art(style, rules, sprites)
        self.facs = []
        for t, x, y in LAYOUT:
            cols, rows, rgba, painted = art[t]
            self.facs.append(Fac(t, x, y, cols, rows, rgba))
            self.facs[-1].painted = painted
        cols, rows, rgba, _p = art[GHOST[0]]
        self.ghost = Fac(GHOST[0], GHOST[1], GHOST[2], cols, rows, rgba)
        self.grid = -np.ones((N, N), int)
        for i, f in enumerate(self.facs):
            self.grid[f.y:f.y + f.rows, f.x:f.x + f.cols] = i

        rock = rock_image(style, sprites)
        alb = rock.copy()
        foot = np.zeros((S, S), np.float32)
        self.build_alb = None
        for f in self.facs:
            sl = (slice(f.y * C, (f.y + f.rows) * C), slice(f.x * C, (f.x + f.cols) * C))
            a = f.rgba[..., 3:4]
            if (f.x, f.y) == BUILDING:
                self.build_rgba = f.rgba
                continue
            alb[sl] = f.rgba[..., :3] * a + alb[sl] * (1 - a)
            foot[sl] = np.maximum(foot[sl], f.rgba[..., 3])
        if not self.before:
            # тень и затенение скалы у стен построек
            sh = ndimage.gaussian_filter(ndimage.shift(foot, (5, 4), order=0, cval=0), 7)   # не np.roll (R-239)
            ao = ndimage.gaussian_filter(foot, 12)
            k = (1 - 0.55 * sh) * (1 - 0.35 * ao)
            alb = alb * np.where(foot[..., None] > 0.5, 1, k[..., None])
            # пустые клетки - едва заметная разметка сетки, где можно строить
            for gy in range(N):
                for gx in range(N):
                    if self.grid[gy, gx] < 0:
                        cy, cx = gy * C, gx * C
                        alb[cy + 4:cy + C - 4, cx + 4:cx + 6] *= 1.25
                        alb[cy + 4:cy + 6, cx + 4:cx + C - 4] *= 1.25
            self.doors = self.make_doors(alb, foot)
        else:
            self.doors = []
        self.rock = rock
        self.alb = np.clip(alb, 0, 1).astype(np.float32)
        self.foot = foot

        # высота: светлое выше, рама постройки - высокая, скала низкая
        lum = self.alb @ np.array([.3, .55, .15], np.float32)
        dist = ndimage.distance_transform_edt(foot > 0.5)
        frame = np.clip(1 - dist / 16.0, 0, 1) * (foot > 0.5)
        h = ndimage.gaussian_filter(lum, 1.4) * 0.45 + frame * 0.55
        h = np.where(foot > 0.5, h, 0.08 + ndimage.gaussian_filter(lum, 2) * 0.25)
        self.height = h.astype(np.float32) * 14.0              # пикселей
        gy, gx = np.gradient(ndimage.gaussian_filter(self.height, 1.0))
        nz = np.ones_like(gx)
        n = np.sqrt(gx * gx + gy * gy + nz)
        self.normal = np.dstack([-gx / n, -gy / n, nz / n]).astype(np.float32)

        self.lights = []
        for i, f in enumerate(self.facs):
            for (u, v), kind, col, rad, prm in lights_of(f, style):
                x, y = f.px(u, v)
                prm = dict(prm, fac=i)
                self.lights.append(self.make_light(x, y, rad * C, np.array(col, np.float32), kind, prm))
        self.water = []
        for f in self.facs:
            if f.type in WATER and (f.x, f.y) != BUILDING:
                self.water.append(self.make_water(f))
        self.spins = []
        for f in self.facs:
            if f.type in SPIN:
                (u, v), r, prm = SPIN[f.type]
                cx, cy = f.px(u, v)
                rr = int(r * f.cols * C)
                self.spins.append((int(cx), int(cy), rr, prm, hash1(f.x, f.y) * 360))
        self.stamps = crew_stamps()
        self.blob = {r: soft_disc(r) for r in (2, 3, 4, 6, 8, 12, 16)}
        rng = np.random.default_rng(seed)
        self.noise = ndimage.gaussian_filter(rng.random((C, C)), 6)
        self.noise = (self.noise - self.noise.min()) / (np.ptp(self.noise) + 1e-6)

    def make_doors(self, alb, foot):
        """Переходы между соседними постройками: короткий металлический проход через рамы."""
        doors = []
        for gy in range(N):
            for gx in range(N):
                a = self.grid[gy, gx]
                for dx, dy in ((1, 0), (0, 1)):
                    x2, y2 = gx + dx, gy + dy
                    if x2 >= N or y2 >= N:
                        continue
                    b = self.grid[y2, x2]
                    if a < 0 or b < 0 or a == b:
                        continue
                    if (gx, gy) == BUILDING or (x2, y2) == BUILDING:
                        continue
                    if dx:
                        cx, cy, w, h = (gx + 1) * C, gy * C + C // 2, 30, 16
                    else:
                        cx, cy, w, h = gx * C + C // 2, (gy + 1) * C, 16, 30
                    y0, y1, x0, x1 = cy - h // 2, cy + h // 2, cx - w // 2, cx + w // 2
                    yy, xx = np.mgrid[y0:y1, x0:x1]
                    across = (yy - cy) / (h / 2) if dx else (xx - cx) / (w / 2)
                    shade = 0.17 + 0.12 * np.cos(across * 1.4)
                    plate = np.dstack([shade, shade * 0.98, shade * 1.04])
                    plate[np.abs(across) > 0.78] = (0.55, 0.42, 0.14)       # золотой кант, как рамы Пираток
                    alb[y0:y1, x0:x1] = plate
                    foot[y0:y1, x0:x1] = 1
                    doors.append(((gx, gy), (x2, y2), (cx, cy)))
        return doors

    def make_light(self, x, y, r, col, kind, prm):
        r = max(8, int(r))
        y0, y1 = max(0, int(y - r)), min(S, int(y + r))
        x0, x1 = max(0, int(x - r)), min(S, int(x + r))
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        lz = 26.0
        lx, ly, lzz = x - xx, y - yy, lz - self.height[y0:y1, x0:x1]
        d = np.sqrt(lx * lx + ly * ly + lzz * lzz) + 1e-3
        nrm = self.normal[y0:y1, x0:x1]
        ndl = np.clip((nrm[..., 0] * lx + nrm[..., 1] * ly + nrm[..., 2] * lzz) / d, 0, 1)
        fall = np.clip(1 - (np.sqrt(lx * lx + ly * ly) / r) ** 2, 0, 1) ** 2
        m = (ndl * fall).astype(np.float32)
        return {"x": x, "y": y, "box": (y0, y1, x0, x1), "map": m, "col": col, "kind": kind, "prm": prm}

    def make_water(self, f):
        sl = (slice(f.y * C, (f.y + f.rows) * C), slice(f.x * C, (f.x + f.cols) * C))
        rgb = self.alb[sl]
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        hue, glint = WATER[f.type]
        if hue == "blue":
            m = (b > r + 0.12) & (b > g * 0.95)
        else:
            m = (g > r + 0.1) & (g > b + 0.12)
        dist = ndimage.distance_transform_edt(f.rgba[..., 3] > 0.5)
        m &= dist > 14
        lab, n = ndimage.label(m)
        if n:
            sizes = ndimage.sum(m, lab, range(1, n + 1))
            keep = [i + 1 for i, s in enumerate(sizes) if s >= 200]
            m = np.isin(lab, keep)
        w = ndimage.gaussian_filter(m.astype(np.float32), 1.5)
        return {"sl": sl, "mask": w, "glint": np.array(glint, np.float32), "type": f.type,
                "pts": np.argwhere(m)}


def soft_disc(r):
    s = int(r * 2 + 3)
    yy, xx = np.mgrid[-s:s + 1, -s:s + 1].astype(np.float32)
    return np.exp(-(xx * xx + yy * yy) / (2 * (r * .6) ** 2)).astype(np.float32)


def crew_stamps():
    """Фигурки сверху: {(роль, направление 0..15, фаза шага 0..5): rgba 0..1}, 21x21 при C=128."""
    roles = {"sci": ((.93, .95, .97), (.35, .22, .15)), "eng": ((1, .55, .12), (.15, .12, .1)),
             "gal": ((.75, .15, .3), (.9, .75, .3)), "gal2": ((.2, .55, .6), (.15, .1, .08)),
             "guard": ((.18, .2, .26), (.55, .3, .15)), "nurse": ((.55, .9, .75), (.95, .85, .6))}
    out = {}
    z = 4
    size = 21 * z
    u = 1.35 * z                                    # фигурка крупнее клетки сетки на 1,35
    for role, (body, hair) in roles.items():
        for ph in range(6):
            swing = math.sin(ph / 6 * 2 * math.pi) * 1.6
            im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            c = size / 2

            def ell(x, y, rx, ry, col):
                d.ellipse([(c + x * u - rx * u), (c + y * u - ry * u), (c + x * u + rx * u), (c + y * u + ry * u)],
                          fill=col)
            bc = tuple(int(v * 255) for v in body)
            hc = tuple(int(v * 255) for v in hair)
            skin = (226, 180, 150, 255)
            ell(1.2, 1.4, 3.6, 4.2, (0, 0, 0, 80))                       # тень
            ell(swing, -3.3, 1.2, 1.1, skin)                             # руки
            ell(-swing, 3.3, 1.2, 1.1, skin)
            ell(0, 0, 2.2, 3.5, bc + (255,))                             # плечи и тело
            ell(0.7, 0, 1.6, 1.6, hc + (255,))                           # голова (волосы сверху)
            ell(1.5, 0, 0.7, 0.9, skin)                                  # лицо вперёд
            for di in range(16):
                rot = im.rotate(-di * 22.5, resample=Image.BICUBIC)
                small = rot.resize((21, 21), Image.LANCZOS)
                out[(role, di, ph)] = np.asarray(small, np.float32) / 255
    return out


# ---------------------------------------------------------------- экипаж

ROLES = [("sci", "lab", False)] * 3 + [("sci", "lab2", False)] * 3 + [("eng", "work", True), ("eng", "work", False),
         ("eng", "build", False), ("eng", "build", False), ("gal", "gym", False), ("gal2", "store", False),
         ("gal", "hell", True), ("gal2", "hangar", False), ("guard", "patrol", True), ("nurse", "med", False),
         ("gal2", "onsen", False), ("gal", "summon", False)]
PLACES = {"lab": "STR_LABORATORY@2,0", "lab2": "STR_LABORATORY@3,0", "work": "STR_WORKSHOP@3,1",
          "build": "STR_WORKSHOP@4,5", "gym": "STR_GYM_ROOM", "store": "STR_GENERAL_STORES",
          "hell": "STR_HELLERIUM_PLANT", "hangar": "STR_HANGAR", "med": "STR_MED_BAY", "onsen": "STR_ONSEN",
          "summon": "STR_SUMMONING_CIRCLE", "home": "STR_LIVING_QUARTERS"}


def cells_of(scene, key):
    if "@" in key:
        t, xy = key.split("@")
        x, y = map(int, xy.split(","))
        f = scene.facs[scene.grid[y, x]]
        return [(cx, cy) for cy in range(f.y, f.y + f.rows) for cx in range(f.x, f.x + f.cols)]
    out = []
    for f in scene.facs:
        if f.type == key:
            out += [(cx, cy) for cy in range(f.y, f.y + f.rows) for cx in range(f.x, f.x + f.cols)]
    return out


def path_cells(scene, a, b):
    from collections import deque
    prev = {a: None}
    q = deque([a])
    while q:
        c = q.popleft()
        if c == b:
            break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + dx, c[1] + dy)
            if not (0 <= n[0] < N and 0 <= n[1] < N) or n in prev or scene.grid[n[1], n[0]] < 0:
                continue
            same = scene.grid[n[1], n[0]] == scene.grid[c[1], c[0]]
            door = any({d[0], d[1]} == {c, n} for d in scene.doors)
            if same or door or n == BUILDING or c == BUILDING:
                prev[n] = c
                q.append(n)
    if b not in prev:
        return [a]
    out = [b]
    while out[-1] != a:
        out.append(prev[out[-1]])
    return out[::-1]


def simulate(scene, seed=5):
    """Положения экипажа на каждый кадр: [(x, y, направление, фаза, роль, виден, фонарь)]."""
    rng = np.random.default_rng(seed)
    frames = int(T_TOTAL * FPS)
    homes = cells_of(scene, "STR_LIVING_QUARTERS") + cells_of(scene, "STR_BURROW")
    agents = []
    for i, (role, job, night_shift) in enumerate(ROLES):
        home = homes[i % len(homes)]
        a = {"role": role, "job": job, "ns": night_shift, "home": home, "cell": None, "pos": None, "path": [],
             "wait": rng.uniform(0, 3), "dir": rng.integers(16), "step": 0.0, "asleep": False}
        start = cells_of(scene, PLACES[job]) if job not in ("patrol", "lab2") else [home]
        a["cell"] = tuple(start[rng.integers(len(start))])
        a["pos"] = spot(a["cell"], rng)
        agents.append(a)
    out = []
    dt = 1.0 / FPS
    for fi in range(frames):
        t = fi * dt
        n = night(t)
        row = []
        for a in agents:
            if a["path"]:
                tx, ty = a["path"][0]
                dx, dy = tx - a["pos"][0], ty - a["pos"][1]
                d = math.hypot(dx, dy)
                v = 46 * dt
                if d <= v:
                    a["pos"] = (tx, ty)
                    a["path"].pop(0)
                else:
                    a["pos"] = (a["pos"][0] + dx / d * v, a["pos"][1] + dy / d * v)
                    a["dir"] = int(round(math.degrees(math.atan2(dy, dx)) / 22.5)) % 16
                    a["step"] += v / 5.5
                if not a["path"]:
                    a["wait"] = rng.uniform(2.5, 6)
            else:
                a["wait"] -= dt
                if a["wait"] <= 0:
                    go_home = n > 0.5 and not a["ns"]
                    if a["job"] == "lab2" and t < LAB2_ON:
                        go_home = True
                    if go_home:
                        target = a["home"]
                    elif a["job"] == "patrol":
                        cor = cells_of(scene, "STR_CORRIDOR") + cells_of(scene, "STR_PRISON")
                        target = tuple(cor[rng.integers(len(cor))])
                    else:
                        cs = cells_of(scene, PLACES[a["job"]])
                        target = tuple(cs[rng.integers(len(cs))])
                    if target == a["cell"]:
                        a["path"] = [spot(target, rng)]
                    else:
                        cells = path_cells(scene, a["cell"], target)
                        pts = []
                        for c0, c1 in zip(cells, cells[1:]):
                            pts.append(door_point(c0, c1))
                            pts.append(((c1[0] + .5) * C, (c1[1] + .5) * C))
                        pts.append(spot(target, rng))
                        a["path"] = pts
                        a["cell"] = target
                    a["asleep"] = False
                    if not a["path"]:
                        a["wait"] = 3
                if n > 0.6 and not a["ns"] and a["cell"] == a["home"] and not a["path"]:
                    a["asleep"] = True
            vis = not a["asleep"]
            lantern = n > 0.4 and vis and bool(a["path"])
            row.append((a["pos"][0], a["pos"][1], a["dir"], int(a["step"]) % 6 if a["path"] else 0, a["role"], vis,
                        lantern))
        out.append(row)
    return out


def spot(cell, rng):
    return ((cell[0] + .5 + rng.uniform(-.24, .24)) * C, (cell[1] + .5 + rng.uniform(-.24, .24)) * C)


def door_point(c0, c1):
    return ((c0[0] + c1[0] + 1) * C / 2, (c0[1] + c1[1] + 1) * C / 2)


# ---------------------------------------------------------------- кадр

def intensity(L, t, n):
    k, p = L["kind"], L["prm"]
    gain = 0.28 + 0.72 * n
    if k == "steady":
        v = 1.0
    elif k == "blink":
        ph = (t / p["period"] + p["phase"]) % 1
        v = 1.0 if ph < 0.5 else 0.08
    elif k == "pulse":
        v = 0.6 + 0.4 * math.sin(t / p["period"] * 2 * math.pi)
    elif k == "flicker":
        v = 0.82 + 0.18 * noise1(t, p["seed"])
    elif k == "tv":
        v = 0.55 + 0.45 * abs(noise1(t * 1.7, 9))
    elif k == "chase":
        ph = (t / p["period"] * p["n"] - p["i"]) % p["n"]
        v = max(0.12, 1 - ph / 2.5) if ph < 2.5 else 0.12
    elif k == "weld":
        on = hash1(int(t * 9), 77) > 0.55
        v = (1.6 + 0.6 * hash1(int(t * 30), 3)) if on else 0.0
    elif k == "night":
        v = n * 0.9
        gain = 1.0
    elif k == "screen":
        v = 0.8 + 0.2 * abs(noise1(t * .5, 4))
        gain = 0.4 + 0.5 * n
    else:
        v = 1.0
    if p.get("home"):
        v *= 1 - 0.85 * n
    return v * gain


def lab2_gate(scene, L, t):
    f = scene.facs[L["prm"]["fac"]]
    if (f.x, f.y) == HOVER and f.type == "STR_LABORATORY":
        return float(smooth((t - LAB2_ON) / 0.8)) * 0.9 + 0.1
    if (f.x, f.y) == BUILDING:
        return 0.0
    return 1.0


def blend(dst, stamp, x, y, mode="alpha", col=None, a=1.0):
    h, w = stamp.shape[:2]
    x0, y0 = int(round(x)) - w // 2, int(round(y)) - h // 2
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x1, y1 = min(dst.shape[1], x0 + w), min(dst.shape[0], y0 + h)
    if x1 <= max(0, x0) or y1 <= max(0, y0):
        return
    st = stamp[sy0:sy0 + (y1 - max(0, y0)), sx0:sx0 + (x1 - max(0, x0))]
    d = dst[max(0, y0):y1, max(0, x0):x1]
    if st.ndim == 2:
        al = (st * a)[..., None]
        c = np.asarray(col, np.float32)
        if mode == "add":
            d += c * al
        else:
            d[:] = d * (1 - al) + c * al
    else:
        al = st[..., 3:4] * a
        d[:] = d * (1 - al) + st[..., :3] * al


def particles(scene, t, n, alb_post, add):
    """Пар онсэна, пузыри и испарения хеллерия, искры сварки, угольки круга, пыль стройки."""
    for f in scene.facs:
        x0, y0 = f.x * C, f.y * C
        W, H = f.cols * C, f.rows * C
        if f.type == "STR_ONSEN":
            for i in range(26):
                life = 4.5
                age = (t + i * life / 26) % life
                k = int((t + i * life / 26) // life)
                bx = x0 + (0.12 + 0.55 * hash1(i, k)) * W
                by = y0 + (0.2 + 0.65 * hash1(i, k, 2)) * H
                x = bx - age * 4 + math.sin(age * 1.3 + i) * 3
                y = by - age * 7
                a = math.sin(age / life * math.pi) * 0.22
                r = 8 if age < 2 else 12
                lum = 0.55 + 0.45 * (1 - n * 0.6)
                blend(alb_post, scene.blob[r], x, y, "alpha", (lum, lum, lum * 1.02), a)
        if f.type == "STR_HELLERIUM_PLANT":
            for i in range(22):
                life = 1.6
                age = (t + i * life / 22) % life
                k = int((t + i * life / 22) // life)
                w = next((w for w in scene.water if w["type"] == f.type), None)
                if w is None or not len(w["pts"]):
                    break
                py, px = w["pts"][int(hash1(i, k) * (len(w["pts"]) - 1))]
                x, y = w["sl"][1].start + px, w["sl"][0].start + py
                rr = 1 + age / life * 5
                ring = np.clip(1 - np.abs(np.hypot(*np.mgrid[-7:8, -7:8]) - rr) / 1.0, 0, 1).astype(np.float32)
                blend(add, ring, x, y, "add", (.6, 1, .3), (1 - age / life) * 0.6)
            for i in range(10):
                life = 3.5
                age = (t + i * life / 10) % life
                k = int((t + i * life / 10) // life)
                x = x0 + (0.3 + 0.3 * hash1(i, k, 5)) * W + math.sin(age + i) * 4
                y = y0 + (0.35 + 0.3 * hash1(i, k, 6)) * H - age * 6
                blend(alb_post, scene.blob[12], x, y, "alpha", (.55, .9, .3), math.sin(age / life * math.pi) * .12)
        if f.type == "STR_WORKSHOP" and (f.x, f.y) != BUILDING:
            wx, wy = f.px(.5, .52)
            for i in range(18):
                life = 0.7
                age = (t + i * life / 18) % life
                k = int((t + i * life / 18) // life)
                if hash1(int((t - age) * 9), 77) <= 0.55:
                    continue
                ang = hash1(i, k, 1) * 2 * math.pi
                sp = 30 + 50 * hash1(i, k, 2)
                x, y = wx + math.cos(ang) * sp * age, wy + math.sin(ang) * sp * age + 20 * age * age
                blend(add, scene.blob[2], x, y, "add", (1, .75, .35), (1 - age / life) * 1.4)
        if f.type == "STR_SUMMONING_CIRCLE":
            cx, cy = f.px(.5, .5)
            for i in range(16):
                life = 5.0
                age = (t + i * life / 16) % life
                k = int((t + i * life / 16) // life)
                ang = hash1(i, k) * 2 * math.pi + age * 0.6
                rad = (0.12 + 0.22 * hash1(i, k, 3)) * W * (1 - age / life * 0.5)
                x, y = cx + math.cos(ang) * rad, cy + math.sin(ang) * rad
                blend(add, scene.blob[2], x, y, "add", (1, .35, .5), math.sin(age / life * math.pi) * 1.2)
    # пыль и искры стройки
    bx, by = BUILDING
    p = build_progress(t)
    if p < 1:
        for i in range(14):
            life = 2.4
            age = (t + i * life / 14) % life
            k = int((t + i * life / 14) // life)
            x = (bx + 0.15 + 0.7 * hash1(i, k)) * C + age * 5
            y = (by + 0.15 + 0.7 * hash1(i, k, 1)) * C - age * 3
            blend(alb_post, scene.blob[8], x, y, "alpha", (.55, .48, .4), math.sin(age / life * math.pi) * .25)
        for i in range(8):
            life = 0.5
            age = (t + i * life / 8) % life
            k = int((t + i * life / 8) // life)
            x = (bx + 0.2 + 0.6 * hash1(i, k, 9)) * C
            y = (by + 0.2 + 0.6 * hash1(i, k, 8)) * C
            ang = hash1(i, k, 7) * 6.28
            blend(add, scene.blob[2], x + math.cos(ang) * 40 * age, y + math.sin(ang) * 40 * age, "add",
                  (1, .7, .3), (1 - age / life) * 1.2)


def aces(x):
    """Кривая ACES: яркое сжимается мягко, белая лаборатория не выгорает в сплошной белый."""
    return np.clip(x * (2.51 * x + 0.03) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)


def build_progress(t):
    return float(np.clip(0.12 + (t / 17.0) * 0.88, 0, 1))


def render(scene, crew, t):
    n = night(t)
    alb = scene.alb.copy()
    # вода: рябь сдвигом по своей карте и блики
    glints = np.zeros_like(alb)
    if not scene.before:
        for w in scene.water:
            sy, sx = w["sl"]
            h, wd = sy.stop - sy.start, sx.stop - sx.start
            yy, xx = np.mgrid[0:h, 0:wd].astype(np.float32)
            dx = 1.8 * np.sin(0.09 * xx + 0.13 * yy + 2.3 * t) + 1.1 * np.sin(0.17 * yy - 0.05 * xx + 3.4 * t)
            dy = 1.8 * np.sin(0.11 * xx - 0.08 * yy + 2.0 * t) + 1.1 * np.sin(0.15 * xx + 0.12 * yy - 2.9 * t)
            reg = alb[sy, sx]
            src = scene.alb[sy, sx]
            moved = np.dstack([ndimage.map_coordinates(src[..., c], [yy + dy, xx + dx], order=1, mode="nearest")
                               for c in range(3)])
            m = w["mask"][..., None]
            reg[:] = reg * (1 - m) + moved * m
            g = np.clip(np.sin(0.21 * xx + 0.05 * yy + 3 * t) * np.sin(0.07 * xx - 0.19 * yy + 2.3 * t) - 0.72, 0, 1)
            glints[sy, sx] += (g * 3.5)[..., None] * w["glint"] * m * (0.5 + 0.5 * n)
        # вращение: радар крутится, турели осматривают сектор
        for cx, cy, r, prm, ph in scene.spins:
            ang = (t * prm["rps"] * 360 + ph) if "rps" in prm else prm["swing"] * math.sin(
                t / prm["period"] * 2 * math.pi + ph)
            box = scene.alb[cy - r:cy + r, cx - r:cx + r]
            im = Image.fromarray((box * 255).astype(np.uint8)).rotate(-ang, resample=Image.BICUBIC)
            rot = np.asarray(im, np.float32) / 255
            yy, xx = np.mgrid[-r:r, -r:r]
            m = np.clip((r - np.hypot(xx, yy)) / 3.0, 0, 1)[..., None]
            alb[cy - r:cy + r, cx - r:cx + r] = box * (1 - m) + rot * m
        # стройка: леса, проявление рисунка по шуму, кромка горит
        bx, by = BUILDING
        p = build_progress(t)
        sl = (slice(by * C, (by + 1) * C), slice(bx * C, (bx + 1) * C))
        art = scene.build_rgba
        rock = alb[sl] * 0.7
        lat = np.zeros((C, C), np.float32)
        lat[:, ::16] = 1
        lat[::16, :] = 1
        yy, xx = np.mgrid[0:C, 0:C]
        lat[((xx + yy) % 32) == 0] = 0.7
        scaffold = rock * (1 - lat[..., None] * 0.8) + np.array([.75, .62, .25]) * lat[..., None] * 0.8
        reveal = np.clip((p - scene.noise) / 0.05 + 0.5, 0, 1)[..., None]
        a = art[..., 3:4]
        built = art[..., :3] * a + rock * (1 - a)
        alb[sl] = scaffold * (1 - reveal) + built * reveal
        edge = np.clip(1 - np.abs(scene.noise - p) / 0.03, 0, 1) * (p < 1) * a[..., 0]
        glints[sl] += edge[..., None] * np.array([1, .55, .15]) * 1.4
    # экипаж (до света: ночью темнеет, фонарики его освещают)
    if crew is not None and not scene.before:
        fi = min(len(crew) - 1, int(t * FPS))
        for x, y, di, ph, role, vis, _lan in crew[fi]:
            if vis:
                blend(alb, scene.stamps[(role, di, ph)], x, y)

    # свет
    amb_day, amb_night = np.array([.9, .88, .85]), np.array([.2, .25, .38])
    amb = amb_day * (1 - n) + amb_night * n
    if scene.before:
        return finish_frame(scene, np.clip(alb, 0, 1), t)
    acc = np.ones((S, S, 3), np.float32) * amb.astype(np.float32)
    emis = np.zeros((S, S, 3), np.float32)
    for L in scene.lights:
        v = intensity(L, t, n) * lab2_gate(scene, L, t)
        if v <= 0.01:
            continue
        y0, y1, x0, x1 = L["box"]
        acc[y0:y1, x0:x1] += L["map"][..., None] * (L["col"] * v * 0.9)
        blend(emis, scene.blob[3], L["x"], L["y"], "add", L["col"], v * (0.2 + 0.6 * n))
    if crew is not None:
        fi = min(len(crew) - 1, int(t * FPS))
        for x, y, di, ph, role, vis, lan in crew[fi]:
            if lan:
                fx, fy = x + math.cos(di * math.pi / 8) * 10, y + math.sin(di * math.pi / 8) * 10
                blend(acc, scene.blob[16], fx, fy, "add", (1, .85, .6), 0.8 * n)
                blend(emis, scene.blob[2], x + math.cos(di * math.pi / 8) * 5, y + math.sin(di * math.pi / 8) * 5,
                      "add", (1, .9, .7), 0.9 * n)
    # мерцание сварки и вспышка готовой постройки освещают округу
    p = build_progress(t)
    if 17.0 <= t < 18.2:
        k = 1 - (t - 17.0) / 1.2
        bx, by = BUILDING
        blend(acc, scene.blob[16] ** 0.3, (bx + .5) * C, (by + .5) * C, "add", (1, .9, .7), 1.5 * k)
    out = alb * acc
    bloom = ndimage.gaussian_filter(emis, (7, 7, 0)) * 1.2 + emis * 0.6
    add = glints + bloom
    post = out.copy()
    particles(scene, t, n, post, add)
    out = post + add
    out = aces(out * 1.25)
    return finish_frame(scene, np.clip(out, 0, 1), t)


def finish_frame(scene, img, t):
    """Подсветка под мышью, голограмма, курсор, подпись."""
    img = img.astype(np.float32)
    if not scene.before:
        # подсветка второй лаборатории под мышью
        if 1.6 <= t < 5.4:
            k = smooth((t - 1.6) / 0.4) * (1 - smooth((t - 5.0) / 0.4))
            f = scene.facs[scene.grid[HOVER[1], HOVER[0]]]
            sl = (slice(f.y * C, (f.y + f.rows) * C), slice(f.x * C, (f.x + f.cols) * C))
            a = f.rgba[..., 3]
            ring = np.clip(ndimage.gaussian_filter(a, 3) * 2 - a * 1.6, 0, 1)
            pulse = 0.75 + 0.25 * math.sin(t * 6)
            img[sl] = np.clip(img[sl] * (1 + 0.08 * k) + ring[..., None] * np.array([1, .9, .6]) * k * pulse, 0, 1)
        # голограмма постройки на свободной клетке
        if 6.2 <= t < 10.8:
            k = smooth((t - 6.2) / 0.5) * (1 - smooth((t - 10.3) / 0.5))
            g = scene.ghost
            sl = (slice(g.y * C, (g.y + g.rows) * C), slice(g.x * C, (g.x + g.cols) * C))
            lum = g.rgba[..., :3] @ np.array([.3, .55, .15], np.float32)
            a = g.rgba[..., 3]
            yy = np.arange(C, dtype=np.float32)[:, None]
            scan = 0.72 + 0.28 * np.sin(yy * 0.9 - t * 14)
            sweep = np.clip(1 - np.abs(yy - ((t * 70) % (C * 1.3))) / 6, 0, 1)
            col = np.array([.35, .95, 1.0], np.float32)
            ghost = (lum[..., None] * 0.9 + 0.15) * col * scan[..., None] + sweep[..., None] * col * 0.6
            alpha = (a * 0.62 * k * (0.9 + 0.1 * math.sin(t * 31)))[..., None]
            ring = np.clip(ndimage.gaussian_filter(a, 2.5) * 2 - a * 1.5, 0, 1)[..., None]
            img[sl] = np.clip(img[sl] * (1 - alpha) + ghost * alpha + ring * col * k * 0.9, 0, 1)
    im = Image.fromarray((img * 255 + 0.5).astype(np.uint8))
    canvas = Image.new("RGB", (S, S + BAR), (10, 10, 13))
    canvas.paste(im, (0, 0))
    d = ImageDraw.Draw(canvas)
    if not scene.before:
        cur = cursor_at(t)
        if cur:
            x, y = cur
            poly = [(x, y), (x, y + 22), (x + 6, y + 17), (x + 10, y + 26), (x + 14, y + 24), (x + 10, y + 15),
                    (x + 17, y + 15)]
            d.polygon(poly, fill=(255, 255, 255), outline=(0, 0, 0))
    try:
        big = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22)
        small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 17)
    except OSError:
        big = small = ImageFont.load_default()
    if scene.before:
        d.text((16, S + 10), "СЕЙЧАС: нынешний пак (Scale2x x4)", font=big, fill=(230, 230, 230))
        d.text((16, S + 40), "вспышки раз в 30-60 с, 5 кадров в секунду", font=small, fill=(160, 160, 170))
    else:
        n = night(t)
        d.text((16, S + 10), "ЖИВАЯ БАЗА  ·  %s  ·  %s" % (clock(t), "ночная смена" if n > 0.5 else "дневная смена"),
               font=big, fill=(235, 225, 200))
        d.text((16, S + 40), caption(t), font=small, fill=(165, 170, 180))
    return canvas


def cursor_at(t):
    lab = ((HOVER[0] + .62) * C, (HOVER[1] + .58) * C)
    ghost = ((GHOST[1] + .55) * C, (GHOST[2] + .55) * C)
    start = (S * .55, S * .45)
    if t < 1.2:
        return None
    if t < 2.0:
        k = smooth((t - 1.2) / 0.8)
        return (start[0] + (lab[0] - start[0]) * k, start[1] + (lab[1] - start[1]) * k)
    if t < 5.6:
        return lab
    if t < 6.6:
        k = smooth((t - 5.6) / 1.0)
        return (lab[0] + (ghost[0] - lab[0]) * k, lab[1] + (ghost[1] - lab[1]) * k)
    if t < 10.6:
        return (ghost[0] + 6 * math.sin(t * 1.5), ghost[1] + 4 * math.sin(t * 1.1))
    return None


def caption(t):
    if t < 1.6:
        return "свет ламп ложится на пол, соседей и скалу; вода, пар, искры - движком, без записанных кадров"
    if t < LAB2_ON:
        return "под мышью - подсветка по форме постройки; лаборатория пустая - в ней дежурный свет"
    if t < 6.2:
        return "в лабораторию назначили учёных: они идут из жилья, загораются экраны"
    if t < 10.8:
        return "место для новой постройки - голограмма её рисунка вместо мигающей рамки"
    if t < 17:
        return "ночь: жильё гаснет, в коридорах дежурный свет, у идущих - фонарики; стройка идёт"
    if t < 18.4:
        return "мастерская достроена - вспышка, леса уходят"
    return "рассвет: смена просыпается и расходится по местам работы"


# ---------------------------------------------------------------- запуск

_SCENE = None
_CREW = None


def _init(style):
    global _SCENE, _CREW
    _SCENE = Scene(style)
    _CREW = simulate(_SCENE) if style != "before" else None


def _frame(job):
    i, path = job
    _SCENE_RENDER = render(_SCENE, _CREW, i / FPS)
    _SCENE_RENDER.save(path)
    return i


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--style", default="painted", help="painted | diorama | pixel | before")
    ap.add_argument("--seconds", type=float, default=T_TOTAL)
    ap.add_argument("--still", default="", help="только кадры в эти секунды, через запятую")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 4))
    ns = ap.parse_args()
    out = os.path.join(OUT, ns.style)
    os.makedirs(out, exist_ok=True)
    if ns.still:
        _init(ns.style)
        for s in ns.still.split(","):
            render(_SCENE, _CREW, float(s)).save(os.path.join(out, "frame_%04.1f.png" % float(s)))
        print("кадры:", out)
        return 0
    tmp = os.path.join(out, "_frames")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    total = int(ns.seconds * FPS)
    jobs = [(i, os.path.join(tmp, "%05d.png" % i)) for i in range(total)]
    with Pool(ns.jobs, initializer=_init, initargs=(ns.style,)) as pool:
        for k, _i in enumerate(pool.imap_unordered(_frame, jobs, chunksize=4)):
            if k % 60 == 0:
                print("  кадр %d из %d" % (k, total), flush=True)
    mp4 = os.path.join(out, "living_base.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i",
                    os.path.join(tmp, "%05d.png"), "-c:v", "libx264", "-crf", "15", "-preset", "slow",
                    "-pix_fmt", "yuv420p", mp4], check=True)
    for s in (3.0, 7.5, 14.0):
        i = int(s * FPS)
        if i < total:
            shutil.copy(os.path.join(tmp, "%05d.png" % i), os.path.join(out, "frame_%04.1f.png" % s))
    shutil.rmtree(tmp, ignore_errors=True)
    print("ролик:", mp4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
