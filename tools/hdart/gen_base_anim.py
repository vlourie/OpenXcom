#!/usr/bin/env python3
"""
gen_base_anim.py - процедурная HD-анимация построек базы по описанию в base_anims.yml.

Постройка собирается так, как её заменяет HD-слой (BaseView::isHdFacility): на каждую
клетку форма (spriteShape + номер) и поверх - картинка (spriteFacility + номер), если она
включена; HD-кадр кладётся под номер hdTileIndex (картинка, если включена, иначе форма).
Каждый слой увеличивается Scale2x дважды (x4, как gen_base.py), затем на цельную постройку
накладываются эффекты из yml, 16 фаз по 200 мс (BaseView::blink) - петля 3.2 с, бесшовная.

Эффекты берут пиксели ВЫБОРКОЙ (sel): цвет палитры (red, orange, yellow, green, cyan, blue,
purple, white, grey, dark), яркость, прямоугольник в пикселях классики, размер связных кусков.
Список эффектов и их ключи - в шапке base_anims.yml.

    py -3 tools/hdart/gen_base_anim.py --probe art/_review/base_anims/probe
    py -3 tools/hdart/gen_base_anim.py --preview art/_review/base_anims
    py -3 tools/hdart/gen_base_anim.py --only STR_ONSEN --out user/mods/hd --out "Пиратки/Dioxine_XPiratez/user/mods/hd"

Без --out ничего в мод не пишется: сначала превью, в мод - после выбора Vitali.
"""
import argparse
import colorsys
import html
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from facility_sheet import load_rules, load_strings, sprites_map  # noqa: E402
from gen_base import scale2x  # noqa: E402
from gen_craft_lights import load_frame  # noqa: E402
import yaml  # noqa: E402

K = 4
PHASES = 16
ENC_W = "utf-8-sig"
SPEC = os.path.join(HERE, "base_anims.yml")
CLASSES = ["none", "red", "orange", "yellow", "green", "cyan", "blue", "purple", "white", "grey", "dark"]
CLASS_RGB = [(0, 0, 0), (255, 40, 40), (255, 140, 0), (255, 235, 0), (40, 220, 40), (0, 230, 230),
             (40, 80, 255), (200, 60, 255), (255, 255, 255), (130, 130, 130), (40, 30, 20)]


# ---------------------------------------------------------------- постройка

class Facility:
    def __init__(self, rule, sprites):
        self.type = rule["type"]
        self.cols = int(rule.get("sizeX", rule.get("size", 1)))
        self.rows = int(rule.get("sizeY", rule.get("size", 1)))
        small = self.cols == 1 and self.rows == 1
        enabled = small or bool(rule.get("spriteEnabled", False))
        shape = int(rule.get("spriteShape", -1))
        graphic = int(rule.get("spriteFacility", -1))
        first = graphic if enabled else shape
        self.indices = [first + n for n in range(self.cols * self.rows)]
        h, w = self.rows * 32, self.cols * 32
        self.rgb = np.zeros((h * K, w * K, 3), np.float32)
        self.alpha = np.zeros((h * K, w * K), np.float32)
        self.crgb = np.zeros((h, w, 3), np.float32)
        self.calpha = np.zeros((h, w), bool)
        self.missing = []
        num = 0
        for y in range(self.rows):
            for x in range(self.cols):
                layers = [shape + num] if shape >= 0 else []
                if enabled and graphic >= 0:
                    layers.append(graphic + num)
                for frame in layers:
                    got = load_frame(frame, sprites)
                    if got is None:
                        self.missing.append(frame)
                        continue
                    idx, pal = got
                    idx = idx[:32, :32].astype(np.int16)
                    pal = pal.astype(np.float32) / 255.0
                    hi = scale2x(scale2x(idx))
                    m, mh = idx != 0, hi != 0
                    cy, cx = y * 32, x * 32
                    ch, cw = idx.shape
                    self.crgb[cy:cy + ch, cx:cx + cw][m] = pal[idx][m]
                    self.calpha[cy:cy + ch, cx:cx + cw] |= m
                    hy, hx = cy * K, cx * K
                    self.rgb[hy:hy + ch * K, hx:hx + cw * K][mh] = pal[hi][mh]
                    self.alpha[hy:hy + ch * K, hx:hx + cw * K][mh] = 1.0
                num += 1
        self.h, self.w = h, w
        self.classes = classify(self.crgb, self.calpha)
        self.hclasses = classify(self.rgb, self.alpha > 0)


def classify(rgb, alpha):
    """Класс цвета пикселя (номер в CLASSES)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    v, s = mx, np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    d = np.maximum(mx - mn, 1e-6)
    hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    out = np.zeros(rgb.shape[:2], np.int8)
    col = (s > 0.35) & (v > 0.25)
    for n, (lo, hi) in ((1, (-1, 14)), (2, (14, 40)), (3, (40, 70)), (4, (70, 160)), (5, (160, 195)),
                        (6, (195, 255)), (7, (255, 340)), (1, (340, 361))):
        out[col & (hue >= lo) & (hue < hi)] = n
    out[~col & (v >= 0.72)] = 8
    out[~col & (v < 0.72) & (v >= 0.2)] = 9
    out[(v < 0.2)] = 10
    out[~alpha] = 0
    return out


def label(mask):
    """4-связные куски маски: (карта номеров, число)."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    n = 0
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]:
            continue
        n += 1
        stack = [(y0, x0)]
        lab[y0, x0] = n
        while stack:
            y, x = stack.pop()
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    stack.append((ny, nx))
    return lab, n


