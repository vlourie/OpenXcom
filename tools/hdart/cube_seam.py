"""Кубы массивов без швов: процедурная правка пака, без генерации (20.10, R-403).

Брак пака у кадров полного куба (силуэт 01a04fe05dc1: GOVTDECOR:5, SGR_BASIS:1, MUSTYX 60-67 и подобные): каждый
блок нарисован отдельным предметом - фаска и светлая крошка по краю, полупрозрачный край альфы. Одиночный кадр
хорош, а в массиве (тот же кадр со сдвигом на период изорешётки и на этаж) крыша идёт сеткой, на боках
вертикальные швы, между этажами светлая полоса. У классики - сплошной монолит.

Что делается с кадром:
  1. Альфа - силуэт классики xk (край ровный, стык с соседом без просвета); пиксели, которых у пака не было,
     заливаются содержимым грани (inpaint).
  2. Каждая грань (верх, левая, правая) делается периодичной: у краёв пак плавно заменяется своей же гранью,
     сдвинутой внутрь (приём бесшовной плитки). Верх - на полпериода по обеим осям решётки; бока - на число
     периодов кладки (автокорреляция грани), ближайшее к половине, иначе в переходе ряды двоятся.
  3. Чей пиксель (верх / левая / правая) - по центру пикселя классики; у классики ромб верха на 0.5 пикселя ниже
     края кадра. Иначе в зубцах ступенек силуэта соседа видна грань.
Не для кадров, где у классики у каждого блока свой рисунок (окна, приборы, панели) или полоса между этажами есть
в самой классике. Проверка - cube_seam_scan.py (мерка швов стопки 2x2x2) и лист стопок классика | пак | новое.

    tools/hdart/.venv/Scripts/python.exe tools/hdart/cube_seam.py <папка>/TERRAIN GOVTDECOR 5,12 [E B]
E - полоса полной замены у края, B - перехода, в пикселях классики (1 и 2).
"""
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb  # noqa: E402

GAME = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN"
E, B = 1.0, 2.0


def ramp(d, k):
    """вес своего пикселя по расстоянию d (пиксели) до края грани: 0 в полосе E, 1 после E+B"""
    x = np.clip((d - E * k) / (B * k), 0, 1)
    return x * x * (3 - 2 * x)


def periodic(img, inside, d1, d2, sh1, sh2, k):
    """img HxWx4 float; inside - маска грани; d1/d2 - расстояние до края по двум осям решётки (пиксели);
    sh1/sh2 - функции (ys, xs) -> (ys', xs') сдвига внутрь по каждой оси"""
    ys, xs = np.nonzero(inside)
    w1, w2 = ramp(d1[ys, xs], k), ramp(d2[ys, xs], k)
    y1, x1 = sh1(ys, xs)
    y2, x2 = sh2(ys, xs)
    y12, x12 = sh2(y1, x1)
    o = img.copy()
    o[ys, xs, :3] = ((w1 * w2)[:, None] * img[ys, xs, :3] + ((1 - w1) * w2)[:, None] * img[y1, x1, :3]
                     + (w1 * (1 - w2))[:, None] * img[y2, x2, :3] + ((1 - w1) * (1 - w2))[:, None] * img[y12, x12, :3])
    return o


def period(a, axis, lo, hi):
    """лаг с наибольшей автокорреляцией в [lo, hi] и сама корреляция"""
    best, bl = -9.0, lo
    for lag in range(lo, hi + 1):
        u, v = (a[:-lag], a[lag:]) if axis == 0 else (a[:, :-lag], a[:, lag:])
        c = float((u * v).mean() / (u.std() * v.std() + 1e-6))
        if c > best:
            best, bl = c, lag
    return bl, best


