#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Сотня оружия HD-BIGOBS, вариант v3 (указание 04.10 после отклонённого RESTORE, art/items/weapons-restore/README.md):
фото-эталон укладывается на геометрию оригинала, модель не рисует.

Роли (указание 04.10): оригинал задаёт размер, расположение частей, ракурс, цветовые зоны и положение дула;
фото-эталон - устройство, объём, материалы и мелкие детали (принятый АК art/items/ak-final сделан так же:
фото по местам частей оригинала, без модели). Шаги на предмет:
  1. эталон: альфа из своего файла или по ровному фону (заливка от края, дыры - то, куда заливка не дотекла),
     подписи у края листа и крошки отброшены;
  2. ракурс: 8 поворотов по 90 градусов с зеркалом и доводка +-6 градусов - по совпадению силуэта с оригиналом;
  3. габарит эталона на габарит оригинала (свой масштаб по каждой оси, перекос записывается);
  4. нежёсткая доводка по контуру (TPS с регуляризацией, контуры и отверстия оригинала, оригинал сглажен до
     ровных линий - лесенка 32x48 в силуэт не переносится); растяжение замеряется, большое - предмет откладывается;
  5. цвет: зоны оригинала (кластеры цвета) - средний тон каждой зоны фото сдвигается к тону зоны оригинала,
     фактура фото остаётся; граница сдвигов размыта;
  6. x16 -> x4 усреднением блоков, альфа - альфа эталона (не маска оригинала: маска - только проверка).
Проверки (gates) - отдельно по подгонке x16 (сырой результат) и по итоговому PNG k=4 до обрезки движком:
размер +-3 % отдельно по ширине и высоте, дуло (или остриё) не дальше 1 пикселя базы от дула оригинала,
отверстия оригинала открыты, тонкие части на месте, лишнего вне силуэта нет, полупрозрачного в теле нет,
каймы цвета фона эталона нет. Любой FAIL - предмет в отложенные, остальные идут дальше.

Запуск (только процессор, модели нет):
    py -3.13 tools/hdart/weapon_fit.py --batch 1           # партия 1 (n 1-20), предметы с готовым эталоном
    py -3.13 tools/hdart/weapon_fit.py --only W-018,W-019