def select(fac, sel):
    """Выборка -> список кусков [(маска HD float, центр HD (x, y), площадь классики)]."""
    sel = sel or {}
    m = fac.calpha.copy()
    if "color" in sel:
        names = sel["color"] if isinstance(sel["color"], list) else [sel["color"]]
        m &= np.isin(fac.classes, [CLASSES.index(c) for c in names])
    v = fac.crgb.max(-1)
    if "bright" in sel:
        m &= v >= float(sel["bright"])
    if "darker" in sel:
        m &= v <= float(sel["darker"])
    if "rect" in sel:
        rects = sel["rect"] if isinstance(sel["rect"][0], list) else [sel["rect"]]
        keep = np.zeros_like(m)
        for x0, y0, x1, y1 in rects:
            keep[y0:y1, x0:x1] = True
        m &= keep
    # золотая рамка постройки не анимируется: слева и сверху 3 пикселя, справа и снизу
    # 6 (там фаска); inset расширяет поле, inset: 0 снимает его
    i = int(sel.get("inset", 3))
    lo, hi = (0, 0) if i == 0 else (i, max(i, 6))
    if lo:
        m[:lo], m[:, :lo] = False, False
    if hi:
        m[-hi:], m[:, -hi:] = False, False
    if "not_rect" in sel:
        rects = sel["not_rect"] if isinstance(sel["not_rect"][0], list) else [sel["not_rect"]]
        for x0, y0, x1, y1 in rects:
            m[y0:y1, x0:x1] = False
    lab, n = label(m)
    parts = []
    for i in range(1, n + 1):
        area = int((lab == i).sum())
        if area < int(sel.get("min", 1)) or area > int(sel.get("max", 10 ** 9)):
            continue
        parts.append((i, area))
    if sel.get("largest"):
        parts = sorted(parts, key=lambda p: -p[1])[:int(sel["largest"])]
    if not parts:
        return []
    keep = np.isin(lab, [i for i, _ in parts])
    lab = np.where(keep, lab, 0)
    hl = scale2x(scale2x(lab))
    out = []
    for i, area in parts:
        hm = (hl == i) & (fac.alpha > 0)
        if sel.get("same_class", True) and "color" in sel:
            hm &= np.isin(fac.hclasses, [CLASSES.index(c) for c in names])
        ys, xs = np.nonzero(hm)
        if not len(xs):
            continue
        out.append((hm.astype(np.float32), (xs.mean() + 0.5, ys.mean() + 0.5), area))
    if sel.get("merge"):
        total = sum(p[0] for p in out)
        ys, xs = np.nonzero(total)
        return [(np.clip(total, 0, 1), (xs.mean() + 0.5, ys.mean() + 0.5), sum(p[2] for p in out))]
    return out


