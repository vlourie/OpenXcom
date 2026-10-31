#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000425: рельсовая ПВО BASEBITS:300 - стволы HD разведены V (левый +5..6 град, правый -5..6), в классике параллельны.

Процедурно, без видеокарты: каждый ствол поворачивается вокруг своего корня (середина ствола у станины) до вертикали - до
параллели с классикой. Поворот - обратное отображение (для точки выхода берётся точка исходника, повёрнутая вокруг корня на угол
w * угол), вес w = 1 на стволе и плавно падает до 0 в 5 пикс (HD 128) от оси и ниже корня, поэтому станина, шар и пол вне
полосы ствола не сдвигаются ни на пиксель. Старое место ствола заполняет пол, взятый рядом со стволом (в 300.png), или
прозрачность (в 300.spin.png).
Ось ствола измеряется по яркости слоя 300.spin.png (центр тяжести тёмных пикселей по строкам, прямая наименьших квадратов).

    py -3.13 tools\hdart\t425_proc.py build        art/tickets/t425/{300.png,300.spin.png} + лист art/_review/tickets_2026-10-30/t425_cand.png
В мод ничего не ставит (арт - сначала показать Vitali).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cv2                                   # noqa: E402
import numpy as np                           # noqa: E402
from PIL import Image                        # noqa: E402

PACK = os.path.join(ROOT, "user", "mods", "hd", "hd", "BASEBITS.PCK")
OUT = os.path.join(ROOT, "art", "tickets", "t425")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")

ROWS = (26, 43)          # строки (HD px), по которым меряется ось ствола (без станины)
Y_ROOT = 47.0            # корень ствола: ниже начинается станина
Y_TOP = 17.0             # выше этой строки (минус 4) вес 0: стена креста над стволами не сдвигается
Y_FADE = 57.0            # к этой строке поворот сходит на нет
LAT_FULL = 5.0           # поле вокруг оси, где вес 1
LAT_FADE = 6.0           # ширина спада


def smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def measure(spin):
    """-> {'L': (угол рад, x оси на строке корня), 'R': ...}; угол - наклон оси от вертикали (x растёт вниз при +)."""
    a = np.asarray(spin).astype(np.float64)
    al = a[..., 3] / 255.0
    w = al * (255.0 - a[..., :3].mean(2)) / 255.0
    out = {}
    for name, (x0, x1) in (("L", (47, 62)), ("R", (66, 82))):
        ys, xs = [], []
        for y in range(ROWS[0], ROWS[1] + 1):
            row = w[y, x0:x1]
            if row.sum() > 0.5:
                ys.append(y)
                xs.append((row * np.arange(x0, x1)).sum() / row.sum())
        sl, ic = np.polyfit(ys, xs, 1)
        out[name] = (math.atan(sl), sl * Y_ROOT + ic)
    return out