def fix(im, cl):
    """im - пак HxWx4 float, cl - кадр классики (индексы); вернуть сшитый кадр и строку отчёта"""
    H, W = im.shape[:2]
    K = W // 32
    cu = np.kron((cl > 0).astype(np.uint8), np.ones((K, K), np.uint8))
    hole = ((im[..., 3] < 250) & (cu > 0)).astype(np.uint8) * 255
    im = im.copy()
    im[..., :3] = cv2.inpaint(np.clip(im[..., :3], 0, 255).astype(np.uint8), hole, 2 * K, cv2.INPAINT_TELEA)
    im[..., 3] = cu * 255.0
    L, hy, hz = 16 * K, 8 * K, 24 * K           # полширины ромба, полвысоты, высота блока
    yraw, xx = np.mgrid[0:H, 0:W].astype(np.float32) + 0.5
    yy = yraw - 0.5 * K                         # у классики вершина ромба на 0.5 пикселя ниже края кадра
    op = im[..., 3] > 0
    # верх: al вдоль gx (N->E), be вдоль gy (N->W), обе 0..1; полпериода - вектор (L/2, hy/2)
    al = (xx - L) / (2 * L) + yy / (2 * hy)
    be = yy / (2 * hy) - (xx - L) / (2 * L)
    yc, xc = (np.floor(yraw / K) + 0.5) * K - 0.5 * K, (np.floor(xx / K) + 0.5) * K
    tc = np.where(xc < L, yc - (hy + xc / 2), yc - (2 * hy - (xc - L) / 2))
    top = op & (tc < 0)
    sides = [op & (xc < L) & (tc >= 0), op & (xc >= L) & (tc >= 0)]
    da = np.minimum(al, 1 - al) * L
    db = np.minimum(be, 1 - be) * L

    def sha(ys, xs):
        sgn = np.where(al[ys, xs] < 0.5, 1, -1)
        return np.clip(ys + sgn * hy // 2, 0, H - 1), np.clip(xs + sgn * L // 2, 0, W - 1)

    def shb(ys, xs):
        sgn = np.where(be[ys, xs] < 0.5, 1, -1)
        return np.clip(ys + sgn * hy // 2, 0, H - 1), np.clip(xs - sgn * L // 2, 0, W - 1)

    o = periodic(im, top, da, db, sha, shb, K)
    rep = []
    # левая грань: s = x (0..L), t = y - (hy + x/2) (0..hz); правая: s = x - L, t = y - (2hy - (x-L)/2)
    for side in (0, 1):
        sx = xx if side == 0 else xx - L
        t = yy - (hy + xx / 2) if side == 0 else yy - (2 * hy - (xx - L) / 2)
        slope = 1 if side == 0 else -1
        ds, dt = np.minimum(sx, L - sx), np.minimum(t, hz - t)
        lum = o[..., :3] @ np.float32([0.3, 0.59, 0.11])
        rect = np.zeros((hz, L), np.float32)
        for si in range(L):
            x0 = si if side == 0 else si + L
            y0 = (hy + x0 / 2) if side == 0 else (2 * hy - (x0 - L) / 2)
            rect[:, si] = lum[np.clip(np.round(y0 + 0.5 * K + np.arange(hz)).astype(int), 0, H - 1), x0]
        core = rect[2 * K:hz - 2 * K, 2 * K:L - 2 * K]
        core = core - core.mean()
        pt, ct = period(core, 0, 2 * K, hz // 2)
        ps, cs = period(core, 1, 4 * K, L // 2)
        TZ = pt * max(1, (hz // 2) // pt) if ct > 0.3 else hz // 2
        SX = ps * max(1, (L // 2) // ps) if cs > 0.3 else L // 2
        SX -= SX % 2
        rep.append("грань %d: ряд %d (r=%.2f) сдвиг %d, вдоль %d (r=%.2f) сдвиг %d" % (side, pt, ct, TZ, ps, cs, SX))

        def shs(ys, xs, sx=sx, slope=slope, SX=SX):
            dx = np.where(sx[ys, xs] < L / 2, 1, -1) * SX
            return np.clip(ys + slope * dx // 2, 0, H - 1), np.clip(xs + dx, 0, W - 1)

        def sht(ys, xs, t=t, TZ=TZ):
            return np.clip(ys + np.where(t[ys, xs] < hz / 2, 1, -1) * TZ, 0, H - 1), xs

        o = periodic(o, sides[side], ds, dt, shs, sht, K)
    return o, "; ".join(rep)


def main():
    global E, B
    sys.stdout.reconfigure(encoding="utf-8")
    out, s = Path(sys.argv[1]), sys.argv[2]
    frames = [int(x) for x in sys.argv[3].split(",")]
    if len(sys.argv) > 5:
        E, B = float(sys.argv[4]), float(sys.argv[5])
    cl = wb.read_set(s)
    d = out / (s + ".PCK")
    d.mkdir(parents=True, exist_ok=True)
    for f in frames:
        im = np.asarray(Image.open(GAME / (s + ".PCK") / ("%d.png" % f)).convert("RGBA")).astype(np.float32)
        o, rep = fix(im, cl[f])
        Image.fromarray(np.clip(o, 0, 255).astype(np.uint8), "RGBA").save(d / ("%d.png" % f))
        print(s, f, rep)


if __name__ == "__main__":
    main()