def points(fac, eff):
    """Источники: at: [[x, y], ...] в пикселях классики, иначе центры кусков выборки."""
    if "at" in eff:
        return [((x + 0.5) * K, (y + 0.5) * K) for x, y in eff["at"]]
    found = [c for _, c, _ in select(fac, eff.get("sel"))]
    limit = int(eff.get("limit", 0))
    if limit and len(found) > limit:
        found = [found[i * len(found) // limit] for i in range(limit)]
    return found


# ---------------------------------------------------------------- помощники

def blur(a, r):
    if r <= 0:
        return a
    # PIL не размывает режимы F и I - раздельная гауссова свёртка на numpy
    n = max(1, int(math.ceil(r * 3)))
    x = np.arange(-n, n + 1, dtype=np.float32)
    k = np.exp(-x * x / (2 * r * r))
    k /= k.sum()
    a = np.asarray(a, np.float32)
    p = np.pad(a, ((n, n), (0, 0)), mode="edge")
    a = sum(k[i] * p[i:i + a.shape[0]] for i in range(2 * n + 1))
    p = np.pad(a, ((0, 0), (n, n)), mode="edge")
    return sum(k[i] * p[:, i:i + a.shape[1]] for i in range(2 * n + 1)).astype(np.float32)


def blur3(rgb, r):
    return np.stack([blur(rgb[..., c], r) for c in range(3)], -1)


def wave(t, ph=0.0, speed=1):
    return math.sin(2 * math.pi * (t * speed + ph))


def screen(out, add):
    return 1 - (1 - out) * (1 - np.clip(add, 0, 1))


def rgb_of(c, default):
    if c is None:
        return np.array(default, np.float32)
    if isinstance(c, str):
        c = c.lstrip("#")
        return np.array([int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)
    return np.array(c, np.float32) / (255.0 if max(c) > 1 else 1.0)


def mean_color(fac, m):
    w = m.sum()
    if w <= 0:
        return np.array([1, 1, 1], np.float32)
    return (fac.rgb * m[..., None]).sum((0, 1)) / w


def vivid(c):
    h, s, v = colorsys.rgb_to_hsv(*[float(x) for x in c])
    return np.array(colorsys.hsv_to_rgb(h, max(s, 0.6) if s > 0.15 else s, 1.0), np.float32)


def soft_disc(h, w, cx, cy, r, soft=1.5):
    y0, y1 = max(0, int(cy - r - soft - 1)), min(h, int(cy + r + soft + 2))
    x0, x1 = max(0, int(cx - r - soft - 1)), min(w, int(cx + r + soft + 2))
    out = np.zeros((h, w), np.float32)
    if y0 >= y1 or x0 >= x1:
        return out
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    d = np.sqrt((xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2)
    out[y0:y1, x0:x1] = np.clip((r - d) / soft + 0.5, 0, 1)
    return out


def periodic_noise(h, w, cells, rng, wrap_y=True):
    g = rng.random((cells, cells)).astype(np.float32)
    g = np.concatenate([g, g[:1]], 0) if wrap_y else np.concatenate([g, rng.random((1, cells))], 0)
    g = np.concatenate([g, g[:, :1]], 1)
    big = Image.fromarray((g * 255).astype(np.uint8)).resize((w + w // cells, h + h // cells), Image.BICUBIC)
    a = np.array(big, np.float32)[:h, :w] / 255.0
    return a


# ---------------------------------------------------------------- эффекты

def fx_pulse(fac, out, p, e, ctx):
    """Яркость выборки дышит; glow - мягкий ореол того же цвета."""
    t = p / PHASES
    amp, glow = float(e.get("amp", 0.35)), float(e.get("glow", 0.0))
    stagger = e.get("stagger", 0)
    for n, (m, c, _) in enumerate(ctx["parts"]):
        ph = float(e.get("phase", 0)) + (n * float(stagger))
        f = wave(t, ph, int(e.get("speed", 1)))
        ms = blur(m, 0.6)
        out = out * (1 + amp * f * ms[..., None])
        if glow:
            col = rgb_of(e.get("tint"), vivid(mean_color(fac, m)))
            halo = blur(m, float(e.get("radius", 3)) * K) * glow * (0.55 + 0.45 * f)
            out = screen(out, halo[..., None] * col)
    return out


def fx_blink(fac, out, p, e, ctx):
    """Выборка мигает: вкл/выкл; stagger - куски по очереди (бегущий огонь)."""
    period = int(e.get("period", 8))
    duty = float(e.get("duty", 0.5))
    dim = float(e.get("dim", 0.35))
    glow = float(e.get("glow", 0.6))
    mode = e.get("stagger", "same")
    parts = ctx["parts"]
    order = list(range(len(parts)))
    if e.get("order") == "x":
        order.sort(key=lambda i: parts[i][1][0])
    elif e.get("order") == "angle":
        cx = np.mean([pp[1][0] for pp in parts])
        cy = np.mean([pp[1][1] for pp in parts])
        order.sort(key=lambda i: math.atan2(parts[i][1][1] - cy, parts[i][1][0] - cx))
    rng = np.random.default_rng(int(e.get("seed", 3)))
    offs = rng.integers(0, period, len(parts))
    for rank, i in enumerate(order):
        m, c, _ = parts[i]
        if mode == "seq":
            off = rank * period // max(1, len(parts))
        elif mode == "random":
            off = int(offs[i])
        else:
            off = 0
        on = ((p + off) % period) < duty * period
        ms = blur(m, 0.6)[..., None]
        if on:
            col = rgb_of(e.get("tint"), vivid(mean_color(fac, m)))
            out = out * (1 + 0.25 * ms)
            if glow:
                out = screen(out, blur(m, float(e.get("radius", 2.5)) * K)[..., None] * col * glow)
        else:
            out = out * (1 - ms * (1 - dim))
    return out


def fx_flicker(fac, out, p, e, ctx):
    """Каждый кусок меняет яркость по своему случайному ряду (экраны, лампы, свечи)."""
    lo, hi = float(e.get("lo", 0.75)), float(e.get("hi", 1.2))
    rng = np.random.default_rng(int(e.get("seed", 5)))
    for m, c, _ in ctx["parts"]:
        seq = rng.random(PHASES)
        if e.get("smooth", True):
            seq = (seq + np.roll(seq, 1) + np.roll(seq, -1)) / 3
        f = lo + (hi - lo) * seq[p]
        out = out * (1 + (f - 1) * blur(m, 0.6)[..., None])
    return out


def fx_ripple(fac, out, p, e, ctx):
    """Рябь воды: бегущие волны яркости и блики на гребнях."""
    t = p / PHASES
    amp, wl = float(e.get("amp", 0.12)), float(e.get("wavelength", 6)) * K
    ang = math.radians(float(e.get("angle", 30)))
    glint = float(e.get("glint", 0.5))
    h, w = out.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    noise = ctx.setdefault("noise", periodic_noise(h, w, 5, np.random.default_rng(11)))
    for m, c, _ in ctx["parts"]:
        ph = (xx * math.cos(ang) + yy * math.sin(ang)) / wl + noise * 1.5
        v = np.sin(2 * math.pi * (ph - t * int(e.get("speed", 1))))
        v2 = np.sin(2 * math.pi * (ph * 0.63 + noise * 0.7 + t * 2))
        s = (v * 0.65 + v2 * 0.35)
        out = out * (1 + amp * s * m)[..., None]
        if glint:
            g = np.clip((s - 0.72) / 0.28, 0, 1) * m * glint
            out = screen(out, g[..., None] * np.array([0.9, 0.97, 1.0], np.float32))
    return out


def fx_bubbles(fac, out, p, e, ctx):
    """Пузыри вздуваются и лопаются кольцом (как gen_base_bubbles.py)."""
    h, w = out.shape[:2]
    for m, c, _ in ctx["parts"]:
        key = ("bub", id(m))
        if key not in ctx:
            rng = np.random.default_rng(int(e.get("seed", 7)))
            inner = m > 0.5
            for _ in range(int(e.get("inset", 2)) * K):
                q = inner.copy()
                q[1:] &= inner[:-1]
                q[:-1] &= inner[1:]
                q[:, 1:] &= inner[:, :-1]
                q[:, :-1] &= inner[:, 1:]
                if not q.any():
                    break
                inner = q
            ys, xs = np.nonzero(inner)
            n = int(e.get("count", max(2, int(len(xs) / (K * K * 40)))))
            bubbles = []
            for i in range(n if len(xs) else 0):
                j = rng.integers(len(xs))
                r = float(rng.uniform(*e.get("radius", [1.0, 1.9]))) * K
                bubbles.append((xs[j] + 0.5, ys[j] + 0.5, r, (i * PHASES // max(1, n) + int(rng.integers(0, 2))) % PHASES))
            base = mean_color(fac, m)
            ctx[key] = (bubbles, np.clip(base * 1.6 + 0.08, 0, 1), base * 0.45)
        bubbles, light, dark = ctx[key]
        life = 5
        grow = life - 2
        mm = m[..., None]
        for bx, by, rmax, start in bubbles:
            age = (p - start) % PHASES
            if age >= life:
                continue
            if age < grow:
                r = rmax * (age + 1) / grow
                body = soft_disc(h, w, bx, by, r, 0.8)
                rim = np.clip(soft_disc(h, w, bx, by, r + 0.8, 0.8) - soft_disc(h, w, bx, by, r - 0.8, 0.8), 0, 1)
                gl = soft_disc(h, w, bx - r * 0.35, by - r * 0.35, max(r * 0.28, 0.7), 0.8)
                out = out * (1 - body[..., None] * 0.85 * mm) + light * body[..., None] * 0.85 * mm
                out = out * (1 - rim[..., None] * 0.6 * mm) + dark * rim[..., None] * 0.6 * mm
                out = out * (1 - gl[..., None] * 0.8 * mm) + gl[..., None] * 0.8 * mm
            else:
                k = age - grow + 1
                r = rmax * (1 + 0.45 * k)
                fade = 0.7 if k == 1 else 0.35
                ring = np.clip(soft_disc(h, w, bx, by, r + 0.9, 0.8) - soft_disc(h, w, bx, by, r - 0.9, 0.8), 0, 1) * fade
                out = out * (1 - ring[..., None] * mm) + light * ring[..., None] * mm
    return out


def fx_smoke(fac, out, p, e, ctx):
    """Дым из точек: клубы поднимаются, растут и тают; steam - то же светлым паром."""
    h, w = out.shape[:2]
    col = rgb_of(e.get("color"), [0.42, 0.42, 0.44])
    rise = float(e.get("rise", 10)) * K
    r0, r1 = float(e.get("r0", 1.2)) * K, float(e.get("r1", 3.2)) * K
    op = float(e.get("opacity", 0.55))
    puffs = int(e.get("puffs", 4))
    drift = float(e.get("drift", 2)) * K
    rng = np.random.default_rng(int(e.get("seed", 9)))
    layer = np.zeros((h, w), np.float32)
    for si, (sx, sy) in enumerate(ctx["points"]):
        jitter = rng.random(puffs)
        side = rng.choice([-1, 1])
        for j in range(puffs):
            start = (j * PHASES / puffs + si * 2.7) % PHASES
            age = ((p - start) % PHASES) / PHASES
            x = sx + side * drift * math.sin(math.pi * age) * (0.6 + jitter[j] * 0.6) + drift * 0.6 * age
            y = sy - rise * age
            r = r0 + (r1 - r0) * age
            a = op * min(1.0, age * 5) * (1 - age) ** 1.3
            layer = np.maximum(layer, soft_disc(h, w, x, y, r, r * 0.6) * a)
    layer *= fac.alpha
    return out * (1 - layer[..., None]) + col * layer[..., None]


def fx_sparks(fac, out, p, e, ctx):
    """Искры: короткие яркие вспышки со штрихом у источников, в случайные фазы."""
    h, w = out.shape[:2]
    col = rgb_of(e.get("color"), [1.0, 0.85, 0.4])
    spread = float(e.get("spread", 2.5)) * K
    chance = float(e.get("chance", 0.35))
    count = int(e.get("count", 3))
    add = np.zeros((h, w), np.float32)
    for si, (sx, sy) in enumerate(ctx["points"]):
        rng = np.random.default_rng(int(e.get("seed", 13)) * 1000 + si * 37 + p)
        if rng.random() > chance:
            continue
        for _ in range(count):
            ang = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(0.2, 1.0) * spread
            x, y = sx + math.cos(ang) * d, sy + math.sin(ang) * d
            for s in range(4):
                q = s / 3.0
                add = np.maximum(add, soft_disc(h, w, x - math.cos(ang) * q * 1.8 * K, y - math.sin(ang) * q * 1.8 * K,
                                                0.55 * K * (1 - q * 0.6), 0.7) * (1 - q * 0.7))
    glow = blur(add, 1.2 * K) * 0.8
    return screen(out, (np.maximum(add, glow) * fac.alpha)[..., None] * col)


def fx_fire(fac, out, p, e, ctx):
    """Огонь: шум бежит вверх по выборке, цвет тянется к пламени."""
    h, w = out.shape[:2]
    strength = float(e.get("strength", 0.6))
    key = "firenoise%d" % int(e.get("seed", 17))
    if key not in ctx:
        ctx[key] = periodic_noise(h, w, int(e.get("cells", 6)), np.random.default_rng(int(e.get("seed", 17))))
    n = np.roll(ctx[key], -int(round(p * h / PHASES)), axis=0)
    n2 = np.roll(ctx[key][:, ::-1], -int(round(p * 2 * h / PHASES)), axis=0)
    v = np.clip(n * 0.6 + n2 * 0.4, 0, 1)
    fire = np.stack([np.clip(0.55 + v * 0.6, 0, 1), np.clip(v ** 1.6 * 0.95, 0, 1), np.clip(v ** 4 * 0.5, 0, 1)], -1)
    for m, c, _ in ctx["parts"]:
        s = (blur(m, 0.8) * strength * (0.5 + 0.7 * v))[..., None]
        out = out * (1 - s) + fire * s
    return out


def fx_sweep(fac, out, p, e, ctx):
    """Вращающийся блик по выборке (радар, рулетка, кольцо): яркий край и гаснущий хвост."""
    t = p / PHASES
    h, w = out.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    turns = int(e.get("turns", 1)) * (-1 if e.get("ccw") else 1)
    tail = math.radians(float(e.get("tail", 90)))
    amp = float(e.get("amp", 0.55))
    for m, c, _ in ctx["parts"]:
        cx, cy = (np.array(e["center"], np.float32) + 0.5) * K if "center" in e else c
        a = np.arctan2(yy + 0.5 - cy, xx + 0.5 - cx)
        th = 2 * math.pi * (t * turns + float(e.get("phase", 0)))
        d = (th - a) * (1 if turns >= 0 else -1)
        d = np.mod(d, 2 * math.pi)
        lead = np.exp(-(np.minimum(d, 2 * math.pi - d) / 0.12) ** 2)
        trail = np.where(d < tail, 1 - d / tail, 0) * 0.55
        i = np.maximum(lead, trail) * m
        col = rgb_of(e.get("tint"), vivid(mean_color(fac, m)) * 0.5 + 0.5)
        out = screen(out, (i * amp)[..., None] * col)
        if e.get("dark_back", 0):
            out = out * (1 - (m * (1 - np.maximum(lead, trail)) * float(e["dark_back"])))[..., None]
    return out


def fx_band(fac, out, p, e, ctx):
    """Полоса света пробегает по выборке (блик, развёртка, полив); pause - доля петли без неё."""
    t = p / PHASES
    ang = math.radians(float(e.get("angle", 0)))
    width = float(e.get("width", 3)) * K
    amp = float(e.get("amp", 0.5))
    pause = float(e.get("pause", 0.0))
    speed = int(e.get("speed", 1))
    h, w = out.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    proj = xx * math.cos(ang) + yy * math.sin(ang)
    col = rgb_of(e.get("tint"), [1, 1, 1])
    for m, c, _ in ctx["parts"]:
        pm = proj[m > 0]
        if not len(pm):
            continue
        lo, hi = pm.min() - width * 2, pm.max() + width * 2
        u = (t * speed + float(e.get("phase", 0))) % 1.0
        if u > 1 - pause:
            continue
        pos = lo + (hi - lo) * u / max(1e-6, 1 - pause)
        i = np.exp(-((proj - pos) / width) ** 2) * m
        out = screen(out, (i * amp)[..., None] * col)
    return out


def fx_sway(fac, out, p, e, ctx):
    """Колыхание: пиксели выборки сдвигаются бегущей волной (листва, флаг, пламя свечи)."""
    t = p / PHASES
    h, w = out.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    amp = float(e.get("amp", 0.5)) * K
    wl = float(e.get("wavelength", 8)) * K
    ang = math.radians(float(e.get("angle", 90)))
    src = out.copy()
    for m, c, _ in ctx["parts"]:
        ph = (xx * math.cos(ang) + yy * math.sin(ang)) / wl
        grow = 1.0
        if "anchor_x" in e:
            grow = np.clip(np.abs(xx - (float(e["anchor_x"]) + 0.5) * K) / (float(e.get("reach", 8)) * K), 0, 1)
        dx = amp * np.sin(2 * math.pi * (ph - t)) * grow
        dy = float(e.get("amp_y", 0)) * K * np.cos(2 * math.pi * (ph - t)) * grow
        sx = np.clip(np.round(xx - dx).astype(int), 0, w - 1)
        sy = np.clip(np.round(yy - dy).astype(int), 0, h - 1)
        ok = (m > 0) & (m[sy, sx] > 0)
        out = np.where(ok[..., None], src[sy, sx], out)
    return out


def fx_swarm(fac, out, p, e, ctx):
    """Рой: точки летают по эллипсам вокруг центров (пчёлы, мухи, роботы, пылинки)."""
    t = p / PHASES
    h, w = out.shape[:2]
    rng = np.random.default_rng(int(e.get("seed", 21)))
    col = rgb_of(e.get("color"), [0.1, 0.08, 0.05])
    size = float(e.get("size", 0.6)) * K
    rad = float(e.get("radius", 5)) * K
    glow = float(e.get("glow", 0))
    for sx, sy in ctx["points"]:
        for _ in range(int(e.get("count", 5))):
            rx, ry = rng.uniform(0.3, 1.0) * rad, rng.uniform(0.2, 0.8) * rad
            sp = int(rng.choice([1, 2, 3])) * (1 if rng.random() < 0.5 else -1)
            ph = rng.random()
            wob = rng.uniform(0, 1)
            a = 2 * math.pi * (t * sp + ph)
            x = sx + rx * math.cos(a) + 0.4 * K * math.sin(2 * math.pi * (t * 3 + wob))
            y = sy + ry * math.sin(a)
            d = soft_disc(h, w, x, y, size, 0.8) * fac.alpha
            if glow:
                out = screen(out, blur(d, 1.5 * K)[..., None] * col * glow)
            out = out * (1 - d[..., None]) + col * d[..., None]
    return out


def fx_roll(fac, out, p, e, ctx):
    """Содержимое прямоугольника едет по кругу (конвейер): за петлю - period пикселей классики."""
    x0, y0, x1, y1 = [v * K for v in e["rect"]]
    step = int(round(float(e.get("period", 4)) * K * p / PHASES))
    axis = 1 if e.get("axis", "x") == "x" else 0
    reg = out[y0:y1, x0:x1].copy()
    out = out.copy()
    out[y0:y1, x0:x1] = np.roll(reg, step * (1 if not e.get("reverse") else -1), axis=axis)
    return out


def fx_lid(fac, out, p, e, ctx):
    """Моргание: веко опускается на выборку в заданные фазы (cover - доля закрытия по фазам)."""
    cover = e.get("cover", {7: 0.5, 8: 1.0, 9: 0.5})
    f = float(cover.get(p, 0.0))
    if f <= 0:
        return out
    col = rgb_of(e.get("color"), [0.12, 0.05, 0.03])
    h, w = out.shape[:2]
    yy = np.mgrid[0:h, 0:w][0].astype(np.float32)
    for m, c, _ in ctx["parts"]:
        ys = np.nonzero(m > 0)[0]
        top, bot = ys.min(), ys.max() + 1
        mid = (top + bot) / 2
        half = (bot - top) / 2 * f
        cov = ((yy >= mid - half) & (yy <= mid + half)).astype(np.float32) * blur(m, 0.8)
        cov = np.maximum(cov, ((yy < mid - (bot - top) / 2 * (1 - f)) | (yy > mid + (bot - top) / 2 * (1 - f))) * m)
        out = out * (1 - cov[..., None]) + col * cov[..., None]
    return out


def fx_breathe(fac, out, p, e, ctx):
    """Вздох: область вокруг центра чуть раздувается и опадает (зверь, пасть, сердце)."""
    t = p / PHASES
    amp = float(e.get("amp", 0.05))
    h, w = out.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    src = out.copy()
    for m, c, _ in ctx["parts"]:
        cx, cy = (np.array(e["center"], np.float32) + 0.5) * K if "center" in e else c
        s = 1 + amp * wave(t, float(e.get("phase", 0)), int(e.get("speed", 1)))
        if e.get("beat"):
            u = t * int(e.get("speed", 1)) % 1.0
            s = 1 + amp * (math.exp(-((u - 0.1) / 0.05) ** 2) + 0.6 * math.exp(-((u - 0.3) / 0.05) ** 2))
        sx = np.clip(np.round(cx + (xx + 0.5 - cx) / s - 0.5).astype(int), 0, w - 1)
        sy = np.clip(np.round(cy + (yy + 0.5 - cy) / s - 0.5).astype(int), 0, h - 1)
        wgt = blur(m, 2 * K)
        wgt = np.clip(wgt / max(1e-6, wgt.max()) * 1.6, 0, 1) * (fac.alpha > 0)
        out = out * (1 - wgt[..., None]) + src[sy, sx] * wgt[..., None]
    return out


def fx_tint(fac, out, p, e, ctx):
    """Цветное свечение поверх выборки, дышит (жар, неон, газ)."""
    t = p / PHASES
    col = rgb_of(e.get("tint"), [1, 0.3, 0.1])
    amp = float(e.get("amp", 0.35))
    for n, (m, c, _) in enumerate(ctx["parts"]):
        f = 0.5 + 0.5 * wave(t, float(e.get("phase", 0)) + n * float(e.get("stagger", 0)), int(e.get("speed", 1)))
        halo = blur(m, float(e.get("radius", 1.5)) * K)
        out = screen(out, (halo * amp * f)[..., None] * col)
    return out


EFFECTS = {
    "pulse": fx_pulse, "blink": fx_blink, "flicker": fx_flicker, "ripple": fx_ripple,
    "bubbles": fx_bubbles, "smoke": fx_smoke, "sparks": fx_sparks, "fire": fx_fire,
    "sweep": fx_sweep, "band": fx_band, "sway": fx_sway, "swarm": fx_swarm, "roll": fx_roll,
    "lid": fx_lid, "breathe": fx_breathe, "tint": fx_tint,
}
POINT_EFFECTS = {"smoke", "sparks", "swarm"}


def expand(spec, name, seen=()):
    """Эффекты постройки с учётом like: <другая постройка> (берутся её эффекты, потом свои)."""
    entry = spec.get(name) or {}
    effects = []
    if entry.get("like") and entry["like"] not in seen:
        effects += expand(spec, entry["like"], seen + (name,))
    return effects + list(entry.get("effects") or [])


def animate(fac, effects):
    ctxs = []
    for e in effects:
        ctx = {}
        if e["fx"] in POINT_EFFECTS:
            ctx["points"] = points(fac, e)
        else:
            ctx["parts"] = select(fac, e.get("sel"))
        ctxs.append(ctx)
    frames = []
    for p in range(PHASES):
        out = fac.rgb.copy()
        for e, ctx in zip(effects, ctxs):
            out = EFFECTS[e["fx"]](fac, out, p, e, ctx)
        frames.append(np.clip(out, 0, 1))
    empty = [e.get("fx") for e, c in zip(effects, ctxs) if not c.get("parts") and not c.get("points")]
    return frames, empty


def write(fac, frames, out_dir):
    dest = os.path.join(out_dir, "hd", "BASEBITS.PCK")
    os.makedirs(dest, exist_ok=True)
    for p, f in enumerate(frames):
        data = np.concatenate([np.clip(f * 255 + 0.5, 0, 255), fac.alpha[..., None] * 255], 2).astype(np.uint8)
        for n, index in enumerate(fac.indices):
            y, x = divmod(n, fac.cols)
            tile = data[y * 32 * K:(y + 1) * 32 * K, x * 32 * K:(x + 1) * 32 * K]
            name = "%d.png" % index if p == 0 else "%d.v%d.png" % (index, p)
            Image.fromarray(tile, "RGBA").save(os.path.join(dest, name))


# ---------------------------------------------------------------- превью и разметка

def to_image(fac, f, bg=(18, 18, 22)):
    rgb = f * fac.alpha[..., None] + np.array(bg, np.float32) / 255 * (1 - fac.alpha[..., None])
    return Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8))


def probe_image(fac, n, title):
    """Постройка x4 с сеткой через 4 пикселя классики (подпись через 8) и карта цветов."""
    z = 6
    pic = Image.fromarray((fac.crgb * 255).astype(np.uint8)).resize((fac.w * z, fac.h * z), Image.NEAREST)
    cls = np.array(CLASS_RGB, np.uint8)[fac.classes]
    cmap = Image.fromarray(cls).resize((fac.w * z, fac.h * z), Image.NEAREST)
    m = 22
    im = Image.new("RGB", (fac.w * z * 2 + m * 3, fac.h * z + m + 20), (0, 0, 0))
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 11)
    dr = ImageDraw.Draw(im)
    dr.text((2, 2), "%d %s" % (n, title), fill=(255, 255, 0), font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14))
    for i, src in enumerate((pic, cmap)):
        ox, oy = m + i * (fac.w * z + m), 20 + m
        im.paste(src, (ox, oy))
        for v in range(0, max(fac.w, fac.h) + 1, 4):
            c = (90, 90, 90) if v % 8 else (200, 200, 60)
            if v <= fac.w:
                dr.line([(ox + v * z, oy), (ox + v * z, oy + fac.h * z)], fill=c, width=1)
                if v % 8 == 0:
                    dr.text((ox + v * z - 4, oy - 13), str(v), fill=(255, 255, 255), font=font)
            if v <= fac.h:
                dr.line([(ox, oy + v * z), (ox + fac.w * z, oy + v * z)], fill=c, width=1)
                if v % 8 == 0:
                    dr.text((ox - 20, oy + v * z - 6), str(v), fill=(255, 255, 255), font=font)
    return im


def main():
    ap = argparse.ArgumentParser(description="HD-анимация построек базы по base_anims.yml")
    ap.add_argument("--spec", default=SPEC)
    ap.add_argument("--only", default="", help="коды построек через запятую")
    ap.add_argument("--out", action="append", default=[], help="папка мода hd (можно несколько)")
    ap.add_argument("--preview", default="", help="папка превью: GIF и лист фаз на постройку, index.html")
    ap.add_argument("--probe", default="", help="папка листов разметки (сетка + карта цветов)")
    args = ap.parse_args()

    facilities, _ = load_rules()
    rows = sorted(facilities.values(), key=lambda f: (int(f.get("listOrder", 0)), f["type"]))
    numbered = [(n, r) for n, r in enumerate(rows, 1)]
    only = set(s.strip() for s in args.only.split(",") if s.strip())
    if only:
        numbered = [(n, r) for n, r in numbered if r["type"] in only]
    ru = load_strings("ru")
    sprites = sprites_map()

    owners = {}
    for n, r in enumerate(rows, 1):
        fac = r
        small = int(fac.get("sizeX", fac.get("size", 1))) == 1 and int(fac.get("sizeY", fac.get("size", 1))) == 1
        first = int(fac.get("spriteFacility", -1)) if small or fac.get("spriteEnabled") else int(fac.get("spriteShape", -1))
        owners.setdefault(first, []).append(fac["type"])

    if args.probe:
        os.makedirs(args.probe, exist_ok=True)
        batch, page = [], 0
        for n, r in numbered:
            batch.append(probe_image(Facility(r, sprites), n, "%s  %s" % (r["type"], ru.get(r["type"], ""))))
            if len(batch) == 4 or (n, r) == numbered[-1]:
                wid = max(b.width for b in batch)
                sheet = Image.new("RGB", (wid, sum(b.height for b in batch)), (0, 0, 0))
                y = 0
                for b in batch:
                    sheet.paste(b, (0, y))
                    y += b.height
                sheet.save(os.path.join(args.probe, "probe_%02d.png" % page))
                page += 1
                batch = []
        print("листов разметки: %d -> %s" % (page, args.probe))
        return 0

    spec = yaml.safe_load(open(args.spec, encoding="utf-8-sig")) or {}
    ideas = {}
    tsv = os.path.join(os.path.dirname(os.path.dirname(HERE)), "art", "_review", "facility_ideas.tsv")
    if os.path.exists(tsv):
        for line in open(tsv, encoding="utf-8-sig"):
            if "\t" in line:
                k, v = line.rstrip("\n").split("\t", 1)
                ideas[k.strip()] = v.strip()
    items, problems = [], []
    for n, r in numbered:
        t = r["type"]
        entry = spec.get(t)
        if not entry:
            problems.append("%s: нет в %s" % (t, os.path.basename(args.spec)))
            continue
        if entry.get("skip"):
            continue
        fac = Facility(r, sprites)
        if fac.missing:
            problems.append("%s: нет кадров %s" % (t, fac.missing))
            continue
        shared = [o for o in owners.get(fac.indices[0], []) if o != t]
        if shared:
            problems.append("%s: кадр %d общий с %s - анимация достанется и им" % (t, fac.indices[0], ", ".join(shared)))
        effects = expand(spec, t)
        frames, empty = animate(fac, effects)
        if empty:
            problems.append("%s: пустая выборка у %s" % (t, ", ".join(empty)))
        for d in args.out:
            write(fac, frames, d)
        if args.preview:
            gif_dir = os.path.join(args.preview, "gif")
            os.makedirs(gif_dir, exist_ok=True)
            imgs = [to_image(fac, f) for f in frames]
            name = "%03d_%s" % (n, t)
            imgs[0].save(os.path.join(gif_dir, name + ".gif"), save_all=True, append_images=imgs[1:], duration=200, loop=0)
            half = [im.resize((im.width // 2, im.height // 2), Image.LANCZOS) for im in imgs]
            sheet = Image.new("RGB", (half[0].width * 8, half[0].height * 2))
            for p, im in enumerate(half):
                sheet.paste(im, ((p % 8) * im.width, (p // 8) * im.height))
            sheet.save(os.path.join(gif_dir, name + "_phases.png"))
        items.append((n, t, ru.get(t, t), ideas.get(t, ""), fac))
        print("%3d %-40s %d клеток, эффектов %d" % (n, t, len(fac.indices), len(effects)))

    if args.preview:
        page = os.path.join(args.preview, "index.html")
        with open(page, "w", encoding=ENC_W) as f:
            f.write("<!doctype html><meta charset=utf-8><title>Анимации построек</title>"
                    "<style>body{background:#111;color:#ddd;font:14px sans-serif}td{vertical-align:top;padding:6px;"
                    "border-bottom:1px solid #333}img{image-rendering:pixelated}</style><table>")
            for n, t, name, idea, fac in items:
                f.write("<tr><td>%d</td><td><b>%s</b><br><small>%s</small></td><td><img src='gif/%03d_%s.gif' width=%d></td>"
                        "<td>%s</td></tr>" % (n, html.escape(name), t, n, t, min(256, fac.w * K), html.escape(idea)))
            f.write("</table>")
        print("превью:", page)
    for line in problems:
        print("!!", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
