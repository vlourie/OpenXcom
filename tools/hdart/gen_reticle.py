#!/usr/bin/env python3
"""
Прицелы боя (CURSOR.PCK, кадры 6..10) построением, а не генерацией.

Почему не моделью. Кадры 6..10 - это одна и та же фигура: силуэт у всех пяти побайтно
одинаковый, проверено по дампу. Анимация 7->10 - бегущий по клиньям свет: рампа из 12
оттенков, яркое пятно смещается на 4 шага за фазу и идёт СНАРУЖИ ВНУТРЬ, то есть энергия
сходится на цели. Кольцо (B88C38) и ромб (ECE468) не мигают вовсе. Кадр 6 - та же фигура
на красной рампе, неподвижная: цель не видно.

Диффузионная модель такую петлю не держит - она решает каждый кадр заново, и фазы выходят
разными рисунками (грабли R-040). Зато построением всё это задаётся точно, и заодно можно
дать то, чего в 32x40 не было места: сглаживание, свечение, раскалённое ядро.

Геометрия снята с кадра 7 оригинала, в координатах 32x40:
  центр (15.5, 17.5); кольцо R = 12.0; клинья от R = 15.5 внутрь, полуширина 2.5 снаружи
  и 0.4 в центре, сужение начинается с R = 9.5; ромб клетки - центр (15.75, 33.5), 13.5 x 6.

    py -3 tools\\hdart\\gen_reticle.py                      все три стиля в _cmp
    py -3 tools\\hdart\\gen_reticle.py --style plasma --pack user\\mods\\hd\\hd\\CURSOR.PCK

Смотреть петлю, а не кадр: reticle_<стиль>.gif.
"""
import argparse
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FW, FH = 32, 40          # кадр оригинала
SS = 16                  # во сколько раз рисуем крупнее, чтобы получить сглаживание даром

CX, CY = 15.5, 17.5      # центр прицела
R_RING = 12.0            # радиус кольца
R_OUT = 15.5             # докуда клин выходит наружу
R_TAPER = 9.5            # с какого радиуса клин начинает сужаться к центру
R_THIN = 6.5             # ближе этого радиуса от клина остаётся только тонкий хвост
HW_OUT, HW_IN = 2.5, 0.4 # полуширина клина снаружи и в центре
DX, DY, DRX, DRY = 15.75, 33.5, 13.5, 6.0   # ромб клетки

# Рампы взяты из самого оригинала, а не подобраны на глаз: кадр 7 и кадр 6, верхний клин.
YELLOW = [(252, 252, 120), (236, 228, 104), (224, 204, 92), (208, 184, 76),
          (196, 160, 68), (184, 140, 56), (168, 120, 44), (156, 100, 36),
          (140, 80, 28), (128, 64, 20), (116, 48, 12), (100, 32, 8)]
RED = [(252, 120, 120), (236, 104, 104), (224, 92, 92), (208, 76, 76),
       (196, 68, 68), (184, 56, 56), (168, 44, 44), (156, 36, 36),
       (140, 28, 28), (128, 20, 20), (116, 12, 12), (100, 8, 8)]
RING_STEP, DIAMOND_STEP = 5, 1   # какими ступенями рампы покрашены кольцо и ромб в оригинале


def ramp_rgb(ramp, level):
    """level - дробный номер ступени рампы; между ступенями смешиваем."""
    level = np.clip(level, 0.0, len(ramp) - 1.001)
    lo = np.floor(level).astype(np.int32)
    f = (level - lo)[..., None]
    tab = np.asarray(ramp, dtype=np.float32)
    return tab[lo] * (1.0 - f) + tab[lo + 1] * f


def fields():
    """Сетка в координатах оригинала: для каждого подпикселя - где он и чему принадлежит."""
    xs = (np.arange(FW * SS, dtype=np.float32) + 0.5) / SS
    ys = (np.arange(FH * SS, dtype=np.float32) + 0.5) / SS
    x = xs[None, :] - CX
    y = ys[:, None] - CY
    x = np.broadcast_to(x, (FH * SS, FW * SS)).copy()
    y = np.broadcast_to(y, (FH * SS, FW * SS)).copy()
    r = np.hypot(x, y)
    return xs, ys, x, y, r


