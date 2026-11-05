#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000512: яйцо на земле FLOOROB 1405 - читается как яйцо (заострённый конец, тонкая обводка, тень, блик), без видеокарты.

Тело - тело вращения с профилем яйца (тупой конец слева, острый справа-вверх), лежит на боку вдоль оси клетки;
освещение сверху слева: свет-тень, мягкий блик, тёмная кромка по нормали. Цвет и крапинка - инвентарное яйцо
BIGOBS 3050 (Resources/Mutant_Egg.png, палитра Пираток): беж/светлый тон, голубые и золотистые крапинки.
Рисуется со сверхвыборкой x6 и сводится по площади: контур ровный, без лесенки (правило 12). Собственная тень -
мягкая, под яйцом, правее и ниже, без обводки. Положение на полу как у стоящего: центр (62,136), низ яйца у y=150.

    py -3.13 egg_build.py            # заготовка art/tickets/egg_1405/1405.png
    py -3.13 egg_build.py --sheet    # лист census/tickets/XP-000512/sheet_new.png
    py -3.13 egg_build.py --yes      # в обе копии мода через манифест (только по слову Vitali, под очередью правок)
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hb_common as hc                  # noqa: E402
import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402
from scipy import ndimage               # noqa: E402

import build_hd_pack as bp              # noqa: E402
import water_build as wb                # noqa: E402

OUT = os.path.join("art", "tickets", "egg_1405")
SHEET = os.path.join("census", "tickets", "XP-000512", "sheet_new.png")
INV = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Resources", "Mutant_Egg.png")
FLOOR = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Resources", "FLOOROB", "Floor_Mutant_Egg.png")
NOW = os.path.join(hc.TERRAIN, "..", "FLOOROB.PCK", "1405.png")
WORD = "XP-000512, яйцо FLOOROB 1405: заострённый конец, тонкая обводка, тень, блик (Vitali, вариант по листу)"
SS = 6
CX, CY = 62.0, 136.0
LEN, RAD = 36.0, 11.0          # длина и наибольший радиус, пикселей кадра 128x160
ANG = np.radians(15.0)         # ось вправо-вверх
P = dict(pt=0.68, bl=0.50, rim=1.9, spec=0.40, amb=0.50)


def inv_colors():
    """Цвета инвентарного яйца по палитре Пираток: светлая основа, голубая и золотистая крапинки."""
    pal = np.asarray(wb.palette())
    ix = np.asarray(Image.open(INV))
    m = ix != 0
    rgb = pal[ix][..., :3].astype(np.float32)
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    body = rgb[m & (lum > 150) & (rgb[..., 2] - rgb[..., 0] < 12)]
    blue = rgb[m & (rgb[..., 2] - rgb[..., 0] > 12)]
    gold = rgb[m & (rgb[..., 0] - rgb[..., 2] > 60)]
    return body.mean(0), blue.mean(0), (gold.mean(0) if len(gold) else np.array([180, 140, 70.0]))


def profile():
    t = np.linspace(-1, 1, 2001)
    p = np.where(t < 0, 0.5, 0.5 + (P["pt"] - 0.5) * np.clip(t * 1.6, 0, 1))
    r = RAD * np.clip(1 - t ** 2, 0, 1) ** p * (1 - 0.10 * t)
    return t * LEN / 2, r


