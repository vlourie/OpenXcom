"""Боевые эффекты HD-слоя: попадания, промахи, удары, вспышки выстрела, взрывы.

Рисует клипы процедурно (частицы в изометрии, без модели): кадры одинаковы при каждом
запуске, цвет и форма управляются числами. Кадр - RGBA 4x, прямая альфа, точка попадания
в центре холста. Раскладка на диске (читает движок, src/Engine/HdFx.cpp; старые кадры SMOKE/HIT/X1 - в gen_fx.py):

    <out>/FX/<клип>/<i>.png        i = 0..L-1, L - длина клипа
    <out>/FX/fx.yml                 какие клипы есть и их размеры

Имена клипов:
    hit_<семья>_<цель>         попадание пули/луча по юниту   (цель: flesh mech armor ghost)
    hit_<семья>_<материал>     попадание в клетку            (dirt sand stone metal wood water snow grass soft)
    hit_<семья>[_<цвет>]       энергия без разделения по цели (цвет: red orange yellow green blue purple white)
    swing_<вид>_<dir>          замах ближнего боя, dir 0..7 как у юнита
    flash_<вид>_<dir>          вспышка у ствола
    boom_<семья>[_<цвет>]      взрыв по площади

Запуск: py -3 tools/hdart/gen_combat_fx.py --out <мод>/hd [--only hit_bullet] [--preview <png/gif каталог>]
"""
import argparse, math, os, sys, time, zlib
import numpy as np
from PIL import Image

K = 4                     # масштаб кадров
SS = 2                    # суперсэмплинг внутри
ENC = "utf-8-sig"

# ------------------------------------------------------------------ холст

class Canvas:
    """Два слоя: 'over' (дым, кровь, обломки - закрывают) и 'glow' (свет - складывается)."""

    def __init__(self, w, h, h0=0.0):
        """w, h - размер в пикселях базы; центр холста - точка попадания, земля на h0 ниже."""
        self.w, self.h = w * K * SS, h * K * SS
        self.h0 = h0
        self.over = np.zeros((self.h, self.w, 4), np.float32)   # premultiplied rgba
        self.glow = np.zeros((self.h, self.w, 3), np.float32)
        self.cx, self.cy = self.w / 2, self.h / 2
        self.yy, self.xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)

    # мировые координаты: x вправо, y в глубину (изометрия ужимает вдвое), z вверх; в пикселях 1x
    def proj(self, x, y, z):
        s = K * SS
        return self.cx + x * s, self.cy + (y * 0.5 - (z - self.h0)) * s

    def _box(self, px, py, r):
        x0, x1 = int(max(0, px - r - 1)), int(min(self.w, px + r + 2))
        y0, y1 = int(max(0, py - r - 1)), int(min(self.h, py + r + 2))
        return x0, x1, y0, y1

    def disc(self, px, py, r, rgb, a, soft=0.5, layer="over", sy=1.0):
        """Мягкий круг радиуса r (пиксели холста), sy - сжатие по вертикали (эллипс на земле)."""
        if a <= 0.002 or r <= 0.05:
            return
        rr = r * (1 + soft) + 1
        x0, x1, y0, y1 = self._box(px, py, rr)
        if x0 >= x1 or y0 >= y1:
            return
        dx = self.xx[y0:y1, x0:x1] - px
        dy = (self.yy[y0:y1, x0:x1] - py) / sy
        d = np.sqrt(dx * dx + dy * dy)
        edge = max(0.6, r * soft)
        m = np.clip((r + edge * 0.5 - d) / edge, 0, 1) * a
        self._put(x0, x1, y0, y1, m, rgb, layer)

    def blob(self, px, py, r, rgb, a, noise, layer="over", sy=1.0, seed=0):
        """Клуб дыма: круг с краем, изъеденным шумом."""
        if a <= 0.002 or r <= 0.3:
            return
        x0, x1, y0, y1 = self._box(px, py, r * 1.3)
        if x0 >= x1 or y0 >= y1:
            return
        dx = self.xx[y0:y1, x0:x1] - px
        dy = (self.yy[y0:y1, x0:x1] - py) / sy
        d = np.sqrt(dx * dx + dy * dy) / r
        n = noise.sample(self.xx[y0:y1, x0:x1] / (r * 0.7) + seed * 13.1, self.yy[y0:y1, x0:x1] / (r * 0.7) + seed * 7.7)
        m = np.clip((1.0 - d) * 1.6 + (n - 0.5) * 1.2, 0, 1) ** 1.3 * a
        self._put(x0, x1, y0, y1, m, rgb, layer)

    def annulus(self, px, py, r, w, rgb, a, layer="glow", sy=0.5):
        """Кольцо сплошной полосой ширины w (эллипс со сжатием sy)."""
        if a <= 0.002 or r <= 0.5:
            return
        x0, x1, y0, y1 = self._box(px, py, r + w * 2)
        if x0 >= x1 or y0 >= y1:
            return
        dx = self.xx[y0:y1, x0:x1] - px
        dy = (self.yy[y0:y1, x0:x1] - py) / sy
        d = np.abs(np.sqrt(dx * dx + dy * dy) - r)
        m = np.exp(-(d / max(0.8, w * 0.5)) ** 2) * a
        self._put(x0, x1, y0, y1, m, rgb, layer)

    def arcband(self, px, py, r, sy, a0, a1, w, rgb, a, layer="over"):
        """След взмаха: дуга эллипса от угла a0 до a1 сплошной полосой; к концу a1 толще и ярче."""
        if a <= 0.002 or abs(a1 - a0) < 1e-3:
            return
        x0, x1, y0, y1 = self._box(px, py, r + w * 2)
        if x0 >= x1 or y0 >= y1:
            return
        dx = self.xx[y0:y1, x0:x1] - px
        dy = (self.yy[y0:y1, x0:x1] - py) / sy
        rad = np.sqrt(dx * dx + dy * dy)
        ang = np.arctan2(dy, dx)
        span = a1 - a0
        t = np.mod((ang - a0) * np.sign(span), 2 * math.pi) / abs(span)
        inside = t <= 1.0
        t = np.clip(t, 0, 1)
        ww = w * (0.25 + 0.75 * t)
        m = np.exp(-((rad - r) / np.maximum(0.8, ww * 0.5)) ** 2) * (t ** 1.5) * inside * a
        self._put(x0, x1, y0, y1, m.astype(np.float32), rgb, layer)

    def line(self, x0, y0, x1, y1, w, rgb, a, layer="over", taper=False):
        """Отрезок толщины w; taper - сходит на нет к (x1, y1)."""
        if a <= 0.002:
            return
        bx0, bx1 = int(max(0, min(x0, x1) - w - 2)), int(min(self.w, max(x0, x1) + w + 3))
        by0, by1 = int(max(0, min(y0, y1) - w - 2)), int(min(self.h, max(y0, y1) + w + 3))
        if bx0 >= bx1 or by0 >= by1:
            return
        X = self.xx[by0:by1, bx0:bx1]; Y = self.yy[by0:by1, bx0:bx1]
        vx, vy = x1 - x0, y1 - y0
        L2 = vx * vx + vy * vy + 1e-6
        t = np.clip(((X - x0) * vx + (Y - y0) * vy) / L2, 0, 1)
        d = np.sqrt((X - x0 - t * vx) ** 2 + (Y - y0 - t * vy) ** 2)
        if taper == "lens":                 # толще в середине, на нет к обоим концам
            ww = w * np.sqrt(np.clip(np.sin(np.pi * t), 0, 1))
        else:
            ww = w * (1 - 0.85 * t) if taper else w
        m = np.clip((ww * 0.5 + 0.7 - d) / 1.4, 0, 1) * a
        self._put(bx0, bx1, by0, by1, m, rgb, layer)

    def _put(self, x0, x1, y0, y1, m, rgb, layer):
        c = np.array(rgb, np.float32) / 255.0
        if layer == "glow":
            self.glow[y0:y1, x0:x1] += m[..., None] * c
        else:
            o = self.over[y0:y1, x0:x1]
            inv = 1 - m[..., None]
            o[..., :3] = o[..., :3] * inv + m[..., None] * c
            o[..., 3] = o[..., 3] * inv[..., 0] + m

    def image(self):
        o = self.over
        g = np.clip(self.glow, 0, 4)
        # свет поверх: складываем цвет, альфа - от яркости света
        la = np.clip(g.max(axis=2), 0, 1)
        rgb = o[..., :3] + g
        a = np.clip(1 - (1 - o[..., 3]) * (1 - la), 0, 1)
        img = np.concatenate([rgb, a[..., None]], axis=2)
        # суперсэмплинг вниз по премультиплицированным значениям
        h, w = self.h // SS, self.w // SS
        img = img.reshape(h, SS, w, SS, 4).mean(axis=(1, 3))
        a = img[..., 3:4]
        rgb = np.where(a > 1e-4, img[..., :3] / np.maximum(a, 1e-4), 0)
        # пересвет уходит в белый, а не обрезается по каналу
        over = np.clip(rgb.max(axis=2, keepdims=True) - 1, 0, None)
        rgb = np.clip(rgb + over * 0.6, 0, 1)
        out = np.concatenate([rgb, a], axis=2)
        return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