def wedge_mask_u(x, y, extra_hw=0.0):
    """Четыре клина: маска покрытия и u - путь вдоль клина, 0 снаружи, 1 в центре.

    Клин считается по своей оси: вдоль - s (расстояние от центра), поперёк - t.
    Профиль взят с дампа кадра 7, а не придуман: от края до R_TAPER ширина ПОСТОЯННА,
    от R_TAPER до R_THIN быстрое сужение, ближе к центру - тонкий хвост в один пиксель.
    Если сужать по всей длине, четыре клина сливаются в бабочку вместо креста."""
    cover = np.zeros(x.shape, dtype=np.float32)
    u = np.zeros(x.shape, dtype=np.float32)
    for ax in (0, 1):
        s = np.abs(y) if ax == 0 else np.abs(x)      # вдоль оси клина
        t = np.abs(x) if ax == 0 else np.abs(y)      # поперёк
        k = np.clip((s - R_THIN) / (R_TAPER - R_THIN), 0.0, 1.0)
        hw = HW_IN + (HW_OUT - HW_IN) * k + extra_hw
        inside = (s <= R_OUT) & (t <= hw)
        uu = np.clip(1.0 - s / R_OUT, 0.0, 1.0)
        cover = np.where(inside, 1.0, cover)
        u = np.where(inside, uu, u)
    return cover, u


def travelling_level(u, phase, phases=4, plateau=1.5, span=12.0):
    """Бегущий свет: яркое пятно в точке peak, дальше падение по рампе.

    В оригинале пятно стоит на 0, 4, 8 и 12 ступенях из тринадцати - то есть за петлю
    проходит клин насквозь снаружи внутрь. Плато в полторы ступени - тоже из оригинала:
    у кадра 7 три верхних пикселя одного цвета."""
    peak = phase / float(phases - 1) if phases > 1 else 0.0
    d = np.abs(u - peak) * span
    return np.clip(d - plateau, 0.0, span - 1.0)


def ring_cover(r, width):
    return (np.abs(r - R_RING) <= width * 0.5).astype(np.float32)


def ring_cover_gapped(r, x, y, width, gap_hw):
    """Кольцо с разрывами там, где его пересекают клинья."""
    c = ring_cover(r, width)
    near_axis = (np.abs(x) <= gap_hw) | (np.abs(y) <= gap_hw)
    return np.where(near_axis, 0.0, c)


def diamond_cover(xs, ys, width):
    x = xs[None, :] - DX
    y = ys[:, None] - DY
    d = np.abs(x) / DRX + np.abs(y) / DRY
    # толщина обводки в исходных пикселях -> в единицах d
    w = width / min(DRX, DRY)
    return ((d >= 1.0 - w) & (d <= 1.0 + w)).astype(np.float32)


def ticks_cover(xs, ys, x, y, r, count=8, inner=13.2, outer=15.0, hw=0.35):
    """Засечки снаружи кольца - по диагоналям, чтобы не спорить с клиньями."""
    c = np.zeros(x.shape, dtype=np.float32)
    band = (r >= inner) & (r <= outer)
    ang = np.arctan2(y, x)
    for k in range(count):
        a = (k + 0.5) * (2.0 * math.pi / count)
        da = np.abs(np.arctan2(np.sin(ang - a), np.cos(ang - a)))
        c = np.where(band & (da * r <= hw), 1.0, c)
    return c


def compose(layers, size):
    """Слои (цвет RGB float, покрытие float) -> RGBA в размере кадра пака."""
    h, w = layers[0][1].shape
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    a = np.zeros((h, w), dtype=np.float32)
    for col, cov in layers:
        cov = np.clip(cov, 0.0, 1.0)
        rgb = rgb * (1.0 - cov[..., None]) + col * cov[..., None]
        a = np.maximum(a, cov)
    im = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a * 255.0]).astype(np.uint8), "RGBA")
    return im.resize(size, Image.LANCZOS)