def render():
    body, blue, gold = inv_colors()
    # область кадра: x 28..100, y 108..160 (72 x 52), сверхвыборка SS
    x0, y0, w, h = 28, 108, 72, 52
    ys, xs = np.mgrid[0:h * SS, 0:w * SS].astype(np.float32)
    px = x0 + (xs + 0.5) / SS - CX
    py = y0 + (ys + 0.5) / SS - CY
    eu = np.array([np.cos(ANG), -np.sin(ANG)])
    ev = np.array([np.sin(ANG), np.cos(ANG)])
    u = px * eu[0] + py * eu[1]
    v = px * ev[0] + py * ev[1]
    ut, rt = profile()
    dr = np.gradient(rt, ut)
    r = np.interp(u, ut, rt, left=0, right=0)
    drr = np.interp(u, ut, dr, left=0, right=0)
    inside = (r > 0) & (np.abs(v) < r)
    hz = np.sqrt(np.clip(r ** 2 - v ** 2, 0, None))
    nu, nv, nh = -r * drr, v, hz
    nn = np.sqrt(nu ** 2 + nv ** 2 + nh ** 2) + 1e-6
    nu, nv, nh = nu / nn, nv / nn, nh / nn
    nx = nu * eu[0] + nv * ev[0]
    ny = nu * eu[1] + nv * ev[1]
    L = np.array([-0.45, -0.55, 0.70])
    L /= np.linalg.norm(L)
    diff = np.clip(nx * L[0] + ny * L[1] + nh * L[2], 0, 1)
    Hh = L + np.array([0, 0, 1.0])
    Hh /= np.linalg.norm(Hh)
    sp = np.clip(nx * Hh[0] + ny * Hh[1] + nh * Hh[2], 0, 1)
    spec = P["spec"] * sp ** 22 * 0.7 + 0.9 * sp ** 110
    # крапинки: в координатах тела, одинаково при любой сверхвыборке
    rng = np.random.default_rng(405)
    alb = np.ones(u.shape + (3,), np.float32) * np.minimum(body * np.array([1.10, 1.04, 0.94]), 250)
    for kind, n, rr, amt, col in (("blue", 30, (0.9, 1.7), 0.80, blue), ("gold", 9, (1.0, 1.7), 0.75, gold)):
        for _ in range(n):
            su = rng.uniform(-0.75, 0.75) * LEN / 2 if kind == "blue" else rng.uniform(0.0, 0.7) * LEN / 2
            rs = float(np.interp(su, ut, rt))
            sv = rng.uniform(-0.8, 0.8) * rs
            rad = rng.uniform(*rr) * (1.0 if kind == "blue" else 1.2)
            d2 = ((u - su) ** 2 * 0.6 + (v - sv) ** 2) / rad ** 2     # чуть вытянуты вдоль оси
            a = np.clip((1.15 - d2) * 3.0, 0, 1) * amt
            alb = alb * (1 - a[..., None]) + col * a[..., None]
    # тон: низкий окклюзионный к краю, тёплый свет, холодная тень
    shade = P["amb"] + (1.12 - P["amb"]) * diff
    rimk = 0.55 + 0.45 * np.clip(nh, 0, 1) ** 0.55
    col = alb * (shade * rimk)[..., None]
    col = col * (1 - 0.10 * (1 - diff))[..., None] + np.array([6, 7, 14]) * (1 - diff)[..., None] * 0.6
    col = col + spec[..., None] * 255 * 0.55
    # тонкая тёмная обводка у самого края
    dist = ndimage.distance_transform_edt(inside) / SS
    e = np.clip(1.0 - dist / P["rim"], 0, 1) ** 1.0 * 0.9
    outline = np.array([54, 34, 28], np.float32)
    col = col * (1 - e[..., None]) + outline * e[..., None]
    a_egg = inside.astype(np.float32)
    # тень: мягкая широкая правее и ниже + плотная у контакта
    def shifted(m, dx, dy, sy=1.0):
        return ndimage.shift(m, (dy * SS, dx * SS), order=1, mode="constant")
    big = shifted(inside.astype(np.float32), 4.5, 3.5)
    big = ndimage.gaussian_filter(big, 3.4 * SS)
    near = ndimage.gaussian_filter(shifted(inside.astype(np.float32), 1.5, 2.6), 1.3 * SS)
    sh_a = np.clip(0.34 * big / max(float(big.max()), 1e-6) * 1.0 + 0.30 * near, 0, 0.62)
    # сводим по площади: premultiplied
    def down(a):
        return a.reshape(h, SS, w, SS, *a.shape[2:]).mean(axis=(1, 3))
    col = np.clip(col, 0, 255)
    pre_e = down(col * a_egg[..., None])
    ae = down(a_egg)
    sa = down(sh_a * (1 - a_egg))
    shc = np.array([8, 12, 4], np.float32)
    tot = ae + sa * (1 - ae) * 0 + sa
    out_rgb = pre_e + shc * sa[..., None]
    out_a = np.clip(ae + sa, 0, 1)
    rgb = out_rgb / np.maximum(out_a[..., None], 1e-4)
    frame = np.zeros((160, 128, 4), np.float32)
    frame[y0:y0 + h, x0:x0 + w, :3] = rgb
    frame[y0:y0 + h, x0:x0 + w, 3] = out_a * 255
    return np.clip(np.rint(frame), 0, 255).astype(np.uint8), ae


def make():
    os.makedirs(OUT, exist_ok=True)
    fr, ae = render()
    p = os.path.join(OUT, "1405.png")
    Image.fromarray(fr, "RGBA").save(p)
    a = fr[..., 3]
    ys, xs = np.nonzero(a > 128)
    print("кадр", fr.shape, "яйцо x %d..%d y %d..%d" % (xs.min(), xs.max(), ys.min(), ys.max()), "(было 45..78, 125..150)")
    return p


def classic_floor():
    pal = np.asarray(wb.palette())
    ix = np.asarray(Image.open(FLOOR))
    rgba = np.zeros(ix.shape + (4,), np.uint8)
    m = ix != 0
    rgba[m, :3] = pal[ix[m]][:, :3]
    rgba[m, 3] = 255
    return Image.fromarray(rgba, "RGBA").resize((128, 160), Image.NEAREST)