class Noise:
    """Периодический сглаженный шум (value noise, 3 октавы)."""

    def __init__(self, seed=1, n=64):
        rng = np.random.default_rng(seed)
        self.g = [rng.random((n, n)).astype(np.float32) for _ in range(3)]
        self.n = n

    def sample(self, x, y):
        out = 0; amp = 0.55; tot = 0
        for i, g in enumerate(self.g):
            f = 2 ** i
            out = out + amp * self._one(g, x * f, y * f); tot += amp; amp *= 0.5
        return out / tot

    def _one(self, g, x, y):
        n = self.n
        xi = np.floor(x).astype(np.int64); yi = np.floor(y).astype(np.int64)
        fx = x - xi; fy = y - yi
        fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy)
        x0 = xi % n; y0 = yi % n; x1 = (x0 + 1) % n; y1 = (y0 + 1) % n
        a = g[y0, x0] * (1 - fx) + g[y0, x1] * fx
        b = g[y1, x0] * (1 - fx) + g[y1, x1] * fx
        return a * (1 - fy) + b * fy


NOISE = Noise(7)

# ------------------------------------------------------------------ цвета

COLORS = {
    "red": (255, 70, 50), "orange": (255, 150, 40), "yellow": (255, 230, 90), "green": (110, 255, 90),
    "blue": (70, 170, 255), "purple": (200, 90, 255), "white": (230, 240, 255), "pink": (255, 110, 190),
}

def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))

def fire_ramp(t):
    """0 - белый жар, 1 - тёмно-красный."""
    stops = [(0, (255, 250, 220)), (0.25, (255, 210, 90)), (0.55, (255, 120, 30)), (1, (150, 30, 10))]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            return mix(c0, c1, (t - t0) / (t1 - t0))
    return stops[-1][1]

def energy_ramp(col, t):
    """Энергия: белое ядро, к краю и к концу - чистый цвет, потом темнее."""
    if t < 0.3:
        return mix((255, 255, 255), col, t / 0.3)
    return mix(col, tuple(c * 0.45 for c in col), (t - 0.3) / 0.7)

# ------------------------------------------------------------------ частицы

class P:
    __slots__ = ("x", "y", "z", "vx", "vy", "vz", "life", "age", "size", "kind", "rgb", "seed", "drag", "g", "bounce", "rest")

    def __init__(self, **kw):
        self.x = self.y = self.z = self.vx = self.vy = self.vz = 0.0
        self.life = 1.0; self.age = 0.0; self.size = 1.0; self.kind = "dot"; self.rgb = (255, 255, 255)
        self.seed = 0; self.drag = 0.0; self.g = 60.0; self.bounce = 0.3; self.rest = False
        for k, v in kw.items():
            setattr(self, k, v)

    def step(self, dt):
        self.age += dt
        if self.rest:
            return
        self.vx *= (1 - self.drag * dt); self.vy *= (1 - self.drag * dt); self.vz *= (1 - self.drag * dt)
        self.vz -= self.g * dt
        self.x += self.vx * dt; self.y += self.vy * dt; self.z += self.vz * dt
        if self.z < 0:
            self.z = 0
            if abs(self.vz) > 8 and self.bounce > 0:
                self.vz = -self.vz * self.bounce; self.vx *= 0.5; self.vy *= 0.5
            else:
                self.vz = 0; self.vx *= 0.3; self.vy *= 0.3
                if self.kind in ("drop", "chunk", "splinter", "goo", "flake"):
                    self.rest = True


def sphere_dir(rng, up=0.5, spread=1.0):
    """Случайное направление: up - доля вверх, spread - насколько широко."""
    a = rng.uniform(0, 2 * math.pi)
    e = rng.uniform(-0.2, 1.0) * spread * math.pi / 2 * up + (1 - up) * rng.uniform(-0.3, 0.6)
    return math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)


class Clip:
    """Клип: частицы плюс рисованные слои (вспышка, кольцо), L кадров на duration секунд."""

    def __init__(self, name, frames, duration, size=64, seed=0, h0=0.0):
        self.name, self.L, self.dur, self.size = name, frames, duration, size
        # crc32, а не hash(): hash строки в питоне свой у каждого процесса
        self.rng = np.random.default_rng(zlib.crc32(name.encode()) + seed)
        self.parts = []
        self.layers = []   # функции (canvas, t_sec, u 0..1)
        self.h0 = h0       # высота точки попадания над землёй (пиксели 1x): у юнита ~10, у пола 0

    def add(self, **kw):
        kw.setdefault("z", self.h0)
        self.parts.append(P(**kw))

    def render(self):
        frames = []
        sub = 4
        dt = self.dur / self.L / sub
        for f in range(self.L):
            t = (f + 1) * self.dur / self.L
            for _ in range(sub):
                for p in self.parts:
                    p.step(dt)
            cv = Canvas(self.size, self.size, self.h0)
            u = f / max(1, self.L - 1)
            for lay in self.layers:
                if getattr(lay, "back", False):
                    lay(cv, t, u)
            for p in self.parts:
                draw_part(cv, p)
            for lay in self.layers:
                if not getattr(lay, "back", False):
                    lay(cv, t, u)
            frames.append(cv.image())
        return frames