def bloom(img, radius, strength):
    """Свечение: размытая копия под картинкой. То, чего в 32x40 не помещалось."""
    if strength <= 0:
        return img
    glow = img.filter(ImageFilter.GaussianBlur(radius))
    g = np.asarray(glow, dtype=np.float32)
    g[..., 3] *= strength
    base = np.asarray(img, dtype=np.float32)
    ga = g[..., 3:4] / 255.0
    ba = base[..., 3:4] / 255.0
    out_a = ga + ba * (1.0 - ga)
    safe = np.maximum(out_a, 1e-4)
    out_rgb = (g[..., :3] * ga + base[..., :3] * ba * (1.0 - ga)) / safe
    return Image.fromarray(np.dstack([np.clip(out_rgb, 0, 255),
                                      np.clip(out_a * 255.0, 0, 255)]).astype(np.uint8), "RGBA")


def render(style, ramp, phase, phases, scale):
    xs, ys, x, y, r = fields()
    size = (FW * scale, FH * scale)
    hot = np.asarray((255, 255, 236), dtype=np.float32) if ramp is YELLOW \
        else np.asarray((255, 236, 236), dtype=np.float32)

    if style == "plasma":
        cover, u = wedge_mask_u(x, y)
        lvl = travelling_level(u, phase, phases)
        col = ramp_rgb(ramp, lvl)
        # раскалённое ядро: у самого пятна цвет уходит в белый
        heat = np.clip(1.0 - lvl / 0.7, 0.0, 1.0)[..., None] * 0.75
        col = col * (1.0 - heat) + hot * heat
        layers = [(ramp_rgb(ramp, np.full(r.shape, float(RING_STEP))), ring_cover(r, 1.9)),
                  (ramp_rgb(ramp, np.full(r.shape, float(DIAMOND_STEP))), diamond_cover(xs, ys, 0.85)),
                  (col, cover)]
        img = compose(layers, size)
        img = bloom(img, radius=max(1, int(scale * 0.7)), strength=0.34)

    elif style == "techno":
        cover, u = wedge_mask_u(x, y, extra_hw=-0.35)
        lvl = travelling_level(u, phase, phases, plateau=0.4, span=14.0)
        col = ramp_rgb(ramp, lvl)
        edge = np.clip(1.0 - lvl / 0.6, 0.0, 1.0)[..., None]   # узкая белая кромка на фронте волны
        col = col * (1.0 - edge) + hot * edge
        ring_col = ramp_rgb(ramp, np.full(r.shape, float(RING_STEP) - 1.0))
        layers = [(ring_col, ring_cover(r, 1.0)),
                  (ramp_rgb(ramp, np.full(r.shape, float(RING_STEP) + 2.0)),
                   ring_cover_gapped(r + (R_RING - 8.0), x, y, 0.7, 1.2)),
                  (ring_col, ticks_cover(xs, ys, x, y, r)),
                  (ramp_rgb(ramp, np.full(r.shape, float(DIAMOND_STEP) + 1.0)),
                   diamond_cover(xs, ys, 0.55)),
                  (col, cover)]
        img = compose(layers, size)
        img = bloom(img, radius=max(1, int(scale * 0.4)), strength=0.22)

    elif style == "predator":
        cover, u = wedge_mask_u(x, y, extra_hw=0.35)
        lvl = travelling_level(u, phase, phases, plateau=2.2, span=11.0)
        col = ramp_rgb(ramp, lvl)
        heat = np.clip(1.0 - lvl / 1.0, 0.0, 1.0)[..., None] * 0.70
        col = col * (1.0 - heat) + hot * heat
        layers = [(ramp_rgb(ramp, np.full(r.shape, float(RING_STEP) - 1.0)),
                   ring_cover_gapped(r, x, y, 2.6, HW_OUT + 1.2)),
                  (ramp_rgb(ramp, np.full(r.shape, float(DIAMOND_STEP))), diamond_cover(xs, ys, 1.1)),
                  (col, cover)]
        img = compose(layers, size)
        img = bloom(img, radius=max(2, scale), strength=0.34)

    elif style == "ring45":
        # то же кольцо, но клинья по диагоналям и обрезаны до центра: середина пустая,
        # линии не пересекаются. Поворот на 45 градусов - просто другой базис для тех же клиньев
        c45 = math.sqrt(0.5)
        xr, yr = (x - y) * c45, (x + y) * c45
        cover, u = wedge_mask_u(xr, yr)
        cover = np.where(r >= R_HOLE, cover, 0.0)
        lvl = travelling_level(u, phase, phases)
        col = ramp_rgb(ramp, lvl)
        heat = np.clip(1.0 - lvl / 0.7, 0.0, 1.0)[..., None] * 0.75
        col = col * (1.0 - heat) + hot * heat
        layers = [(ramp_rgb(ramp, np.full(r.shape, float(RING_STEP))), ring_cover(r, 1.9)),
                  (ramp_rgb(ramp, np.full(r.shape, float(DIAMOND_STEP))), diamond_cover(xs, ys, 0.85)),
                  (col, cover)]
        img = compose(layers, size)
        img = bloom(img, radius=max(1, int(scale * 0.7)), strength=0.34)

    else:
        raise SystemExit("нет такого стиля: %s" % style)
    return img


