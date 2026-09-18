#!/usr/bin/env python3
"""
HD effects (stage 4b): the battlescape's fire, smoke, hit flashes, the melee star and the big
explosion, drawn procedurally (no GPU, seconds) as an HD pack of the classic sets:

    hd/SMOKE.PCK/<i>.png    0-3 tile fire, 4-7 burning unit (each with <i>.v1.png, the picture half a step
                            later: the engine shows it on the odd animation tick, 8 phases instead of 4),
                            8-19 smoke (3 densities x 4 frames),
                            26-35 bullet hit (--bullet-style; <i>.v1.png = the same hit with blood, which the
                            engine draws when the shot landed on a unit), 36-45 laser hit (red-orange burst),
                            46-55 plasma hit (green)
    hd/HIT.PCK/<i>.png      0-3 the mark of a melee hit (--melee-style; <i>.v1.png with blood, as above)
    hd/X1.PCK/<i>.png       0-7 the big explosion (128x64 frames)

Frames 20-25 of SMOKE.PCK (the rank badges) are left alone. Every frame keeps the classic
frame's size (x --scale) and anchor, so the engine places them exactly where it placed the
classic ones; the smoke gets real translucency instead of a dither, the fire a glow, the hits
sparks and flashes. Soft edges throughout - nothing is a blob of pixels any more.

    python gen_fx.py --mod user\\mods\\hd            writes the three packs
    python gen_fx.py --mod out --preview fx.png     also a sheet of every frame for a look
    python gen_fx.py --fire-compare fire_compare    ten fire styles next to the current fire (GIF + sheet)
    python gen_fx.py --mod user\\mods\\hd --fire-style 4 --only-fire     the chosen fire only
    python gen_fx.py --hit-compare hit_compare                     the melee and bullet hits, every style
    python gen_fx.py --mod user\\mods\\hd --melee-style 3 --bullet-style 2 --only-hits    the chosen hits only

The fire is one looping flame in eight phases (--fire-style 1-10, default 1): the rising noise repeats
after a whole number of its periods and every tongue sways a whole number of beats per loop, so phase 8
is phase 0 again.
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image


# ----------------------------------------------------------------------------- noise

def value_noise(shape, cell, seed, offset=(0.0, 0.0), shear=0.0):
    """Smooth value noise (quintic interpolation) over `shape` (h, w) with lattice spacing `cell`
    pixels, shifted by `offset` pixels, the lattice sheared by `shear` (no rows of features); -1..1."""
    h, w = shape
    rng = np.random.default_rng(seed)
    gw, gh = int((w + abs(shear) * h) / cell) + 4, int(h / cell) + 4
    grid = rng.random((gh + 1, gw + 1)) * 2 - 1
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    fx = (xs + offset[0] + shear * ys) / cell + 1.0 + (abs(shear) * h / cell if shear < 0 else 0.0)
    fy = (ys + offset[1]) / cell + 1.0
    x0 = np.floor(fx).astype(int)
    y0 = np.floor(fy).astype(int)
    tx = fx - x0
    ty = fy - y0
    x0 = np.clip(x0, 0, gw - 1)
    y0 = np.clip(y0, 0, gh - 1)
    sx = tx * tx * tx * (tx * (tx * 6 - 15) + 10)
    sy = ty * ty * ty * (ty * (ty * 6 - 15) + 10)
    a = grid[y0, x0]
    b = grid[y0, x0 + 1]
    c = grid[y0 + 1, x0]
    d = grid[y0 + 1, x0 + 1]
    return (a * (1 - sx) + b * sx) * (1 - sy) + (c * (1 - sx) + d * sx) * sy


def fbm(shape, cell, seed, octaves=4, gain=0.5, offset=(0.0, 0.0), shear=0.0):
    """Fractal noise, roughly -1..1 (the octaves sheared alternately, so no lattice shows)."""
    out = np.zeros(shape, dtype=np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        sh = shear * (1 if o % 2 == 0 else -1) + 0.3 * (o % 2)
        out += amp * value_noise(shape, cell / (2 ** o), seed + o * 101, (offset[0] * (2 ** o), offset[1] * (2 ** o)), sh)
        total += amp
        amp *= gain
    return out / total


def fbm_loop(shape, cell, seed, phase, octaves=4, offset=(0.0, 0.0), shear=0.0):
    """Noise that loops over phase 0..2pi (two fields blended by cos/sin): animation frames that cycle."""
    a = fbm(shape, cell, seed, octaves, offset=offset, shear=shear)
    b = fbm(shape, cell, seed + 5000, octaves, offset=offset, shear=shear)
    return a * math.cos(phase) + b * math.sin(phase)


def blur(a, radius):
    """A small box blur (two passes ~ Gaussian), for softening a generated field."""
    if radius < 1:
        return a
    out = a
    for _ in range(2):
        pad = np.pad(out, radius, mode="edge")
        acc = np.zeros_like(out)
        n = 2 * radius + 1
        for d in range(n):
            acc += pad[d:d + out.shape[0], radius:radius + out.shape[1]]
        out = acc / n
        pad = np.pad(out, radius, mode="edge")
        acc = np.zeros_like(out)
        for d in range(n):
            acc += pad[radius:radius + out.shape[0], d:d + out.shape[1]]
        out = acc / n
    return out


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def ramp(t, stops):
    """Colour ramp: stops = [(t, (r, g, b)), ...] with t ascending; t array in 0..1 -> (h, w, 3) floats."""
    t = np.clip(t, 0, 1)
    out = np.zeros(t.shape + (3,), dtype=np.float32)
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        sel = (t >= t0) & (t <= t1)
        f = ((t - t0) / max(t1 - t0, 1e-6))[..., None]
        out[sel] = (np.array(c0) * (1 - f) + np.array(c1) * f)[sel]
    return out


def to_image(rgb, alpha):
    """rgb floats 0..255 (h, w, 3), alpha 0..1 -> RGBA image."""
    a = np.clip(alpha, 0, 1)
    out = np.zeros(rgb.shape[:2] + (4,), dtype=np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = (a * 255 + 0.5).astype(np.uint8)
    out[a <= 0.002] = 0
    return Image.fromarray(out, "RGBA")


def grid(h, w, k):
    """Pixel centres in base (classic) pixel units."""
    ys, xs = np.mgrid[0:h * k, 0:w * k].astype(np.float32)
    return (xs + 0.5) / k, (ys + 0.5) / k


def gauss(xs, ys, cx, cy, r):
    return np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * r * r))


# ----------------------------------------------------------------------------- the effects

FIRE_RAMP = [(0.0, (58, 4, 0)), (0.18, (140, 18, 0)), (0.38, (214, 58, 4)), (0.58, (245, 104, 10)),
             (0.76, (253, 158, 28)), (0.90, (255, 208, 78)), (1.0, (255, 244, 186))]


def fire(k, frame, big, seed):
    """Flames on a tile (frames 0-3, footprint x 2..30, base y 36) or on a unit (frames 4-7,
    x 8..24, base y 27).

    A tile of fire is drawn with one of these four frames, chosen by the tile's own random offset
    (Tile::_animationOffset), so the four are not four phases of one flame - each is its own
    arrangement of tongues, and a burning field shows four different silhouettes instead of the
    same one repeated. Within a tile they still read as flicker, which is what fire does anyway.

    The shape is a few tongues of flame whose sideways lick grows with height (domain-warped
    noise), eaten away towards the tips so the flame breaks into wisps, over a bed of embers. The
    colour is the heat of each pixel, hottest at the core and the base; the whole thing is
    translucent, more so at the tips, so the ground shows through instead of an opaque cut-out.
    """
    w, h = 32, 40
    xs, ys = grid(h, w, k)
    shape = (h * k, w * k)
    rng = np.random.default_rng(seed * 31 + frame * 7 + (0 if big else 3))
    if big:
        base, top, spread, count = 36.5, 5.5, 9.5, 4
        bed = (16.0, 34.8, 11.5, 3.6)
    else:
        base, top, spread, count = 27.5, 5.0, 4.2, 3
        bed = (16.0, 26.0, 6.5, 2.6)
    # this frame's tongues: where they stand, how high they reach, how wide they are
    tongues = []
    for i in range(count):
        side = (i - (count - 1) / 2.0) / max(count - 1, 1) * 2.0
        cx = 16.0 + side * spread + rng.uniform(-1.6, 1.6)
        low_tall = (0.26 if big else 0.62)
        tall = (1.0 if i == count // 2 else rng.uniform(low_tall, 0.92)) * rng.uniform(0.8, 1.15)
        half = (3.4 if big else 2.8) * rng.uniform(0.6, 1.0) * (0.5 + 0.5 * tall)
        tongues.append((cx, min(tall, 1.0), half, rng.uniform(-1.0, 1.0)))
    # the noise fields are offset by a random fraction of a cell as well, or the lattice of the
    # finest octave lines up between frames and shows as rows across the flame
    jx, jy = rng.uniform(0, 97), rng.uniform(0, 97)
    warp = fbm(shape, 7.5 * k, seed + frame * 131 + 11, 4, offset=(jx, jy - frame * 9.0 * k), shear=0.45)
    fine = fbm(shape, 4.0 * k, seed + frame * 197 + 23, 3, offset=(jy, jx - frame * 14.0 * k), shear=0.32)
    grain = fbm(shape, 2.6 * k, seed + frame * 311 + 37, 2, offset=(jx * 2, jy * 2 - frame * 18.0 * k), shear=-0.25)
    density = np.zeros(shape, dtype=np.float32)
    # a low body across the whole footprint: the tongues rise out of one flame, not each on its own
    body_tip = base - (base - top) * (0.30 if big else 0.46)
    vb = np.clip((base - ys) / max(base - body_tip, 1.0), 0, 1.4)
    ub = (xs - 16.0 + warp * 1.6 * (0.3 + vb)) / (spread * (1.05 - 0.45 * np.clip(vb, 0, 1)))
    low = np.exp(-0.5 * ub * ub * 1.35) * np.clip(1.2 - vb, 0, 1) ** 0.6 * (0.72 + 0.5 * fine)
    low -= 0.5 * np.clip(vb, 0, 1.2) ** 1.4 * (0.45 + 0.55 * fine)
    density = np.maximum(density, low * smoothstep(base + 2.0, base - 1.5, ys))
    for cx, tall, half, lean in tongues:
        tip = base - (base - top) * tall
        v = np.clip((base - ys) / max(base - tip, 1.0), 0, 1.6)        # 0 at the base, 1 at the tip
        lick = (warp * (0.4 + 2.6 * v) + lean * 1.1 * v * v) * half * 0.6
        width = half * (1.0 - 0.74 * np.clip(v, 0, 1) ** 1.05)
        u = (xs - cx + lick) / np.maximum(width, 0.3)
        body = np.exp(-0.5 * u * u * (1.0 + 0.55 * np.clip(v, 0, 1)))
        along = np.clip(1.12 - v, 0, 1) ** 0.62
        d = body * along * (0.7 + 0.52 * fine + 0.14 * grain)
        d -= 0.78 * np.clip(v, 0, 1.3) ** 1.5 * (0.4 + 0.6 * fine)     # the tip breaks into wisps
        d *= smoothstep(base + 2.0, base - 1.5, ys)                    # nothing below the ground
        density = np.maximum(density, d)
    bx, by, brx, bry = bed
    ember = np.exp(-(((xs - bx) / brx) ** 2 + ((ys - by) / bry) ** 2) * 1.15) * (0.55 + 0.45 * fine)
    density = np.maximum(density, ember * 0.66)
    # a touch of blur takes the noise's hairiness off, then the silhouette is brought back with a
    # curve: soft edges, but tongues with an edge to them rather than blobs
    soft = blur(np.clip(density, 0, 1), max(1, k // 4))
    density = np.clip(smoothstep(0.06, 0.55, soft) * 0.88 + soft * 0.3, 0, 1)
    height = np.clip((base - ys) / (base - top), 0, 1)
    # heat: the core and the base are white-hot, the tips are dull red
    # only the bottom of the core burns white; the body stays orange-yellow and the tips go red
    heat = np.clip(density * (0.72 - 0.38 * height) + 0.28 * density ** 2 * np.clip(1.0 - 2.8 * height, 0, 1), 0, 1)
    rgb = ramp(heat ** 0.82, FIRE_RAMP)
    alpha = smoothstep(0.06, 0.38, density) * (1.0 - 0.45 * height) * 0.96
    # a warm glow on the ground under the flames
    glow = np.exp(-(((xs - bx) / (brx * 1.5)) ** 2 + ((ys - by) / (bry * 1.7)) ** 2)) * smoothstep(base + 3.0, base - 6.0, ys)
    rgb = rgb * np.clip(alpha, 0, 1)[..., None] + np.array(FIRE_RAMP[2][1], dtype=np.float32) * (glow * 0.5)[..., None]
    alpha = np.clip(alpha + glow * 0.34, 0, 1)
    rgb = np.where(alpha[..., None] > 0.004, rgb / np.maximum(alpha, 0.004)[..., None], 0.0)
    return to_image(np.clip(rgb, 0, 255), alpha)


# ----------------------------------------------------------------------------- looping fire (8 phases, 10 styles)

def periodic_noise(shape, cell, seed, scroll, period, sway=0.0, shear=0.0):
    """Value noise (quintic) whose lattice repeats every `period` pixels upwards and that is shifted up by
    `scroll` pixels (scroll = period * whole number closes the loop); -1..1."""
    h, w = shape
    rng = np.random.default_rng(seed)
    rows = max(1, int(round(period / cell)))
    cell_y = period / rows
    gw = int((w + abs(shear) * h) / cell) + 4
    grid_ = rng.random((rows, gw + 1)) * 2 - 1
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    fx = (xs + sway + shear * ys) / cell + 1.0 + (abs(shear) * h / cell if shear < 0 else 0.0)
    fy = (ys + scroll) / cell_y
    x0 = np.clip(np.floor(fx).astype(int), 0, gw - 1)
    y0 = np.floor(fy).astype(int)
    tx = fx - np.floor(fx)
    ty = fy - y0
    sx = tx * tx * tx * (tx * (tx * 6 - 15) + 10)
    sy = ty * ty * ty * (ty * (ty * 6 - 15) + 10)
    r0 = np.mod(y0, rows)
    r1 = np.mod(y0 + 1, rows)
    a = grid_[r0, x0]
    b = grid_[r0, x0 + 1]
    c = grid_[r1, x0]
    d = grid_[r1, x0 + 1]
    return (a * (1 - sx) + b * sx) * (1 - sy) + (c * (1 - sx) + d * sx) * sy


def rising_fbm(shape, cell, seed, phase, period, speeds, sway=0.0, shear=0.4):
    """Fractal noise flowing upwards that loops over phase 0..1: octave o scrolls speeds[o] periods per loop."""
    out = np.zeros(shape, dtype=np.float32)
    amp, total = 1.0, 0.0
    for o, sp in enumerate(speeds):
        c = cell / (2 ** o)
        sh = shear * (1 if o % 2 == 0 else -1) + 0.3 * (o % 2)
        out += amp * periodic_noise(shape, c, seed + o * 101, phase * period * sp, period, sway * (o + 1), sh)
        total += amp
        amp *= 0.5
    return out / total


FIRE_STYLES = {
    # name, look: ramp (heat colours), tall (flame height), wide (width), tongues, lick (how much the
    # flame sways), wisps (how the tips break up), speed (how fast it rises), alpha, glow, embers,
    # blur (softness), crisp (hard edge), smoke (a veil of smoke over it), sparks, gas (blue base)
    1: dict(name="classic", ru="классика: оранжевые языки со свечением (как сейчас, но течёт плавно)"),
    2: dict(name="tall", ru="высокий: высокие узкие языки", tall=1.3, wide=0.75, tongues=3, lick=0.8),
    3: dict(name="campfire", ru="костёр: низкий и широкий, много углей", tall=0.62, wide=1.15, tongues=5, embers=1.0, glow=0.45),
    4: dict(name="wild", ru="буйный: турбулентный, рвётся на клочья", lick=1.9, wisps=1.5, speed=1.5),
    5: dict(name="smoky", ru="дымный: тёмно-красное пламя под пеленой дыма",
            ramp=[(0.0, (40, 4, 0)), (0.25, (110, 16, 0)), (0.5, (190, 48, 6)), (0.75, (235, 110, 24)), (1.0, (255, 190, 90))], smoke=1.0, glow=0.22),
    6: dict(name="hot", ru="жаркий: яркое жёлто-белое ядро",
            ramp=[(0.0, (90, 10, 0)), (0.15, (200, 50, 0)), (0.35, (255, 120, 10)), (0.55, (255, 190, 40)), (0.75, (255, 235, 120)), (1.0, (255, 255, 235))], core=1.7, glow=0.45),
    7: dict(name="soft", ru="мягкий: полупрозрачный, как на фото", alpha=0.72, blur=2.2, glow=0.25, wisps=1.2),
    8: dict(name="crisp", ru="чёткий: резкие края, мало оттенков", crisp=1.0, blur=0.0,
            ramp=[(0.0, (150, 20, 0)), (0.34, (150, 20, 0)), (0.35, (240, 90, 10)), (0.64, (240, 90, 10)), (0.65, (255, 190, 50)), (0.9, (255, 190, 50)), (0.91, (255, 245, 170)), (1.0, (255, 245, 170))]),
    9: dict(name="gas", ru="газовый: синий у основания, оранжевый выше", gas=1.0),
    10: dict(name="sparks", ru="искры: пламя и летящие вверх искры", sparks=1.0, embers=0.8),
}
FIRE_DEFAULTS = dict(ramp=None, tall=1.0, wide=1.0, tongues=None, lick=1.0, wisps=1.0, speed=1.0, alpha=0.96,
                     glow=0.34, embers=0.66, blur=1.0, crisp=0.0, core=1.0, smoke=0.0, sparks=0.0, gas=0.0)


def fire_loop(k, phase, big, seed, style):
    """One phase (0..1) of a looping fire: a tile fire (big: footprint x 2..30, base y 36) or a unit fire
    (x 8..24, base y 27). Phases 0, 1/8, ... 7/8 are the eight pictures; phase 1 is phase 0 again."""
    st = dict(FIRE_DEFAULTS)
    st.update(FIRE_STYLES[style])
    w, h = 32, 40
    xs, ys = grid(h, w, k)
    shape = (h * k, w * k)
    two_pi = 2 * math.pi
    rng = np.random.default_rng(seed * 31 + (0 if big else 3) + style * 1009)
    if big:
        base, top, spread, count = 36.5, 5.5, 9.5, 4
        bed = (16.0, 34.8, 11.5, 3.6)
    else:
        base, top, spread, count = 27.5, 5.0, 4.2, 3
        bed = (16.0, 26.0, 6.5, 2.6)
    if st["tongues"]:
        count = st["tongues"] if big else max(2, st["tongues"] - 1)
    spread *= st["wide"]
    top = base - (base - top) * min(st["tall"], (base - 1.0) / (base - top))
    period = 26.0 * k                       # the flow's vertical period (pixels)
    sp = st["speed"]
    speeds = [1 * sp, 2 * sp, 2 * sp, 3 * sp]
    speeds = [max(1, int(round(s))) for s in speeds]
    sway = 1.3 * k * math.sin(two_pi * phase)
    warp = rising_fbm(shape, 7.5 * k, seed + 11 + style, phase, period, speeds, sway, 0.45)
    fine = rising_fbm(shape, 4.0 * k, seed + 23 + style, phase, period, [s + 1 for s in speeds[:3]], -sway, 0.32)
    grain = rising_fbm(shape, 2.6 * k, seed + 37 + style, phase, period, [s + 2 for s in speeds[:2]], sway, -0.25)
    tongues = []
    for i in range(count):
        side = (i - (count - 1) / 2.0) / max(count - 1, 1) * 2.0
        cx = 16.0 + side * spread + rng.uniform(-1.2, 1.2)
        low_tall = 0.34 if big else 0.62
        tall0 = 1.0 if i == count // 2 else rng.uniform(low_tall, 0.9)
        beat = rng.integers(1, 3)           # whole beats per loop: the loop closes
        ph0 = rng.uniform(0, two_pi)
        tall = np.clip(tall0 * (0.86 + 0.16 * math.sin(two_pi * phase * beat + ph0)), 0.2, 1.0)
        half = (3.4 if big else 2.8) * rng.uniform(0.65, 1.0) * (0.5 + 0.5 * tall) * st["wide"] ** 0.5
        lean = 0.8 * math.sin(two_pi * phase + ph0 * 1.7)
        cx += 0.6 * math.sin(two_pi * phase * beat + ph0 * 0.5)
        tongues.append((cx, float(tall), half, lean))
    density = np.zeros(shape, dtype=np.float32)
    body_tip = base - (base - top) * (0.30 if big else 0.46)
    vb = np.clip((base - ys) / max(base - body_tip, 1.0), 0, 1.4)
    ub = (xs - 16.0 + warp * 1.6 * (0.3 + vb)) / (spread * (1.05 - 0.45 * np.clip(vb, 0, 1)))
    low = np.exp(-0.5 * ub * ub * 1.35) * np.clip(1.2 - vb, 0, 1) ** 0.6 * (0.72 + 0.5 * fine)
    low -= 0.5 * np.clip(vb, 0, 1.2) ** 1.4 * (0.45 + 0.55 * fine)
    density = np.maximum(density, low * smoothstep(base + 2.0, base - 1.5, ys))
    for cx, tall, half, lean in tongues:
        tip = base - (base - top) * tall
        v = np.clip((base - ys) / max(base - tip, 1.0), 0, 1.6)
        lick = (warp * (0.4 + 2.6 * v) * st["lick"] + lean * 1.1 * v * v) * half * 0.6
        width = half * (1.0 - 0.74 * np.clip(v, 0, 1) ** 1.05)
        u = (xs - cx + lick) / np.maximum(width, 0.3)
        body = np.exp(-0.5 * u * u * (1.0 + 0.55 * np.clip(v, 0, 1)))
        along = np.clip(1.12 - v, 0, 1) ** 0.62
        d = body * along * (0.7 + 0.52 * fine + 0.14 * grain)
        d -= 0.78 * st["wisps"] * np.clip(v, 0, 1.3) ** 1.5 * (0.4 + 0.6 * fine)
        d *= smoothstep(base + 2.0, base - 1.5, ys)
        density = np.maximum(density, d)
    bx, by, brx, bry = bed
    ember = np.exp(-(((xs - bx) / (brx * st["wide"])) ** 2 + ((ys - by) / bry) ** 2) * 1.15) * (0.55 + 0.45 * fine)
    density = np.maximum(density, ember * st["embers"])
    br = int(round(max(0, k // 4) * st["blur"]))
    soft = blur(np.clip(density, 0, 1), br) if br >= 1 else np.clip(density, 0, 1)
    if st["crisp"] > 0:
        density = np.clip(smoothstep(0.26, 0.32, soft), 0, 1)
    else:
        density = np.clip(smoothstep(0.06, 0.55, soft) * 0.88 + soft * 0.3, 0, 1)
    height = np.clip((base - ys) / (base - top), 0, 1)
    heat = np.clip(density * (0.72 - 0.38 * height) * st["core"] ** 0.5
                   + 0.28 * st["core"] * density ** 2 * np.clip(1.0 - 2.8 * height, 0, 1), 0, 1)
    if st["crisp"] > 0:
        heat = np.clip(soft * (1.05 - 0.55 * height) * 1.25, 0, 1) * (density > 0)
    rgb = ramp(heat ** 0.82, st["ramp"] or FIRE_RAMP)
    if st["gas"] > 0:
        blue = ramp(np.clip(heat * 1.2, 0, 1), [(0.0, (10, 20, 120)), (0.5, (40, 90, 255)), (1.0, (170, 220, 255))])
        m = (smoothstep(0.32, 0.0, height) * st["gas"])[..., None]
        rgb = rgb * (1 - m) + blue * m
    alpha = smoothstep(0.06, 0.38, density) * (1.0 - 0.45 * height) * st["alpha"]
    if st["crisp"] > 0:
        alpha = density * 0.95
    glow = np.exp(-(((xs - bx) / (brx * 1.5 * st["wide"])) ** 2 + ((ys - by) / (bry * 1.7)) ** 2)) * smoothstep(base + 3.0, base - 6.0, ys)
    glow_rgb = np.array((120, 150, 255) if st["gas"] > 0 else (st["ramp"] or FIRE_RAMP)[2][1], dtype=np.float32)
    rgb = rgb * np.clip(alpha, 0, 1)[..., None] + glow_rgb * (glow * 0.5 * st["glow"] / 0.34)[..., None]
    alpha = np.clip(alpha + glow * st["glow"], 0, 1)
    if st["sparks"] > 0:
        spark_rng = np.random.default_rng(seed + 77 + (0 if big else 1))
        field = np.zeros(shape, dtype=np.float32)
        n_sp = 14 if big else 8
        for i in range(n_sp):
            start = spark_rng.random()
            beat = spark_rng.integers(1, 3)
            life = (phase * beat + start) % 1.0
            x0 = 16.0 + spark_rng.uniform(-1, 1) * spread * 0.9
            px = x0 + 2.2 * math.sin(two_pi * (life * 1.5 + start)) * life
            py = base - 3.0 - life * (base - 1.0) * spark_rng.uniform(0.7, 1.0)
            r = 0.45 + 0.25 * (1 - life)
            field += np.exp(-((xs - px) ** 2 + ((ys - py) * 0.7) ** 2) / (2 * r * r)) * (1 - life) ** 0.7
        field = np.clip(field * st["sparks"], 0, 1)
        spark_rgb = ramp(0.6 + 0.4 * field, st["ramp"] or FIRE_RAMP)
        rgb = rgb + spark_rgb * field[..., None]
        alpha = np.clip(alpha + field * 0.9, 0, 1)
    if st["smoke"] > 0:
        veil = smoothstep(0.35, 1.0, height + 0.25 * warp) * smoothstep(-0.1, 0.5, fine + 0.3) * 0.55 * st["smoke"]
        veil *= smoothstep(base + 1.0, base - 8.0, ys) * np.exp(-(((xs - 16.0) / (spread * 1.3)) ** 2))
        # thin out before the frame's edges: the engine cuts the picture there
        veil *= smoothstep(0.0, 9.0, ys) * smoothstep(0.0, 6.0, xs) * smoothstep(float(w), w - 6.0, xs)
        grey = np.full(shape + (3,), 58.0, dtype=np.float32)
        a_new = np.clip(alpha + veil * (1 - alpha), 0, 1)
        rgb = rgb + grey * (veil * (1 - alpha))[..., None]
        alpha = a_new
    rgb = np.where(alpha[..., None] > 0.004, rgb / np.maximum(alpha, 0.004)[..., None], 0.0)
    return to_image(np.clip(rgb, 0, 255), alpha)


def label_font():
    """A font for the comparison pictures and whether it can write Russian (the built-in one cannot)."""
    from PIL import ImageFont
    for path in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf"):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, 14), True
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=14), False
    except TypeError:
        return ImageFont.load_default(), False


def fire_compare(out_dir, k, seed):
    """Every style next to the current fire: an animated GIF at game speed (both tile and unit fire, on a
    dark and a snowy ground) and a sheet of the eight phases of each."""
    from PIL import ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    font, cyrillic = label_font()
    cw, ch = 32 * k, 40 * k
    grounds = [(46, 58, 40), (214, 222, 230)]
    styles = [0] + sorted(FIRE_STYLES)
    # frames: style 0 is the current fire (4 frames, each shown for two ticks)
    phases = {}
    for s in styles:
        for big in (True, False):
            if s == 0:
                pics = [fire(k, f, big, seed if big else seed + 1) for f in range(4)]
                phases[(s, big)] = [pics[t // 2] for t in range(8)]
            else:
                phases[(s, big)] = [fire_loop(k, t / 8.0, big, seed if big else seed + 1, s) for t in range(8)]
    label_h = 20
    cols = len(styles)
    width = cols * cw
    height = label_h + len(grounds) * ch
    frames = []
    for t in range(8):
        im = Image.new("RGBA", (width, height), (24, 24, 24, 255))
        d = ImageDraw.Draw(im)
        for c, s in enumerate(styles):
            d.text((c * cw + 4, 3), "%d %s" % (s, "now" if s == 0 else FIRE_STYLES[s]["name"]), fill=(240, 240, 240), font=font)
            for r, gc in enumerate(grounds):
                x, y = c * cw, label_h + r * ch
                tile = Image.new("RGBA", (cw, ch), gc + (255,))
                # the tile fire, and a small unit fire beside it in the lower corner
                tile.alpha_composite(phases[(s, True)][t])
                im.alpha_composite(tile, (x, y))
        frames.append(im.convert("RGB"))
    gif = os.path.join(out_dir, "fire_styles.gif")
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=110, loop=0, optimize=False)
    # unit fire strip
    uframes = []
    for t in range(8):
        im = Image.new("RGBA", (width, label_h + ch), (24, 24, 24, 255))
        d = ImageDraw.Draw(im)
        for c, s in enumerate(styles):
            d.text((c * cw + 4, 3), "%d %s" % (s, "now" if s == 0 else FIRE_STYLES[s]["name"]), fill=(240, 240, 240), font=font)
            tile = Image.new("RGBA", (cw, ch), grounds[0] + (255,))
            tile.alpha_composite(phases[(s, False)][t])
            im.alpha_composite(tile, (c * cw, label_h))
        uframes.append(im.convert("RGB"))
    ugif = os.path.join(out_dir, "fire_styles_unit.gif")
    uframes[0].save(ugif, save_all=True, append_images=uframes[1:], duration=110, loop=0, optimize=False)
    # the sheet: a row per style, the eight phases
    sheet = Image.new("RGBA", (8 * cw + 170, len(styles) * ch), (24, 24, 24, 255))
    d = ImageDraw.Draw(sheet)
    for r, s in enumerate(styles):
        d.text((6, r * ch + 6), "%d %s" % (s, "now (4 frames)" if s == 0 else FIRE_STYLES[s]["name"]), fill=(240, 240, 240), font=font)
        for t in range(8):
            tile = Image.new("RGBA", (cw, ch), grounds[0] + (255,))
            tile.alpha_composite(phases[(s, True)][t])
            sheet.alpha_composite(tile, (170 + t * cw, r * ch))
    png = os.path.join(out_dir, "fire_styles.png")
    sheet.save(png)
    with open(os.path.join(out_dir, "fire_styles.txt"), "w", encoding="utf-8") as f:
        f.write("0 сейчас: нынешний огонь (4 разных пламени, каждое по два тика)\n")
        for s in sorted(FIRE_STYLES):
            f.write("%d %s\n" % (s, FIRE_STYLES[s]["ru"]))
    print("compare: %s, %s, %s" % (gif, ugif, png))


def smoke(k, frame, density, seed):
    """A cloud over the tile: 4 looping frames per density (0 light, 1 medium, 2 heavy). The classic
    cloud fills the frame (x 1..31, y 1..39, centre about (15.5, 21))."""
    w, h = 32, 40
    xs, ys = grid(h, w, k)
    shape = (h * k, w * k)
    phase = frame * math.pi / 2
    rng = np.random.default_rng(seed + density * 13)
    n = fbm_loop(shape, 6.0 * k, seed + density * 31, phase, 4)
    n2 = fbm_loop(shape, 3.2 * k, seed + density * 31 + 9, phase + 0.7, 3)
    # puffs: a few overlapping balls, drifting a little with the frame
    cover = np.zeros(shape, dtype=np.float32)
    puffs = [(15.5, 22, 9.5), (10, 17, 6.5), (21, 16, 6.5), (13, 28, 6.0), (19, 27, 6.0), (15.5, 11, 5.5)]
    for i, (px, py, pr) in enumerate(puffs):
        dx = 0.8 * math.cos(phase + i * 1.7)
        dy = 0.6 * math.sin(phase + i * 1.1) - 0.5 * frame * 0.0
        r = pr * (0.9 + 0.2 * rng.random())
        cover = 1 - (1 - cover) * (1 - gauss(xs, ys, px + dx, py + dy, r * 0.62))
    edge = np.clip(cover * (0.62 + 0.55 * n), 0, 1)
    max_alpha = [0.42, 0.62, 0.82][density]
    alpha = smoothstep(0.08, 0.55, edge) * max_alpha
    # shading: lighter on top, darker below and inside the denser cloud
    light = 0.62 + 0.30 * np.clip((22 - ys) / 20, -1, 1) + 0.18 * n2
    grey = np.clip(150 + 75 * light - 25 * density, 60, 245)
    rgb = np.stack([grey * 1.0, grey * 1.0, grey * 1.02], axis=-1)
    return to_image(rgb, alpha)


def sparks(xs, ys, cx, cy, count, t, seed, speed=(1.3, 2.6), gravity=0.0, width=0.9, streak=0.7):
    """Spark particles flying out of (cx, cy) at frame t: brightness field 0..1."""
    rng = np.random.default_rng(seed)
    field = np.zeros(xs.shape, dtype=np.float32)
    for i in range(count):
        ang = rng.random() * 2 * math.pi
        sp = speed[0] + rng.random() * (speed[1] - speed[0])
        vx, vy = math.cos(ang) * sp, math.sin(ang) * sp * 0.8
        px, py = cx + vx * t, cy + vy * t + 0.5 * gravity * t * t
        qt = max(t - streak, 0.0)
        qx, qy = cx + vx * qt, cy + vy * qt + 0.5 * gravity * qt * qt
        # a short streak from q to p
        dx, dy = px - qx, py - qy
        ll = dx * dx + dy * dy + 1e-6
        tt = np.clip(((xs - qx) * dx + (ys - qy) * dy) / ll, 0, 1)
        dist2 = (xs - (qx + tt * dx)) ** 2 + (ys - (qy + tt * dy)) ** 2
        life = 1.0 - t / 10.0 * (0.7 + 0.6 * rng.random())
        field += np.exp(-dist2 / (2 * width * width)) * max(life, 0)
    return np.clip(field, 0, 1)


def hit_bullet(k, t, seed):
    """Frames 26-35: a white flash that bursts into blue sparks."""
    w, h = 32, 40
    xs, ys = grid(h, w, k)
    cx, cy = 15.5, 15.5
    flash = gauss(xs, ys, cx, cy, 2.6 * max(1 - t / 3.0, 0) + 0.3) * max(1 - t / 3.0, 0)
    glow = gauss(xs, ys, cx, cy, 5.5) * max(1 - t / 5.0, 0) * 0.5
    sp = sparks(xs, ys, cx, cy, 16, t, seed, speed=(1.2, 2.4), gravity=0.05, width=0.75)
    core = np.clip(flash * 1.6 + sp, 0, 1)
    # colour: white core, blue sparks
    rgb = ramp(core, [(0.0, (60, 110, 255)), (0.45, (130, 180, 255)), (0.8, (220, 235, 255)), (1.0, (255, 255, 255))])
    alpha = np.clip(core * 1.4 + glow, 0, 1)
    return to_image(rgb, alpha)


def hit_laser(k, t, seed):
    """Frames 36-45: a laser hit - a hot red-orange burst with straight sparks, gone quickly."""
    w, h = 32, 40
    xs, ys = grid(h, w, k)
    cx, cy = 15.0, 15.0
    shape = (h * k, w * k)
    n = fbm(shape, 3.0 * k, seed + t * 7, 3)
    r = 3.5 + 4.0 * min(t / 2.0, 1.0)
    burst = np.clip((1 - np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / r) * (1.1 + 0.5 * n) * 1.4, 0, 1)
    fade = max(1 - t / 5.0, 0) ** 0.9
    core = gauss(xs, ys, cx, cy, 2.2) * max(1 - t / 3.0, 0)
    sp = sparks(xs, ys, cx, cy, 12, t, seed + 1, speed=(1.6, 3.2), gravity=0.0, width=0.65, streak=1.2)
    heat = np.clip(burst * fade + core * 1.5 + sp * 0.95, 0, 1)
    rgb = ramp(heat ** 0.9, [(0.0, (120, 0, 0)), (0.3, (230, 40, 0)), (0.6, (255, 130, 20)), (0.85, (255, 220, 120)), (1.0, (255, 255, 230))])
    glow = gauss(xs, ys, cx, cy, 6.0) * fade * 0.35
    alpha = np.clip(smoothstep(0.04, 0.35, heat) + glow, 0, 1)
    return to_image(rgb, alpha)


def hit_plasma(k, t, seed):
    """Frames 46-55: a green flash and rings running out, sparse sparks at the end."""
    w, h = 32, 40
    xs, ys = grid(h, w, k)
    cx, cy = 15.5, 15.5
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    flash = gauss(xs, ys, cx, cy, 3.0) * max(1 - t / 3.0, 0)
    field = flash * 1.5
    for start, gain in ((0, 1.0), (3, 0.6)):
        if t >= start:
            rr = 1.5 + 1.25 * (t - start)
            ring = np.exp(-((d - rr) ** 2) / (2 * 0.9 ** 2)) * gain * max(1 - (t - start) / 8.0, 0)
            field += ring
    if t >= 4:
        field += sparks(xs, ys, cx, cy, 10, t - 3, seed, speed=(1.0, 2.0), gravity=0.0, width=0.6) * 0.8
    core = np.clip(field, 0, 1)
    rgb = ramp(core, [(0.0, (30, 140, 40)), (0.5, (90, 230, 100)), (0.85, (200, 255, 200)), (1.0, (245, 255, 245))])
    alpha = np.clip(core * 1.3, 0, 1)
    return to_image(rgb, alpha)


def melee_star(k, t, seed):
    """HIT.PCK 0-3: the yellow star of a melee hit, centred at (16.5, 24.8), fading."""
    w, h = 32, 40
    xs, ys = grid(h, w, k)
    cx, cy = 16.5, 24.8
    ang = np.arctan2(ys - cy, xs - cx)
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    outer = 10.0 + 2.0 * t
    inner = 4.0 + 0.8 * t
    # a 5-point star as a radius that swings between inner and outer with the angle
    star_r = inner + (outer - inner) * (0.5 + 0.5 * np.cos(5 * (ang + 0.3 * t))) ** 1.6
    inside = smoothstep(1.0, -1.0, d - star_r)
    core = gauss(xs, ys, cx, cy, 3.5 + 0.5 * t)
    fade = [1.0, 0.8, 0.55, 0.3][t]
    field = np.clip(inside * (0.35 + 0.65 * np.clip(1 - d / (outer + 1), 0, 1)) + core, 0, 1) * fade
    rgb = ramp(field, [(0.0, (200, 90, 10)), (0.4, (255, 190, 40)), (0.8, (255, 240, 130)), (1.0, (255, 255, 230))])
    alpha = np.clip(inside * fade * 0.95 + core * fade, 0, 1)
    return to_image(rgb, alpha)


def big_explosion(k, t, seed):
    """X1.PCK 0-7 (128x64): a fireball that bursts out of the ground point (62, 60), rises and
    turns to smoke; a ground flash and a faint shock ring in the first frames."""
    w, h = 128, 64
    xs, ys = grid(h, w, k)
    shape = (h * k, w * k)
    gx, gy = 62.0, 60.0
    n = fbm(shape, 9.0 * k, seed + t * 3, 4)
    n2 = fbm(shape, 4.0 * k, seed + 50 + t * 3, 3)
    rise = [0, 4, 9, 13, 16, 19, 22, 25][t]
    radius = [12, 19, 26, 31, 33, 34, 33, 30][t]
    cx, cy = gx, gy - 5 - rise
    d = np.sqrt((xs - cx) ** 2 + ((ys - cy) * 1.15) ** 2)
    edge = (1 - d / radius) + 0.35 * n
    ball = np.clip(edge * 1.4, 0, 1)
    # heat: bright and white first, then orange, then only the core glows through the smoke
    heat_gain = [1.8, 1.6, 1.35, 1.05, 0.7, 0.42, 0.22, 0.1][t]
    heat = np.clip((ball ** 1.2) * heat_gain * (0.85 + 0.35 * n2), 0, 1)
    smoke_gain = [0.0, 0.1, 0.35, 0.6, 0.85, 0.95, 0.9, 0.7][t]
    smoke_a = smoothstep(0.02, 0.5, ball) * smoke_gain
    rgb_fire = ramp(heat, FIRE_RAMP)
    grey = 55 + 60 * (0.5 + 0.5 * n2)
    rgb_smoke = np.stack([grey * 1.05, grey, grey * 0.95], axis=-1)
    rgb = rgb_fire * heat[..., None] + rgb_smoke * (1 - heat[..., None])
    alpha = np.clip(smoothstep(0.03, 0.35, heat) + smoke_a, 0, 1)
    # the ground flash: a flat ellipse of light at the base
    if t <= 2:
        flat = np.exp(-(((xs - gx) / (26 + 12 * t)) ** 2 + ((ys - gy) / 4.5) ** 2)) * (1.1 - t / 3.0)
        rgb = rgb * (1 - flat[..., None]) + np.array([255, 235, 170], dtype=np.float32) * flat[..., None]
        alpha = np.clip(alpha + flat * 0.9, 0, 1)
    # a shock ring
    if 1 <= t <= 3:
        rr = 14 + 18 * (t - 1)
        dd = np.sqrt((xs - gx) ** 2 + ((ys - gy) * 2.6) ** 2)
        ring = np.exp(-((dd - rr) ** 2) / (2 * 1.6 ** 2)) * (0.5 - 0.15 * (t - 1))
        rgb = rgb * (1 - ring[..., None]) + np.array([255, 240, 200], dtype=np.float32) * ring[..., None]
        alpha = np.clip(alpha + ring, 0, 1)
    # embers
    if t >= 2:
        sp = sparks(xs, ys, cx, cy + 4, 18, t - 1, seed + 9, speed=(1.5, 4.5), gravity=0.6, width=0.7, streak=0.6)
        rgb = rgb * (1 - sp[..., None]) + ramp(sp, FIRE_RAMP) * sp[..., None]
        alpha = np.clip(alpha + sp * 0.9, 0, 1)
    return to_image(rgb, alpha)


# ----------------------------------------------------------------------------- hits: the mark and the blood

def straighten(rgb, alpha):
    """Layers stacked with `over` are premultiplied by their alpha; the PNG wants plain colours."""
    return np.where(alpha[..., None] > 0.004, rgb / np.maximum(alpha, 0.004)[..., None], 0.0)


def blob(xs, ys, shapes):
    """A smooth silhouette out of ellipses: shapes = [(cx, cy, rx, ry, angle)]; > 0 inside."""
    field = np.full(xs.shape, -9.0, dtype=np.float32)
    for cx, cy, rx, ry, ang in shapes:
        ca, sa = math.cos(ang), math.sin(ang)
        px = (xs - cx) * ca + (ys - cy) * sa
        py = -(xs - cx) * sa + (ys - cy) * ca
        field = np.maximum(field, 1.0 - np.sqrt((px / rx) ** 2 + (py / ry) ** 2))
    return field


def blob_shaded(field, body, dark, light=(-0.7, -0.7), edge=0.16, k=4):
    """A blob painted like a game sprite: lit from the upper left, a dark outline along its edge.
    Returns (rgb, alpha) with alpha antialiased on the silhouette."""
    alpha = np.clip(field / (0.9 / k) + 0.5, 0, 1)
    gy, gx = np.gradient(field)
    norm = np.sqrt(gx ** 2 + gy ** 2) + 1e-6
    lit = np.clip((-gx / norm) * light[0] + (-gy / norm) * light[1], -1, 1)
    shade = 0.72 + 0.42 * np.clip(lit, 0, 1) - 0.25 * np.clip(-lit, 0, 1)
    rgb = np.asarray(body, np.float32)[None, None, :] * shade[..., None]
    rim = np.clip(1.0 - field / edge, 0, 1) ** 1.5 * (alpha > 0.02)
    rgb = rgb * (1 - rim[..., None]) + np.asarray(dark, np.float32)[None, None, :] * rim[..., None]
    return rgb, alpha


def burst_field(xs, ys, cx, cy, radius, spikes, turn=0.0, thin=1.6):
    """A star-shaped flash of light around (cx, cy): `spikes` rays out to `radius`."""
    ang = np.arctan2(ys - cy, xs - cx)
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    r = radius * (0.35 + 0.65 * (0.5 + 0.5 * np.cos(spikes * (ang + turn))) ** thin)
    return np.clip((1.0 - d / np.maximum(r, 0.1)) * 1.6, 0, 1)


def punch_parts(cx, cy, u, reach, size, glove):
    """The ellipses of a punch whose knuckles are `reach` px short of (cx, cy), coming in along the unit
    vector `u`: {"arm": the sleeve, "hand": the fist or glove, "cuff": the glove's white band}."""
    ux, uy = u
    px, py = -uy, ux                      # across the punch (positive = the lower side)
    ang = math.atan2(uy, ux)
    fx, fy = cx - ux * reach, cy - uy * reach
    parts = {"arm": [], "hand": [], "cuff": []}

    def at(part, along, across, rx, ry):
        parts[part].append((fx - ux * along * size + px * across * size, fy - uy * along * size + py * across * size,
                            rx * size, ry * size, ang))
    if glove:
        at("hand", 3.6, 0.0, 5.0, 4.8)    # the round head
        at("hand", 5.6, -3.0, 2.2, 2.0)   # the thumb, on the upper side
        at("cuff", 9.2, 0.1, 2.4, 3.4)    # the white band
        at("arm", 12.8, 0.2, 3.4, 3.0)    # the sleeve
    else:
        for i in range(4):                # the knuckles, across the front
            at("hand", 0.7, (i - 1.5) * 1.65, 1.5, 1.8)
        at("hand", 4.8, 0.0, 5.2, 5.0)    # the back of the hand
        at("hand", 2.9, -3.8, 2.1, 1.8)   # the thumb
        at("arm", 10.6, 0.1, 3.0, 2.7)    # the wrist
        at("arm", 14.0, 0.2, 3.7, 3.4)    # the sleeve
    return parts


MELEE_STYLES = {
    1: {"name": "star", "ru": "звезда: как сейчас"},
    2: {"name": "fist", "ru": "кулак: удар из-за левого плеча"},
    3: {"name": "glove", "ru": "боксёрская перчатка (рисованная)"},
    4: {"name": "impact", "ru": "удар: вспышка с лучами и волной"},
    5: {"name": "slash", "ru": "росчерк: два скрещённых разреза"},
    6: {"name": "glovepic", "ru": "боксёрская перчатка из картинки (--glove 1..10)"},
}
# where the cut-out gloves of style 6 live (cut_gloves.py made them out of the sheet of ten)
GLOVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gloves")
GLOVE_COLOURS = {1: "красная", 2: "синяя", 3: "чёрная", 4: "белая с золотом", 5: "жёлтая",
                 6: "зелёная (шнуровка)", 7: "фиолетовая", 8: "оранжевая", 9: "розовая", 10: "коричневая кожа"}
GLOVE_COLOURS_EN = {1: "red", 2: "blue", 3: "black", 4: "white-gold", 5: "yellow",
                    6: "green laced", 7: "purple", 8: "orange", 9: "pink", 10: "leather"}
GLOVE_LENGTH = 16.0     # the glove's length in classic pixels (the frame is 32x40, so it fits at the hit)
GLOVE_TURN = -107.0     # the picture punches upwards; this turns it along the punch


def glove_sprite(k, glove, size, glove_dir=None):
    """The cut-out glove `glove` (1..10), scaled `size` and turned along the punch. Returns the picture
    and the place of its knuckles in it."""
    path = os.path.join(glove_dir or GLOVE_DIR, "%02d.png" % glove)
    if not os.path.exists(path):
        raise SystemExit("no glove picture %s - put the cut-out gloves 01.png..10.png there "
                         "(cut_gloves.py makes them out of a sheet of gloves)" % path)
    im = Image.open(path).convert("RGBA")
    h = max(4, int(round(GLOVE_LENGTH * k * size)))
    im = im.resize((max(1, int(round(im.width * h / im.height))), h), Image.LANCZOS)
    pad = Image.new("RGBA", (im.width + 2 * h, im.height + 2 * h), (0, 0, 0, 0))
    pad.alpha_composite(im, (h, h))
    a = np.asarray(pad)[:, :, 3].astype(np.float32)
    ys, xs = np.nonzero(a > 40)
    top = ys.min()
    band = (ys >= top) & (ys <= top + max(2, h // 12))
    tip = (float(xs[band].mean()), float(top))          # the knuckles: the middle of the top edge
    turned = pad.rotate(GLOVE_TURN, resample=Image.BICUBIC, center=tip)
    return turned, tip

BULLET_STYLES = {
    1: {"name": "spark", "ru": "искры: белые и жёлтые (как сейчас, но без синего)"},
    2: {"name": "dust", "ru": "пыль и осколки: вспышка, облачко пыли, мелкие обломки"},
    3: {"name": "flash", "ru": "короткая вспышка: почти без частиц, гаснет быстро"},
    4: {"name": "ricochet", "ru": "рикошет: пучок искр в сторону и пыль"},
}


def melee_hit(k, t, seed, style=1, blood=False, glove=1, glove_dir=None):
    """HIT.PCK 0-3: the mark of a melee hit at (16.5, 24.8). `blood` adds the spray the engine draws
    when the hit landed on a unit."""
    if style == 1 and not blood:
        return melee_star(k, t, seed)
    w, h = 32, 40
    xs, ys = grid(h, w, k)
    cx, cy = 16.5, 24.8
    rgb = np.zeros(xs.shape + (3,), np.float32)
    alpha = np.zeros(xs.shape, np.float32)

    def over(new_rgb, new_a):
        nonlocal rgb, alpha
        rgb = new_rgb * new_a[..., None] + rgb * (1 - new_a)[..., None]
        alpha = np.clip(new_a + alpha * (1 - new_a), 0, 1)

    def light(field, stops):
        over(ramp(np.clip(field, 0, 1), stops), np.clip(field * 1.35, 0, 1))
    name = MELEE_STYLES[style]["name"] if style in MELEE_STYLES else "star"
    if name == "star":
        im = np.asarray(melee_star(k, t, seed)).astype(np.float32) / 255.0
        over(im[:, :, :3] * 255.0, im[:, :, 3])
    elif name in ("fist", "glove"):
        u = (0.96, 0.29)
        reach = [5.5, 0.0, 2.6, 7.0][t]
        size = [1.0, 1.14, 1.10, 1.0][t]
        fade = [0.85, 1.0, 0.9, 0.0][t]
        if name == "glove":
            body, dark = (205, 45, 45), (70, 12, 12)
        else:
            body, dark = (226, 182, 148), (64, 34, 24)
        if t >= 1:
            # the flash of the blow, behind the fist
            light(burst_field(xs, ys, cx, cy, [0, 9.5, 12.5, 14.0][t], 8, 0.25 * t) * [0, 1.0, 0.6, 0.25][t],
                  [(0.0, (190, 90, 15)), (0.45, (255, 190, 45)), (0.85, (255, 240, 150)), (1.0, (255, 255, 235))])
        if fade > 0:
            parts = punch_parts(cx, cy, u, reach, size, name == "glove")
            if t == 0:
                # a motion streak behind the punch
                back = punch_parts(cx, cy, u, reach + 4.0, size * 0.92, name == "glove")
                streak_a = np.clip(blob(xs, ys, back["hand"]) / (0.9 / k) + 0.5, 0, 1) * 0.3
                over(np.asarray(dark, np.float32)[None, None, :] * 1.5, streak_a)
            for shapes, col, col_dark in ((parts["arm"], (78, 84, 98), (26, 28, 36)),
                                          (parts["cuff"], (226, 226, 231), (92, 92, 98)),
                                          (parts["hand"], body, dark)):
                if not shapes:
                    continue
                part_rgb, part_a = blob_shaded(blob(xs, ys, shapes), col, col_dark, k=k)
                over(part_rgb, part_a * fade)
    elif name == "glovepic":
        u = (0.96, 0.29)
        reach = [4.0, 0.0, 2.2, 6.0][t]
        size = [1.0, 1.1, 1.06, 1.0][t]
        fade = [0.85, 1.0, 0.9, 0.0][t]
        if t >= 1:
            light(burst_field(xs, ys, cx, cy, [0, 9.5, 12.5, 14.0][t], 8, 0.25 * t) * [0, 1.0, 0.6, 0.25][t],
                  [(0.0, (190, 90, 15)), (0.45, (255, 190, 45)), (0.85, (255, 240, 150)), (1.0, (255, 255, 235))])
        if fade > 0:
            pic, tip = glove_sprite(k, glove, size, glove_dir)
            canvas = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
            px = int(round((cx - u[0] * reach) * k - tip[0]))
            py = int(round((cy - u[1] * reach) * k - tip[1]))
            canvas.alpha_composite(pic, (px, py))
            arr = np.asarray(canvas).astype(np.float32)
            over(arr[:, :, :3], arr[:, :, 3] / 255.0 * fade)
    elif name == "impact":
        r = [5.0, 11.0, 14.5, 17.0][t]
        gain = [0.9, 1.0, 0.6, 0.28][t]
        light(burst_field(xs, ys, cx, cy, r, 9, 0.2 * t, 2.0) * gain,
              [(0.0, (180, 70, 10)), (0.4, (255, 175, 40)), (0.8, (255, 235, 140)), (1.0, (255, 255, 240))])
        d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
        if t >= 1:
            ring = np.exp(-((d - r * 0.85) ** 2) / (2 * 0.8 ** 2)) * gain * 0.8
            light(ring, [(0.0, (255, 210, 120)), (1.0, (255, 255, 240))])
    else:  # slash
        ang0 = -0.5
        gain = [1.0, 0.95, 0.6, 0.25][t]
        length = [7.0, 11.0, 12.5, 13.0][t]
        for n, a in enumerate((ang0, ang0 + 1.5)):
            ca, sa = math.cos(a), math.sin(a)
            px = (xs - cx) * ca + (ys - cy) * sa
            py = -(xs - cx) * sa + (ys - cy) * ca
            bend = py - 0.035 * px * px + 1.2 * n - 0.6
            core = np.exp(-(bend ** 2) / (2 * (0.55 + 0.25 * t) ** 2)) * np.clip(1 - np.abs(px) / length, 0, 1) ** 0.7
            light(core * gain, [(0.0, (170, 40, 20)), (0.4, (255, 140, 60)), (0.85, (255, 235, 170)), (1.0, (255, 255, 245))])
    if blood:
        b_rgb, b_a = blood_spray(xs, ys, cx, cy - 1.0, t / 3.0, seed + 91, k, count=16, spread=(1.4, 3.6))
        over(b_rgb, b_a)
    return to_image(np.clip(straighten(rgb, alpha), 0, 255), alpha)


def bullet_hit(k, t, seed, style=1, blood=False):
    """SMOKE.PCK 26-35: the mark of a bullet hit at (15.5, 15.5), ten frames. `blood` adds the spray
    the engine draws when the hit landed on a unit."""
    w, h = 32, 40
    xs, ys = grid(h, w, k)
    shape = (h * k, w * k)
    cx, cy = 15.5, 15.5
    rgb = np.zeros(xs.shape + (3,), np.float32)
    alpha = np.zeros(xs.shape, np.float32)

    def over(new_rgb, new_a):
        nonlocal rgb, alpha
        rgb = new_rgb * new_a[..., None] + rgb * (1 - new_a)[..., None]
        alpha = np.clip(new_a + alpha * (1 - new_a), 0, 1)
    name = BULLET_STYLES[style]["name"] if style in BULLET_STYLES else "spark"
    flash = gauss(xs, ys, cx, cy, 1.15 + 0.55 * t) * max(1 - t / 2.2, 0)
    glow = gauss(xs, ys, cx, cy, 3.6) * max(1 - t / 3.0, 0) * 0.3
    if name == "spark":
        sp = sparks(xs, ys, cx, cy, 22, t, seed, speed=(1.0, 2.6), gravity=0.08, width=0.42, streak=0.5)
        core = np.clip(flash * 1.8 + sp, 0, 1)
        over(ramp(core, [(0.0, (180, 60, 0)), (0.4, (255, 170, 40)), (0.8, (255, 240, 160)), (1.0, (255, 255, 240))]),
             np.clip(core * 1.4 + glow * 0.8, 0, 1))
    elif name == "dust":
        n = fbm(shape, 4.0 * k, seed + 5, 3)
        puff_r = 2.0 + 1.15 * t
        d = np.sqrt((xs - cx) ** 2 + ((ys - (cy - 0.35 * t)) * 1.1) ** 2)
        puff = np.clip((1 - d / puff_r) * (1.05 + 0.5 * n) * 1.5, 0, 1) * max(1 - t / 7.0, 0) ** 1.1
        grey = 155 + 60 * (0.5 + 0.5 * n)
        over(np.stack([grey * 1.02, grey * 0.99, grey * 0.94], axis=-1), np.clip(puff * 0.9, 0, 1))
        chips = sparks(xs, ys, cx, cy, 11, t, seed + 2, speed=(0.9, 2.2), gravity=0.2, width=0.36, streak=0.18)
        over(ramp(np.clip(chips, 0, 1), [(0.0, (60, 52, 44)), (0.6, (150, 132, 108)), (1.0, (205, 190, 165))]),
             np.clip(chips * 1.7, 0, 1))
        core = np.clip(flash * 1.6, 0, 1)
        over(ramp(core, [(0.0, (200, 120, 30)), (0.6, (255, 215, 120)), (1.0, (255, 255, 240))]), np.clip(core * 1.3, 0, 1))
    elif name == "flash":
        f = max(1 - t / 3.2, 0)
        core = np.clip(gauss(xs, ys, cx, cy, 1.2 + 1.1 * t) * f * 1.8, 0, 1)
        sp = sparks(xs, ys, cx, cy, 6, t, seed + 3, speed=(1.0, 2.0), gravity=0.12, width=0.38, streak=0.4) * f
        core = np.clip(core + sp, 0, 1)
        over(ramp(core, [(0.0, (190, 80, 10)), (0.5, (255, 200, 90)), (1.0, (255, 255, 245))]),
             np.clip(core * 1.3 + glow * f, 0, 1))
    else:  # ricochet
        rng = np.random.default_rng(seed + 11)
        base_ang = -1.05
        field = np.zeros(xs.shape, np.float32)
        for i in range(12):
            a = base_ang + rng.normal(0, 0.28)
            sp = 1.1 + rng.random() * 2.2
            vx, vy = math.cos(a) * sp, math.sin(a) * sp
            px, py = cx + vx * t, cy + vy * t + 0.5 * 0.12 * t * t
            qx, qy = cx + vx * (t - 1.1), cy + vy * (t - 1.1)
            dx, dy = px - qx, py - qy
            ll = dx * dx + dy * dy + 1e-6
            tt = np.clip(((xs - qx) * dx + (ys - qy) * dy) / ll, 0, 1)
            dist2 = (xs - (qx + tt * dx)) ** 2 + (ys - (qy + tt * dy)) ** 2
            field += np.exp(-dist2 / (2 * 0.42 ** 2)) * max(1 - t / 9.0, 0)
        dust = gauss(xs, ys, cx, cy + 0.2 * t, 2.0 + 0.7 * t) * max(1 - t / 6.0, 0) * 0.6
        over(np.stack([np.full(xs.shape, 160.0)] * 3, axis=-1) * np.array([1.02, 0.99, 0.93]), np.clip(dust * 0.8, 0, 1))
        core = np.clip(field + flash * 1.6, 0, 1)
        over(ramp(core, [(0.0, (190, 70, 0)), (0.45, (255, 180, 50)), (0.85, (255, 245, 180)), (1.0, (255, 255, 245))]),
             np.clip(core * 1.45, 0, 1))
    if blood and t > 0:
        b_rgb, b_a = blood_spray(xs, ys, cx, cy, (t - 1) / 8.0, seed + 71, k, count=20, spread=(1.5, 4.0))
        over(b_rgb, b_a)
    return to_image(np.clip(straighten(rgb, alpha), 0, 255), alpha)


def blood_spray(xs, ys, cx, cy, life, seed, k, count=16, spread=(1.2, 3.4)):
    """Blood at a hit: small drops and a few longer streaks flying out and falling, over a thin red
    mist. `life` runs 0..1 over the animation. Returns (rgb, alpha)."""
    rng = np.random.default_rng(seed)
    t = life * 6.0
    drops = np.zeros(xs.shape, np.float32)
    for i in range(count + 4):
        long_one = i >= count           # a few drops fly far and leave a streak
        ang = rng.random() * 2 * math.pi
        sp = (spread[0] + rng.random() ** 1.7 * (spread[1] - spread[0])) * (1.7 if long_one else 1.0)
        vx, vy = math.cos(ang) * sp, math.sin(ang) * sp * 0.7
        fall = 0.5
        px, py = cx + vx * t, cy + vy * t + 0.5 * fall * t * t
        r = (0.34 + 0.3 * rng.random()) * (1.0 - 0.3 * life) * (0.8 if long_one else 1.0)
        tail = 1.0 if long_one else 0.1
        # the streak behind a drop follows its own arc (its fall counts too, or the drop smears down)
        qt = max(t - tail, 0.0)
        qx, qy = cx + vx * qt, cy + vy * qt + 0.5 * fall * qt * qt
        dx, dy = px - qx, py - qy
        ll = dx * dx + dy * dy + 1e-6
        tt = np.clip(((xs - qx) * dx + (ys - qy) * dy) / ll, 0, 1)
        dist2 = (xs - (qx + tt * dx)) ** 2 + (ys - (qy + tt * dy)) ** 2
        drops = np.maximum(drops, np.clip(1.0 - dist2 / (r * r), 0, 1))
    mist = gauss(xs, ys, cx, cy + 0.5 * t, 2.2 + 2.4 * life) * max(1 - life * 1.5, 0) * 0.7
    # the splash at the wound itself: a ragged patch, strongest at once, then gone
    lobes = np.zeros(xs.shape, np.float32)
    for i in range(7):
        a = rng.random() * 2 * math.pi
        rr = (0.9 + 1.5 * rng.random()) * (1.0 + 0.8 * life)
        lx, ly = cx + math.cos(a) * (0.5 + 1.4 * life) * 1.6, cy + math.sin(a) * (0.5 + 1.4 * life) * 1.2
        lobes = np.maximum(lobes, np.clip(1.0 - ((xs - lx) ** 2 + ((ys - ly) * 1.15) ** 2) / (rr * rr), 0, 1))
    splash = lobes * max(1 - life * 1.25, 0) ** 0.8
    body = np.clip(drops * 1.4 + splash * 1.2, 0, 1)
    field = np.clip(body + mist * 0.7, 0, 1)
    rgb = ramp(field, [(0.0, (44, 4, 6)), (0.45, (115, 10, 12)), (0.8, (175, 24, 22)), (1.0, (220, 66, 56))])
    alpha = np.clip(body * (1.0 - 0.3 * life) + mist * 0.4, 0, 1)
    return rgb, alpha


def hit_compare(out_dir, k, seed, glove=1, glove_dir=None):
    """Every melee and bullet style, on a wall and on a unit (with the blood the engine adds): animated
    GIFs at game speed and sheets of every frame; with the glove pictures also every glove colour."""
    from PIL import ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    font, cyrillic = label_font()
    cw, ch = 32 * k, 40 * k
    out = []
    for what, styles, frames, maker in (("melee", MELEE_STYLES, 4, melee_hit), ("bullet", BULLET_STYLES, 10, bullet_hit)):
        keys = sorted(styles)
        pics = {}
        for st in keys:
            for b in (False, True):
                for t in range(frames):
                    pics[(st, b, t)] = (maker(k, t, seed + 3, st, b, glove, glove_dir)
                                        if what == "melee" else maker(k, t, seed + 3, st, b))
        label_h = 20
        head = Image.new("RGB", (cw * len(keys), label_h), (0, 0, 0))
        d = ImageDraw.Draw(head)
        for n, st in enumerate(keys):
            d.text((n * cw + 6, 3), "%d %s" % (st, styles[st]["name"]), fill=(255, 255, 255), font=font)
        gif = []
        for t in range(frames):
            sheet = Image.new("RGB", (cw * len(keys), label_h + ch * 2), (30, 30, 34))
            sheet.paste(head, (0, 0))
            for n, st in enumerate(keys):
                for row, b in enumerate((False, True)):
                    cell = Image.new("RGBA", (cw, ch), (78, 74, 70, 255) if row == 0 else (96, 104, 120, 255))
                    cell.alpha_composite(pics[(st, b, t)])
                    sheet.paste(cell.convert("RGB"), (n * cw, label_h + row * ch))
            gif.append(sheet)
        path = os.path.join(out_dir, "%s_styles.gif" % what)
        gif[0].save(path, save_all=True, append_images=gif[1:], duration=110 if what == "melee" else 70, loop=0)
        out.append(path)
        # a sheet: every frame of every style, the wall row and the unit row
        sheet = Image.new("RGB", (cw * frames, (label_h + ch * 2) * len(keys)), (30, 30, 34))
        d = ImageDraw.Draw(sheet)
        for n, st in enumerate(keys):
            y = n * (label_h + ch * 2)
            d.text((6, y + 3), "%d %s%s" % (st, styles[st]["name"], " - " + styles[st]["ru"] if cyrillic else ""),
                   fill=(255, 255, 0), font=font)
            for t in range(frames):
                for row, b in enumerate((False, True)):
                    cell = Image.new("RGBA", (cw, ch), (78, 74, 70, 255) if row == 0 else (96, 104, 120, 255))
                    cell.alpha_composite(pics[(st, b, t)])
                    sheet.paste(cell.convert("RGB"), (t * cw, y + label_h + row * ch))
        path = os.path.join(out_dir, "%s_styles.png" % what)
        sheet.save(path)
        out.append(path)
    # the ten glove colours in the punch, if their pictures are there
    if os.path.exists(os.path.join(glove_dir or GLOVE_DIR, "01.png")):
        colours = sorted(GLOVE_COLOURS)
        pics = {(g, t): melee_hit(k, t, seed + 3, 6, False, g, glove_dir) for g in colours for t in range(4)}
        head = Image.new("RGB", (cw * len(colours), 20), (0, 0, 0))
        d = ImageDraw.Draw(head)
        for n, g in enumerate(colours):
            d.text((n * cw + 6, 3), "%d" % g, fill=(255, 255, 255), font=font)
        gif = []
        for t in range(4):
            sheet = Image.new("RGB", (cw * len(colours), 20 + ch), (30, 30, 34))
            sheet.paste(head, (0, 0))
            for n, g in enumerate(colours):
                cell = Image.new("RGBA", (cw, ch), (78, 74, 70, 255))
                cell.alpha_composite(pics[(g, t)])
                sheet.paste(cell.convert("RGB"), (n * cw, 20))
            gif.append(sheet)
        path = os.path.join(out_dir, "glove_colours.gif")
        gif[0].save(path, save_all=True, append_images=gif[1:], duration=110, loop=0)
        out.append(path)
        sheet = Image.new("RGB", (cw * 4, (20 + ch) * len(colours)), (30, 30, 34))
        d = ImageDraw.Draw(sheet)
        for n, g in enumerate(colours):
            y = n * (20 + ch)
            d.text((6, y + 3), "--glove %d: %s" % (g, GLOVE_COLOURS[g] if cyrillic else GLOVE_COLOURS_EN[g]),
                   fill=(255, 255, 0), font=font)
            for t in range(4):
                cell = Image.new("RGBA", (cw, ch), (78, 74, 70, 255))
                cell.alpha_composite(pics[(g, t)])
                sheet.paste(cell.convert("RGB"), (t * cw, y + 20))
        path = os.path.join(out_dir, "glove_colours.png")
        sheet.save(path)
        out.append(path)
    with open(os.path.join(out_dir, "hit_styles.txt"), "w", encoding="utf-8") as f:
        f.write("--melee-style (HIT.PCK 0-3):\n")
        for st in sorted(MELEE_STYLES):
            f.write("%d %s\n" % (st, MELEE_STYLES[st]["ru"]))
        f.write("\n--glove (with --melee-style 6):\n")
        for g in sorted(GLOVE_COLOURS):
            f.write("%d %s\n" % (g, GLOVE_COLOURS[g]))
        f.write("\n--bullet-style (SMOKE.PCK 26-35):\n")
        for st in sorted(BULLET_STYLES):
            f.write("%d %s\n" % (st, BULLET_STYLES[st]["ru"]))
    out.append(os.path.join(out_dir, "hit_styles.txt"))
    print("compare:", ", ".join(out))


# ----------------------------------------------------------------------------- packs

def write_frames(frames, tweens, smoke_dir, hit_dir, x1_dir, fire_only=False):
    """Writes <i>.png for every frame and <i>.v1.png for every second picture (the fire's in-between
    phase, a hit's blood); a frame written without one loses the .v1.png it had."""
    dirs = {"SMOKE": smoke_dir, "HIT": hit_dir, "X1": x1_dir}
    for key, im in frames.items():
        setn, i = key
        im.save(os.path.join(dirs[setn], "%d.png" % i))
        if fire_only and setn == "SMOKE" and i > 7:
            continue
        path = os.path.join(dirs[setn], "%d.v1.png" % i)
        if key in tweens:
            tweens[key].save(path)
        elif os.path.exists(path):
            os.remove(path)


def build(mod, k, seed, preview, fire_style=1, only_fire=False, melee_style=1, bullet_style=1, blood=True,
          only_hits=False, glove=1, glove_dir=None):
    smoke_dir = os.path.join(mod, "hd", "SMOKE.PCK")
    hit_dir = os.path.join(mod, "hd", "HIT.PCK")
    x1_dir = os.path.join(mod, "hd", "X1.PCK")
    for d in (smoke_dir, hit_dir, x1_dir):
        os.makedirs(d, exist_ok=True)
    frames = {}
    tweens = {}   # frame -> its <i>.v1.png (the fire's in-between picture, a hit's blood)
    if only_hits:
        for t in range(10):
            frames[("SMOKE", 26 + t)] = bullet_hit(k, t, seed + 3, bullet_style)
            if blood:
                tweens[("SMOKE", 26 + t)] = bullet_hit(k, t, seed + 3, bullet_style, True)
        for t in range(4):
            frames[("HIT", t)] = melee_hit(k, t, seed + 6, melee_style, False, glove, glove_dir)
            if blood:
                tweens[("HIT", t)] = melee_hit(k, t, seed + 6, melee_style, True, glove, glove_dir)
        write_frames(frames, tweens, smoke_dir, hit_dir, x1_dir)
        print("HIT.PCK: melee style %d, SMOKE.PCK: bullet style %d, frames 26-35%s -> %s" % (
            melee_style, bullet_style, " + blood in <i>.v1.png" if blood else " (no blood)", os.path.join(mod, "hd")))
        return
    for f in range(4):
        if fire_style == 0:
            frames[("SMOKE", f)] = fire(k, f, True, seed)
            frames[("SMOKE", 4 + f)] = fire(k, f, False, seed + 1)
        else:
            # eight phases of one looping flame: the frame and its in-between picture (<i>.v1.png, drawn
            # by the engine on the odd animation tick)
            frames[("SMOKE", f)] = fire_loop(k, (2 * f) / 8.0, True, seed, fire_style)
            tweens[("SMOKE", f)] = fire_loop(k, (2 * f + 1) / 8.0, True, seed, fire_style)
            frames[("SMOKE", 4 + f)] = fire_loop(k, (2 * f) / 8.0, False, seed + 1, fire_style)
            tweens[("SMOKE", 4 + f)] = fire_loop(k, (2 * f + 1) / 8.0, False, seed + 1, fire_style)
        if only_fire:
            continue
        for density in range(3):
            frames[("SMOKE", 8 + density * 4 + f)] = smoke(k, f, density, seed + 2)
    if only_fire:
        write_frames(frames, tweens, smoke_dir, hit_dir, x1_dir, fire_only=True)
        print("SMOKE.PCK: fire style %d, frames 0-7%s -> %s" % (fire_style, " + 0-7.v1" if tweens else "", smoke_dir))
        return
    for t in range(10):
        frames[("SMOKE", 26 + t)] = bullet_hit(k, t, seed + 3, bullet_style)
        if blood:
            tweens[("SMOKE", 26 + t)] = bullet_hit(k, t, seed + 3, bullet_style, True)
        frames[("SMOKE", 36 + t)] = hit_laser(k, t, seed + 4)
        frames[("SMOKE", 46 + t)] = hit_plasma(k, t, seed + 5)
    for t in range(4):
        frames[("HIT", t)] = melee_hit(k, t, seed + 6, melee_style, False, glove, glove_dir)
        if blood:
            tweens[("HIT", t)] = melee_hit(k, t, seed + 6, melee_style, True, glove, glove_dir)
    for t in range(8):
        frames[("X1", t)] = big_explosion(k, t, seed + 7)
    write_frames(frames, tweens, smoke_dir, hit_dir, x1_dir)
    print("SMOKE.PCK: %d frames (fire style %d, bullet style %d), HIT.PCK: 4 (melee style %d), X1.PCK: 8 -> %s" % (
        sum(1 for s, _ in frames if s == "SMOKE"), fire_style, bullet_style, melee_style, os.path.join(mod, "hd")))
    if preview:
        # every frame over a dark green ground, 8 per row, the big explosion below
        cw, ch = 32 * k, 40 * k
        rows = 7
        sheet = Image.new("RGBA", (8 * cw, rows * ch + 64 * k * 4), (40, 70, 40, 255))
        order = [("SMOKE", i) for i in range(20)] + [("SMOKE", i) for i in range(26, 56)] + [("HIT", i) for i in range(4)]
        for n, key in enumerate(order):
            sheet.alpha_composite(frames[key], ((n % 8) * cw, (n // 8) * ch))
        for t in range(8):
            sheet.alpha_composite(frames[("X1", t)], ((t % 2) * 128 * k, rows * ch + (t // 2) * 64 * k))
        sheet.save(preview)
        print("preview:", preview)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mod", default="", help="mod folder to write hd/SMOKE.PCK, hd/HIT.PCK, hd/X1.PCK into")
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--preview", default="", help="write a sheet of every frame to this PNG")
    ap.add_argument("--fire-style", type=int, default=1, choices=[0] + sorted(FIRE_STYLES),
                    help="the fire: 1-10 = a looping flame in 8 phases (see --fire-compare), 0 = the old 4 separate flames")
    ap.add_argument("--fire-compare", default="", help="write fire_styles.gif / fire_styles_unit.gif / fire_styles.png "
                    "(every style next to the current fire) into this folder and stop")
    ap.add_argument("--only-fire", action="store_true", help="write only the fire frames (0-7 and their in-between pictures)")
    ap.add_argument("--melee-style", type=int, default=1, choices=sorted(MELEE_STYLES),
                    help="the mark of a melee hit, HIT.PCK 0-3 (see --hit-compare): 1 the star as it is, 2 a fist, "
                         "3 a drawn boxing glove, 4 a burst of light, 5 a slash, 6 a boxing glove out of a picture")
    ap.add_argument("--glove", type=int, default=1, choices=sorted(GLOVE_COLOURS),
                    help="which glove picture style 6 uses (1 red, 2 blue, 3 black, 4 white-gold, 5 yellow, "
                         "6 green, 7 purple, 8 orange, 9 pink, 10 leather)")
    ap.add_argument("--glove-dir", default="", help="folder with the cut-out gloves 01.png..10.png (default tools/hdart/gloves)")
    ap.add_argument("--bullet-style", type=int, default=1, choices=sorted(BULLET_STYLES),
                    help="the mark of a bullet hit, SMOKE.PCK 26-35: 1 sparks, 2 dust and chips, 3 a short flash, 4 a ricochet")
    ap.add_argument("--no-blood", action="store_true", help="no blood: a hit on a unit looks the same as a hit on a wall")
    ap.add_argument("--hit-compare", default="", help="write melee_styles.gif / .png, bullet_styles.gif / .png "
                    "(every style on a wall and on a unit) into this folder and stop")
    ap.add_argument("--only-hits", action="store_true", help="write only the hit frames (HIT.PCK and SMOKE.PCK 26-35 with their blood)")
    args = ap.parse_args()
    if args.fire_compare:
        fire_compare(args.fire_compare, args.scale, args.seed)
        return 0
    if args.hit_compare:
        hit_compare(args.hit_compare, args.scale, args.seed, args.glove, args.glove_dir or None)
        return 0
    if not args.mod:
        ap.error("--mod is required (or --fire-compare / --hit-compare)")
    if args.only_fire and args.only_hits:
        ap.error("--only-fire and --only-hits are different jobs: run them one at a time")
    build(args.mod, args.scale, args.seed, args.preview, args.fire_style, args.only_fire,
          args.melee_style, args.bullet_style, not args.no_blood, args.only_hits, args.glove, args.glove_dir or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