def draw_part(cv, p):
    if p.age < 0 or p.age > p.life:
        return
    u = p.age / p.life
    px, py = cv.proj(p.x, p.y, p.z)
    s = K * SS
    if p.kind == "spark":           # искра: светящийся штрих вдоль скорости
        vx, vy = (p.vx) * s * 0.018, (p.vy * 0.5 - p.vz) * s * 0.018
        col = fire_ramp(u * 0.9) if p.rgb == "fire" else energy_ramp(p.rgb, u)
        a = (1 - u) ** 1.2
        cv.line(px - vx, py - vy, px, py, p.size * s * 0.35, col, a, "glow", taper=False)
        cv.disc(px, py, p.size * s * 0.3, col, a * 0.8, 0.6, "glow")
    elif p.kind == "ember":         # тлеющая точка
        col = fire_ramp(0.3 + u * 0.7)
        cv.disc(px, py, p.size * s * 0.4, col, (1 - u) ** 0.8, 0.8, "glow")
    elif p.kind in ("drop", "goo"):  # капля, на земле - клякса
        a = 1.0 if u < 0.7 else (1 - u) / 0.3
        if p.rest:
            cv.disc(px, py, p.size * s * 0.7, p.rgb, a * 0.9, 0.3, "over", sy=0.5)
        else:
            vx, vy = p.vx * s * 0.012, (p.vy * 0.5 - p.vz) * s * 0.012
            cv.line(px - vx, py - vy, px, py, p.size * s * 0.55, p.rgb, a, "over")
            hl = mix(p.rgb, (255, 255, 255), 0.35)
            cv.disc(px - p.size * s * 0.12, py - p.size * s * 0.12, p.size * s * 0.18, hl, a * 0.6, 0.5, "over")
    elif p.kind in ("chunk", "flake"):  # осколок: неровный многоугольник, вращается
        a = 1.0 if u < 0.75 else (1 - u) / 0.25
        r = p.size * s * 0.5
        ang = p.seed + p.age * 14 * (0 if p.rest else 1)
        pts = []
        for i in range(5):
            aa = ang + i * 2 * math.pi / 5
            rr = r * (0.6 + 0.4 * ((p.seed * 7 + i * 3.1) % 1))
            pts.append((px + math.cos(aa) * rr, py + math.sin(aa) * rr * (0.55 if p.kind == "flake" else 0.9)))
        for i in range(5):
            x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % 5]
            cv.line(x0, y0, x1, y1, r * 0.9, p.rgb, a, "over")
        cv.disc(px, py, r * 0.6, p.rgb, a, 0.3, "over")
        hl = mix(p.rgb, (255, 255, 255), 0.3)
        cv.disc(px - r * 0.25, py - r * 0.3, r * 0.3, hl, a * 0.7, 0.5, "over")
    elif p.kind == "splinter":      # щепка: длинная палочка
        a = 1.0 if u < 0.75 else (1 - u) / 0.25
        L = p.size * s * 1.3
        ang = p.seed + p.age * 18 * (0 if p.rest else 1)
        dx, dy = math.cos(ang) * L, math.sin(ang) * L * 0.6
        cv.line(px - dx, py - dy, px + dx, py + dy, p.size * s * 0.35, p.rgb, a, "over")
    elif p.kind == "puff":          # клуб пыли/дыма, растёт и тает
        grow = 0.35 + 0.65 * (1 - (1 - u) ** 2)
        a = (min(1.0, u * 6) * (1 - u) ** 1.4) * 0.85
        cv.blob(px, py, p.size * s * grow, p.rgb, a, NOISE, "over", seed=p.seed)
    elif p.kind == "mist":          # кровяной туман
        grow = 0.4 + 0.6 * u
        a = (1 - u) ** 2 * 0.55
        cv.blob(px, py, p.size * s * grow, p.rgb, a, NOISE, "over", seed=p.seed)
    elif p.kind == "fire":          # клуб пламени: тело огня (закрывает) и свет поверх
        grow = 0.45 + 0.55 * (1 - (1 - u) ** 2)
        a = min(1.0, (1 - u) * 1.6)
        col = fire_ramp(min(1.0, u * 1.1))
        r = p.size * s * grow
        cv.blob(px, py, r, col, a, NOISE, "over", seed=p.seed)
        cv.blob(px, py, r * 0.7, fire_ramp(u * 0.6), a * (1 - u) * 0.8, NOISE, "glow", seed=p.seed + 3)
    elif p.kind == "wisp":          # призрачная струйка: светящийся клуб
        grow = 0.5 + 0.5 * u
        a = math.sin(math.pi * u) * 0.8
        cv.blob(px, py, p.size * s * grow, p.rgb, a * 0.5, NOISE, "glow", seed=p.seed)
    elif p.kind == "heart":
        a = math.sin(math.pi * u)
        r = p.size * s * 0.5 * (0.6 + 0.4 * u)
        cv.disc(px - r * 0.5, py, r * 0.6, p.rgb, a, 0.3, "over")
        cv.disc(px + r * 0.5, py, r * 0.6, p.rgb, a, 0.3, "over")
        cv.line(px - r * 0.95, py + r * 0.15, px, py + r * 1.25, r * 0.8, p.rgb, a, "over")
        cv.line(px + r * 0.95, py + r * 0.15, px, py + r * 1.25, r * 0.8, p.rgb, a, "over")
        cv.disc(px - r * 0.6, py - r * 0.2, r * 0.2, (255, 220, 235), a * 0.8, 0.5, "over")


def layer(back=False):
    def deco(f):
        f.back = back
        return f
    return deco

# ------------------------------------------------------------------ кирпичики

def flash(clip, col, r, dur, h=None):
    """Вспышка в точке попадания: белое ядро и ореол цвета col."""
    h = clip.h0 if h is None else h
    @layer()
    def f(cv, t, u):
        if t > dur:
            return
        v = 1 - t / dur
        px, py = cv.proj(0, 0, h)
        s = K * SS
        cv.disc(px, py, r * s * (0.6 + 0.6 * (1 - v)), col, v * 0.9, 1.5, "glow")
        cv.disc(px, py, r * s * 0.35 * v, (255, 255, 255), v, 0.8, "glow")
    clip.layers.append(f)

def star(clip, col, r, dur, rays=4, h=None):
    """Звезда рикошета: лучи крестом."""
    h = clip.h0 if h is None else h
    rot = clip.rng.uniform(0, math.pi)
    @layer()
    def f(cv, t, u):
        if t > dur:
            return
        v = 1 - t / dur
        px, py = cv.proj(0, 0, h)
        s = K * SS
        for i in range(rays):
            a = rot + i * math.pi / rays
            L = r * s * (1.2 if i % 2 == 0 else 0.6) * (0.7 + 0.3 * v)
            dx, dy = math.cos(a) * L, math.sin(a) * L
            cv.line(px - dx, py - dy, px + dx, py + dy, s * 0.9 * v, col, v, "glow")
        cv.disc(px, py, r * s * 0.3 * v, (255, 255, 255), v, 0.6, "glow")
    clip.layers.append(f)

def ring(clip, col, r0, r1, dur, width=1.0, h=0.0, glow=True):
    """Кольцо по земле (эллипс 2:1), растёт от r0 до r1. В воздухе (h > 0) - ударная волна:
    круг, а не эллипс, и тоньше - иначе на теле юнита читается как нимб."""
    sy = 0.5 if h <= 0.5 else 1.0
    if h > 0.5:
        width *= 0.6
    @layer(back=not glow)
    def f(cv, t, u):
        if t > dur:
            return
        v = t / dur
        r = (r0 + (r1 - r0) * (1 - (1 - v) ** 2)) * K * SS
        px, py = cv.proj(0, 0, h)
        a = (1 - v) ** 1.5 * (0.6 if h > 0.5 else 1.0)
        cv.annulus(px, py, r, width * K * SS * (1 + v), col, a, "glow" if glow else "over", sy)
    clip.layers.append(f)

def arcs(clip, col, n, reach, dur, h=None):
    """Электрические дуги: ломаные из точки попадания, перебрасываются каждый кадр."""
    h = clip.h0 if h is None else h
    rng = clip.rng
    seeds = [rng.integers(1 << 30) for _ in range(64)]
    @layer()
    def f(cv, t, u):
        if t > dur:
            return
        v = 1 - t / dur
        r2 = np.random.default_rng(seeds[int(t * 60) % 64])
        s = K * SS
        for _ in range(n):
            x, y, z = 0.0, 0.0, h
            ang = r2.uniform(0, 2 * math.pi); el = r2.uniform(-0.6, 0.9)
            L = reach * r2.uniform(0.5, 1.0)
            seg = 6
            px0, py0 = cv.proj(x, y, z)
            for i in range(seg):
                x += math.cos(ang) * L / seg + r2.normal(0, L * 0.08)
                y += math.sin(ang) * L / seg + r2.normal(0, L * 0.08)
                z += el * L / seg + r2.normal(0, L * 0.08)
                px1, py1 = cv.proj(x, y, z)
                w = s * 0.7 * (1 - i / seg)
                cv.line(px0, py0, px1, py1, w * 2.5, col, v * 0.35, "glow")
                cv.line(px0, py0, px1, py1, w, (255, 255, 255), v, "glow")
                px0, py0 = px1, py1
    clip.layers.append(f)