Вход: art/items/weapons100-v3/ident/batch_<k>.tsv (опознание и эталоны), art/items/weapons100-v1/cards/originals.
Выход art/items/weapons100-v3/: fit/<ТИП>.png (x16 RGBA, сырой результат), pack/BIGOBS.PCK/<кадр>.<ТИП>.png
(k=4, 128x192), meta/<ТИП>.json (числа и вердикт), sheet_batch<k>.png, gates_batch<k>.tsv."""
import argparse
import csv
import json
import math
import os
import sys
import time
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENC = "utf-8-sig"
OUT = "art/items/weapons100-v3"
BATCH = "art/items/weapons100-v1"
Z = 16                          # рабочий масштаб подгонки к пикселю базы
K = 4                           # кадр пака
TOL_SIZE = 0.03                 # контракт v4 §3: +-3 % по каждой оси
TOL_MUZZLE = 1.0                # дуло - не дальше пикселя базы
ANISO_MAX = 1.45                # перекос масштабов осей эталона больше - конструкция не та, откладывать
STRETCH_MAX = 1.8               # местное растяжение TPS (наибольшее к наименьшему) больше - откладывать
EXTRA_MAX = 0.02                # лишнее вне силуэта оригинала (с запасом пикселя базы), доля площади
# пропажа и тонкое - с допуском в пиксель базы: пиксельный кадр условнее настоящей вещи, принятый АК (ak-final)
# уже оригинала по кромке (попиксельно пропало 0.149, тонкого на месте 0.72), а часть целиком не теряет.
# Пороги сверены по АК: принятый 0.030 / 0.932 проходит, отклонённый ak-v4 0.125 / 0.74 - нет (control_ak)
DROP_MAX = 0.035                # пропало из силуэта оригинала дальше пикселя базы от результата, доля площади
THIN_MIN = 0.90                 # тонкие части оригинала (толщина до 2 пикселей базы) - доля с результатом в пикселе
HOLE_OPEN = 0.5                 # отверстие оригинала открыто хотя бы наполовину
SEMI_MAX = 0.01                 # полупрозрачное внутри тела (не на кромке), доля
HALO_MAX = 0.15                 # кромка цвета фона эталона, доля пикселей кромки
RIM_MAX = 1.05                  # кромка не светлее тела (принятый АК: кайма 55.2 при стали 81.4) - тень и подложка
                                # фото, прилипшие к силуэту, светлее тёмного металла; HALO их не видит
DARK = (28, 30, 34)             # тёмный фон листа и проверки в игровом размере
DIRS = {"top": (0, -1), "bottom": (0, 1), "left": (-1, 0), "right": (1, 0), "top-left": (-1, -1),
        "top-right": (1, -1), "bottom-left": (-1, 1), "bottom-right": (1, 1)}


# ---------------------------------------------------------------- данные

def read_tsv(p):
    with open(p, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def batch_rows(k):
    p = os.path.join(OUT, "ident", "batch_%d.tsv" % k)
    return read_tsv(p) if os.path.exists(p) else []


def list_rows():
    return {r["master"]: r for r in read_tsv(os.path.join(BATCH, "list.tsv"))}


def original(t):
    """Кадр оригинала по индексам, как движок (R-043): RGB float, маска непрозрачного (индекс 0 прозрачен)."""
    d = os.path.join(BATCH, "cards", "originals", t)
    im = Image.open(os.path.join(d, sorted(os.listdir(d))[0]))
    idx = np.asarray(im)
    pal = np.asarray(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    return pal[idx].astype(np.float32), idx != 0


def bbox(m):
    ys, xs = np.nonzero(m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


# ---------------------------------------------------------------- простые операции над масками без scipy

def blur(a, sigma):
    """Гаусс по отдельности по осям (numpy), края - повтор."""
    if sigma <= 0:
        return a.astype(np.float32)
    r = int(math.ceil(sigma * 3))
    x = np.arange(-r, r + 1, dtype=np.float32)
    k = np.exp(-x * x / (2 * sigma * sigma))
    k /= k.sum()
    a = a.astype(np.float32)
    pad = [(0, 0)] * a.ndim
    out = a
    for ax in (0, 1):
        pw = list(pad)
        pw[ax] = (r, r)
        b = np.pad(out, pw, mode="edge")
        acc = np.zeros_like(out)
        for i, w in enumerate(k):
            sl = [slice(None)] * a.ndim
            sl[ax] = slice(i, i + out.shape[ax])
            acc += w * b[tuple(sl)]
        out = acc
    return out


def labels(m):
    """Связные области (4-связность) маски: массив меток 1..n и площади."""
    h, w = m.shape
    lab = np.zeros((h, w), np.int32)
    areas = [0]
    n = 0
    ys, xs = np.nonzero(m)
    for y0, x0 in zip(ys, xs):
        if lab[y0, x0]:
            continue
        n += 1
        q = deque([(y0, x0)])
        lab[y0, x0] = n
        a = 0
        while q:
            y, x = q.popleft()
            a += 1
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    q.append((yy, xx))
        areas.append(a)
    return lab, np.asarray(areas)


def holes_of(m):
    """Прозрачное, не связанное с краем кадра: отверстия (просвет скобы, стоек)."""
    h, w = m.shape
    pad = np.pad(~m, 1, constant_values=True)
    lab, _a = labels(pad)
    outside = lab[0, 0]
    return (pad & (lab != outside))[1:-1, 1:-1]


def dist_inside(m, cap=8):
    """Расстояние до края маски в пикселях (шахматное, до cap) - грубая толщина."""
    d = np.zeros(m.shape, np.int32)
    cur = m.copy()
    for i in range(1, cap + 1):
        d[cur] = i
        e = cur.copy()
        e[1:] &= cur[:-1]
        e[:-1] &= cur[1:]
        e[:, 1:] &= cur[:, :-1]
        e[:, :-1] &= cur[:, 1:]
        cur = e
        if not cur.any():
            break
    return d


def dilate(m, r=1):
    out = m.copy()
    for _ in range(r):
        e = out.copy()
        e[1:] |= out[:-1]
        e[:-1] |= out[1:]
        e[:, 1:] |= out[:, :-1]
        e[:, :-1] |= out[:, 1:]
        out = e
    return out


def contour_pts(m, n):
    """n точек кромки маски (пиксели маски с пустым соседом), равномерно по порядку обхода строк."""
    e = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1))
    ys, xs = np.nonzero(e)
    if len(xs) == 0:
        return np.zeros((0, 2), np.float32)
    pts = np.stack([xs, ys], 1).astype(np.float32)
    if len(pts) > n:
        # прореживание по сетке, чтобы не сбиться в одном месте
        step = max(1, int(math.sqrt(len(pts) / n)))
        key = (pts[:, 0] // step) * 100000 + pts[:, 1] // step
        _u, first = np.unique(key, return_index=True)
        pts = pts[first]
        if len(pts) > n:
            pts = pts[np.linspace(0, len(pts) - 1, n).astype(int)]
    return pts


# ---------------------------------------------------------------- эталон

def matte(path, base_h=0):
    """Эталон -> RGB float и альфа 0..1, кроп по предмету. Альфа файла, если она есть; иначе ровный фон по краю:
    заливка от края по близкому к фону цвету, мягкая кромка по расстоянию цвета. Подписи у верхнего и нижнего края
    листа и крошки (меньше 1 % крупнейшей области) отброшены."""
    im = Image.open(os.path.join(ROOT, path))
    long_side = max(im.size)
    if long_side > 1600:
        s = 1600.0 / long_side
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    rgba = np.asarray(im.convert("RGBA")).astype(np.float32)
    rgb = rgba[..., :3]
    h, w = rgb.shape[:2]
    bg = None
    if im.mode in ("RGBA", "LA") and rgba[..., 3].min() < 128 and (rgba[..., 3] < 128).mean() > 0.05:
        a = rgba[..., 3] / 255.0
    else:
        # фонов может быть несколько (поле листа и подложка рисунка): кластеры цвета края, мелкие (подпись) - мимо
        e = max(4, min(h, w) // 100)
        edge = np.concatenate([rgb[:e].reshape(-1, 3), rgb[-e:].reshape(-1, 3), rgb[:, :e].reshape(-1, 3),
                               rgb[:, -e:].reshape(-1, 3)])
        bgs = border_bgs(edge)
        bg = bgs[0]
        d = np.min([np.sqrt(((rgb - b) ** 2).sum(2)) for b in bgs], 0)
        de = np.min([np.sqrt(((edge - b) ** 2).sum(1)) for b in bgs], 0)
        t0 = float(np.clip(np.percentile(de, 90) * 1.6, 9.0, 30.0))
        near = d <= t0
        if float(np.mean(bg)) > 150:
            # светлый фон фото: мягкая тень и перепад света - серое, ровное (малый местный разброс), не темнее
            # фона больше чем на 70 - тоже фон, если связано с краем (заливка ниже); гладкую светлую сталь,
            # если она съедена, покажет проверка DROP
            L = rgb.mean(2)
            mu = blur(L, 2.0)
            sd = np.sqrt(np.maximum(blur(L * L, 2.0) - mu * mu, 0))
            grey = (rgb.max(2) - rgb.min(2)) < 20
            near |= grey & (sd < 4.0) & (L >= float(np.mean(bg)) - 70)
        # снаружи - всё, что связано с краем листа по близкому к фону (рамка в пиксель вокруг - одно затравочное место)
        pad = np.pad(np.where(near, 255, 0).astype(np.uint8), 1, constant_values=255)
        inv = Image.fromarray(pad, "L")
        ImageDraw.floodfill(inv, (0, 0), 128)
        outside = (np.asarray(inv) == 128)[1:-1, 1:-1]
        body = ~outside
        # отверстия: внутренние области цвета фона (строже порога снаружи) не меньше пикселя базы.
        # Тёмный металл на тёмной подложке иначе стал бы полупрозрачным - мелкое близкое к фону остаётся телом
        q = 4
        sb = np.asarray(Image.fromarray((body & (d <= t0 * 0.8)).astype(np.uint8) * 255).resize(
            (max(1, w // q), max(1, h // q)), Image.BOX)) > 160
        x0b, y0b, x1b, y1b = bbox(body)
        px_base = max(x1b - x0b, y1b - y0b) / float(base_h) if base_h else 10.0
        lab, areas = labels(sb)
        hole_s = np.zeros_like(sb)
        for i in range(1, len(areas)):
            if areas[i] * q * q >= px_base * px_base * 1.0:
                hole_s |= lab == i
        hole = np.asarray(Image.fromarray(hole_s.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 127
        hole &= d <= t0
        body &= ~hole
        a = body.astype(np.float32)
    m = a > 0.5
    small = Image.fromarray((m * 255).astype(np.uint8)).resize((max(1, w // 4), max(1, h // 4)), Image.BOX)
    sm = np.asarray(small) > 127
    lab, areas = labels(sm)
    keep = np.zeros_like(sm)
    if len(areas) > 1:
        big = areas[1:].max()
        band = max(1, int(sm.shape[0] * 0.06))
        for i in range(1, len(areas)):
            reg = lab == i
            ys, _xs = np.nonzero(reg)
            label_band = ys.max() < band or ys.min() > sm.shape[0] - band
            if areas[i] >= 0.15 * big and not (label_band and areas[i] < 0.2 * big):
                keep |= reg
    keep = np.asarray(Image.fromarray((keep * 255).astype(np.uint8)).resize((w, h), Image.NEAREST)) > 127
    keep = dilate(keep, 4)
    a = a * keep
    if bg is not None:
        # кромка: альфа - сглаженная маска (не расстояние цвета: тёмная обводка рисунка близка к тёмному фону),
        # цвет кромки в 2 пикселя - от соседей изнутри, без примеси фона
        m = a > 0.5
        core = m.copy()
        for _ in range(2):
            core = core & np.roll(core, 1, 0) & np.roll(core, -1, 0) & np.roll(core, 1, 1) & np.roll(core, -1, 1)
        num = blur(rgb * core[..., None], 2.0)
        den = blur(core.astype(np.float32), 2.0)
        band = m & ~core & (den > 0.05)
        rgb = rgb.copy()
        rgb[band] = num[band] / den[band][:, None]
        a = np.clip(blur(m.astype(np.float32), 0.7), 0, 1)
    x0, y0, x1, y1 = bbox(a > 0.5)
    return rgb[y0:y1, x0:x1], a[y0:y1, x0:x1], (None if bg is None else [float(v) for v in bg])


def border_bgs(edge, k=3):
    """Цвета фона по пикселям края листа: k-средних, кластеры меньше 12 % края (подпись, кусок предмета) - мимо."""
    cen = edge[np.linspace(0, len(edge) - 1, k).astype(int)].copy()
    for _ in range(15):
        lab = ((edge[:, None, :] - cen[None]) ** 2).sum(2).argmin(1)
        for j in range(k):
            if (lab == j).any():
                cen[j] = np.median(edge[lab == j], 0)
    share = np.bincount(lab, minlength=k) / float(len(edge))
    order = np.argsort(-share)
    return [cen[j] for j in order if share[j] >= 0.12]


def orient(rgb, a, k, mirror):
    """Поворот на k*90 градусов против часовой и зеркало по горизонтали."""
    if mirror:
        rgb, a = rgb[:, ::-1], a[:, ::-1]
    return np.rot90(rgb, k).copy(), np.rot90(a, k).copy()


# ---------------------------------------------------------------- отображение и TPS

def sample(img, X, Y):
    """Билинейная выборка img (h, w[, c]) в точках X, Y (float массивы), вне - ноль."""
    h, w = img.shape[:2]
    x0 = np.floor(X).astype(np.int64)
    y0 = np.floor(Y).astype(np.int64)
    fx, fy = X - x0, Y - y0
    out = 0
    for dy, wy in ((0, 1 - fy), (1, fy)):
        for dx, wx in ((0, 1 - fx), (1, fx)):
            xx, yy = x0 + dx, y0 + dy
            ok = (xx >= 0) & (xx < w) & (yy >= 0) & (yy < h)
            v = img[np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1)]
            wgt = (wx * wy * ok)
            if img.ndim == 3:
                wgt = wgt[..., None]
            out = out + v * wgt
    return out


def tps_fit(src, dst, lam):
    """TPS: функция f(src_i) ~ dst_i со сглаживанием lam (в долях среднего ядра). -> (W, A, src)."""
    n = len(src)
    d2 = ((src[:, None, :] - src[None, :, :]) ** 2).sum(2)
    Kx = np.where(d2 > 0, d2 * np.log(d2 + 1e-12), 0.0)
    Kx = Kx + lam * np.abs(Kx).mean() * np.eye(n)
    P = np.hstack([np.ones((n, 1)), src])
    L = np.zeros((n + 3, n + 3))
    L[:n, :n] = Kx
    L[:n, n:] = P
    L[n:, :n] = P.T
    Y = np.zeros((n + 3, 2))
    Y[:n] = dst
    sol = np.linalg.solve(L, Y)
    return sol[:n], sol[n:], src


def tps_eval(model, X, Y):
    W, A, src = model
    pts = np.stack([X.ravel(), Y.ravel()], 1)
    out = np.empty_like(pts)
    for i in range(0, len(pts), 20000):
        p = pts[i:i + 20000]
        d2 = ((p[:, None, :] - src[None, :, :]) ** 2).sum(2)
        U = np.where(d2 > 0, d2 * np.log(d2 + 1e-12), 0.0)
        out[i:i + 20000] = A[0] + p @ A[1:] + U @ W
    return out[:, 0].reshape(X.shape), out[:, 1].reshape(X.shape)


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum()) / u if u else 0.0


# ---------------------------------------------------------------- подгонка

def target_of(m):
    """Целевой силуэт x16 по кропу оригинала: маска, сглаженная до ровных линий (лесенка 32x48 - не форма),
    отверстия оригинала тоже сглажены и сохранены."""
    x0, y0, x1, y1 = bbox(m)
    crop = m[y0:y1, x0:x1]
    big = np.repeat(np.repeat(crop.astype(np.float32), Z, 0), Z, 1)
    sm = blur(big, Z * 0.45) > 0.5
    # тонкие места (толщина в пиксель базы) сглаживание может съесть - вернуть по исходной маске x16 с отступом
    thin = np.repeat(np.repeat(dist_inside(crop, 2) == 1, Z, 0), Z, 1)
    sm |= thin & (blur(big, Z * 0.2) > 0.5)
    return sm, (x0, y0, x1, y1)


def fit_global(rgb, a, T):
    """Лучший из 8 ракурсов и доводка +-6 градусов: габарит эталона на габарит цели, совпадение силуэта.
    -> (rgb, a, ракурс, угол, iou, перекос)."""
    H, W = T.shape
    best = None
    for k in range(4):
        for mir in (False, True):
            r2, a2 = orient(rgb, a, k, mir)
            sc = fit_bbox_iou(a2, T, 0.0)
            if best is None or sc[0] > best[0]:
                best = (sc[0], k, mir, 0.0)
    _s, k, mir, _ = best
    r2, a2 = orient(rgb, a, k, mir)
    for ang in range(-6, 7):
        if ang == 0:
            continue
        sc = fit_bbox_iou(a2, T, float(ang))
        if sc[0] > best[0] + 1e-4:
            best = (sc[0], k, mir, float(ang))
    _s, k, mir, ang = best
    r2, a2 = orient(rgb, a, k, mir)
    if ang:
        r2, a2 = rotate(r2, a2, ang)
    h, w = a2.shape
    x0, y0, x1, y1 = bbox(a2 > 0.5)
    sx, sy = (x1 - x0) / float(W), (y1 - y0) / float(H)
    aniso = max(sx / sy, sy / sx)
    return r2[y0:y1, x0:x1], a2[y0:y1, x0:x1], (k, mir), ang, best[0], aniso


def rotate(rgb, a, ang):
    im = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a[..., None] * 255]).astype(np.uint8), "RGBA")
    im = im.rotate(ang, Image.BICUBIC, expand=True)
    arr = np.asarray(im).astype(np.float32)
    return arr[..., :3], arr[..., 3] / 255.0


def fit_bbox_iou(a, T, ang):
    if ang:
        _r, a = rotate(np.zeros(a.shape + (3,), np.float32), a, ang)
    m = a > 0.5
    if not m.any():
        return (0.0,)
    x0, y0, x1, y1 = bbox(m)
    crop = Image.fromarray((m[y0:y1, x0:x1] * 255).astype(np.uint8))
    H, W = T.shape
    s = Image.fromarray((T * 255).astype(np.uint8)).resize((max(8, W // 4), max(8, H // 4)), Image.BOX)
    t = np.asarray(s) > 127
    c = np.asarray(crop.resize((t.shape[1], t.shape[0]), Image.BOX)) > 127
    # подгонка габарита растягивает каждую ось по-своему, и боком положенное фото тоже даёт неплохое совпадение
    # силуэта - ценой перекоса в 2-3 раза; ракурс выбирается по совпадению с поправкой на перекос
    sx, sy = (x1 - x0) / float(W), (y1 - y0) / float(H)
    aniso = max(sx / sy, sy / sx)
    v = iou(c, t)
    return (v - 0.35 * math.log(aniso), v, aniso)


def row_profile(M):
    """Левый и правый край и заполненность каждой строки маски в долях ширины; пустая строка - nan."""
    H, W = M.shape
    any_ = M.any(1)
    left = np.where(any_, M.argmax(1), np.nan) / float(W)
    right = np.where(any_, W - M[:, ::-1].argmax(1), np.nan) / float(W)
    occ = M.mean(1)
    return np.stack([left, right, occ], 1)


def smooth1(v, r):
    if r <= 0:
        return v
    k = np.ones(2 * r + 1) / (2 * r + 1)
    p = np.pad(v, r, mode="edge")
    return np.convolve(p, k, mode="valid")


def dtw_rows(ft, fp, band=0.3, slope=0.15):
    """Монотонное соответствие строк цели строкам эталона (DTW по профилю, коридор band, шаг вбок дороже на slope).
    -> для каждой строки цели - номер строки эталона (дробный, среднее по пути)."""
    n, m = len(ft), len(fp)
    def cost(i, j):
        a, b = ft[i], fp[j]
        if np.isnan(a[0]) or np.isnan(b[0]):
            return 0.0 if (np.isnan(a[0]) and np.isnan(b[0])) else 1.0
        return float(abs(a[0] - b[0]) + abs(a[1] - b[1]) + 2 * abs(a[2] - b[2]))
    C = np.full((n, m), np.inf)
    P = np.zeros((n, m), np.int8)
    bw = max(3, int(band * max(n, m)))
    for i in range(n):
        jc = i * (m - 1) / float(max(1, n - 1))
        for j in range(max(0, int(jc) - bw), min(m, int(jc) + bw + 1)):
            c = cost(i, j)
            if i == 0 and j == 0:
                C[i, j] = c
                continue
            best, mv = np.inf, 0
            if i > 0 and j > 0 and C[i - 1, j - 1] < best:
                best, mv = C[i - 1, j - 1], 0
            if i > 0 and C[i - 1, j] + slope < best:
                best, mv = C[i - 1, j] + slope, 1
            if j > 0 and C[i, j - 1] + slope < best:
                best, mv = C[i, j - 1] + slope, 2
            C[i, j] = c + best
            P[i, j] = mv
    i, j = n - 1, m - 1
    acc = [[] for _ in range(n)]
    while True:
        acc[i].append(j)
        if i == 0 and j == 0:
            break
        mv = P[i, j]
        if i == 0:
            j -= 1
        elif j == 0:
            i -= 1
        elif mv == 0:
            i, j = i - 1, j - 1
        elif mv == 1:
            i -= 1
        else:
            j -= 1
    return np.array([np.mean(v) for v in acc])


def profile_init(a, T, bins=4):
    """Начальное отображение по профилю вдоль длинной оси: каждая строка цели берёт строку эталона по DTW
    (части спрайта нарисованы в других пропорциях, чем у настоящего ствола - затвор длиннее, рукоять меньше), а по
    поперечной оси - свой отрезок [левый край, правый край] в этой строке. Сдвиги сглажены, растяжение участка
    ограничено [0.5, 2]. -> Fx, Fy в пикселях эталона a."""
    H, W = T.shape
    h, w = a.shape
    tr = W > H
    Tm = T.T if tr else T
    Am = (a > 0.5).T if tr else (a > 0.5)
    Hm, Wm = Tm.shape
    P = np.asarray(Image.fromarray(Am.astype(np.uint8) * 255).resize((Wm, Hm), Image.BOX)) > 127
    nb = max(8, Hm // bins)
    def binned(M):
        rows = np.asarray(Image.fromarray(M.astype(np.uint8) * 255).resize((Wm, nb), Image.BOX)) > 100
        return row_profile(rows)
    path = dtw_rows(binned(Tm), binned(P))
    g = np.interp((np.arange(Hm) + 0.5) / Hm * nb - 0.5, np.arange(nb), path)
    g = smooth1((g + 0.5) / nb * Hm - 0.5, max(1, Hm // 40))
    d = np.clip(np.diff(g), 0.5, 2.0)
    g = np.concatenate([[g[0]], g[0] + np.cumsum(d)])
    g = g * ((Hm - 1) / max(g[-1], 1e-6)) if g[-1] > Hm - 1 else g
    pt, pp = row_profile(Tm), row_profile(P)
    gi = np.clip(np.round(g).astype(int), 0, Hm - 1)
    lt, rt = pt[:, 0] * Wm, pt[:, 1] * Wm
    lp, rp = pp[gi, 0] * Wm, pp[gi, 1] * Wm
    ok = ~(np.isnan(lt) | np.isnan(lp))
    idx = np.arange(Hm)
    if ok.sum() >= 2:
        lt, rt, lp, rp = [np.interp(idx, idx[ok], v[ok]) for v in (lt, rt, lp, rp)]
    else:
        lt, rt, lp, rp = np.zeros(Hm), np.full(Hm, Wm), np.zeros(Hm), np.full(Hm, Wm)
    r = max(1, Hm // 30)
    lt, rt, lp, rp = [smooth1(v, r) for v in (lt, rt, lp, rp)]
    sc = np.clip((rp - lp) / np.maximum(rt - lt, 1.0), 0.6, 1.6)
    yy, xx = np.mgrid[0:Hm, 0:Wm].astype(np.float64)
    XP = lp[:, None] + (xx - lt[:, None]) * sc[:, None]
    YP = np.repeat(g[:, None], Wm, 1)
    # в пиксели эталона (P - эталон, сжатый в размер цели)
    if tr:
        XP, YP = YP.T, XP.T                 # обратно: строки были столбцами
        Fx = (XP + 0.5) * (w / float(W)) - 0.5
        Fy = (YP + 0.5) * (h / float(H)) - 0.5
    else:
        Fx = (XP + 0.5) * (w / float(W)) - 0.5
        Fy = (YP + 0.5) * (h / float(H)) - 0.5
    return Fx, Fy


def spline_fit(y, g, knots):
    """Непрерывная ломаная по узлам knots (включая концы) методом наименьших квадратов. -> значения в y, ошибка."""
    B = np.zeros((len(y), len(knots)))
    for k in range(len(knots)):
        if k > 0:
            s = (y >= knots[k - 1]) & (y <= knots[k])
            B[s, k] = (y[s] - knots[k - 1]) / max(knots[k] - knots[k - 1], 1e-6)
        if k < len(knots) - 1:
            s = (y >= knots[k]) & (y <= knots[k + 1])
            B[s, k] = np.maximum(B[s, k], (knots[k + 1] - y[s]) / max(knots[k + 1] - knots[k], 1e-6))
    c, *_ = np.linalg.lstsq(B, g, rcond=None)
    f = B @ c
    return f, float(np.sqrt(np.mean((f - g) ** 2)))


def segments_init(a, T, max_knots=3, min_seg=0.12):
    """Сборка по участкам (как АК по частям, но без ручной разметки): соответствие строк по DTW профиля
    (profile_init) приближается ломаной с 0-3 внутренними узлами, участок между узлами переносится одним
    аффинным преобразованием - фактура фото внутри участка не размазывается. Поперечная ось - своё
    a*x + b на участке по краям строк; на узлах сшивка плавная (полпикселя базы в каждую сторону).
    -> Fx, Fy, число участков."""
    H, W = T.shape
    h, w = a.shape
    tr = W > H
    Tm = T.T if tr else T
    Am = (a > 0.5).T if tr else (a > 0.5)
    Hm, Wm = Tm.shape
    P = np.asarray(Image.fromarray(Am.astype(np.uint8) * 255).resize((Wm, Hm), Image.BOX)) > 127
    nb = max(8, Hm // 4)
    def binned(M):
        rows = np.asarray(Image.fromarray(M.astype(np.uint8) * 255).resize((Wm, nb), Image.BOX)) > 100
        return row_profile(rows)
    path = dtw_rows(binned(Tm), binned(P))
    yb = np.arange(nb, dtype=np.float64)
    knots = [0.0, nb - 1.0]
    f, err = spline_fit(yb, path, knots)
    cand = np.arange(int(nb * min_seg), int(nb * (1 - min_seg)), max(1, nb // 24)).astype(float)
    for _ in range(max_knots):
        best = None
        for c in cand:
            ks = sorted(knots + [c])
            if min(np.diff(ks)) < nb * min_seg:
                continue
            f2, e2 = spline_fit(yb, path, ks)
            if best is None or e2 < best[1]:
                best = (ks, e2)
        if best is None or best[1] > err * 0.8 - 0.05:      # узел должен заметно уменьшать ошибку
            break
        knots, err = best[0], best[1]
    f, err = spline_fit(yb, path, knots)
    # в строки цели: g(y) - строка эталона (в размере цели)
    ys = (np.arange(Hm) + 0.5) / Hm * nb - 0.5
    g = np.interp(ys, yb, f)
    g = (g + 0.5) / nb * Hm - 0.5
    d = np.clip(np.diff(g), 0.5, 2.0)
    g = np.concatenate([[g[0]], g[0] + np.cumsum(d)])
    kn = [(k + 0.5) / nb * Hm - 0.5 for k in knots]
    seg = np.searchsorted(np.asarray(kn[1:-1]), np.arange(Hm))
    pt, pp = row_profile(Tm), row_profile(P)
    gi = np.clip(np.round(g).astype(int), 0, Hm - 1)
    A = np.ones(Hm)
    Bv = np.zeros(Hm)
    for s in range(len(kn) - 1):
        rows = np.nonzero(seg == s)[0]
        lt, rt = pt[rows, 0] * Wm, pt[rows, 1] * Wm
        lp, rp = pp[gi[rows], 0] * Wm, pp[gi[rows], 1] * Wm
        ok = ~(np.isnan(lt) | np.isnan(lp))
        if ok.sum() < 2:
            continue
        X = np.concatenate([lt[ok], rt[ok]])
        Y = np.concatenate([lp[ok], rp[ok]])
        M = np.stack([X, np.ones_like(X)], 1)
        (sa, sb), *_ = np.linalg.lstsq(M, Y, rcond=None)
        sa = float(np.clip(sa, 0.6, 1.6))
        sb = float(np.mean(Y - sa * X))
        A[rows], Bv[rows] = sa, sb
    r = max(1, Z // 2) if Hm > 100 else 1
    A, Bv = smooth1(A, r), smooth1(Bv, r)
    yy, xx = np.mgrid[0:Hm, 0:Wm].astype(np.float64)
    XP = A[:, None] * xx + Bv[:, None]
    YP = np.repeat(g[:, None], Wm, 1)
    if tr:
        XP, YP = YP.T, XP.T
    Fx = (XP + 0.5) * (w / float(W)) - 0.5
    Fy = (YP + 0.5) * (h / float(H)) - 0.5
    return Fx, Fy, len(kn) - 1


def fit_tps(rgb, a, T, holes_t, iters=10, init=None, cap=None, lam0=2.0):
    """Нежёсткая доводка: точки кромки цели (и её отверстий) -> ближайшие точки кромки текущего результата,
    TPS со сглаживанием, убывающим от итерации к итерации. Отображение - обратное: пиксель цели берёт эталон
    в точке F(p). -> (Fx, Fy, растяжение max/min, история iou)."""
    H, W = T.shape
    h, w = a.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    if init is not None:
        Fx, Fy = init
    else:
        Fx = (xx + 0.5) * (w / float(W)) - 0.5
        Fy = (yy + 0.5) * (h / float(H)) - 0.5
    hist = []
    tgt_edge = T | holes_t
    for it in range(iters):
        cur = sample(a, Fx, Fy) > 0.5
        hist.append(iou(cur, T))
        ct = contour_pts(T, 220)
        hp = contour_pts(holes_t, 60) if holes_t.any() else np.zeros((0, 2), np.float32)
        ct = np.vstack([ct, hp]) if len(hp) else ct
        cw = contour_pts(cur, 400)
        if len(ct) < 8 or len(cw) < 8:
            break
        d = ((ct[:, None, :] - cw[None, :, :]) ** 2).sum(2)
        nn = d.argmin(1)
        disp = cw[nn] - ct                       # куда смотреть, чтобы контур попал на цель
        dist = np.sqrt((disp ** 2).sum(1))
        cp = cap if cap is not None else max(2.0, Z * 1.5)
        disp = disp * np.minimum(1.0, cp / np.maximum(dist, 1e-6))[:, None]
        # опоры по углам и центру - чтобы не уплывала середина
        anch = np.array([[0, 0], [W - 1, 0], [0, H - 1], [W - 1, H - 1], [W / 2.0, H / 2.0]], np.float64)
        src = np.vstack([ct, anch])
        dd = np.vstack([disp, np.zeros((len(anch), 2))])
        lam = lam0 * (0.6 ** it) + 0.02
        model = tps_fit(src.astype(np.float64), dd.astype(np.float64), lam)
        gx, gy = tps_eval(model, xx, yy)
        # композиция: новый F(p) = F(p + g(p))
        Fx2 = sample(Fx[..., None], xx + gx, yy + gy)[..., 0]
        Fy2 = sample(Fy[..., None], xx + gx, yy + gy)[..., 0]
        okx = (xx + gx >= 0) & (xx + gx <= W - 1) & (yy + gy >= 0) & (yy + gy <= H - 1)
        Fx = np.where(okx, Fx2, Fx)
        Fy = np.where(okx, Fy2, Fy)
    cur = sample(a, Fx, Fy) > 0.5
    hist.append(iou(cur, T))
    stretch = local_stretch(Fx, Fy, cur, w / float(W), h / float(H))
    return Fx, Fy, stretch, hist


def local_stretch(Fx, Fy, m, sx, sy):
    """Местный масштаб отображения против общего: корень определителя якобиана, по пикселям внутри силуэта,
    в окне 4 пикселя (шум выборки не считается). -> наибольший к наименьшему (p98 / p2)."""
    s = 4
    jx = (Fx[s:, s:] - Fx[s:, :-s]) / s
    jy = (Fy[s:, s:] - Fy[:-s, s:]) / s
    det = np.abs(jx * jy) / (sx * sy)
    mm = m[s:, s:]
    if mm.sum() < 50:
        return 1.0
    v = np.sqrt(np.maximum(det[mm], 1e-6))
    return float(np.percentile(v, 98) / max(np.percentile(v, 2), 1e-6))


# ---------------------------------------------------------------- цвет

def to_lab(rgb):
    c = np.clip(rgb / 255.0, 0, 1)
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def from_lab(lab):
    fy = (lab[..., 0] + 16) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f > 0.2069, f ** 3, (f - 16 / 116.0) / 7.787) * np.array([0.9505, 1.0, 1.089])
    M = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    c = xyz @ M.T
    c = np.where(c > 0.0031308, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055, 12.92 * c)
    return np.clip(c * 255.0, 0, 255)


def zones(rgb, m, kmax=4, merge=18.0):
    """Цветовые зоны оригинала: k-средних в Lab по пикселям предмета, близкие (dE < merge) сливаются.
    -> карта зон (-1 вне предмета), средние Lab зон."""
    lab = to_lab(rgb)
    px = lab[m]
    if len(px) == 0:
        return np.full(m.shape, -1), np.zeros((0, 3))
    k = min(kmax, len(np.unique(px.round(0), axis=0)))
    cen = px[np.linspace(0, len(px) - 1, k).astype(int)].copy()
    order = np.argsort(px[:, 0])
    cen = px[order[np.linspace(0, len(px) - 1, k).astype(int)]].copy()
    for _ in range(20):
        lab_i = ((px[:, None, :] - cen[None]) ** 2).sum(2).argmin(1)
        for j in range(k):
            if (lab_i == j).any():
                cen[j] = px[lab_i == j].mean(0)
    changed = True
    while changed and len(cen) > 1:
        changed = False
        d = np.sqrt(((cen[:, None] - cen[None]) ** 2).sum(2)) + np.eye(len(cen)) * 1e9
        i, j = np.unravel_index(d.argmin(), d.shape)
        if d[i, j] < merge:
            cen[i] = (cen[i] + cen[j]) / 2
            cen = np.delete(cen, j, 0)
            changed = True
    zi = ((px[:, None, :] - cen[None]) ** 2).sum(2).argmin(1)
    zmap = np.full(m.shape, -1)
    zmap[m] = zi
    means = np.array([px[zi == j].mean(0) if (zi == j).any() else cen[j] for j in range(len(cen))])
    return zmap, means


def color_zones(rgb_fit, a_fit, rgb_o, m_o, box, w_l=0.6):
    """Тон каждой зоны оригинала переносится на фото: средний a, b зоны фото - к зоне оригинала полностью,
    L - на w_l; фактура (отклонения внутри зоны) - фото. Сдвиги размыты по границе зон."""
    x0, y0, x1, y1 = box
    zmap, means = zones(rgb_o[y0:y1, x0:x1], m_o[y0:y1, x0:x1])
    H, W = a_fit.shape
    zbig = np.repeat(np.repeat(zmap, Z, 0), Z, 1)[:H, :W]
    lab = to_lab(rgb_fit)
    inside = a_fit > 0.5
    shift = np.zeros(lab.shape, np.float32)
    weight = np.zeros(a_fit.shape, np.float32)
    rep = []
    for j in range(len(means)):
        reg = inside & (zbig == j)
        if reg.sum() < 20:
            continue
        mu = lab[reg].mean(0)
        dv = means[j] - mu
        dv[0] *= w_l
        lay = np.zeros(lab.shape, np.float32)
        lay[reg] = dv
        shift += lay
        weight += reg
        rep.append({"zone": j, "orig_lab": [round(float(v), 1) for v in means[j]],
                    "photo_lab": [round(float(v), 1) for v in mu], "px": int(reg.sum())})
    sig = Z * 0.5
    sb = blur(shift, sig)
    wb = blur(weight, sig)
    sb = sb / np.maximum(wb, 1e-3)[..., None]
    out = lab + sb * inside[..., None]
    return from_lab(out), rep


# ---------------------------------------------------------------- проверки

def gates(alpha, rgb, m_o, box_o, scale, muzzle, bg_ref, pal=None, full=None, org=(0, 0)):
    """alpha, rgb - результат на холсте кропа оригинала в масштабе scale (x16 подгонка или x4 кадр).
    full - альфа всего холста, org - угол кропа на нём: размер меряется по нему, иначе вылезшее за габарит
    оригинала срезано кропом и SIZE его не видит. Всё сравнивается с оригиналом в пикселях базы.
    -> (dict чисел, list провалов)."""
    x0, y0, x1, y1 = box_o
    mo = m_o[y0:y1, x0:x1]
    hb, wb = mo.shape
    op = alpha >= 0.5
    rep, fails = {}, []
    if not op.any():
        return {"empty": True}, ["EMPTY"]
    if full is not None and (full >= 0.5).any():
        bx0, by0, bx1, by1 = bbox(full >= 0.5)
        bx0, bx1, by0, by1 = bx0 - org[0], bx1 - org[0], by0 - org[1], by1 - org[1]
    else:
        bx0, by0, bx1, by1 = bbox(op)
    dw = (bx1 - bx0) / float(wb * scale) - 1.0
    dh = (by1 - by0) / float(hb * scale) - 1.0
    rep["dw_pct"], rep["dh_pct"] = round(dw * 100, 2), round(dh * 100, 2)
    rep["shift_base"] = [round(bx0 / scale, 2), round(by0 / scale, 2)]
    if abs(dw) > TOL_SIZE:
        fails.append("SIZE_W %+.1f%%" % (dw * 100))
    if abs(dh) > TOL_SIZE:
        fails.append("SIZE_H %+.1f%%" % (dh * 100))
    # покрытие по пикселям базы: средняя альфа блока
    blk = alpha[:hb * scale, :wb * scale].reshape(hb, scale, wb, scale).mean((1, 3))
    covered = blk >= 0.5
    area = mo.sum()
    near = dilate(blk >= 0.3, 1)
    drop = (mo & ~near).sum() / float(area)
    extra = (covered & ~dilate(mo, 1)).sum() / float(area)
    rep["drop"], rep["extra"] = round(float(drop), 4), round(float(extra), 4)
    rep["drop_px"] = round(float((mo & (blk < 0.3)).sum() / float(area)), 4)       # попиксельно - для сведения
    if drop > DROP_MAX:
        fails.append("DROP %.3f" % drop)
    if extra > EXTRA_MAX:
        fails.append("EXTRA %.3f" % extra)
    thin = mo & (dist_inside(mo, 3) <= 1)
    if thin.sum() >= 3:
        tk = float((thin & near).sum()) / thin.sum()
        rep["thin_kept"] = round(tk, 3)
        if tk < THIN_MIN:
            fails.append("THIN %.2f" % tk)
    ho = holes_of(mo)
    if ho.any():
        lab, areas = labels(ho)
        # отверстие открыто, если рядом с местом оригинала (сдвиг до пикселя базы) прозрачного внутри силуэта
        # не меньше половины его площади; прозрачное снаружи оригинала не в счёт
        opened = []
        fine_t = alpha < 0.5
        mo_up = np.repeat(np.repeat(mo, scale, 0), scale, 1)[:alpha.shape[0], :alpha.shape[1]]
        inner = fine_t & (mo_up | np.repeat(np.repeat(ho, scale, 0), scale, 1)[:alpha.shape[0], :alpha.shape[1]])
        for i in range(1, len(areas)):
            reg = lab == i
            near = np.repeat(np.repeat(dilate(reg, 1), scale, 0), scale, 1)[:alpha.shape[0], :alpha.shape[1]]
            got = float((inner & near).sum()) / (areas[i] * scale * scale)
            opened.append(round(min(1.0, got), 2))
        rep["holes_open"] = opened
        if min(opened) < HOLE_OPEN:
            fails.append("HOLE %s" % opened)
    # дуло: середина крайней полосы силуэта по направлению дула
    if muzzle in DIRS:
        dx, dy = DIRS[muzzle]
        po = muzzle_point(mo.astype(np.float32), dx, dy, 1.0)
        pr_ = muzzle_point(op.astype(np.float32), dx, dy, float(scale))
        dmz = math.hypot(po[0] - pr_[0] / scale, po[1] - pr_[1] / scale)
        rep["muzzle_base"] = [round(po[0], 2), round(po[1], 2)]
        rep["muzzle_res"] = [round(pr_[0] / scale, 2), round(pr_[1] / scale, 2)]
        rep["muzzle_dist"] = round(dmz, 2)
        if dmz > TOL_MUZZLE:
            fails.append("MUZZLE %.2f" % dmz)
    # полупрозрачное внутри тела и кайма фона эталона
    # тело - пиксели, вокруг которых на 2 шага всё не прозрачнее половины; кромка и края отверстий - не тело
    any_ = alpha > 0.02
    half = alpha > 0.5
    core = half.copy()
    for r in range(1, 3):
        core &= np.roll(half, r, 0) & np.roll(half, -r, 0) & np.roll(half, r, 1) & np.roll(half, -r, 1)
    semi_core = core & (alpha < 0.9)
    rep["semi_core"] = round(float(semi_core.sum()) / max(1, core.sum()), 4)
    if rep["semi_core"] > SEMI_MAX:
        fails.append("SEMI %.3f" % rep["semi_core"])
    rim = any_ & ~core
    if rim.sum() > 10 and core.sum() > 10:
        Y = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
        yr = float((Y * alpha)[rim].sum() / max(alpha[rim].sum(), 1e-6))
        yc = float(Y[core].mean())
        rep["rim_y"], rep["core_y"] = round(yr, 1), round(yc, 1)
        # тёмное тело (до 40) - отношение шумит, сравнивается разность
        if yr > max(yc * RIM_MAX, yc + 8):
            fails.append("RIM %.0f/%.0f" % (yr, yc))
    if bg_ref is not None:
        # кайма: пиксель кромки ближе к фону эталона, чем к любому цвету оригинала (R-157: против всей палитры
        # предмета, а не порогом от фона - тёмная обводка рисунка сама близка к тёмной подложке)
        edge = any_ & ~core
        if edge.sum() > 10 and pal is not None:
            ce = rgb[edge]
            d_bg = np.sqrt(((ce - np.asarray(bg_ref, np.float32)) ** 2).sum(1))
            d_pal = np.sqrt(((ce[:, None, :] - pal[None]) ** 2).sum(2)).min(1)
            halo = float(((d_bg < 8) & (d_pal > d_bg + 10)).mean())
            rep["halo"] = round(halo, 3)
            # на почти чёрном фоне эталона (яркость < 40) его цвет - это и цвет тёмной обводки рисунка; такая кайма
            # на тёмном полу игры не видна - число пишется, провалом не считается
            if halo > HALO_MAX and float(np.mean(bg_ref)) >= 40:
                fails.append("HALO %.2f" % halo)
    return rep, fails


def carry_raw_size(raw_fail, fin_fail):
    """Брак размера сырого остаётся браком итога (указание 05.10): итог с альфой по силуэту оригинала срезан маской
    до габарита и SIZE у него проходит, хотя модель нарисовала предмет не того размера. -> новый список итога."""
    have = {f.split()[0] for f in fin_fail}
    out = list(fin_fail)
    for f in raw_fail:
        k = f.split()[0]
        if k in ("SIZE_W", "SIZE_H") and k not in have:
            out.append("%s (сырой ответ; итог срезан маской до габарита)" % f)
    return out


def muzzle_point(m, dx, dy, scale):
    """Середина крайних пикселей маски по направлению (dx, dy): полоса шириной в пиксель базы."""
    ys, xs = np.nonzero(m > 0.5)
    proj = xs * dx + ys * dy
    top = proj.max()
    band = proj >= top - scale * (1.0 if dx == 0 or dy == 0 else 1.5)
    return float(xs[band].mean() + 0.5), float(ys[band].mean() + 0.5)


# ---------------------------------------------------------------- один предмет

def cut_holes(a16, rgb16, m_o, box, bg, tol=14.0):
    """Отверстия: там, где они у оригинала (окрестность в пиксель базы), и только по пикселям, которые в эталоне
    цвета его фона. Маску оригинала на ответ не натягиваем: нет фона в эталоне - отверстия нет, проверка это
    покажет. -> (альфа, вырезано пикселей x16 по каждому отверстию)."""
    if bg is None:
        return a16, []
    x0, y0, x1, y1 = box
    ho = holes_of(m_o[y0:y1, x0:x1])
    if not ho.any():
        return a16, []
    lab, areas = labels(ho)
    H, W = a16.shape
    d = np.sqrt(((rgb16 - np.asarray(bg, np.float32)) ** 2).sum(2))
    cut = np.zeros((H, W), bool)
    rep = []
    for i in range(1, len(areas)):
        near = np.repeat(np.repeat(dilate(lab == i, 1), Z, 0), Z, 1)[:H, :W]
        c = near & (d <= tol) & (a16 > 0.5)
        cut |= c
        rep.append(int(c.sum()))
    if cut.any():
        soft = np.clip(blur(cut.astype(np.float32), 0.7) * 1.6, 0, 1)
        a16 = a16 * (1 - soft)
    return a16, rep


def to_k4(rgb16, a16):
    """x16 -> x4: альфа - среднее блока 4x4, цвет - среднее по альфе (без подложки)."""
    H, W = a16.shape
    h, w = H // 4, W // 4
    a = a16[:h * 4, :w * 4].reshape(h, 4, w, 4)
    c = rgb16[:h * 4, :w * 4].reshape(h, 4, w, 4, 3)
    asum = a.sum((1, 3))
    col = (c * a[..., None]).sum((1, 3)) / np.maximum(asum, 1e-6)[..., None]
    alpha = asum / 16.0
    alpha = np.where(alpha > 0.985, 1.0, alpha)
    return col, alpha


def do_item(row, lrow):
    t = row["type"]
    rgb_o, m_o = original(t)
    T, box = target_of(m_o)
    holes_t = holes_of(T)
    ref = row.get("ref", "-").strip()
    res = {"master": row["master"], "type": t, "frame": lrow["frame"], "ref": ref, "ref_src": row.get("ref_src")}
    if not ref or ref == "-" or not os.path.exists(os.path.join(ROOT, ref)):
        res["verdict"] = "NO_REF"
        return res, None
    t0 = time.time()
    bo = bbox(m_o)
    rgb_r, a_r, bg = matte(ref, max(bo[2] - bo[0], bo[3] - bo[1]))
    r2, a2, ori, ang, iou0, aniso = fit_global(rgb_r, a_r, T)
    res.update({"orient": [ori[0] * 90, ori[1]], "angle": ang, "fit_score": round(iou0, 3), "aniso": round(aniso, 3),
                "ref_bg": bg})
    # три начала: габарит целиком, профиль вдоль ствола, участки (аффинно по участкам и мягкая доводка - сдвиг
    # за шаг до половины пикселя базы, 4 шага). Каждое проходит все проверки; берётся прошедшее с наименьшим
    # растяжением, не прошло ни одно - с наименьшим числом провалов, при равенстве - меньшее растяжение
    sFx, sFy, nseg = segments_init(a2, T)
    res["segments"] = nseg
    tries = []
    for name, init, kw in (("rigid", None, {"iters": 0}), ("segments0", (sFx, sFy), {"iters": 0}),
                           ("bbox", None, {}), ("profile", profile_init(a2, T), {}),
                           ("segments", (sFx, sFy), {"iters": 4, "cap": Z * 0.5, "lam0": 6.0}),
                           ("segments+", (sFx, sFy), {"iters": 10, "cap": Z * 1.0, "lam0": 4.0})):
        Fx, Fy, stretch, hist = fit_tps(a2, a2, T, holes_t, init=init, **kw)
        out = finish(r2, a2, Fx, Fy, stretch, hist, aniso, rgb_o, m_o, box, bg, row)
        tries.append((name, out))
    name, out = min(tries, key=lambda t_: (len(t_[1]["fail"]), t_[1]["stretch"]))
    res["init"] = name
    res["tries"] = {n_: {"iou": o_["iou_tps"][-1], "stretch": o_["stretch"], "fail": o_["fail"]} for n_, o_ in tries}
    imgs = out.pop("imgs")
    res.update(out)
    res["seconds"] = round(time.time() - t0, 1)
    res["verdict"] = "CANDIDATE" if not res["fail"] else "DEFERRED"
    res["status"] = row.get("status", "").strip()
    return res, imgs


def do_synth(row, lrow, sdir):
    """Готовый эталон weapons_synth.py (нарисован сразу в раскладке оригинала) - без подгонки, только проверки:
    сырой ответ - матт модели на холсте кропа x4 (item_photo.canvas_map, то же преобразование, что у вырезки),
    итог - кадр пака k=4. Альфа итога идёт от силуэта оригинала (R-089), поэтому пропажа и тонкое честны только
    у сырого; кромка, полупрозрачное и дуло - у обоих."""
    import item_photo as ip
    t = row["type"]
    res = {"master": row["master"], "type": t, "frame": lrow["frame"], "ref": "-", "ref_src": "synth"}
    mp = os.path.join(sdir, "meta", t + ".json")
    if not os.path.exists(mp):
        res["verdict"] = "NO_SYNTH"
        return res, None
    with open(mp, encoding=ENC) as f:
        meta = json.load(f)
    rgb_o, m_o = original(t)
    box = bbox(m_o)
    x0, y0, x1, y1 = box
    ip.CARDS = os.path.join(BATCH, "cards")
    full, _src = ip.load_frame(t, int(lrow["frame"]))
    crop, cbox = ip.crop_job(full)
    native = meta.get("raw_alpha") and os.path.exists(meta["raw_alpha"])
    if native:
        # ответ со своей альфой: она и есть матт сырого, подложки нет - вычитать нечего (R-089, седьмой раз)
        ha = np.asarray(Image.open(meta["raw_alpha"]).convert("RGBA"), np.float32)
        cw4, ch4 = crop.width * K, crop.height * K
        al = ha[..., 3] / 255.0
        pre = [Image.fromarray(ha[..., i] * al, "F").resize((cw4, ch4), Image.LANCZOS) for i in range(3)]
        m_c = np.clip(np.asarray(Image.fromarray(al, "F").resize((cw4, ch4), Image.LANCZOS)), 0, 1).astype(np.float32)
        rgb4 = np.dstack([np.asarray(p) for p in pre]) / np.maximum(m_c, 1e-3)[..., None]
        rgb4 = np.where(m_c[..., None] > 1e-3, np.clip(rgb4, 0, 255), 0).astype(np.float32)
        bg = np.asarray((176, 176, 182), np.float32)
    else:
        hd = Image.open(meta["raw"])
        rgb4, _mc, _mr, bg, _own, _info = ip.canvas_map(hd, crop)
        # матт проверки - расстояние до подложки ответа, без заливки замкнутого: render_matte закрывает просвет
        # (тетива лука, рамка приклада), и проверка видела бы «лишнее» там, где модель нарисовала подложку
        m_c = np.clip((ip.pb.shadow_dist(rgb4, bg) - 10.0) / 14.0, 0, 1).astype(np.float32)
    ox, oy = cbox[0] - ip.PAD, cbox[1] - ip.PAD          # угол кропа в кадре 32x48
    H4, W4 = (y1 - y0) * K, (x1 - x0) * K
    a_raw = np.zeros((H4, W4), np.float32)
    c_raw = np.zeros((H4, W4, 3), np.float32)
    sy, sx = (y0 - oy) * K, (x0 - ox) * K
    ys0, xs0 = max(0, sy), max(0, sx)
    ys1, xs1 = min(m_c.shape[0], sy + H4), min(m_c.shape[1], sx + W4)
    a_raw[ys0 - sy:ys1 - sy, xs0 - sx:xs1 - sx] = m_c[ys0:ys1, xs0:xs1]
    # цвет кромки ответа смешан с подложкой (матт мягкий) - очищен той же decontaminate, что и итог, иначе RIM
    # сырого меряет подложку, а не кайму модели; форма и матт сырого - без правки
    if not native:
        rgb4 = ip.pb.decontaminate(rgb4, m_c, bg)
    c_raw[ys0 - sy:ys1 - sy, xs0 - sx:xs1 - sx] = rgb4[ys0:ys1, xs0:xs1]
    pal = np.unique(rgb_o[m_o], axis=0)
    # у холодного оружия дула нет - точка «дула» по направлению острия не проверяется (специалист 05.10)
    mz = "-" if lrow.get("kind", "").strip() == "melee" else row.get("muzzle", "-").strip()
    bgl = [float(v) for v in bg]
    raw_rep, raw_fail = gates(a_raw, c_raw, m_o, box, K, mz, bgl, pal, full=m_c, org=(sx, sy))
    fr = np.asarray(Image.open(meta["file"]).convert("RGBA")).astype(np.float32)
    # итог place_fixed срезан по клеткам (без решения inherit_overflow - decisions.tsv, только названные мастера):
    # оригинал, который сам заходит за клетки, мерить итог против оригинала в клетках, а выход - отдельно, вопросом
    cw_, ch_ = [int(v) for v in lrow["cells"].split("x")]
    gx0, gy0, gx1, gy1 = ip.iac.grid_rect(cw_, ch_)
    cells = np.zeros_like(m_o)
    cells[gy0:gy1, gx0:gx1] = True
    m_f = m_o & cells
    res["overflow_px"] = int((m_o & ~cells).sum())
    fbox = bbox(m_f) if res["overflow_px"] and m_f.any() else box
    fx0, fy0, fx1, fy1 = fbox
    fin_rep, fin_fail = gates(fr[fy0 * K:fy1 * K, fx0 * K:fx1 * K, 3] / 255.0,
                              fr[fy0 * K:fy1 * K, fx0 * K:fx1 * K, :3], m_f if res["overflow_px"] else m_o, fbox, K,
                              mz, bgl, pal, full=fr[..., 3] / 255.0, org=(fx0 * K, fy0 * K))
    fin_fail = carry_raw_size(raw_fail, fin_fail)
    res.update({"raw": raw_rep, "raw_fail": raw_fail, "final": fin_rep, "final_fail": fin_fail,
                "model_geometry": meta.get("model_geometry"), "machine": meta.get("machine"),
                "synth_raw": meta["raw"], "generator_rev": meta.get("generator_rev"),
                "fail": ["raw:" + f_ for f_ in raw_fail] + ["final:" + f_ for f_ in fin_fail],
                "status": row.get("status", "").strip()})
    res["verdict"] = "CANDIDATE" if not res["fail"] else "DEFERRED"
    raw_img = Image.fromarray(np.dstack([np.clip(c_raw, 0, 255), a_raw[..., None] * 255]).astype(np.uint8), "RGBA")
    res["ref"] = meta["raw"]
    return res, (raw_img, Image.open(meta["file"]).convert("RGBA"))


def finish(r2, a2, Fx, Fy, stretch, hist, aniso, rgb_o, m_o, box, bg, row):
    """Отображение -> подгонка x16, цвет по зонам, кадр k=4 и проверки обоих."""
    res = {}
    rgb16 = sample(r2, Fx, Fy)
    a16 = np.clip(sample(a2, Fx, Fy), 0, 1)
    a16, res["holes_cut"] = cut_holes(a16, rgb16, m_o, box, bg)
    res["iou_tps"] = [round(v, 3) for v in hist]
    res["stretch"] = round(stretch, 2)
    rgb16c, zrep = color_zones(rgb16, a16, rgb_o, m_o, box)
    res["zones"] = zrep
    # сырой результат подгонки (x16) - проверки
    pal = np.unique(rgb_o[m_o], axis=0)
    raw_rep, raw_fail = gates(a16, rgb16c, m_o, box, Z, row.get("muzzle", "-").strip(), bg, pal)
    # итог k=4 на кадре оригинала
    col4, al4 = to_k4(rgb16c, a16)
    hb, wb = m_o.shape
    frame = np.zeros((hb * K, wb * K, 4), np.float32)
    x0, y0, x1, y1 = box
    hh, ww = al4.shape
    frame[y0 * K:y0 * K + hh, x0 * K:x0 * K + ww, :3] = col4
    frame[y0 * K:y0 * K + hh, x0 * K:x0 * K + ww, 3] = al4
    fin_rep, fin_fail = gates(frame[y0 * K:y1 * K, x0 * K:x1 * K, 3], frame[y0 * K:y1 * K, x0 * K:x1 * K, :3], m_o,
                              box, K, row.get("muzzle", "-").strip(), bg, pal)
    fin_fail = carry_raw_size(raw_fail, fin_fail)
    fails = []
    if aniso > ANISO_MAX:
        fails.append("ANISO %.2f" % aniso)
    if stretch > STRETCH_MAX:
        fails.append("STRETCH %.2f" % stretch)
    res.update({"raw": raw_rep, "raw_fail": raw_fail, "final": fin_rep, "final_fail": fin_fail,
                "fail": fails + ["raw:" + f for f in raw_fail] + ["final:" + f for f in fin_fail]})
    img16 = Image.fromarray(np.dstack([np.clip(rgb16c, 0, 255), a16[..., None] * 255]).astype(np.uint8), "RGBA")
    img4 = Image.fromarray(np.dstack([np.clip(frame[..., :3], 0, 255), frame[..., 3:] * 255]).astype(np.uint8),
                           "RGBA")
    res["imgs"] = (img16, img4)
    return res


# ---------------------------------------------------------------- лист

def font(sz):
    for p in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def on_dark(im):
    c = Image.new("RGBA", im.size, DARK + (255,))
    c.alpha_composite(im.convert("RGBA"))
    return c


def diff_cell(alpha4, m_o):
    """Пиксели базы: совпало (серое), выпало (красное), лишнее (синее), отверстие оригинала закрыто (жёлтое)."""
    hb, wb = m_o.shape
    blk = alpha4[:hb * K, :wb * K].reshape(hb, K, wb, K).mean((1, 3))
    v = np.zeros((hb, wb, 3), np.uint8)
    v[:] = DARK
    v[m_o & (blk >= 0.3)] = (150, 150, 150)
    v[m_o & (blk < 0.3)] = (235, 60, 50)
    v[(blk >= 0.5) & ~dilate(m_o, 1)] = (60, 110, 240)
    v[(blk >= 0.5) & ~m_o & dilate(m_o, 1)] = (70, 75, 85)
    x0, y0, x1, y1 = bbox(m_o)
    ho = np.zeros_like(m_o)
    ho[y0:y1, x0:x1] = holes_of(m_o[y0:y1, x0:x1])
    v[ho & (blk >= 0.5)] = (240, 210, 40)
    return Image.fromarray(v).resize((wb * 8, hb * 8), Image.NEAREST).convert("RGBA")


def sheet(items, path, title):
    """Строка на предмет: оригинал x8 | эталон | подгонка x16 (сырой) | итог k=4 x2 | в игре 1:1 на тёмном."""
    CH = 400
    cols = ["оригинал x8", "эталон", "подгонка (сырой)", "итог k=4, x2", "в игре 1:1",
            "разница x8: серое совпало, красное выпало, синее лишнее, жёлтое - отверстие закрыто"]
    f, fs = font(18), font(14)
    rows = []
    for it in items:
        t = it["res"]["type"]
        rgb_o, m_o = original(t)
        o = Image.fromarray(np.dstack([rgb_o, m_o[..., None] * 255]).astype(np.uint8), "RGBA")
        cells = [on_dark(o.resize((o.width * 8, o.height * 8), Image.NEAREST))]
        ref = it["res"].get("ref")
        if ref and ref != "-" and os.path.exists(os.path.join(ROOT, ref)):
            r = Image.open(os.path.join(ROOT, ref)).convert("RGBA")
            s = min(CH / float(r.height), 260 / float(r.width))
            cells.append(on_dark(r.resize((max(1, int(r.width * s)), max(1, int(r.height * s))), Image.LANCZOS)))
        else:
            cells.append(Image.new("RGBA", (200, CH), DARK + (255,)))
        if it.get("imgs"):
            i16, i4 = it["imgs"]
            s = CH / float(i16.height)
            cells.append(on_dark(i16.resize((max(1, int(i16.width * s)), CH), Image.LANCZOS)))
            cells.append(on_dark(i4.resize((i4.width * 2, i4.height * 2), Image.LANCZOS)))
            cells.append(on_dark(i4))
            cells.append(diff_cell(np.asarray(i4)[..., 3] / 255.0, m_o))
        rows.append((it, cells))
    nc = len(cols)
    W = 20 + sum(max((c[1][i].width if i < len(c[1]) else 0) for c in rows) + 20 for i in range(nc))
    widths = [max((c[1][i].width if i < len(c[1]) else 0) for c in rows) for i in range(nc)]
    H = 60 + sum(max(c.height for c in cells) + 70 for _it, cells in rows)
    sh = Image.new("RGB", (max(W, 900), H), (18, 19, 22))
    d = ImageDraw.Draw(sh)
    d.text((20, 10), title, fill=(230, 230, 230), font=f)
    x = 20
    for i, c in enumerate(cols):
        d.text((x, 36), c, fill=(170, 170, 170), font=fs)
        x += widths[i] + 20
    y = 60
    for it, cells in rows:
        x = 20
        for i, c in enumerate(cells):
            sh.paste(c.convert("RGB"), (x, y))
            x += widths[i] + 20
        r = it["res"]
        hgt = max(c.height for c in cells)
        v = r.get("verdict")
        colr = (120, 220, 120) if v == "CANDIDATE" else (240, 160, 90)
        line1 = "%s %s  %s  %s" % (r["master"], r["type"], v, it["row"].get("model", "")[:70])
        fr = r.get("final") or {}
        rw = r.get("raw") or {}
        line2 = ("сырой ш %+.1f%% в %+.1f%% | итог ш %+.1f%% в %+.1f%%  дуло %s  выпало %s  лишнее %s  тонкое %s  перекос %s  растяж %s" % (
            rw.get("dw_pct", 0), rw.get("dh_pct", 0), fr.get("dw_pct", 0), fr.get("dh_pct", 0), fr.get("muzzle_dist", "-"), fr.get("drop", "-"),
            fr.get("extra", "-"), fr.get("thin_kept", "-"), r.get("aniso", "-"), r.get("stretch", "-"))
                 if fr else "")
        if r.get("overflow_px"):
            line2 += "  OVERFLOW: оригинал за клетками %d пикс базы - итог срезан по клетке" % r["overflow_px"]
        d.text((20, y + hgt + 6), line1, fill=colr, font=fs)
        d.text((20, y + hgt + 26), line2, fill=(200, 200, 200), font=fs)
        if r.get("fail"):
            d.text((20, y + hgt + 46), "; ".join(r["fail"])[:180], fill=(240, 120, 100), font=fs)
        y += hgt + 70
    sh.save(path)


# ---------------------------------------------------------------- main

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--ident", default="", help="свой файл опознания вместо ident/batch_*.tsv")
    ap.add_argument("--tag", default="")
    ap.add_argument("--synth", default="", help="папка weapons_synth.py: проверить готовые эталоны без подгонки")
    a = ap.parse_args()
    os.chdir(ROOT)
    lrows = list_rows()
    rows = []
    if a.ident:
        rows = read_tsv(a.ident)
    else:
        for k in ([a.batch] if a.batch else range(1, 6)):
            rows += batch_rows(k)
    if a.only:
        want = set(a.only.split(","))
        rows = [r for r in rows if r["master"] in want]
    if not rows:
        raise SystemExit("нет строк опознания (art/items/weapons100-v3/ident/batch_*.tsv)")
    for sub in ("fit", "pack/BIGOBS.PCK", "meta"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    items = []
    for r in rows:
        lr = lrows[r["master"]]
        res, imgs = do_synth(r, lr, a.synth) if a.synth else do_item(r, lr)
        if a.synth and res["verdict"] == "NO_SYNTH":
            continue
        if imgs and not a.synth:
            imgs[0].save(os.path.join(OUT, "fit", r["type"] + ".png"))
            imgs[1].save(os.path.join(OUT, "pack", "BIGOBS.PCK", "%s.%s.png" % (lr["frame"], r["type"])))
        with open(os.path.join(OUT, "meta", r["type"] + ".json"), "w", encoding=ENC) as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print("%s %s %s %s" % (r["master"], r["type"], res["verdict"], "; ".join(res.get("fail", []))), flush=True)
        items.append({"row": r, "res": res, "imgs": imgs})
    tag = ("batch%d" % a.batch) if a.batch else "all"
    if a.only:
        tag += "_only"
    if a.tag:
        tag = a.tag
    # спорное опознание - отдельным листом (указание 04.10): подгоняется так же, но эталон под вопросом
    main_ = [it for it in items if it["row"].get("status", "").strip() != "DISPUTED"]
    disp = [it for it in items if it["row"].get("status", "").strip() == "DISPUTED"]
    if main_:
        sheet(main_, os.path.join(OUT, "sheet_%s.png" % tag),
              "weapons100-v3 %s: фото-эталон на геометрии оригинала" % tag)
    if disp:
        sheet(disp, os.path.join(OUT, "sheet_%s_disputed.png" % tag),
              "weapons100-v3 %s: СПОРНОЕ ОПОЗНАНИЕ - эталон под вопросом" % tag)
    with open(os.path.join(OUT, "gates_%s.tsv" % tag), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        # dw_pct/dh_pct - итог (часто срезан маской до габарита), raw_dw_pct/raw_dh_pct - что нарисовала модель
        w.writerow(["master", "type", "verdict", "dw_pct", "dh_pct", "raw_dw_pct", "raw_dh_pct", "muzzle_dist", "drop", "extra", "thin_kept",
                    "holes_open", "semi_core", "halo", "aniso", "stretch", "overflow_px", "raw_fail", "final_fail"])
        for it in items:
            r = it["res"]
            fr = r.get("final") or {}
            rw = r.get("raw") or {}
            w.writerow([r["master"], r["type"], r["verdict"], fr.get("dw_pct", ""), fr.get("dh_pct", ""),
                        rw.get("dw_pct", ""), rw.get("dh_pct", "")] +
                       [fr.get(k, "") for k in ("muzzle_dist", "drop", "extra", "thin_kept",
                                                "holes_open", "semi_core", "halo")] +
                       [r.get("aniso", ""), r.get("stretch", ""), r.get("overflow_px", ""),
                        "; ".join(r.get("raw_fail", [])),
                        "; ".join(r.get("final_fail", []))])
    print("лист -> %s" % os.path.join(OUT, "sheet_%s.png" % tag))


if __name__ == "__main__":
    main()
