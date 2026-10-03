"""Прицелы v2: тонкие версии нынешних и 10 новых. Та же механика, что у gen_reticle.py:
кадр 6 - красный неподвижный (цели не видно), 7..10 - жёлтая петля из 4 фаз, сходится на цель.
Геометрия центра и ромба клетки - как у оригинала. Ключи стилей = Mod::HD_RETICLES в движке
(папки hd/CURSOR.PCK/reticle_<ключ>/6..10.png), порядок там менять нельзя - номер в options.cfg.

    py -3.13 tools\\hdart\\gen_reticle_v2.py                 листы thin/new10 (png и gif) в art/_review/reticle_v2
    py -3.13 tools\\hdart\\gen_reticle_v2.py --pack user\\mods\\hd\\hd\\CURSOR.PCK --pack <копия мода в Пиратках>
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_reticle as g  # noqa: E402

K = 4
OUT = r"E:\OpenXCom\art\_review\reticle_v2"
SSO = g.SS // K          # подпикселей на пиксель пака

XS, YS, X, Y, R = g.fields()
ANG = np.arctan2(Y, X)


# ---------------------------------------------------------------- примитивы (покрытие 0/1 на сетке SS)
def seg(x0, y0, x1, y1, hw):
    """Отрезок в координатах от центра: покрытие и t - 0 у (x0,y0), 1 у (x1,y1)."""
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    t = np.clip(((X - x0) * dx + (Y - y0) * dy) / L2, 0.0, 1.0)
    d = np.hypot(X - (x0 + t * dx), Y - (y0 + t * dy))
    return (d <= hw).astype(np.float32), t


def ring(r0, w):
    return (np.abs(R - r0) <= w * 0.5).astype(np.float32)


def disc(r0, cx=0.0, cy=0.0):
    return (np.hypot(X - cx, Y - cy) <= r0).astype(np.float32)


def diamond(width):
    return g.diamond_cover(XS, YS, width)


def wedges(f, rot=0.0, hole=0.0):
    """Клинья оригинала с шириной, умноженной на f; rot - поворот, hole - пустой центр."""
    c, s = math.cos(rot), math.sin(rot)
    x, y = X * c + Y * s, -X * s + Y * c
    cover = np.zeros(X.shape, np.float32)
    u = np.zeros(X.shape, np.float32)
    for ax in (0, 1):
        a = np.abs(y) if ax == 0 else np.abs(x)
        t = np.abs(x) if ax == 0 else np.abs(y)
        k = np.clip((a - g.R_THIN) / (g.R_TAPER - g.R_THIN), 0.0, 1.0)
        hw = np.maximum((g.HW_IN + (g.HW_OUT - g.HW_IN) * k) * f, 0.16)
        inside = (a <= g.R_OUT) & (t <= hw) & (R >= hole)
        cover = np.where(inside, 1.0, cover)
        u = np.where(inside, np.clip(1.0 - a / g.R_OUT, 0, 1), u)
    return cover, u


def flat(ramp, step):
    return g.ramp_rgb(ramp, np.full(R.shape, float(step)))


def running(ramp, u, phase, phases=4, plateau=1.5, span=12.0, heat=0.75, hot=None):
    lvl = g.travelling_level(u, phase, phases, plateau, span)
    col = g.ramp_rgb(ramp, lvl)
    h = np.clip(1.0 - lvl / 0.7, 0, 1)[..., None] * heat
    return col * (1 - h) + hot * h


# ---------------------------------------------------------------- сборка
def compose(layers):
    """Слои (цвет, покрытие, непрозрачность) с честной альфой; уменьшение - среднее по блоку."""
    h, w = R.shape
    rgb = np.zeros((h, w, 3), np.float32)
    a = np.zeros((h, w), np.float32)
    for col, cov, op in layers:
        c = (np.clip(cov, 0, 1) * op)
        if np.ndim(op):
            c = np.clip(cov, 0, 1) * op
        rgb = rgb * (1 - c[..., None]) + col * c[..., None]
        a = a * (1 - c) + c
    H, W = h // SSO, w // SSO
    rgb = rgb.reshape(H, SSO, W, SSO, 3).mean(axis=(1, 3))
    a = a.reshape(H, SSO, W, SSO).mean(axis=(1, 3))
    out = rgb / np.maximum(a, 1e-4)[..., None]
    return Image.fromarray(np.dstack([np.clip(out, 0, 255), a * 255]).astype(np.uint8), "RGBA")


def finish(layers, glow=0.0, rad=2):
    img = compose(layers)
    return g.bloom(img, rad, glow) if glow > 0 else img


# ---------------------------------------------------------------- стили
def thin_classic(kind, ramp, ph, hot):
    """Те же 4 стиля, линии примерно вдвое тоньше, свечение слабее."""
    if kind == "ring45":
        cov, u = wedges(0.45, math.pi / 4, hole=g.R_HOLE)
        return finish([(flat(ramp, g.RING_STEP), ring(g.R_RING, 0.8), 1.0),
                       (flat(ramp, g.DIAMOND_STEP), diamond(0.4), 1.0),
                       (running(ramp, u, ph, hot=hot), cov, 1.0)], 0.22, 2)
    if kind == "plasma":
        cov, u = wedges(0.45)
        return finish([(flat(ramp, g.RING_STEP), ring(g.R_RING, 0.8), 1.0),
                       (flat(ramp, g.DIAMOND_STEP), diamond(0.4), 1.0),
                       (running(ramp, u, ph, hot=hot), cov, 1.0)], 0.22, 2)
    if kind == "techno":
        cov, u = wedges(0.35)
        rc = flat(ramp, g.RING_STEP - 1)
        inner = ring(8.0, 0.4) * ((np.abs(X) > 1.0) & (np.abs(Y) > 1.0))
        return finish([(rc, ring(g.R_RING, 0.45), 1.0),
                       (flat(ramp, g.RING_STEP + 2), inner, 1.0),
                       (rc, g.ticks_cover(XS, YS, X, Y, R, hw=0.18), 1.0),
                       (flat(ramp, g.DIAMOND_STEP + 1), diamond(0.3), 1.0),
                       (running(ramp, u, ph, plateau=0.4, span=14.0, heat=1.0, hot=hot), cov, 1.0)], 0.15, 1)
    if kind == "predator":
        cov, u = wedges(0.6)
        gap = (np.abs(X) > 2.2) & (np.abs(Y) > 2.2)
        return finish([(flat(ramp, g.RING_STEP - 1), ring(g.R_RING, 1.2) * gap, 1.0),
                       (flat(ramp, g.DIAMOND_STEP), diamond(0.55), 1.0),
                       (running(ramp, u, ph, plateau=2.2, span=11.0, heat=0.7, hot=hot), cov, 1.0)], 0.28, 3)
    raise SystemExit(kind)


def lasers(ramp, ph, hot, axes=False):
    """Четыре тонких луча из-за края сходятся в центре цели; по лучу бежит вспышка внутрь,
    на последней фазе в центре загорается точка."""
    layers = [(flat(ramp, g.DIAMOND_STEP + 1), diamond(0.2), 0.85)]
    L = 15.5
    dirs = [(0, -1), (1, 0), (0, 1), (-1, 0)] if axes else \
        [(c * math.sqrt(0.5), s * math.sqrt(0.5)) for c, s in ((1, 1), (1, -1), (-1, 1), (-1, -1))]
    for dx, dy in dirs:
        halo, _ = seg(dx * L, dy * L, dx * 0.9, dy * 0.9, 0.5)
        layers.insert(0, (np.zeros(R.shape + (3,), np.float32), halo, 0.3))   # тень: луч виден и на светлом
        cov, t = seg(dx * L, dy * L, dx * 0.9, dy * 0.9, 0.22)
        col = running(ramp, t, ph, plateau=0.5, span=10.0, heat=0.9, hot=hot)
        op = 0.7 + 0.3 * t                         # луч гуще к цели
        layers.append((col, cov, op))
    arrive = 1.0 if ph == 3 else 0.35
    layers.append((hot, disc(0.55), arrive))
    layers.append((flat(ramp, 2), ring(1.6, 0.25), 0.8))
    return finish(layers, 0.45, 2)


def brackets(ramp, ph, hot):
    """Четыре угла рамки съезжаются к цели и разгораются; рамка - захват."""
    d = 12.0 - 1.4 * ph                            # от 12 до 7.8
    lvl = 6.0 - 2.0 * ph
    col = flat(ramp, lvl) if ph < 3 else hot * 0.4 + flat(ramp, 0) * 0.6
    cov = np.zeros(R.shape, np.float32)
    arm = 3.2
    for sx in (-1, 1):
        for sy in (-1, 1):
            cov = np.maximum(cov, seg(sx * d, sy * d, sx * (d - arm), sy * d, 0.2)[0])
            cov = np.maximum(cov, seg(sx * d, sy * d, sx * d, sy * (d - arm), 0.2)[0])
    return finish([(flat(ramp, g.DIAMOND_STEP + 1), diamond(0.2), 0.85),
                   (flat(ramp, 3), disc(0.45), 1.0),
                   (col, cov, 1.0)], 0.3, 2)


def ripple(ramp, ph, hot):
    """Три тонких круга сжимаются к центру - волна, сходящаяся на цель. Петля бесшовная."""
    layers = [(flat(ramp, g.DIAMOND_STEP + 1), diamond(0.2), 0.85)]
    step = 4.5
    for j in range(4):
        r0 = 14.5 - step * ((ph / 4.0 + j) % 3.0) if j < 3 else None
        if r0 is None:
            continue
        fade = np.clip(r0 / 14.5, 0, 1)
        layers.append((flat(ramp, 1 + 6 * (1 - fade)), ring(r0, 0.35), 0.35 + 0.65 * (1 - fade)))
    layers.append((hot, disc(0.6), 1.0))
    return finish(layers, 0.35, 2)


def sniper(ramp, ph, hot):
    """Снайперская сетка: тонкое кольцо, нити креста с разрывом в центре, по 3 метки на нити;
    метки загораются по очереди к центру."""
    rc = flat(ramp, g.RING_STEP)
    hair = np.zeros(R.shape, np.float32)
    for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
        hair = np.maximum(hair, seg(dx * 14.5, dy * 14.5, dx * 2.2, dy * 2.2, 0.12)[0])
    layers = [(rc, ring(g.R_RING, 0.3), 1.0), (rc, hair, 1.0),
              (flat(ramp, g.DIAMOND_STEP + 1), diamond(0.2), 0.85)]
    for n, rr in enumerate((10.0, 7.0, 4.2)):
        on = (ph == n + 1) or (ph == 0 and n == 0 and False)
        col = hot if on else flat(ramp, 2)
        dots = np.zeros(R.shape, np.float32)
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            dots = np.maximum(dots, disc(0.42 if on else 0.3, dx * rr, dy * rr))
        layers.append((col, dots, 1.0))
    layers.append((hot if ph == 0 else flat(ramp, 1), disc(0.3), 1.0))
    return finish(layers, 0.25, 2)


def chevrons(ramp, ph, hot):
    """По два шеврона на каждой оси ползут к центру конвейером; петля бесшовная."""
    layers = [(flat(ramp, g.DIAMOND_STEP + 1), diamond(0.2), 0.85)]
    for j in range(2):
        s = 14.0 - 5.0 * ((ph / 4.0 + j) % 2.0)    # 14 -> 4
        lvl = np.clip((s - 4.0) / 10.0, 0, 1) * 8.0
        col = flat(ramp, lvl)
        cov = np.zeros(R.shape, np.float32)
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            px, py = -dy, dx
            tip = (dx * (s - 1.6), dy * (s - 1.6))
            for side in (-1, 1):
                cov = np.maximum(cov, seg(dx * s + side * px * 1.6, dy * s + side * py * 1.6,
                                          tip[0], tip[1], 0.2)[0])
        layers.append((col, cov, 1.0))
    layers.append((flat(ramp, g.RING_STEP), ring(g.R_RING, 0.3) * 0.0, 1.0))
    layers.append((hot, disc(0.45), 1.0))
    return finish(layers, 0.3, 2)


def dashed(ramp, ph, hot):
    """Пунктирное кольцо поворачивается (22.5 градуса за фазу, петля в 90), внутрь смотрят
    четыре короткие засечки, в центре точка."""
    rot = ph * (math.pi / 8)
    dash = (np.cos((ANG - rot) * 12) > 0.15)
    layers = [(flat(ramp, g.RING_STEP - 1), ring(g.R_RING, 0.45) * dash, 1.0),
              (flat(ramp, g.DIAMOND_STEP + 1), diamond(0.2), 0.85)]
    tick = np.zeros(R.shape, np.float32)
    for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
        tick = np.maximum(tick, seg(dx * 10.0, dy * 10.0, dx * 6.0, dy * 6.0, 0.2)[0])
    layers.append((flat(ramp, 1), tick, 1.0))
    layers.append((hot, disc(0.5), 1.0))
    return finish(layers, 0.28, 2)


def trilock(ramp, ph, hot):
    """Три дуги и три жала по 120 градусов; вся фигура поворачивается на 30 градусов за фазу."""
    rot = ph * (math.pi / 6)
    a = (ANG - rot) % (2 * math.pi / 3)
    arcs = ring(g.R_RING - 1.0, 0.45) * ((a > 0.35) & (a < 2 * math.pi / 3 - 0.35))
    stings = np.zeros(R.shape, np.float32)
    for k in range(3):
        th = rot + k * 2 * math.pi / 3
        c, s = math.cos(th), math.sin(th)
        for side in (-1, 1):
            px, py = -s * side * 1.4, c * side * 1.4
            stings = np.maximum(stings, seg(c * 13.5 + px, s * 13.5 + py, c * 6.5, s * 6.5, 0.18)[0])
    return finish([(flat(ramp, g.RING_STEP), arcs, 1.0),
                   (flat(ramp, g.DIAMOND_STEP + 1), diamond(0.2), 0.85),
                   (flat(ramp, 1), stings, 1.0),
                   (hot, disc(0.45), 1.0)], 0.3, 2)


def dot(ramp, ph, hot):
    """Почти ничего: полое кольцо-точка в центре дышит, на ромбе - только углы."""
    r0 = 2.6 - 0.45 * ph
    x = XS[None, :] - g.DX
    y = YS[:, None] - g.DY
    dd = np.abs(x) / g.DRX + np.abs(y) / g.DRY
    corners = ((np.abs(x) > g.DRX * 0.62) | (np.abs(y) > g.DRY * 0.62))
    dia = ((dd >= 1 - 0.05) & (dd <= 1 + 0.05) & corners).astype(np.float32)
    return finish([(flat(ramp, g.DIAMOND_STEP), dia, 1.0),
                   (flat(ramp, 4 - ph), ring(r0, 0.35), 1.0),
                   (hot, disc(0.4), 1.0 if ph == 3 else 0.6)], 0.35, 2)


def ghost(ramp, ph, hot):
    """Почти прозрачный: тонкая Плазма на трети непрозрачности, видна только бегущая искра."""
    cov, u = wedges(0.4)
    lvl = g.travelling_level(u, ph, 4, 0.3, 12.0)
    spark = np.clip(1.0 - lvl / 1.5, 0, 1)
    col = g.ramp_rgb(ramp, lvl)
    col = col * (1 - spark[..., None] * 0.8) + hot * spark[..., None] * 0.8
    op = 0.28 + 0.72 * spark
    return finish([(flat(ramp, g.RING_STEP), ring(g.R_RING, 0.6), 0.28),
                   (flat(ramp, g.DIAMOND_STEP), diamond(0.35), 0.4),
                   (col, cov, op)], 0.3, 2)


NEW = [
    ("lasers", "Лазеры", lambda r, p, h: lasers(r, p, h)),
    ("lasercross", "Лазерный крест", lambda r, p, h: lasers(r, p, h, axes=True)),
    ("brackets", "Захват (уголки)", brackets),
    ("ripple", "Сходящиеся круги", ripple),
    ("sniper", "Снайпер", sniper),
    ("chevrons", "Шевроны", chevrons),
    ("dashed", "Пунктир", dashed),
    ("trilock", "Трилистник", trilock),
    ("dot", "Точка", dot),
    ("ghost", "Призрак", ghost),
]
THIN = [("thin_" + k, ru + " тонкий" if k == "predator" else ru + " тонкая" if k in ("plasma",) else ru + " тонкое",
         (lambda kk: lambda r, p, h: thin_classic(kk, r, p, h))(k))
        for k, ru in (("ring45", "Кольцо 45"), ("plasma", "Плазма"), ("techno", "Техно"), ("predator", "Хищник"))]


def frames_of(fn):
    hot_y = np.asarray((255, 255, 236), np.float32)
    hot_r = np.asarray((255, 236, 236), np.float32)
    fr = {6: fn(g.RED, 0, hot_r)}
    for n in range(4):
        fr[7 + n] = fn(g.YELLOW, n, hot_y)
    return fr


def tile(im, bg=(52, 46, 40)):
    t = Image.new("RGBA", im.size, bg + (255,))
    t.alpha_composite(im)
    return t.convert("RGB")


def board(rows, title, path, gif_path):
    FW, FH = 32 * K, 40 * K
    LW, PAD, TOP = 230, 10, 44
    W = LW + 6 * (FW + PAD) + PAD
    H = TOP + len(rows) * (FH + PAD) + PAD
    fb = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 19)
    fs = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 14)
    sheet = Image.new("RGB", (W, H), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    d.text((10, 10), title, font=fb, fill=(255, 255, 255))
    for n, t in enumerate(["6 цели нет", "7", "8", "9", "10", "на светлом"]):
        d.text((LW + PAD + n * (FW + PAD), 22), t, font=fs, fill=(190, 190, 190))
    anim = [sheet.copy() for _ in range(4)]
    for r, (key, ru, fr) in enumerate(rows):
        y = TOP + r * (FH + PAD)
        for img in [sheet] + anim:
            ImageDraw.Draw(img).text((10, y + FH // 2 - 12), "%d  %s" % (r + 1, ru), font=fb, fill=(235, 235, 235))
        for n, i in enumerate(range(6, 11)):
            sheet.paste(tile(fr[i]), (LW + PAD + n * (FW + PAD), y))
        sheet.paste(tile(fr[8], (150, 140, 118)), (LW + PAD + 5 * (FW + PAD), y))
        for p in range(4):
            anim[p].paste(tile(fr[6]), (LW + PAD, y))
            for n in range(4):
                anim[p].paste(tile(fr[7 + p]), (LW + PAD + (n + 1) * (FW + PAD), y))
            anim[p].paste(tile(fr[7 + p], (150, 140, 118)), (LW + PAD + 5 * (FW + PAD), y))
    sheet.save(path)
    pal = [a.quantize(colors=255, method=Image.Quantize.MEDIANCUT) for a in anim]
    pal[0].save(gif_path, save_all=True, append_images=pal[1:], duration=110, loop=0)
    print(path, gif_path, sheet.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT, help="куда класть листы и кадры на просмотр")
    ap.add_argument("--pack", action="append", default=[],
                    help="каталог CURSOR.PCK мода: сюда лягут reticle_<ключ>/6..10.png (можно несколько)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rows_thin = [(k, ru, frames_of(fn)) for k, ru, fn in THIN]
    rows_new = [(k, ru, frames_of(fn)) for k, ru, fn in NEW]
    for k, ru, fr in rows_thin + rows_new:
        for root in [args.out] + args.pack:
            dd = os.path.join(root, "reticle_" + k)
            os.makedirs(dd, exist_ok=True)
            for i, im in fr.items():
                im.save(os.path.join(dd, "%d.png" % i))
    board(rows_thin, "Тонкие версии нынешних прицелов", os.path.join(args.out, "thin.png"), os.path.join(args.out, "thin.gif"))
    board(rows_new, "10 новых прицелов", os.path.join(args.out, "new10.png"), os.path.join(args.out, "new10.gif"))
    for root in args.pack:
        print("в пак: %d стилей -> %s" % (len(rows_thin) + len(rows_new), root))


if __name__ == "__main__":
    main()