def hotspot(clip, col, r, dur, h=None):
    """Раскалённая точка попадания: тлеет и остывает до конца dur."""
    h = clip.h0 if h is None else h
    @layer()
    def f(cv, t, u):
        if t > dur:
            return
        v = 1 - t / dur
        px, py = cv.proj(0, 0, h)
        s = K * SS
        cv.disc(px, py, r * s, mix((120, 20, 0), col, v), v ** 0.7 * 0.9, 1.0, "glow", sy=0.7 if h <= 0.5 else 1.0)
    clip.layers.append(f)

def scorch(clip, rgb, r, a=0.7):
    """Подпалина на земле, остаётся до конца клипа."""
    @layer(back=True)
    def f(cv, t, u):
        px, py = cv.proj(0, 0, 0)
        cv.blob(px, py, r * K * SS, rgb, a * min(1, t * 8) * (1 - max(0, u - 0.7) / 0.3), NOISE, "over", sy=0.5, seed=3)
    clip.layers.append(f)

def spray(clip, n, kind, rgb, speed, up=0.6, size=(0.6, 1.2), life=(0.3, 0.6), g=60, drag=1.0, bounce=0.2, spread=1.0, delay=0.0):
    rng = clip.rng
    for _ in range(n):
        dx, dy, dz = sphere_dir(rng, up, spread)
        sp = speed * rng.uniform(0.4, 1.0)
        clip.add(vx=dx * sp, vy=dy * sp, vz=dz * sp + speed * 0.25 * up, kind=kind, rgb=rgb,
                 size=rng.uniform(*size), life=rng.uniform(*life), g=g, drag=drag, bounce=bounce,
                 seed=rng.uniform(0, 10), age=-rng.uniform(0, delay))

def puffs(clip, n, rgb, r, rise, spread, life=(0.4, 0.8), delay=0.05, h=None):
    rng = clip.rng
    h = clip.h0 if h is None else h
    for _ in range(n):
        a = rng.uniform(0, 2 * math.pi)
        c = rgb if isinstance(rgb[0], (int, float)) else rgb[rng.integers(len(rgb))]
        clip.add(x=math.cos(a) * spread * rng.uniform(0, 1), y=math.sin(a) * spread * rng.uniform(0, 1), z=h,
                 vx=math.cos(a) * spread * 1.5, vy=math.sin(a) * spread * 1.5, vz=rise * rng.uniform(0.5, 1),
                 kind="puff", rgb=c, size=r * rng.uniform(0.7, 1.2), life=rng.uniform(*life), g=0, drag=3.0,
                 seed=rng.uniform(0, 50), age=-rng.uniform(0, delay))

# ------------------------------------------------------------------ цели и материалы

UNIT_H = 11.0   # высота попадания по юниту над полом (пиксели 1x)

def target_fx(clip, target, power=1.0):
    """Что брызжет из цели. power: 0.5 - игла, 1 - пуля, 2 - снаряд."""
    p = power
    if target == "flesh":
        # тёмный пол боя съедает тёмно-красное: кровь светлее, чем в жизни, и с бликом
        spray(clip, int(22 * p), "drop", (205, 24, 24), 48 * p ** 0.5, up=0.5, size=(0.6, 1.2), life=(0.4, 0.75), g=90)
        spray(clip, int(8 * p), "drop", (150, 10, 14), 34 * p ** 0.5, up=0.4, size=(0.9, 1.6), life=(0.5, 0.85), g=90)
        # первый кадр - облачко брызг, видно сразу, а не когда капли разлетятся
        clip.add(kind="mist", rgb=(225, 40, 35), size=3.4 * p ** 0.5, life=0.22, g=0, drag=0, seed=1.5)
        for _ in range(int(3 * p) + 1):
            clip.add(vx=clip.rng.normal(0, 8), vy=clip.rng.normal(0, 8), vz=6, kind="mist", rgb=(190, 25, 25),
                     size=3.0 * p ** 0.5, life=0.55, g=0, drag=4, seed=clip.rng.uniform(0, 50))
        flash(clip, (255, 120, 90), 1.6 * p ** 0.5, 0.06)
    elif target == "mech":
        spray(clip, int(16 * p), "spark", "fire", 70 * p ** 0.5, up=0.6, size=(0.5, 0.9), life=(0.2, 0.45), g=70, drag=1.5)
        spray(clip, int(5 * p), "drop", (25, 22, 18), 30, up=0.5, size=(0.5, 0.9), life=(0.4, 0.7), g=90)
        spray(clip, int(3 * p), "chunk", (150, 150, 155), 35, up=0.6, size=(0.4, 0.8), life=(0.5, 0.8), g=90)
        puffs(clip, 4, [(95, 92, 90), (70, 70, 75)], 3.8 * p ** 0.5, 14, 1.2, life=(0.6, 1.0), delay=0.12)
        flash(clip, (255, 200, 120), 3.0 * p ** 0.5, 0.12)
        hotspot(clip, (255, 150, 60), 1.4 * p ** 0.5, 0.45)
    elif target == "armor":           # броня выдержала: рикошет
        star(clip, (255, 235, 180), 4.5 * p ** 0.5, 0.14)
        spray(clip, int(10 * p), "spark", "fire", 85, up=0.5, size=(0.4, 0.8), life=(0.15, 0.35), g=40, drag=1.0)
        flash(clip, (255, 230, 170), 2.5 * p ** 0.5, 0.1)
    elif target == "ghost":
        for _ in range(int(6 * p) + 2):
            d = sphere_dir(clip.rng, 0.4)
            clip.add(vx=d[0] * 14, vy=d[1] * 14, vz=d[2] * 10 + 8, kind="wisp", rgb=(120, 255, 210),
                     size=clip.rng.uniform(2.0, 3.5), life=clip.rng.uniform(0.4, 0.8), g=-10, drag=2, seed=clip.rng.uniform(0, 50))
        spray(clip, int(10 * p), "spark", (130, 255, 220), 40, up=0.5, size=(0.4, 0.7), life=(0.3, 0.5), g=-5, drag=2)
        flash(clip, (140, 255, 220), 3.0, 0.15)

MATERIALS = {
    #          обломки         тип        пыль                   искры
    "dirt":  ((95, 70, 48),   "chunk",   [(120, 96, 70), (100, 80, 60)], False),
    "sand":  ((196, 168, 112), "flake",  [(210, 186, 138), (190, 165, 120)], False),
    "stone": ((128, 126, 120), "chunk",  [(150, 148, 142), (120, 118, 112)], True),
    "metal": ((150, 152, 160), "flake",  [(90, 90, 95)], True),
    "wood":  ((140, 96, 55),   "splinter", [(150, 120, 90)], False),
    "water": ((170, 205, 235), "drop",   [(215, 235, 250)], False),
    "snow":  ((235, 240, 250), "flake",  [(245, 248, 255), (225, 232, 245)], False),
    "grass": ((70, 120, 40),   "splinter", [(115, 100, 70), (95, 110, 60)], False),
    "soft":  ((175, 160, 140), "flake",  [(190, 180, 165)], False),
}

