#!/usr/bin/env python3
"""
Иконки над телами: Zzz (оглушён), капли крови (кровотечение), огонь (горит), призрак (шок).

Откуда они берутся в игре: X-Piratez объявляет FloorStunIndicator / FloorWoundIndicator /
FloorBurnIndicator / FloorShockIndicator как singleImage 16x16 (Piratez_Resources.rul, около
строки 10734), а Map.cpp рисует их поверх тела в клетке. В ванильном UFO их нет вовсе.

Почему рисуем по координатам, а не моделью (грабли R-042): это пиктограммы из линий и
силуэтов - буква Z, капля, язык пламени, круглый рот призрака. Увеличение маски с порогом
скругляет острия, а диффузия на 64 пикселях кладёт фактуру, которая читается как грязь.
Все формы здесь считаются аналитически с запасом SS отсчётов на выходной пиксель и
усредняются при уменьшении: диагональ буквы ровная, остриё пламени острое.

Чем эти иконки отличаются от стрелочек пути: Map.cpp зовёт surface->blit(..., tileShade),
без newBaseColor. Значит цвет кадра доходит до экрана как есть, и можно рисовать в цвете,
а не калиброванной серой рампой, как в gen_path.py.

Палитры взяты с самих оригиналов (дамп пикселей), а не по памяти: тёмно-красный обод капли
(84,8,0), жёлтое ядро огня (252,208,0), серые Z от 88 до 196.

    py -3 tools\\hdart\\gen_icons.py --pack user\\mods\\hd\\hd\\UI
    ... --scale 2            собрать для k = 2
    ... --sheet "Claude outputs\\indicators_cmp.png"

Смотреть в первую очередь лист сравнения: слева оригинал, справа как вышло, фон - тёмный
пол боя, а не шахматка (грабли R-041: остаток подложки виден только на тёмном).
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = 16      # оригиналы 16x16
SS = 8         # отсчётов геометрии на выходной пиксель по каждой оси

SRC_DIR = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez",
                       "Resources", "UnitUI")

# имя файла в hd/UI -> имя оригинала, по которому движок ищет картинку (он приводит к нижнему)
OUT_NAMES = {
    "stun":  ("floorstunindicator.png",  "Zzz.png"),
    "wound": ("floorwoundindicator.png", "Bleed.png"),
    "burn":  ("floorburnindicator.png",  "Burn.png"),
    "shock": ("floorshockindicator.png", "Spritt.png"),
}


# ---------------------------------------------------------------- инструменты

def grids(k):
    """Сетка отсчётов в единицах базового пикселя (0..16)."""
    h = BASE * k * SS
    u = (np.arange(h, dtype=np.float64) + 0.5) / (k * SS)
    return np.meshgrid(u, u)


def down(mask, k):
    """Из логической сетки отсчётов - покрытие 0..1 на выходном разрешении."""
    n = BASE * k
    return mask.astype(np.float32).reshape(n, SS, n, SS).mean(axis=(1, 3))


def gauss(a, r):
    """Разделимое размытие: PIL не умеет режим F, а радиусы здесь дробные."""
    if r <= 0:
        return a.astype(np.float32).copy()
    n = max(1, int(r * 3.0 + 0.5))
    x = np.arange(-n, n + 1, dtype=np.float64)
    ker = np.exp(-(x * x) / (2.0 * r * r))
    ker /= ker.sum()
    out = a.astype(np.float64)
    p = np.pad(out, ((0, 0), (n, n)), mode="edge")
    out = np.apply_along_axis(lambda m: np.convolve(m, ker, "valid"), 1, p)
    p = np.pad(out, ((n, n), (0, 0)), mode="edge")
    out = np.apply_along_axis(lambda m: np.convolve(m, ker, "valid"), 0, p)
    return out.astype(np.float32)


def smooth(t, lo, hi):
    t = np.clip((t - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def mix(a, b, t):
    """a, b - цвет (3,) или поле HxWx3; t - поле HxW."""
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    if a.ndim == 1:
        a = np.broadcast_to(a, t.shape + (3,))
    if b.ndim == 1:
        b = np.broadcast_to(b, t.shape + (3,))
    return a + (b - a) * t[..., None]


def polygon(x, y, pts):
    """Чётно-нечётная заливка простого многоугольника."""
    inside = np.zeros(x.shape, bool)
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if y1 == y2:
            continue
        cross = (y1 > y) != (y2 > y)
        xint = (x2 - x1) * (y - y1) / (y2 - y1) + x1
        inside ^= cross & (x < xint)
    return inside


def disc(x, y, cx, cy, rx, ry=None):
    ry = rx if ry is None else ry
    return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0


def crspline(vals, q):
    """Catmull-Rom по равномерным узлам: кривая проходит через точки и не даёт граней."""
    v = np.asarray(vals, np.float64)
    v = np.concatenate([[2 * v[0] - v[1]], v, [2 * v[-1] - v[-2]]])
    i = np.clip(np.floor(q).astype(int), 0, len(vals) - 2)
    t = q - i
    p0, p1, p2, p3 = v[i], v[i + 1], v[i + 2], v[i + 3]
    return 0.5 * (2 * p1 + (-p0 + p2) * t
                  + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)


def profile(x, y, top, bottom, widths, centers, wscale=1.0, cshift=0.0):
    """Силуэт, заданный полушириной и осью по высоте: язык пламени, тело призрака."""
    q = (y - top) / (bottom - top) * (len(widths) - 1)
    ok = (y >= top) & (y <= bottom)
    qq = np.clip(q, 0.0, len(widths) - 1.0)
    w = crspline(widths, qq) * wscale
    c = crspline(centers, qq) + cshift
    return ok & (np.abs(x - c) <= np.maximum(w, 0.0))


def bevel(m, k, c_edge, c_body, edge_px=0.55, rim=0.52, depth=0.30):
    """Общий приём всех четырёх иконок: тёмный обод снаружи, тело внутри."""
    d = gauss(m, edge_px * k)
    core = smooth(d, rim, rim + depth)
    return mix(c_edge, c_body, core), core


def blob(x, y, cx, cy, rx, ry, k):
    """Мягкое пятно света на выходном разрешении."""
    return down(disc(x, y, cx, cy, rx, ry), k)


# ---------------------------------------------------------------- сами иконки

Z_BOXES = [
    # x0,  y0,   x1,   y1,  полоса, диагональ, яркость
    (1.0, 1.0,  9.2, 11.0, 1.80, 2.35, 1.00),
    (6.0, 4.3, 12.0, 12.8, 1.50, 1.95, 0.80),
    (9.6, 7.2, 14.9, 14.9, 1.28, 1.70, 0.64),
]
Z_EDGE = np.float32([48, 48, 48])
Z_BODY = np.float32([146, 146, 146])
Z_LITE = np.float32([240, 240, 240])


def z_glyph(x0, y0, x1, y1, bar, diag):
    """Буква Z одним замкнутым контуром: у неё восемь углов, и все обязаны быть острыми."""
    return [
        (x0, y0), (x1, y0),
        (x0 + diag, y1 - bar), (x1, y1 - bar),
        (x1, y1), (x0, y1),
        (x0, y1 - bar), (x1 - diag, y0 + bar),
        (x0, y0 + bar),
    ]


def icon_stun(x, y, k):
    n = BASE * k
    rgb = np.zeros((n, n, 3), np.float32)
    a = np.zeros((n, n), np.float32)
    for x0, y0, x1, y1, bar, diag, lit in Z_BOXES:
        m = down(polygon(x, y, z_glyph(x0, y0, x1, y1, bar, diag)), k)
        col, core = bevel(m, k, Z_EDGE, Z_BODY * lit, edge_px=0.62)
        # свет сверху-слева, как у выдавленной буквы
        up = smooth((y1 - down(y, k)) / (y1 - y0), 0.30, 1.00) * core
        col = mix(col, Z_LITE * lit, up * 0.72)
        rgb = mix(rgb, col, m)
        a = np.maximum(a, m)
    return rgb, a


B_EDGE = np.float32([70, 6, 0])
B_BODY = np.float32([150, 32, 32])
B_LITE = np.float32([236, 120, 116])
DROPS = [
    # cx,   cy,   r,   вершина
    (5.40, 11.50, 3.50, 1.80),
    (11.50, 6.60, 2.40, 1.00),
]


def drop_mask(x, y, cx, cy, r, apex):
    """Капля: круг плюс конус до вершины по касательным, а не треугольник на глаз."""
    h = cy - apex
    cs = np.clip(r / h, 0.0, 1.0)
    sn = float(np.sqrt(max(0.0, 1.0 - cs * cs)))
    t1 = (cx - r * sn, cy - r * cs)
    t2 = (cx + r * sn, cy - r * cs)
    cone = polygon(x, y, [(cx, apex), t2, t1])
    return disc(x, y, cx, cy, r) | cone


def icon_wound(x, y, k):
    n = BASE * k
    rgb = np.zeros((n, n, 3), np.float32)
    a = np.zeros((n, n), np.float32)
    for cx, cy, r, apex in DROPS:
        m = down(drop_mask(x, y, cx, cy, r, apex), k)
        col, core = bevel(m, k, B_EDGE, B_BODY, edge_px=0.55)
        # блик в верхней левой четверти пузыря и тень в нижней правой
        spec = gauss(blob(x, y, cx - r * 0.34, cy - r * 0.40, r * 0.46, r * 0.56, k), 0.55 * k)
        col = mix(col, B_LITE, np.clip(spec * 2.4, 0.0, 1.0) * core)
        shade = gauss(blob(x, y, cx + r * 0.45, cy + r * 0.50, r * 0.75, r * 0.70, k), 0.7 * k)
        col = mix(col, B_EDGE, np.clip(shade * 0.9, 0.0, 1.0) * core * 0.45)
        rgb = mix(rgb, col, m)
        a = np.maximum(a, m)
    return rgb, a


F_TOP, F_BOT = 1.00, 15.80
F_W = [0.00, 0.42, 0.82, 1.32, 2.02, 2.98, 4.02, 4.74, 4.68, 3.55, 1.70]
F_C = [8.95, 8.76, 8.48, 8.20, 8.00, 7.90, 7.84, 7.84, 7.90, 7.96, 8.00]
F_EDGE = np.float32([148, 32, 32])
F_BODY = np.float32([196, 62, 58])
F_RIM = np.float32([232, 104, 96])
F_ORANGE = np.float32([204, 118, 8])
F_ORANGE_LITE = np.float32([230, 168, 16])
F_YELLOW = np.float32([250, 206, 10])
F_CORE = np.float32([255, 242, 158])


def icon_burn(x, y, k):
    m0 = down(profile(x, y, F_TOP, F_BOT, F_W, F_C), k)
    m1 = down(profile(x, y, 4.40, 15.20, F_W, F_C, wscale=0.64, cshift=0.30), k)
    m2 = down(profile(x, y, 7.00, 14.60, F_W, F_C, wscale=0.37, cshift=0.58), k)

    rgb, core = bevel(m0, k, F_EDGE, F_BODY, edge_px=0.50)
    # светлый рубчик по левому краю - он есть и в оригинале (F = 224,92,92)
    left = smooth(F_C[5] - down(x, k), 1.2, 4.2) * (1.0 - core)
    rgb = mix(rgb, F_RIM, np.clip(left, 0.0, 1.0) * m0 * 0.85)

    t1 = smooth(gauss(m1, 0.22 * k), 0.30, 0.85)
    rgb = mix(rgb, mix(F_ORANGE, F_ORANGE_LITE, t1), t1)

    t2 = smooth(gauss(m2, 0.20 * k), 0.30, 0.85)
    rgb = mix(rgb, F_YELLOW, t2)
    t3 = smooth(gauss(m2, 0.20 * k), 0.78, 1.00)
    rgb = mix(rgb, F_CORE, t3 * 0.75)
    return rgb, m0


G_TOP, G_BOT = 0.60, 13.20
G_W = [1.10, 2.30, 3.05, 3.50, 3.80, 4.05, 4.45, 5.00, 5.60, 6.10]
G_C = [7.30] * 10
G_HEM = [(3.27, 2.03, 2.30), (7.30, 2.03, 2.45), (11.33, 2.03, 2.30)]
G_EDGE = np.float32([70, 70, 70])
G_BODY = np.float32([188, 188, 188])
G_LITE = np.float32([244, 244, 244])
G_DARK = np.float32([74, 74, 74])


def icon_shock(x, y, k):
    body = profile(x, y, G_TOP, G_BOT, G_W, G_C)
    # подол тремя свисающими лепестками: у призрака он рваный, а не прямой
    for cx, rx, ry in G_HEM:
        body |= disc(x, y, cx, G_BOT, rx, ry) & (y >= G_BOT)
    # две лапки по бокам: без них силуэт читается как капля, а в оригинале выступы есть
    body |= disc(x, y, 1.35, 9.60, 1.60, 1.35)
    body |= disc(x, y, 13.25, 9.60, 1.60, 1.35)
    mouth = disc(x, y, 7.30, 10.05, 2.10, 2.50)
    m = down(body & ~mouth, k)

    rgb, core = bevel(m, k, G_EDGE, G_BODY, edge_px=0.62)
    spec = gauss(blob(x, y, 5.45, 3.30, 2.10, 2.25, k), 0.8 * k)
    rgb = mix(rgb, G_LITE, np.clip(spec * 1.6, 0.0, 1.0) * core * 0.9)

    eyes = down(disc(x, y, 5.50, 4.90, 0.95, 1.25) | disc(x, y, 9.10, 4.90, 0.95, 1.25), k)
    eyes = np.minimum(eyes, m)
    rgb = mix(rgb, G_DARK, eyes)
    return rgb, m


ICONS = {
    "stun": icon_stun,
    "wound": icon_wound,
    "burn": icon_burn,
    "shock": icon_shock,
}


# ---------------------------------------------------------------- сборка

def render(key, k):
    x, y = grids(k)
    rgb, a = ICONS[key](x, y, k)
    rgb = np.clip(rgb, 0.0, 255.0)
    a = np.clip(a, 0.0, 1.0)
    out = np.zeros(a.shape + (4,), np.uint8)
    out[..., :3] = np.round(rgb).astype(np.uint8)
    out[..., 3] = np.round(a * 255.0).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def check(img, key, orig):
    """Приёмка числом, а не глазом: углы пусты, габарит совпадает с оригиналом."""
    a = np.asarray(img)[..., 3].astype(np.float32)
    k = img.size[0] // BASE
    c = max(2, k)
    corners = [a[:c, :c], a[:c, -c:], a[-c:, :c], a[-c:, -c:]]
    worst = max(float(x.mean()) for x in corners)
    ys, xs = np.nonzero(a > 8)
    box = (xs.min() / k, ys.min() / k, (xs.max() + 1) / k, (ys.max() + 1) / k)
    oa = np.asarray(orig.convert("RGBA"))[..., 3]
    oys, oxs = np.nonzero(oa > 8)
    obox = (oxs.min(), oys.min(), oxs.max() + 1, oys.max() + 1)
    drift = max(abs(box[i] - obox[i]) for i in range(4))
    print("    углы: %.2f из 255   габарит %s против %s   расхождение %.2f пикс. базы"
          % (worst, tuple(round(v, 1) for v in box), obox, drift))
    return worst, drift


def sheet(pairs, path, k):
    """Лист «оригинал | как вышло» на тёмном полу боя (грабли R-041)."""
    cell = BASE * k
    pad = 10
    w = len(pairs) * (cell * 2 + pad) + pad
    im = Image.new("RGBA", (w, cell + 2 * pad), (34, 38, 30, 255))
    x = pad
    for orig, new in pairs:
        im.alpha_composite(orig.convert("RGBA").resize((cell, cell), Image.NEAREST), (x, pad))
        im.alpha_composite(new, (x + cell, pad))
        x += cell * 2 + pad
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    im.save(path)
    print("лист:", path, im.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=4, help="k, во сколько раз крупнее базы")
    ap.add_argument("--pack", default="", help="куда положить кадры (user\\mods\\hd\\hd\\UI)")
    ap.add_argument("--out", default="", help="каталог для отдельных PNG, если пак не нужен")
    ap.add_argument("--sheet", default=os.path.join("Claude outputs", "indicators_cmp.png"))
    ap.add_argument("--only", default="", help="через запятую: stun,wound,burn,shock")
    args = ap.parse_args()

    k = args.scale
    keys = [s.strip() for s in args.only.split(",") if s.strip()] or list(ICONS)
    pairs = []
    bad = 0
    for key in keys:
        name, src = OUT_NAMES[key]
        img = render(key, k)
        orig = Image.open(os.path.join(SRC_DIR, src))
        print("%-6s %s  %dx%d" % (key, name, img.size[0], img.size[1]))
        worst, drift = check(img, key, orig)
        if worst > 0.5 or drift > 2.0:
            bad += 1
        pairs.append((orig, img))
        for d in (args.pack, args.out):
            if d:
                os.makedirs(d, exist_ok=True)
                p = os.path.join(d, name)
                img.save(p)
                print("    ->", p)
    if args.sheet:
        sheet(pairs, args.sheet, k)
    if bad:
        print("ПРОВЕРЬ: %d кадр(ов) не прошли приёмку по углам или габариту" % bad)
    return 0


if __name__ == "__main__":
    sys.exit(main())
