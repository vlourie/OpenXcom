#!/usr/bin/env python3
"""
HD-набор Pathfinding: стрелочки предпросмотра пути.

Классика лежит в bin/common/Resources/Pathfinding/Pathfinding.png - лист 384x80,
24 кадра по 32x40: 0..7 восемь направлений, 8 вверх, 9 вниз, 10 кольцо цели,
11 ромб клетки; 12..23 те же формы в шахматку (поддельная полупрозрачность,
их движок кладёт поверх объектов).

Два условия, из-за которых кадр нельзя просто нарисовать красками:

1. Каждый блит перекрашивается по стоимости хода: Map.cpp передаёт
   tile->getMarkerColor() как newBaseColor, и Canvas32::doBlitHd гонит кадр
   через hdRow<true,true>: яркость пикселя -> ступень рампы палитры -> запись
   той же ступени в ГРУППЕ маркера. То есть от картинки берётся только ЯРКОСТЬ
   и альфа; свой цвет ей иметь бессмысленно. Поэтому кадры серые, а яркости
   взяты ровно те, что дают нужную ступень (таблица GREY ниже).

2. Шахматка в кадрах 12..23 - это обход отсутствия альфы у классики. В HD альфа
   есть, поэтому те же кадры выходят с настоящей полупрозрачностью.

Файл bin/common править нельзя (Святое правило), поэтому HD-набор кладётся в
user/mods/hd/hd/Pathfinding/<N>.png - ни кода, ни рулсета это не требует.

Линии на сетке модели не отдаём (грабли R-040) и пиксели не увеличиваем
(грабли R-042): каждая форма считается аналитически - многоугольник стрелки,
эллипс цели, ромб клетки - с запасом в шестнадцать отсчётов на пиксель базы,
а сглаживание берётся из усреднения при уменьшении. Так диагональ выходит
прямой, а остриё остаётся острым.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):   # консоль msys бывает cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

SHEET = os.path.join(ROOT, "bin", "common", "Resources", "Pathfinding", "Pathfinding.png")
PIRATEZ_PAL = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods",
                           "Piratez", "Resources", "Pals", "delicious_regular.pal")

FW, FH = 32, 40
COUNT = 24
SOLID = 12           # кадры 0..11 сплошные, 12..23 - те же в полупрозрачности
OVERLAY_ALPHA = 0.5  # чем шахматка была на самом деле

# Яркость серого, дающая ступень рампы L. Считано по самой рампе палитры
# (Canvas32::rebuildToneTables): среднее двух палитр - боевой ванильной и
# delicious_regular Пираток, они расходятся не больше чем на треть ступени.
GREY = [234, 212, 192, 172, 154, 136, 120, 104, 90, 75, 62, 49, 38, 28, 20, 13]

# Цвета маркера пути: Mod.cpp -> Pathfinding::green/yellow/red (номер группы + 1)
MARKERS = [("green", 4), ("yellow", 10), ("red", 3)]

STYLES = {
    # "чисто": тот же рисунок, только без ступенек - тёмная кромка снизу, как в оригинале
    "clean":  dict(kind="bevel", body=1.2, dark=4.6, hi=1.2, glow=0.0, glow_r=0.0, glow_lvl=6.0),
    # "плазма": та же кромка плюс мягкое свечение вокруг - под новый прицел
    "plasma": dict(kind="bevel", body=1.0, dark=4.2, hi=1.0, glow=0.42, glow_r=3.0, glow_lvl=6.0),
    # "неон": светится обвод, середина приглушена
    "neon":   dict(kind="neon",  body=6.0, edge=0.0, glow=0.60, glow_r=3.5, glow_lvl=5.0),
}


def gauss(a, radius):
    """Разделимое размытие по numpy: PIL не умеет гаусс на вещественной картинке."""
    if radius <= 0:
        return a.astype(np.float32).copy()
    r = int(max(1, round(radius * 3)))
    x = np.arange(-r, r + 1, dtype=np.float32)
    ker = np.exp(-(x * x) / (2.0 * radius * radius))
    ker /= ker.sum()
    out = a.astype(np.float32)
    pad = np.pad(out, ((0, 0), (r, r)), mode="edge")
    out = np.apply_along_axis(lambda m: np.convolve(m, ker, mode="valid"), 1, pad)
    pad = np.pad(out, ((r, r), (0, 0)), mode="edge")
    out = np.apply_along_axis(lambda m: np.convolve(m, ker, mode="valid"), 0, pad)
    return out.astype(np.float32)


def load_frames(path):
    im = Image.open(path)
    if im.mode != "P":
        raise SystemExit("ожидался индексный PNG: %s" % path)
    a = np.asarray(im)
    cols = a.shape[1] // FW
    out = []
    for f in range(COUNT):
        cx, cy = (f % cols) * FW, (f // cols) * FH
        out.append(a[cy:cy + FH, cx:cx + FW])
    return out


def box_down(a, n):
    h, w = a.shape
    return a.reshape(h // n, n, w // n, n).mean(axis=(1, 3))


# --- геометрия: всё строится по координатам, а не увеличением пикселей ---------
#
# Направления - экранные, изометрические: север идёт вправо-вверх, северо-восток
# вправо, и так по кругу (Pathfinding::getPreview -> кадр 0..7). Стрелка лежит НА
# земле, поэтому её толщина укорочена так же, как укорочена клетка: поперечник
# берётся из той же изометрии, что и длина. Отсюда и вид оригинала: боковые
# стрелки узкие, стрелка «вниз по экрану» широкая и короткая.

ARROW_C = (16.0, 32.0)      # середина стрелки в пикселях базы
TILE_C = (16.0, 31.0)       # середина ромба клетки
TILE_RX, TILE_RY = 16.0, 8.0

DIRS = [
    (2.0, -1.0),   # 0 север      - вправо-вверх
    (1.0, 0.0),    # 1 северо-восток - вправо
    (2.0, 1.0),    # 2 восток     - вправо-вниз
    (0.0, 1.0),    # 3 юго-восток - вниз
    (-2.0, 1.0),   # 4 юг         - влево-вниз
    (-1.0, 0.0),   # 5 юго-запад  - влево
    (-2.0, -1.0),  # 6 запад      - влево-вверх
    (0.0, -1.0),   # 7 северо-запад - вверх
]

# длина, полуширина древка, полуширина головы, длина головы - в пикселях базы
ARROW_P = {
    "diag":  (12.6, 1.5, 3.6, 5.0),
    "horiz": (14.4, 1.1, 3.3, 5.6),
    "vert":  (9.2, 2.1, 5.6, 4.2),
}


def arrow_class(i):
    return "horiz" if i in (1, 5) else "vert" if i in (3, 7) else "diag"


def arrow_poly(centre, direction, L, sw, hw, hl):
    d = np.asarray(direction, dtype=np.float64)
    d /= np.hypot(d[0], d[1])
    q = np.array([-d[1], d[0]])
    c = np.asarray(centre, dtype=np.float64)
    tip, base, tail = L / 2.0, L / 2.0 - hl, -L / 2.0
    uv = [(tail, -sw), (base, -sw), (base, -hw), (tip, 0.0),
          (base, hw), (base, sw), (tail, sw)]
    return [tuple(c + u * d + v * q) for u, v in uv]


def poly_mask(pts, X, Y):
    inside = np.zeros(X.shape, dtype=bool)
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if y0 == y1:
            continue
        cond = (y0 > Y) != (y1 > Y)
        xint = (x1 - x0) * (Y - y0) / (y1 - y0) + x0
        inside ^= cond & (X < xint)
    return inside


def shape_mask(i, k, ss):
    """Силуэт кадра i с запасом k*ss: 1 внутри, 0 снаружи."""
    n = k * ss
    W, H = FW * n, FH * n
    xs = (np.arange(W) + 0.5) / n
    ys = (np.arange(H) + 0.5) / n
    X, Y = np.meshgrid(xs, ys)

    if i < 8:
        L, sw, hw, hl = ARROW_P[arrow_class(i)]
        return poly_mask(arrow_poly(ARROW_C, DIRS[i], L, sw, hw, hl), X, Y).astype(np.float32)

    if i in (8, 9):
        # «вверх этажом» и «вниз этажом»: прямая стрелка, свой сдвиг по вертикали
        up = (i == 8)
        centre = (16.0, 27.5 if up else 32.5)
        poly = arrow_poly(centre, (0.0, -1.0 if up else 1.0), 11.5, 1.9, 5.0, 6.6)
        return poly_mask(poly, X, Y).astype(np.float32)

    if i == 10:
        # цель пути: залитый овал с крестообразной дыркой
        cx, cy = 16.0, 32.0
        oval = ((X - cx) / 10.0) ** 2 + ((Y - cy) / 5.5) ** 2 <= 1.0
        barh = (np.abs(X - cx) <= 8.6) & (np.abs(Y - cy) <= 1.2)
        barv = (np.abs(X - cx) <= 2.1) & (np.abs(Y - cy) <= 4.1)
        return (oval & ~(barh | barv)).astype(np.float32)

    if i == 11:
        # ромб клетки: обвод в два пикселя базы по горизонтали
        f = np.abs(X - TILE_C[0]) / TILE_RX + np.abs(Y - TILE_C[1]) / TILE_RY
        return ((f <= 1.0) & (f >= 1.0 - 2.0 / TILE_RX)).astype(np.float32)

    raise ValueError("нет кадра %d" % i)


def render(shape, style, k, ss):
    """Серая картинка k x с альфой: возвращает (val 0..255, alpha 0..1)."""
    p = STYLES[style]
    unit = float(k * ss) / 4.0            # сколько пикселей в одном пикселе базы при k=4
    soft = gauss(shape, 1.5 * unit)
    t = np.clip((soft - 0.5) / 0.5, 0.0, 1.0)      # 0 у самой кромки, 1 в глубине
    edge = (1.0 - t) * shape

    gy, gx = np.gradient(soft)
    gl = np.sqrt(gx * gx + gy * gy) + 1e-6
    ny = -gy / gl                                   # внешняя нормаль: >0 - кромка смотрит вниз

    if p["kind"] == "neon":
        level = p["edge"] + (p["body"] - p["edge"]) * t
    else:
        dark = np.clip(ny * 0.9 + 0.30, 0.0, 1.0)
        high = np.clip(-ny - 0.20, 0.0, 1.0)
        level = p["body"] + p["dark"] * edge * dark - p["hi"] * edge * high
    level = np.clip(level, 0.0, 15.0)
    val = np.interp(level, np.arange(16.0), GREY).astype(np.float32)

    alpha = shape.copy()
    premul = val * shape
    if p["glow"] > 0.0:
        g = gauss(shape, p["glow_r"] * unit)
        g = np.clip(g * p["glow"] * 2.2, 0.0, 1.0) * (1.0 - shape)
        gval = float(np.interp(p["glow_lvl"], np.arange(16.0), GREY))
        premul = premul + gval * g
        alpha = shape + g

    a_ds = box_down(alpha, ss)
    p_ds = box_down(premul, ss)
    v_ds = p_ds / np.maximum(a_ds, 1e-4)
    return np.clip(v_ds, 0, 255), np.clip(a_ds, 0.0, 1.0)


def to_rgba(val, alpha, mul=1.0):
    h, w = val.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    v = val.astype(np.uint8)
    out[..., 0] = v
    out[..., 1] = v
    out[..., 2] = v
    out[..., 3] = np.clip(alpha * mul * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


# --- предпросмотр: считаем ровно то, что покажет движок ------------------------

def load_pal(path):
    data = open(path, "rb").read()
    if data[:4] == b"JASC":
        lines = data.decode("latin1").splitlines()
        return [tuple(int(x) for x in l.split()[:3]) for l in lines[3:3 + 256]]
    return [(data[i * 3], data[i * 3 + 1], data[i * 3 + 2]) for i in range(256)]


def load_dat(path, index):
    data = open(path, "rb").read()
    off = index * (768 + 6)
    pal = data[off:off + 768]
    return [(pal[i * 3] * 4, pal[i * 3 + 1] * 4, pal[i * 3 + 2] * 4) for i in range(256)]


def level_lut(colors):
    """Повтор Canvas32::rebuildToneTables: яркость 0..255 -> ступень 0..15."""
    lum = [(0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255.0 for c in colors]
    ramp = [0.0] * 17
    top, groups = 0.0, 0
    for g in range(16):
        base = lum[g * 16]
        if base < 0.2 or lum[g * 16 + 15] > base * 0.5:
            continue
        for L in range(16):
            ramp[L] += lum[g * 16 + L] / base
        top += max(colors[g * 16]) / 255.0
        groups += 1
    if groups == 0:
        return None
    for L in range(16):
        ramp[L] /= groups
    top = max(0.25, top / groups)
    ramp[0], ramp[16] = 1.0, 0.0
    for L in range(1, 17):
        ramp[L] = min(ramp[L], ramp[L - 1])

    def level_of(y):
        if y >= ramp[0]:
            return 0.0
        for i in range(16):
            if ramp[i] >= y >= ramp[i + 1]:
                d = ramp[i] - ramp[i + 1]
                return i + ((ramp[i] - y) / d if d > 0 else 0.0)
        return 16.0

    lut = np.zeros(256, dtype=np.uint8)
    for v in range(256):
        lut[v] = int(min(15.0, max(0.0, round(level_of(min(1.0, v / 255.0 / top))))))
    return lut


def recolor(rgba, lut, colors, base_color, bg):
    a = np.asarray(rgba, dtype=np.float32)
    lum = ((a[..., 0] * 77 + a[..., 1] * 151 + a[..., 2] * 28) / 256.0).astype(np.int32)
    idx = (base_color - 1) * 16 + lut[np.clip(lum, 0, 255)]
    pal = np.asarray(colors, dtype=np.float32)
    col = pal[idx]
    al = (a[..., 3] / 255.0)[..., None]
    out = col * al + np.asarray(bg, dtype=np.float32) * (1.0 - al)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def classic_rgba(src):
    """Классический кадр как RGBA той же яркостной шкалы - для листа сравнения."""
    rgb = np.zeros((FH, FW, 4), dtype=np.uint8)
    for v in np.unique(src):
        if v == 0:
            continue
        g = GREY[min(15, int(v))]
        rgb[src == v] = (g, g, g, 255)
    return Image.fromarray(rgb, "RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", default="plasma", choices=sorted(STYLES))
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--ss", type=int, default=4, help="запас при расчёте, потом усредняется")
    ap.add_argument("--pack", default="", help="куда положить <N>.png (набор игры)")
    ap.add_argument("--out", default="", help="куда положить листы предпросмотра")
    ap.add_argument("--all-styles", action="store_true", help="листы по всем стилям")
    ap.add_argument("--verify", default="", metavar="ПАК",
                    help="сверка по готовому паку: лист и поле собираются из <N>.png, "
                         "которые читает игра, а не из того, что сейчас в памяти")
    args = ap.parse_args()

    frames = load_frames(SHEET)
    shapes = [shape_mask(i, args.scale, args.ss) for i in range(SOLID)]

    # габарит против оригинала: расхождение больше пары пикселей базы означает,
    # что стрелка съехала с клетки, а не «стала другой»
    for i in range(SOLID):
        ys, xs = np.nonzero(frames[i] > 0)
        hy, hx = np.nonzero(shapes[i] > 0)
        n = args.scale * args.ss
        print("кадр %2d: оригинал x %2d..%2d y %2d..%2d | наш x %4.1f..%4.1f y %4.1f..%4.1f"
              % (i, xs.min(), xs.max(), ys.min(), ys.max(),
                 hx.min() / n, hx.max() / n, hy.min() / n, hy.max() / n))

    colors = load_pal(PIRATEZ_PAL) if os.path.exists(PIRATEZ_PAL) else \
        load_dat(os.path.join(ROOT, "bin", "UFO", "GEODATA", "PALETTES.DAT"), 4)
    lut = level_lut(colors)

    styles = sorted(STYLES) if args.all_styles else [args.style]
    made = {}
    if args.verify:
        # R-019: судить по файлу, который читает игра, а не по тому, что в памяти
        made["pack"] = []
        for i in range(SOLID):
            im = Image.open(os.path.join(args.verify, "%d.png" % i)).convert("RGBA")
            a = np.asarray(im, dtype=np.float32)
            made["pack"].append((a[..., 0], a[..., 3] / 255.0))
        styles = ["pack"]
        print("сверка по паку: %s" % args.verify)
    else:
        for st in styles:
            made[st] = [render(shapes[i], st, args.scale, args.ss) for i in range(SOLID)]
            print("стиль %s: %d кадров" % (st, SOLID))

    if args.pack and not args.verify:
        os.makedirs(args.pack, exist_ok=True)
        st = args.style
        for i in range(COUNT):
            val, al = made[st][i % SOLID]
            mul = 1.0 if i < SOLID else OVERLAY_ALPHA
            to_rgba(val, al, mul).save(os.path.join(args.pack, "%d.png" % i))
        print("пак: %s (%d кадров %dx%d)" % (args.pack, COUNT, FW * args.scale, FH * args.scale))

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        k = args.scale
        bgs = [(28, 26, 24), (96, 88, 72)]
        for st in styles:
            rows = []
            for name, base in MARKERS:
                for bg in bgs:
                    strip = Image.new("RGB", (FW * k * SOLID, FH * k), bg)
                    for i in range(SOLID):
                        val, al = made[st][i]
                        strip.paste(recolor(to_rgba(val, al), lut, colors, base, bg), (i * FW * k, 0))
                    rows.append(strip)
            sheet = Image.new("RGB", (rows[0].width, rows[0].height * len(rows)))
            for n, r in enumerate(rows):
                sheet.paste(r, (0, n * r.height))
            path = os.path.join(args.out, "path_%s.png" % st)
            sheet.save(path)
            print("лист: %s" % path)

        # тот же ряд в классике - судить по сравнению, а не по памяти
        rows = []
        for bg in bgs:
            strip = Image.new("RGB", (FW * k * SOLID, FH * k), bg)
            for i in range(SOLID):
                big = classic_rgba(frames[i]).resize((FW * k, FH * k), Image.NEAREST)
                strip.paste(recolor(big, lut, colors, MARKERS[1][1], bg), (i * FW * k, 0))
            rows.append(strip)
        sheet = Image.new("RGB", (rows[0].width, rows[0].height * len(rows)))
        for n, r in enumerate(rows):
            sheet.paste(r, (0, n * r.height))
        path = os.path.join(args.out, "path_classic.png")
        sheet.save(path)
        print("лист: %s" % path)

        # поле: путь из клеток, а не одна стрелка - решётка и шум видны только так
        for st in styles + ["classic"]:
            field = path_field(st, made, frames, lut, colors, k)
            path = os.path.join(args.out, "field_%s.png" % st)
            field.save(path)
            print("поле: %s" % path)


# Путь по клеткам: шаги и цвет маркера меняются с ростом расхода ОВ, как в игре.
FIELD_STEPS = [1, 1, 0, 0, 1, 2, 3, 3, 2, 1, 1]
STEP_SCREEN = {0: (16, -8), 1: (32, 0), 2: (16, 8), 3: (0, 16),
               4: (-16, 8), 5: (-32, 0), 6: (-16, -8), 7: (0, -16)}


def path_field(style, made, frames, lut, colors, k, bg=(26, 24, 22)):
    pos = [(0, 0)]
    for d in FIELD_STEPS:
        dx, dy = STEP_SCREEN[d]
        pos.append((pos[-1][0] + dx, pos[-1][1] + dy))
    xs = [p[0] for p in pos]
    ys = [p[1] for p in pos]
    pad = 24
    W = (max(xs) - min(xs) + FW + 2 * pad) * k
    H = (max(ys) - min(ys) + FH + 2 * pad) * k
    out = Image.new("RGB", (W, H), bg)
    ox, oy = (pad - min(xs)) * k, (pad - min(ys)) * k

    for n, d in enumerate(FIELD_STEPS + [None]):
        i = 10 if d is None else d          # последняя клетка - кольцо цели
        base = MARKERS[0][1] if n < 4 else MARKERS[1][1] if n < 8 else MARKERS[2][1]
        if style == "classic":
            rgba = classic_rgba(frames[i]).resize((FW * k, FH * k), Image.NEAREST)
        else:
            val, al = made[style][i]
            rgba = to_rgba(val, al)
        x, y = ox + pos[n][0] * k, oy + pos[n][1] * k
        tile = out.crop((x, y, x + FW * k, y + FH * k))
        out.paste(blend_over(rgba, tile, lut, colors, base), (x, y))
    return out


def blend_over(rgba, tile, lut, colors, base_color):
    a = np.asarray(rgba, dtype=np.float32)
    lum = ((a[..., 0] * 77 + a[..., 1] * 151 + a[..., 2] * 28) / 256.0).astype(np.int32)
    idx = (base_color - 1) * 16 + lut[np.clip(lum, 0, 255)]
    col = np.asarray(colors, dtype=np.float32)[idx]
    al = (a[..., 3] / 255.0)[..., None]
    under = np.asarray(tile.convert("RGB"), dtype=np.float32)
    return Image.fromarray(np.clip(col * al + under * (1.0 - al), 0, 255).astype(np.uint8), "RGB")


if __name__ == "__main__":
    main()