def material_fx(clip, mat, power=1.0):
    p = power
    deb, kind, dust, sparks = MATERIALS[mat]
    rng = clip.rng
    n = int(12 * p)
    if mat == "water":
        spray(clip, int(22 * p), "drop", deb, 50 * p ** 0.5, up=0.9, size=(0.5, 1.0), life=(0.35, 0.7), g=110, spread=0.4)
        ring(clip, (200, 230, 255), 1, 9 * p ** 0.5, 0.5, 0.8, glow=False)
        ring(clip, (200, 230, 255), 0.5, 5 * p ** 0.5, 0.4, 0.6, glow=False)
        return
    # фонтанчик: пыль вверх столбиком в первые кадры, дальше оседает клубами
    for i in range(3):
        clip.add(vx=rng.normal(0, 3), vy=rng.normal(0, 3), vz=30 + i * 12, kind="puff", rgb=dust[0],
                 size=(2.2 - i * 0.4) * p ** 0.5, life=0.45, g=40, drag=5, seed=rng.uniform(0, 50))
    spray(clip, n, kind, deb, 45 * p ** 0.5, up=0.75, size=(0.6, 1.3), life=(0.4, 0.75), g=110, bounce=0.3, spread=0.7)
    if kind != "flake":
        spray(clip, n // 2, "flake", mix(deb, (0, 0, 0), 0.2), 35, up=0.7, size=(0.3, 0.6), life=(0.3, 0.6), g=110)
    puffs(clip, int(4 * p) + 2, dust, 3.6 * p ** 0.5, 12 * p ** 0.5, 1.5, life=(0.45, 0.9))
    if sparks:
        spray(clip, int(8 * p), "spark", "fire", 70, up=0.6, size=(0.4, 0.7), life=(0.15, 0.35), g=60)
        flash(clip, (255, 220, 160), 2.2 * p ** 0.5, 0.08, h=0)
    scorch(clip, mix(deb, (0, 0, 0), 0.55), 2.2 * p ** 0.5, 0.45)

TARGETS = ["flesh", "mech", "armor", "ghost"]
MATS = list(MATERIALS)
ECOLORS = ["red", "orange", "yellow", "green", "blue", "purple", "white"]

# ------------------------------------------------------------------ семьи попаданий

L_HIT = 10
DUR_HIT = 0.55

def kinetic(name, where, power, extra=None):
    """Пуля, снаряд, стрела, тупое: разное только силой и добавкой."""
    onunit = where in TARGETS
    c = Clip(name, L_HIT, DUR_HIT, 64, h0=UNIT_H if onunit else 0.0)
    if onunit:
        target_fx(c, where, power)
    else:
        material_fx(c, where, power)
    if extra:
        extra(c, onunit)
    return c

def ex_bullet(c, onunit):
    flash(c, (255, 210, 140), 1.6, 0.06)

def ex_shell(c, onunit):
    flash(c, (255, 190, 90), 4.5, 0.14)
    spray(c, 14, "ember", None, 40, up=0.6, size=(0.4, 0.8), life=(0.3, 0.6), g=30)
    puffs(c, 5, [(80, 75, 70), (60, 58, 55)], 4.5, 14, 2, life=(0.5, 1.0), delay=0.08)

# ступени калибра пули: сила разлёта и добавка (вспышка, искры, дым)
CAL = {1: 0.55, 2: 0.8, 3: 1.1, 4: 1.5, 5: 2.1}

def ex_cal(step):
    def f(c, onunit):
        flash(c, (255, 210, 140), 1.2 + 0.5 * step, 0.05 + 0.015 * step)
        if step >= 4:
            spray(c, 5 * step - 12, "ember", None, 30 + 5 * step, up=0.6, size=(0.4, 0.8), life=(0.25, 0.5), g=30)
        if step >= 5:
            puffs(c, 4, [(80, 75, 70), (60, 58, 55)], 4.0, 12, 2, life=(0.5, 1.0), delay=0.08)
    return f

def ex_arrow(c, onunit):
    pass

def ex_blunt(c, onunit):
    ring(c, (255, 255, 230), 1, 6, 0.25, 0.8, h=c.h0)
    star(c, (255, 250, 200), 3.5, 0.18)

def ex_whip(c, onunit):
    # щелчок: короткая белая волна и искорки
    ring(c, (255, 250, 235), 0.5, 5, 0.18, 0.5, h=c.h0)
    spray(c, 6, "spark", (255, 240, 200), 55, up=0.4, size=(0.3, 0.5), life=(0.1, 0.25), g=10)


def energy(name, fam, col, where):
    """Лучевое и прочее: цвет - от исходной анимации оружия."""
    onunit = where == "unit"
    c = Clip(name, L_HIT, DUR_HIT, 64, h0=UNIT_H if onunit else 0.0)
    rgb = COLORS[col]
    if fam == "laser":
        flash(c, rgb, 3.5, 0.18)
        spray(c, 14, "spark", rgb, 60, up=0.5, size=(0.4, 0.7), life=(0.2, 0.4), g=30)
        puffs(c, 4, [(90, 88, 85), (70, 68, 66)], 2.6, 16, 0.6, life=(0.5, 0.9), delay=0.08)
        if onunit:
            spray(c, 8, "ember", None, 20, up=0.7, size=(0.4, 0.7), life=(0.3, 0.6), g=10)
        else:
            scorch(c, (35, 25, 20), 2.6, 0.8)
        hotspot(c, mix(rgb, (255, 160, 60), 0.5), 1.6, DUR_HIT)
    elif fam == "plasma":
        flash(c, rgb, 6.0, 0.25)
        ring(c, rgb, 1, 9, 0.3, 1.2, h=c.h0)
        spray(c, 22, "spark", rgb, 55, up=0.6, size=(0.6, 1.1), life=(0.25, 0.5), g=20, drag=2)
        for _ in range(5):
            d = sphere_dir(c.rng, 0.5)
            c.add(vx=d[0] * 18, vy=d[1] * 18, vz=d[2] * 12 + 6, kind="wisp", rgb=rgb, size=c.rng.uniform(2.5, 4),
                  life=c.rng.uniform(0.3, 0.6), g=0, drag=3, seed=c.rng.uniform(0, 50))
        if not onunit:
            scorch(c, (30, 25, 25), 3.4, 0.8)
    elif fam == "electric":
        flash(c, rgb, 3.5, 0.3)
        arcs(c, rgb, 5, 12, 0.45)
        spray(c, 10, "spark", rgb, 70, up=0.5, size=(0.3, 0.6), life=(0.1, 0.3), g=40)
    elif fam == "warp":
        ring(c, rgb, 9, 0.5, 0.5, 1.2, h=c.h0)        # схлопывается внутрь
        ring(c, (255, 255, 255), 6, 0.3, 0.35, 0.6, h=c.h0)
        for _ in range(10):
            a = c.rng.uniform(0, 2 * math.pi); r = c.rng.uniform(6, 11)
            c.add(x=math.cos(a) * r, y=math.sin(a) * r, vx=-math.cos(a) * r * 2.2, vy=-math.sin(a) * r * 2.2, vz=0,
                  kind="spark", rgb=rgb, size=0.6, life=0.4, g=0)
        flash(c, rgb, 4.0, 0.2)
    elif fam == "psi":
        for i in range(3):
            ring(c, rgb, 1 + i, 10 + i * 3, 0.35 + i * 0.1, 0.8, h=c.h0)
        for _ in range(6):
            d = sphere_dir(c.rng, 0.6)
            c.add(vx=d[0] * 10, vy=d[1] * 10, vz=d[2] * 8 + 10, kind="wisp", rgb=rgb, size=c.rng.uniform(2, 3.2),
                  life=c.rng.uniform(0.4, 0.7), g=-8, drag=2, seed=c.rng.uniform(0, 50))
    elif fam == "acid":
        spray(c, 22, "goo", (130, 220, 40), 38, up=0.6, size=(0.5, 1.0), life=(0.4, 0.8), g=90)
        puffs(c, 5, [(170, 230, 90), (140, 200, 70)], 3.0, 14, 1, life=(0.5, 0.9), delay=0.1)
        flash(c, (190, 255, 110), 2.5, 0.12)
    elif fam == "bio":
        spray(c, 18, "goo", (80, 150, 40), 34, up=0.6, size=(0.6, 1.2), life=(0.4, 0.8), g=90)
        for _ in range(8):
            d = sphere_dir(c.rng, 0.5)
            c.add(vx=d[0] * 10, vy=d[1] * 10, vz=d[2] * 6 + 6, kind="puff", rgb=(120, 170, 60), size=c.rng.uniform(1.5, 2.6),
                  life=c.rng.uniform(0.5, 0.9), g=0, drag=2.5, seed=c.rng.uniform(0, 50))
    elif fam == "fire":
        flash(c, (255, 180, 70), 4.0, 0.2)
        spray(c, 20, "ember", None, 35, up=0.8, size=(0.5, 1.0), life=(0.3, 0.7), g=-15, drag=2)
        for _ in range(6):
            d = sphere_dir(c.rng, 0.3)
            c.add(vx=d[0] * 8, vy=d[1] * 8, vz=14 + c.rng.uniform(0, 8), kind="wisp", rgb=(255, 140, 40),
                  size=c.rng.uniform(2.0, 3.4), life=c.rng.uniform(0.3, 0.6), g=-10, drag=2, seed=c.rng.uniform(0, 50))
        puffs(c, 3, [(60, 55, 50)], 3.2, 18, 0.8, life=(0.5, 0.9), delay=0.15)
    elif fam == "gas":
        puffs(c, 9, [(190, 200, 170), (160, 175, 150)], 4.2, 6, 3.5, life=(0.6, 1.0), delay=0.1)
    elif fam == "charm":
        for _ in range(6):
            d = sphere_dir(c.rng, 0.8)
            c.add(vx=d[0] * 10, vy=d[1] * 10, vz=12 + c.rng.uniform(0, 8), kind="heart", rgb=(235, 60, 110),
                  size=c.rng.uniform(2.2, 3.4), life=c.rng.uniform(0.4, 0.55), g=-6, drag=2, age=-c.rng.uniform(0, 0.12))
        spray(c, 10, "spark", COLORS["pink"], 30, up=0.7, size=(0.3, 0.5), life=(0.3, 0.5), g=0)
    elif fam == "daze":
        ring(c, (255, 255, 240), 1, 7, 0.3, 0.8, h=c.h0)
        for i in range(5):
            a = i * 2 * math.pi / 5
            c.add(x=math.cos(a) * 4, y=math.sin(a) * 4, z=c.h0 + 6, vx=-math.sin(a) * 18, vy=math.cos(a) * 18, vz=4,
                  kind="spark", rgb=(255, 240, 120), size=0.9, life=0.5, g=0)
        flash(c, (255, 255, 220), 2.5, 0.12)
    return c

# ------------------------------------------------------------------ ближний бой: замах

L_MELEE = 4
DUR_MELEE = 0.3
# направление юнита 0..7: 0 - север (вверх-вправо на экране), по часовой
# как Pathfinding::dir_x / dir_y движка
DIRV = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]