def scene_with_egg(sc, egg_by_mode, k=4):
    """Поляна FORESTSWAMP: яйцо на клетке травы, как предмет на полу (кадр кладётся в начало клетки). Три окна."""
    import ticket_scene as ts
    terrain = "FORESTSWAMP"
    block = "FINNIKFOREST05"
    keys = [("FORESTSWAMPBITS", 5)]
    sets = sc.w.sets_of(terrain)
    print("наборы", sets)
    found = ts.find_cells(sc, terrain, block, keys)
    zmin = min(f[3] for f in found)
    found = [f for f in found if f[3] == zmin]
    pick = found[0]
    return terrain, block, zmin, pick


def sheet(path):
    import ticket_scene as ts
    sc = ts.Scene()
    new = Image.open(path).convert("RGBA")
    cur = Image.open(NOW).convert("RGBA")
    cls = classic_floor()
    inv = Image.open(INV)
    pal = np.asarray(wb.palette())
    ia = np.asarray(inv)
    irgba = np.zeros(ia.shape + (4,), np.uint8)
    mm_ = ia != 0
    irgba[mm_, :3] = pal[ia[mm_]][:, :3]
    irgba[mm_, 3] = 255
    inv_big = Image.fromarray(irgba, "RGBA").crop((0, 0, 16, 18)).resize((16 * 14, 18 * 14), Image.NEAREST)
    box = (24, 104, 104, 160)
    def crop(im, z):
        return im.crop(box).resize((80 * z, 56 * z), Image.LANCZOS if im.width > 40 else Image.NEAREST)
    Z = 8
    pans = [hc.title_bar(hc.on_bg(cls.crop(box).resize((80 * Z, 56 * Z), Image.NEAREST)), "классика (FLOOROB 405, яйцо 7x5)", 22),
            hc.title_bar(hc.on_bg(cur.crop(box).resize((80 * Z, 56 * Z), Image.LANCZOS)), "сейчас (XP-000322)", 22),
            hc.title_bar(hc.on_bg(new.crop(box).resize((80 * Z, 56 * Z), Image.LANCZOS)), "новое", 22),
            hc.title_bar(hc.on_bg(inv_big), "инвентарное яйцо BIGOBS 3050", 22)]
    row1 = hc.hstack(pans)
    # сцена: яйца на траве настоящего блока FORESTSWAMP
    terrain, block, z, pick = scene_with_egg(sc, None)
    k = 4
    scene_rows = []
    sx, sy, sz, cells = hc.mm.read_block(sc.w, block)
    # ячейки травы: берём клетки, где найден кадр-ориентир и ещё две соседние по найденным
    found = ts.find_cells(sc, terrain, block, [("FORESTSWAMPBITS", 5)])
    found = [f for f in found if f[3] == z][:1]
    found = [(f[0], f[1], tuple(v * k for v in f[2]), f[3], f[4]) for f in found]
    f0 = found[0]
    found = [f0, (f0[0], f0[1], (f0[2][0] + 32 * k, f0[2][1] + 16 * k, f0[2][2], f0[2][3]), f0[3], f0[4]),
             (f0[0], f0[1], (f0[2][0] - 32 * k, f0[2][1] + 16 * k, f0[2][2], f0[2][3]), f0[3], f0[4])]
    for mode, title, egg in (("classic", "классика", cls), ("hd", "сейчас", cur), ("hd", "новое", new)):
        im, _f = sc.render(terrain, block, mode, k=k, maxz=z)
        for f in found:
            spr = egg if mode == "hd" else egg.resize((128, 160), Image.NEAREST)
            im.alpha_composite(spr, (f[2][0], f[2][1]))
        cx = f0[2][0] + 64
        cy = f0[2][1] + 100
        bx = (cx - 300, cy - 200, cx + 300, cy + 120)
        scene_rows.append(hc.title_bar(ts.crop_pad(im, bx), title + " (яйцо на траве, блок %s, k=4)" % block, 22))
    scene = hc.hstack(scene_rows)
    out = hc.vstack([row1, scene])
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    out.save(SHEET)
    print("лист:", SHEET, out.size)


def install(path):
    man = bp.load()
    rel = "FLOOROB.PCK/1405.png"
    old = man["files"].get(rel, {})
    bp.stage(man, rel, path, generator="egg_build", generator_version="egg_build 05.11: яйцо-тело вращения, заострённый конец, свет, тень; было: %s" % old.get("generator"),
             source_path=path.replace(os.sep, "/"), approved=True, approval=WORD)
    bp.save(man, why="FLOOROB 1405: яйцо (%s)" % WORD)
    print("game:", bp.install(man, "game", only=[rel]))
    print("repo:", bp.install(man, "repo", only=[rel]))
    for root in bp.TARGETS.values():
        with open(os.path.join(root, rel), "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != man["files"][rel]["sha256"]:
                raise SystemExit("РАСХОДИТСЯ %s" % root)
    print("сверено: обе копии")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = make()
    if "--sheet" in sys.argv:
        sheet(p)
    if "--yes" in sys.argv:
        install(p)