R_HOLE = 4.0             # ring45: ближе этого радиуса клиньев нет - центр пустой

STYLES = ("plasma", "techno", "predator", "ring45")
STYLE_RU = {"plasma": "Плазма", "techno": "Техно", "predator": "Хищник", "ring45": "Кольцо 45"}


def checker(im, step=16):
    bg = Image.new("RGB", im.size, (58, 56, 54))
    d = ImageDraw.Draw(bg)
    for yy in range(0, im.height, step):
        for xx in range(0, im.width, step):
            if (xx // step + yy // step) % 2 == 0:
                d.rectangle((xx, yy, xx + step - 1, yy + step - 1), fill=(82, 80, 78))
    bg.paste(im, (0, 0), im)
    return bg


def on_floor(im, zoom):
    """Как в бою: на тёмном полу, без затенения."""
    bg = Image.new("RGBA", im.size, (38, 32, 28, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize((im.width * zoom, im.height * zoom), Image.NEAREST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", default="", choices=("",) + STYLES,
                    help="пусто - нарисовать все три на выбор")
    ap.add_argument("--scale", type=int, default=4, help="масштаб пака: кадр будет 32k x 40k")
    ap.add_argument("--out", default="art/_review/_cmp", help="куда класть листы и петли")
    ap.add_argument("--pack", default="", help="каталог пака: сюда лягут 6.png..10.png")
    ap.add_argument("--gif-ms", type=int, default=110, dest="gif_ms")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    styles = [args.style] if args.style else list(STYLES)
    f = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 15)

    for style in styles:
        frames = {6: render(style, RED, 0, 1, args.scale)}
        for n in range(4):
            frames[7 + n] = render(style, YELLOW, n, 4, args.scale)

        W = FW * args.scale * 4
        H = FH * args.scale * 4
        board = Image.new("RGB", (5 * (W + 8), H + 22), (25, 25, 28))
        dr = ImageDraw.Draw(board)
        for n, i in enumerate(sorted(frames)):
            big = frames[i].resize((W, H), Image.LANCZOS)
            dr.text((n * (W + 8) + 4, 2), "%d%s" % (i, " красный" if i == 6 else ""),
                    font=f, fill=(230, 230, 230))
            board.paste(checker(big), (n * (W + 8), 19))
        sheet = os.path.join(args.out, "reticle_%s.png" % style)
        board.save(sheet)

        loop = [on_floor(frames[i], 3) for i in (7, 8, 9, 10)]
        gif = os.path.join(args.out, "reticle_%s.gif" % style)
        loop[0].save(gif, save_all=True, append_images=loop[1:], duration=args.gif_ms, loop=0)
        print("%-9s лист %s   петля %s" % (STYLE_RU[style], sheet, gif))

        if args.pack:
            os.makedirs(args.pack, exist_ok=True)
            for i, im in sorted(frames.items()):
                im.save(os.path.join(args.pack, "%d.png" % i))
            print("           в пак: кадры 6..10 -> %s" % args.pack)


if __name__ == "__main__":
    main()