def dir_screen(d):
    """Единичный вектор взгляда юнита в экранных координатах изометрии."""
    x, y = DIRV[d]
    sx, sy = x - y, (x + y) * 0.5
    n = math.hypot(sx, sy)
    return sx / n, sy / n

SWING = {
    # вид: (цвет следа, толщина, дуга градусов, тип)
    "fist":   ((255, 250, 235), 2.2, 0,   "jab"),
    "claw":   ((255, 235, 230), 1.3, 0,   "wolverine"),
    "bite":   ((255, 245, 235), 1.1, 0,   "bite"),
    "blade":  ((235, 245, 255), 1.4, 150, "arc"),
    "pierce": ((240, 245, 255), 1.0, 0,   "thrust"),
    "club":   ((255, 245, 220), 2.8, 120, "arc"),
    "whip":   ((255, 240, 215), 0.8, 200, "whip"),
    "sting":  ((230, 255, 220), 0.7, 0,   "thrust"),
    "butt":   ((245, 240, 230), 2.4, 60,  "arc"),
    "shock":  ((150, 200, 255), 1.4, 120, "arc"),
}

def swing(kind, d, col=None):
    rgb, width, arcdeg, style = SWING[kind]
    width *= 1.5
    if col:
        rgb = COLORS[col]
    c = Clip(f"swing_{kind}{'_' + col if col else ''}_{d}", L_MELEE, DUR_MELEE, 96, h0=UNIT_H)
    fx, fy = dir_screen(d)
    # удар приходит со стороны атакующего: против направления взгляда
    ox, oy = -fx, -fy
    s = K * SS
    glowy = col is not None or kind == "shock"

    @layer()
    def f(cv, t, u):
        cx, cy = cv.proj(0, 0, UNIT_H)
        k = min(1.0, t / DUR_MELEE)
        fade = 1 - max(0, (k - 0.55) / 0.45)
        R = 16 * s
        if style in ("arc", "claws"):
            # центр дуги - со стороны атакующего, середина дуги ложится на точку удара
            half = math.radians(arcdeg) / 2
            mid = math.atan2(-oy, -ox)
            ccx, ccy = cx + ox * R, cy + oy * R * 0.55
            a0 = mid - half
            a1 = a0 + 2 * half * min(1.0, 0.35 + k * 1.3)
            offs = [0] if style != "claws" else [-2.6, 0, 2.6]
            for off in offs:
                rr = R + off * s
                cv.arcband(ccx, ccy, rr, 0.55, a0, a1, width * s * 2.6, rgb, fade * 0.3, "glow")
                cv.arcband(ccx, ccy, rr, 0.55, a0, a1, width * s, rgb, fade * 0.95, "glow" if glowy else "over")
        elif style == "whip":
            half = math.radians(arcdeg) / 2
            base = math.atan2(oy, ox)
            # дуга проходит через точку удара поперёк направления
            sweep = [base + math.pi / 2 - half + 2 * half * min(1, k * 1.8) * i / 23 for i in range(24)]
            offs = [0] if style != "claws" else [-2.2, 0, 2.2]
            for off in offs:
                pts = []
                for i, a in enumerate(sweep):
                    r = R * (0.95 if style != "whip" else 0.7 + 0.5 * math.sin(i / 23 * math.pi * 2 + k * 6) * 0.3)
                    px = cx + ox * R * 0.55 + math.cos(a) * r * 0.9 + (-oy) * off * s
                    py = cy + oy * R * 0.55 + math.sin(a) * r * 0.55 + ox * off * s * 0.5
                    pts.append((px, py))
                n = len(pts)
                for i in range(n - 1):
                    tt = i / (n - 1)
                    a = (tt ** 1.5) * fade
                    w = width * s * (0.3 + 0.7 * tt)
                    cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], w * 2.2, rgb, a * 0.25, "glow")
                    cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], w, rgb, a * 0.9, "glow" if glowy else "over")
            if style == "whip" and k > 0.4:
                ex, ey = pts[-1]
                cv.disc(ex, ey, 2.5 * s * (1 - k), (255, 255, 240), fade, 1.0, "glow")
        elif style == "wolverine":
            # как в оригинале: три прямых штриха-линзы, но двумя лапами -
            # первая тройка косо, вторая крест-накрест поверх неё
            px, py = -oy, ox
            def slash(x0, y0, dx, dy, L, w, g, a):
                # линза по всей длине, но прочерчена только до головки g: штрих растёт
                n = 14
                for i in range(n):
                    t0, t1 = i / n, (i + 1) / n
                    if t0 >= g:
                        break
                    t1 = min(t1, g)
                    lw = w * math.sqrt(max(0.0, math.sin(math.pi * (t0 + t1) / 2)))
                    xa, ya = x0 + dx * L * t0, y0 + dy * L * t0
                    xb, yb = x0 + dx * L * t1, y0 + dy * L * t1
                    cv.line(xa, ya, xb, yb, lw * 2.4, (220, 30, 30), a * 0.3, "glow")
                    cv.line(xa, ya, xb, yb, lw, rgb, a * 0.95, "over")
            for rot, lead in ((0.75, 0.2), (-0.75, -0.2)):
                kk = min(1.0, max(0.0, (k + lead) / 0.45))
                if kk <= 0:
                    continue
                ca, sa = math.cos(rot), math.sin(rot)
                dx, dy = px * ca - py * sa, (px * sa + py * ca) * 0.8
                n = math.hypot(dx, dy); dx, dy = dx / n, dy / n
                nx, ny = -dy, dx
                hf = 1.0 if k < 0.7 else 1 - (k - 0.7) / 0.3 * 0.6
                for off, ln, sh in ((-1, 0.7, -0.15), (0, 1.0, 0.0), (1, 0.7, 0.15)):
                    L = 26 * s * ln
                    mx = cx + nx * off * 4.0 * s + dx * sh * L
                    my = cy + ny * off * 4.0 * s + dy * sh * L
                    g = min(1.0, kk * 1.4)
                    w = width * s * (1.0 if off == 0 else 0.75)
                    slash(mx - dx * L / 2, my - dy * L / 2, dx, dy, L, w, g, hf)
        elif style == "jab":
            # кулак: линии скорости сходятся в точку удара, там толчок
            # параллельные штрихи движения, короткие, сзади кулака
            head = min(1.0, k * 3)
            for j, (off, ln) in enumerate([(-1, 0.55), (0, 0.8), (1, 0.6)]):
                bx, by = cx + (-oy) * off * 2.2 * s, cy + ox * off * 2.2 * s
                st = R * (0.25 + 0.6 * (1 - head))
                x0, y0 = bx + ox * (st + R * ln * 0.6), by + oy * (st + R * ln * 0.6)
                x1, y1 = bx + ox * st, by + oy * st
                cv.line(x0, y0, x1, y1, width * s * 0.3, rgb, fade * 0.6, "over", taper=False)
        elif style == "thrust":
            L = R * 1.2
            head = min(1.0, k * 2.5)
            x0, y0 = cx + ox * L, cy + oy * L
            x1, y1 = cx + ox * L * (1 - head), cy + oy * L * (1 - head)
            cv.line(x0, y0, x1, y1, width * s * 3, rgb, fade * 0.25, "glow")
            cv.line(x0, y0, x1, y1, width * s, rgb, fade * 0.9, "glow" if glowy else "over")
            cv.disc(x1, y1, width * s * 1.4, (255, 255, 255), fade, 0.8, "glow")
        elif style == "bite":
            gap = (1 - min(1, k * 2.2)) * 6 * s
            for sgn in (-1, 1):
                for i in range(4):
                    tx = cx + (i - 1.5) * 2.2 * s
                    ty = cy + sgn * (gap + 1.5 * s)
                    cv.line(tx - 0.8 * s, ty, tx, ty - sgn * 2.5 * s, width * s, rgb, fade, "over")
                    cv.line(tx + 0.8 * s, ty, tx, ty - sgn * 2.5 * s, width * s, rgb, fade, "over")
    c.layers.append(f)
    # толчок в точке удара: у тупого сильнее, у режущего - искра по краю
    if style in ("jab", "arc") and kind in ("fist", "club", "butt"):
        star(c, (255, 250, 225), 3.5 if kind == "fist" else 5, DUR_MELEE * 0.7)
        ring(c, (255, 250, 230), 1, 7 if kind == "fist" else 10, DUR_MELEE, 0.8, h=UNIT_H)
    elif style in ("thrust", "bite"):
        star(c, (255, 250, 235), 2.5, DUR_MELEE * 0.5)
    if kind == "shock" or col:
        arcs(c, rgb if col else (150, 200, 255), 3, 8, DUR_MELEE)
    return c