def field(shape, ax):
    """Поле источника: (mapx, mapy) для cv2.remap и максимум веса. ax - измерения measure()."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = np.zeros_like(xx)
    dy = np.zeros_like(yy)
    for name, (ang, xp) in ax.items():
        # вес по выходной точке: боковое расстояние до новой (вертикальной) оси и положение ниже корня
        lat = np.abs(xx - xp)
        wl = 1.0 - smooth((lat - LAT_FULL) / LAT_FADE)
        wy = 1.0 - smooth((yy - Y_ROOT) / (Y_FADE - Y_ROOT))
        wt = wl * wy * smooth((yy - Y_TOP) / 4.0)           # выше дульного среза (y 24) пол не трогаем
        a = -ang * wt                       # угол, на который берётся исходная точка
        c, s = np.cos(a), np.sin(a)
        px, py = xx - xp, yy - Y_ROOT
        sx = xp + c * px - s * py
        sy = Y_ROOT + s * px + c * py
        m = wt > 1e-4
        dx = np.where(m, dx + (sx - xx), dx)
        dy = np.where(m, dy + (sy - yy), dy)
    return (xx + dx).astype(np.float32), (yy + dy).astype(np.float32)


def warp(rgba, mx, my):
    """RGBA (PIL) -> повёрнутая; цвет в предумноженной альфе (чтобы края не темнели), кубическая выборка."""
    a = np.asarray(rgba.convert("RGBA")).astype(np.float32) / 255.0
    pm = np.dstack([a[..., :3] * a[..., 3:4], a[..., 3:4]])
    o = cv2.remap(pm, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    al = np.clip(o[..., 3:4], 0, 1)
    rgb = np.where(al > 1e-4, o[..., :3] / np.maximum(al, 1e-4), 0.0)
    # там, где исходник не тронут (вес 0), результат побайтно тот же: кубическая выборка в целых точках точна
    out = np.dstack([np.clip(rgb, 0, 1), al])
    return Image.fromarray(np.rint(out * 255).astype(np.uint8), "RGBA")


def build():
    os.makedirs(OUT, exist_ok=True)
    spin = Image.open(os.path.join(PACK, "300.spin.png")).convert("RGBA")
    still = Image.open(os.path.join(PACK, "300.png")).convert("RGBA")
    ax = measure(spin)
    print("оси: L %.2f град, корень x=%.2f; R %.2f град, корень x=%.2f" % (
        math.degrees(ax["L"][0]), ax["L"][1], math.degrees(ax["R"][0]), ax["R"][1]))
    mx, my = field((128, 128), ax)
    moved = (np.abs(mx - np.mgrid[0:128, 0:128][1]) + np.abs(my - np.mgrid[0:128, 0:128][0])) > 1e-3
    ys, xs = np.nonzero(moved)
    print("тронута область x %d-%d, y %d-%d (%d пикс)" % (xs.min(), xs.max(), ys.min(), ys.max(), moved.sum()))
    new_spin = warp(spin, mx, my)
    new_still = warp(still, mx, my)
    # вне тронутой области - побайтно исходное
    for src, dst in ((spin, new_spin), (still, new_still)):
        a, b = np.asarray(src).copy(), np.asarray(dst).copy()
        keep = ~moved
        b[keep] = a[keep]
        dst.paste(Image.fromarray(b, "RGBA"))
    new_spin.save(os.path.join(OUT, "300.spin.png"))
    new_still.save(os.path.join(OUT, "300.png"))
    after = measure(new_spin)
    print("после: L %.2f град, R %.2f град" % (math.degrees(after["L"][0]), math.degrees(after["R"][0])))
    return spin, still, new_spin, new_still


def comp(under, spin):
    c = under.copy()
    c.alpha_composite(spin)
    return c


def sheet():
    import facility_sheet as fs
    from gen_craft_lights import load_frame
    spin, still, new_spin, new_still = build()
    idx, pal = load_frame(300, fs.sprites_map())
    rgba = np.zeros((32, 32, 4), np.uint8)
    m = idx > 0
    rgba[m, :3] = pal[idx[m]]
    rgba[m, 3] = 255
    cl = Image.fromarray(rgba, "RGBA")
    box = (36, 14, 92, 90)                  # окно вокруг турели, HD px
    z = 8
    bg = (36, 36, 40, 255)

    def crop_hd(im):
        p = Image.new("RGBA", im.size, bg)
        p.alpha_composite(im)
        return p.crop(box).resize(((box[2] - box[0]) * z, (box[3] - box[1]) * z), Image.LANCZOS)

    cl4 = cl.resize((128, 128), Image.NEAREST)
    p0 = Image.new("RGBA", (128, 128), bg)
    p0.alpha_composite(cl4)
    p0 = p0.crop(box).resize(((box[2] - box[0]) * z, (box[3] - box[1]) * z), Image.NEAREST)
    panels = [("классика x32 (стволы параллельны)", p0), ("HD сейчас (300.png)", crop_hd(still)),
              ("кандидат: стволы у корня до параллели", crop_hd(new_still))]
    # направляющие: вертикали по корням
    import ticket_scene as ts
    from PIL import ImageDraw
    ax = measure(spin)
    outs = []
    for i, (t, im) in enumerate(panels):
        d = ImageDraw.Draw(im)
        if i == 0:
            xs = [13.5 * 4, 18.5 * 4]
        else:
            xs = [ax["L"][1], ax["R"][1]]
        for x in xs:
            X = (x - box[0]) * z
            d.line([(X, 20 * z), (X, 52 * z)], fill=(0, 220, 230, 255), width=1)
        outs.append((t, im))
    # второй ряд: сама клетка x4 до/после (турель на ровном месте, в полный вид) + кадр качания (угол max)
    full_now = Image.new("RGBA", (128, 128), bg)
    full_now.alpha_composite(still)
    full_new = Image.new("RGBA", (128, 128), bg)
    full_new.alpha_composite(new_still)
    under = Image.open(os.path.join(PACK, "300.under.png")).convert("RGBA")

    def swung(sp, deg):
        r = sp.rotate(deg, resample=Image.BICUBIC, center=(64.0, 66.2))
        base = Image.new("RGBA", (128, 128), bg)
        base.alpha_composite(under)
        base.alpha_composite(r)
        return base.resize((384, 384), Image.LANCZOS)
    row2 = [("HD сейчас, качание +9.75", swung(spin, 9.75)), ("кандидат, качание +9.75", swung(new_spin, 9.75)),
            ("кандидат, качание -9.75", swung(new_spin, -9.75))]
    W = sum(p.width for _t, p in outs) + 8 * 4
    H1 = max(p.height for _t, p in outs)
    sheetim = Image.new("RGB", (W, H1 + 40 + 384 + 40 + 8), (12, 12, 14))
    x = 8
    for t, p in outs:
        sheetim.paste(ts.label(p.convert("RGB"), t, 20), (x, 8))
        x += p.width + 8
    x = 8
    y2 = H1 + 16
    for t, p in row2:
        sheetim.paste(ts.label(p.convert("RGB"), t, 20), (x, y2))
        x += p.width + 8
    os.makedirs(REV, exist_ok=True)
    sheetim.save(os.path.join(REV, "t425_cand.png"))
    print("лист:", os.path.join(REV, "t425_cand.png"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        sheet()
    else:
        print(__doc__)