# ------------------------------------------------------------------ вспышки выстрела

L_FLASH = 3
DUR_FLASH = 0.12

FLASH = {
    # вид: (цвет, длина, ширина, дым)
    "pistol":  ((255, 210, 120), 5, 3, 0),
    "smg":     ((255, 215, 130), 6, 3, 0),
    "rifle":   ((255, 200, 110), 8, 3.5, 0),
    "sniper":  ((255, 205, 120), 13, 4, 2),   # длинный язык и боковые струи дульного тормоза
    "heavy":   ((255, 190, 90), 12, 5.5, 2),
    "cannon":  ((255, 180, 80), 15, 8, 6),
    "shotgun": ((255, 200, 110), 10, 7, 3),
    "powder":  ((255, 180, 80), 8, 5, 8),    # кремнёвое: облако дыма
    "rocket":  ((255, 170, 70), 7, 6, 5),     # выхлоп назад
    "flame":   ((255, 150, 40), 10, 6, 1),
    "none":    ((230, 220, 200), 3, 3, 1),    # тетива, праща
}

def muzzle(kind, d, col=None):
    rgb, length, width, smoke = FLASH.get(kind, FLASH["rifle"])
    if col:
        rgb = COLORS[col]
    c = Clip(f"flash_{kind}{'_' + col if col else ''}_{d}", L_FLASH, DUR_FLASH, 64, h0=0)
    fx, fy = dir_screen(d)
    if kind == "rocket":
        fx, fy = -fx, -fy
    s = K * SS

    @layer()
    def f(cv, t, u):
        cx, cy = cv.cx, cv.cy
        v = 1 - u * 0.75
        L = length * s * (0.7 + 0.3 * math.sin(u * math.pi + 0.5))
        W = width * s * v
        # конус: несколько лучей
        for j, (off, sc) in enumerate([(0, 1.0), (0.35, 0.6), (-0.35, 0.6)] if kind != "shotgun" else [(0, 1), (0.25, 0.9), (-0.25, 0.9), (0.5, 0.6), (-0.5, 0.6)]):
            ca, sa = math.cos(off), math.sin(off)
            dx, dy = fx * ca - fy * sa, fx * sa + fy * ca
            cv.line(cx, cy, cx + dx * L * sc, cy + dy * L * sc, W * sc, rgb, v * (0.9 if j == 0 else 0.6), "glow", taper=True)
        if kind in ("sniper", "cannon"):
            # дульный тормоз: две короткие струи поперёк ствола чуть впереди среза
            bx, by = cx + fx * W * 0.8, cy + fy * W * 0.8
            for sg in (-1, 1):
                qx, qy = -fy * sg, fx * sg
                ex, ey = qx * 0.8 - fx * 0.2, qy * 0.8 - fy * 0.2
                cv.line(bx, by, bx + ex * L * 0.4, by + ey * L * 0.4, W * 0.6, rgb, v * 0.7, "glow", taper=True)
        cv.disc(cx + fx * W * 0.3, cy + fy * W * 0.3, W * 0.9, (255, 255, 240), v, 1.0, "glow")
        cv.disc(cx + fx * L * 0.3, cy + fy * L * 0.3, L * 0.6, rgb, v * 0.35, 1.5, "glow")
    c.layers.append(f)
    if smoke:
        for _ in range(smoke):
            sp = c.rng.uniform(4, 14)
            c.add(x=fx * 3, y=fy * 6, z=-fy * 0, vx=fx * sp, vy=fy * sp * 2, vz=c.rng.uniform(1, 5), kind="puff",
                  rgb=(170, 165, 160) if kind == "powder" else (120, 118, 115), size=c.rng.uniform(1.8, 3.2),
                  life=c.rng.uniform(0.25, 0.4), g=0, drag=4, seed=c.rng.uniform(0, 50))
    return c

# ------------------------------------------------------------------ взрывы

L_BOOM = 8
DUR_BOOM = 0.7

def boom(fam, col=None):
    c = Clip(f"boom_{fam}{'_' + col if col else ''}", L_BOOM, DUR_BOOM, 128, h0=4)
    rgb = COLORS[col] if col else (255, 170, 60)
    rng = c.rng
    if fam in ("he", "fire"):
        flash(c, (255, 210, 130), 20, 0.25)
        # дым сзади огня: встаёт позже, живёт дольше, поднимается столбом
        puffs(c, 14, [(70, 64, 58), (55, 50, 46), (90, 82, 72)], 11, 22, 9, life=(0.6, 1.0), delay=0.2)
        # огненный шар: крупные клубы пламени, разлетаются и поднимаются
        for _ in range(22):
            d = sphere_dir(rng, 0.7)
            sp = rng.uniform(8, 40)
            c.add(vx=d[0] * sp, vy=d[1] * sp, vz=abs(d[2]) * sp * 0.7 + 10, kind="fire",
                  size=rng.uniform(7, 12), life=rng.uniform(0.3, 0.55), g=-10, drag=3.5, seed=rng.uniform(0, 50),
                  age=-rng.uniform(0, 0.06))
        spray(c, 30, "spark", "fire", 110, up=0.7, size=(0.6, 1.1), life=(0.3, 0.6), g=50)
        spray(c, 12, "chunk", (70, 60, 50), 70, up=0.8, size=(0.8, 1.5), life=(0.5, 0.9), g=90)
        ring(c, (255, 230, 190), 4, 30, 0.3, 2.0, h=0)
        scorch(c, (30, 24, 20), 12, 0.7)
        if fam == "fire":
            for _ in range(10):
                a = rng.uniform(0, 2 * math.pi); r = rng.uniform(0, 14)
                c.add(x=math.cos(a) * r, y=math.sin(a) * r, z=0, vz=rng.uniform(8, 18), kind="wisp", rgb=(255, 120, 30),
                      size=rng.uniform(3, 5), life=rng.uniform(0.3, 0.6), g=-4, drag=2, seed=rng.uniform(0, 50), age=-rng.uniform(0.1, 0.35))
    elif fam == "gas":
        puffs(c, 16, [(185, 195, 165), (160, 170, 145)], 8, 5, 14, life=(0.6, 1.0), delay=0.2)
    elif fam == "acid":
        puffs(c, 10, [(160, 225, 80), (130, 200, 60)], 7, 10, 10, life=(0.6, 1.0), delay=0.15)
        spray(c, 30, "goo", (120, 210, 40), 55, up=0.7, size=(0.6, 1.2), life=(0.4, 0.8), g=90)
        flash(c, (200, 255, 120), 10, 0.15)
    elif fam in ("plasma", "energy"):
        flash(c, rgb, 18, 0.3)
        ring(c, rgb, 2, 30, 0.4, 2.0, h=0)
        ring(c, (255, 255, 255), 1, 18, 0.25, 1.0, h=0)
        spray(c, 40, "spark", rgb, 80, up=0.6, size=(0.7, 1.3), life=(0.3, 0.6), g=20, drag=1.5)
        for _ in range(10):
            d = sphere_dir(rng, 0.6)
            c.add(vx=d[0] * 25, vy=d[1] * 25, vz=abs(d[2]) * 15 + 8, kind="wisp", rgb=rgb, size=rng.uniform(5, 8),
                  life=rng.uniform(0.3, 0.55), g=0, drag=3, seed=rng.uniform(0, 50))
    elif fam == "electric":
        flash(c, rgb, 12, 0.3)
        arcs(c, rgb, 10, 26, 0.6, h=6)
        ring(c, rgb, 2, 24, 0.4, 1.2, h=0)
    elif fam == "psi":
        for i in range(4):
            ring(c, rgb, 2 + i * 2, 26 + i * 4, 0.45 + i * 0.07, 1.4, h=2 + i * 3)
        for _ in range(12):
            d = sphere_dir(rng, 0.6)
            c.add(vx=d[0] * 15, vy=d[1] * 15, vz=abs(d[2]) * 10 + 12, kind="wisp", rgb=rgb, size=rng.uniform(4, 6),
                  life=rng.uniform(0.4, 0.7), g=-6, drag=2, seed=rng.uniform(0, 50))
    elif fam == "stun":
        flash(c, (255, 255, 240), 22, 0.25)
        ring(c, (255, 255, 255), 2, 28, 0.3, 1.5, h=0)
        spray(c, 30, "spark", (255, 255, 220), 90, up=0.6, size=(0.4, 0.8), life=(0.15, 0.35), g=10)
        puffs(c, 8, [(225, 225, 220)], 6, 10, 8, life=(0.5, 0.9), delay=0.15)
    elif fam == "bio":
        puffs(c, 12, [(120, 170, 60), (100, 150, 50)], 7, 8, 10, life=(0.6, 1.0), delay=0.15)
        spray(c, 24, "goo", (80, 150, 40), 45, up=0.7, size=(0.6, 1.2), life=(0.4, 0.8), g=90)
    return c

# ------------------------------------------------------------------ состав

def build_all():
    clips = []
    kin = {"arrow": (0.7, ex_arrow), "blunt": (1.0, ex_blunt), "whip": (0.6, ex_whip),
           "pellet": (0.5, ex_bullet)}
    # пули по ступеням калибра: какую ступень берёт оружие - tools/hdart/weapon_classes.py
    for step, pw in CAL.items():
        kin[f"cal{step}"] = (pw, ex_cal(step))
    for fam, (pw, ex) in kin.items():
        for w in TARGETS + MATS:
            clips.append(lambda fam=fam, w=w, pw=pw, ex=ex: kinetic(f"hit_{fam}_{w}", w, pw, ex))
    for fam in ("laser", "plasma", "electric", "warp", "psi"):
        for col in ECOLORS:
            for w in ("unit", "ground"):
                clips.append(lambda fam=fam, col=col, w=w: energy(f"hit_{fam}_{col}_{w}", fam, col, w))
    for fam in ("acid", "bio", "fire", "gas", "charm", "daze"):
        for w in ("unit", "ground"):
            clips.append(lambda fam=fam, w=w: energy(f"hit_{fam}_{w}", fam, "white", w))
    for kind in SWING:
        for d in range(8):
            clips.append(lambda kind=kind, d=d: swing(kind, d))
    for col in ECOLORS:                    # энергоклинки
        for d in range(8):
            clips.append(lambda col=col, d=d: swing("blade", d, col))
    for kind in FLASH:
        for d in range(8):
            clips.append(lambda kind=kind, d=d: muzzle(kind, d))
    for kind in ("laser", "plasma", "electric", "spit"):
        for col in ECOLORS:
            for d in range(8):
                clips.append(lambda kind=kind, col=col, d=d: muzzle(kind, d, col))
    for fam in ("he", "fire", "gas", "acid", "stun", "bio"):
        clips.append(lambda fam=fam: boom(fam))
    for fam in ("plasma", "electric", "psi", "energy"):
        for col in ECOLORS:
            clips.append(lambda fam=fam, col=col: boom(fam, col))
    return clips


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="каталог hd мода (кладём в <out>/FX)")
    ap.add_argument("--only", default="", help="префиксы имён клипов через запятую")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    makers = build_all()
    pref = [p for p in args.only.split(",") if p]
    t0 = time.time(); done = 0
    index = []
    for mk in makers:
        c = mk()
        if pref and not any(c.name.startswith(p) for p in pref):
            continue
        if args.list:
            print(c.name, c.L, c.size); continue
        frames = c.render()
        d = os.path.join(args.out, "FX", c.name)
        os.makedirs(d, exist_ok=True)
        for i, im in enumerate(frames):
            im.save(os.path.join(d, f"{i}.png"), optimize=True)
        index.append((c.name, c.L, c.size))
        done += 1
        if done % 25 == 0:
            print(f"{done} клипов, {time.time() - t0:.0f} с", flush=True)
    if args.out and not args.list:
        # полный список клипов на диске, а не только этого прогона
        root = os.path.join(args.out, "FX")
        rows = []
        for name in sorted(os.listdir(root)):
            p = os.path.join(root, name)
            if not os.path.isdir(p):
                continue
            n = len([f for f in os.listdir(p) if f.endswith(".png")])
            w, h = Image.open(os.path.join(p, "0.png")).size
            rows.append(f"  {name}: [{n}, {w // K}, {h // K}]")
        with open(os.path.join(root, "clips.yml"), "w", encoding="utf-8") as f:
            f.write("# written by tools/hdart/gen_fx.py: clip: [frames, base width, base height]\nclips:\n" + "\n".join(rows) + "\n")
        print(f"готово: {done} клипов за {time.time() - t0:.0f} с -> {root}")


if __name__ == "__main__":
    main()
