#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000222: жёлтая двойная разметка PORTROADS:9-14 - сплошные полосы по маске классики. Без генерации.

Что не так: в HD концы полос недотянуты и сглажены, у соседних кадров сдвинуты на 1-2 px, на стыке клеток тёмный просвет, а
сама полоса рваная «пилой» (HD рисован клетка за клеткой). В классике полоса каждой клетки доходит до края ромба.

Рецепт (вариант А разбора, Vitali 23.10):
  1. маска полос классики - индексы 71, 19, 18 (жёлтое с зелёной каймой), контур берётся на сетке x16 по углам пикселей классики
     и упрощается до прямых (approxPolyDP): ступеньки 2x1 превращаются в прямую со склонами +-1/2, вершины - острые углы;
  2. концы полос лежат на ступенчатом краю ромба: такой край (все точки ближе ~1 px классики к пустоте) вытягивается наружу
     по соседним длинным рёбрам (экструзия) и затем режется ТОЧНОЙ маской классики x4 (ступеньки ромба) - соседние клетки
     стыкуются без просвета и перехлёста (маски соседних кадров дополняют друг друга, R-247, R-249);
  3. углы шевронов слегка скругляются (раскрытие кругом), полоса сужается на ~1.5 px HD с каждой стороны (классика берёт зелёную кайму);
  4. прежняя жёлтая полоса HD убирается (inpaint по расширенной маске жёлтого), асфальт остаётся своим; новая полоса - цвет и
     зерно текущей жёлтой полосы HD (медиана, умеренное мотыление), без зелёного;
  5. основы 9 и 11; 10 - зеркало 9 по горизонтали, 14 - зеркало 11 (R-296, в классике побайтно так же); 12 и 13 - свои основы
     (классика 12 и 13 не зеркала друг друга: ромб классики несимметричен по вертикали).
Альфа кадра не меняется (она уже точно по силуэту классики x4).

    py -3.13 tools/hdart/t222_lines.py                  # кадры в art/tickets/t222/out_lines/TERRAIN/PORTROADS.PCK
    py -3.13 tools/hdart/t222_lines.py --install --yes  # + в мод hd через манифест (под очередью правок)
ABUNKER:39-44 и XOPSDESERT:80-85 - ложная семья по силуэту (R-468), не трогаются.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts  # noqa: E402
import water_build as wb   # noqa: E402

OUT = ROOT / "art" / "tickets" / "t222" / "out_lines"
PACK = ts.PACK / "PORTROADS.PCK"
S = 16                     # сетка контура: 1 px классики = 16, 1 px HD = 4
STRIPE = [71, 19, 18]
EPS = 1.1                  # допуск упрощения, px классики
EXT = 6.0                  # вытягивание концов наружу, px классики
INSET = 1.5                # сужение полосы с каждой стороны, px HD
ROUND = 2.5                # скругление выпуклых углов, px HD
BASES = {9: "own", 11: "own", 12: "own", 13: "own"}
MIRRORS = {10: 9, 14: 11}


def load_hd(f):
    return np.asarray(Image.open(PACK / ("%d.png" % f)).convert("RGBA")).astype(np.uint8)


def yellow(a, strict=True):
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    if strict:
        return (a[..., 3] > 127) & (r > 110) & (g > 60) & (r - b > 70)
    return (a[..., 3] > 127) & (r - b > 38) & (r > 70)


def _fit(pts, sg):
    """Прямая y = sg*0.5*x + c по точкам контура (ступеньки 2x1: средняя по ступеням - середина)."""
    c = float(np.mean(pts[:, 1] - sg * 0.5 * pts[:, 0]))
    return sg * 0.5, c


def _cross(l1, l2):
    (m1, c1), (m2, c2) = l1, l2
    if abs(m1 - m2) < 1e-6:
        return None
    x = (c2 - c1) / (m1 - m2)
    return np.array([x, m1 * x + c1])


def polygons(c):
    """Контуры полос классики на сетке x16 (список Nx2 float): длинные стороны - прямые со склоном ровно +-1/2 (по всем точкам
    ступенек), углы - пересечения прямых, концы на ступенчатом краю ромба вытянуты наружу по прямым (потом режутся маской)."""
    m = np.isin(c, STRIPE)
    sil = c > 0
    big = np.kron(m, np.ones((S, S), np.uint8)).astype(np.uint8) * 255
    dist = ndi.distance_transform_edt(np.kron(sil, np.ones((S, S), bool)))     # до пустоты, в точках сетки
    cnts, _ = cv2.findContours(big, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out, fills = [], []
    silbig = np.kron(sil, np.ones((S, S), np.uint8)) > 0
    for cn in cnts:
        if cv2.contourArea(cn) < 40 * S * S * 0.25:
            continue
        fl = np.zeros(big.shape, np.uint8)
        cv2.drawContours(fl, [cn], -1, 255, -1)
        fills.append(fl > 0)
        pts_all = cn[:, 0, :].astype(np.float64)
        ap = cv2.approxPolyDP(cn, EPS * S, True)[:, 0, :].astype(np.float64)
        # индексы вершин в контуре
        idx = []
        for v in ap:
            idx.append(int(np.nonzero((pts_all == v).all(1))[0][0]))
        order = np.argsort(idx)
        ap = ap[order]
        idx = [idx[i] for i in order]
        n = len(ap)

        def edge_pts(i):
            i0, i1 = idx[i], idx[(i + 1) % n]
            if i1 > i0:
                return pts_all[i0:i1 + 1]
            return np.vstack([pts_all[i0:], pts_all[:i1 + 1]])

        def is_end(i):
            a_, b_ = ap[i], ap[(i + 1) % n]
            q = [a_ + (b_ - a_) * t for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
            d = [dist[min(int(p[1]), dist.shape[0] - 1), min(int(p[0]), dist.shape[1] - 1)] for p in q]
            return max(d) <= 1.3 * S and np.hypot(*(b_ - a_)) < 12 * S

        kind, line = [], []
        for i in range(n):
            a_, b_ = ap[i], ap[(i + 1) % n]
            L = np.hypot(*(b_ - a_))
            sl = (b_[1] - a_[1]) / (b_[0] - a_[0]) if abs(b_[0] - a_[0]) > 1e-6 else 99.0
            if is_end(i):
                kind.append("E"); line.append(None)
            elif L >= 3.5 * S and abs(abs(sl) - 0.5) < 0.22:
                sg = 1 if sl > 0 else -1
                kind.append("L"); line.append(_fit(edge_pts(i), sg))
            else:
                kind.append("O"); line.append(None)
        poly = []
        for j in range(n):                       # вершина j между рёбрами j-1 и j
            e0, e1 = (j - 1) % n, j
            k0, k1 = kind[e0], kind[e1]
            if k0 != "L" and k1 != "L":           # промежуточная вершина между короткими рёбрами конца - выбросить
                continue
            v = ap[j].copy()
            if k0 == "L" and k1 == "L":
                x = _cross(line[e0], line[e1])
                if x is not None and np.hypot(*(x - ap[j])) < 6 * S:
                    v = x
            elif k0 == "L" and k1 in ("E", "O"):
                m_, c_ = line[e0]                # конец прямой: проекция вершины на неё и вытягивание вперёд
                d = np.array([1.0, m_]); d /= np.hypot(*d)
                if np.dot(ap[j] - ap[e0], d) < 0:
                    d = -d
                x0 = ap[j][0]
                v = np.array([x0, m_ * x0 + c_])
                if k1 == "E":
                    v = v + d * EXT * S
            elif k1 == "L" and k0 in ("E", "O"):
                m_, c_ = line[e1]
                d = np.array([1.0, m_]); d /= np.hypot(*d)
                if np.dot(ap[j] - ap[(j + 1) % n], d) < 0:
                    d = -d
                x0 = ap[j][0]
                v = np.array([x0, m_ * x0 + c_])
                if k0 == "E":
                    v = v + d * EXT * S
            poly.append(v)
        out.append(np.array(poly))
    return _repair(out, fills, silbig)


def _raster(poly, shape, dx=0.0, dy=0.0):
    r = np.zeros(shape, np.uint8)
    cv2.fillPoly(r, [np.round(poly + np.array([dx, dy])).astype(np.int32)], 1)
    return r > 0


def _iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def _repair(polys, fills, silbig):
    """Малая полоса (внутренний шеврон) при упрощении теряет вырез: её заменяет перенос лучшей полосы кадра, если он ложится на маску
    классики (IoU >= 0.75). Перенос ищется по целым px классики."""
    sh = fills[0].shape
    q = [_iou(_raster(p, sh) & silbig, f) for p, f in zip(polys, fills)]
    if not q or max(q) < 0.8:
        return polys
    donor = polys[int(np.argmax(q))]
    out = []
    for p, f, qi in zip(polys, fills, q):
        if qi >= 0.78:
            out.append(p)
            continue
        best = (qi, None)
        for dy in range(-14, 15):
            for dx in range(-6, 7):
                v = _iou(_raster(donor, sh, dx * S, dy * S) & silbig, f)
                if v > best[0]:
                    best = (v, (dx, dy))
        if best[1] is not None and best[0] >= 0.75:
            print("  полоса заменена переносом основной на %s (IoU %.2f -> %.2f)" % (best[1], qi, best[0]))
            out.append(donor + np.array([best[1][0] * S, best[1][1] * S]))
        else:
            out.append(p)
    return out


def stripe_cover(c):
    """Покрытие полосой (0..1) на сетке HD 128x160 по классике c (40x32)."""
    polys = polygons(c)
    big = np.zeros((160 * 4, 128 * 4), np.uint8)       # x16 от классики: 40*16=640 x 32*16=512
    for p in polys:
        cv2.fillPoly(big, [np.round(p).astype(np.int32)], 255)
    k = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(r) * 2 + 1, int(r) * 2 + 1))
    big = cv2.morphologyEx(big, cv2.MORPH_OPEN, k(ROUND * 4))
    big = cv2.erode(big, k(INSET * 4))
    sil = np.kron(c > 0, np.ones((S, S), np.uint8)) * 255
    big = cv2.bitwise_and(big, sil)
    cov = cv2.resize(big, (128, 160), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    return cov


def fbm(shape, rng, sig=(1.5, 3.5), w=(0.6, 0.4)):
    n = np.zeros(shape, np.float32)
    for s, k in zip(sig, w):
        g = ndi.gaussian_filter(rng.standard_normal(shape).astype(np.float32), s, mode="wrap")
        n += k * g / (g.std() + 1e-6)
    return n / (n.std() + 1e-6)


def build(f, rng):
    c = wb.read_set("PORTROADS")[f]
    hd = load_hd(f)
    rgb = hd[..., :3].copy()
    a = hd[..., 3]
    ys = yellow(hd)
    col = np.median(rgb[ys], axis=0) if ys.sum() > 50 else np.array([225, 150, 10.0])
    # прежняя полоса прочь: расширенная маска жёлтого, inpaint по асфальту
    old = ndi.binary_dilation(yellow(hd, strict=False), iterations=4) & (a > 0)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    inp = cv2.inpaint(bgr, old.astype(np.uint8) * 255, 7, cv2.INPAINT_TELEA)
    base = cv2.cvtColor(inp, cv2.COLOR_BGR2RGB).astype(np.float32)
    # зерно асфальта в залитом: шум по статистике вне маски
    ok = (a > 0) & ~old
    if ok.sum() > 100 and old.sum() > 0:
        lum = base @ np.array([0.299, 0.587, 0.114], np.float32)
        hf = lum - ndi.gaussian_filter(lum, 2.0)
        sd = hf[ok].std()
        nz = fbm(a.shape, rng, sig=(0.8, 1.6)) * sd * 0.8
        base += (nz * old.astype(np.float32))[..., None] * ndi.gaussian_filter(old.astype(np.float32), 1.0)[..., None]
    cov = stripe_cover(c)
    tex = 1 + 0.06 * fbm(a.shape, rng)
    stripe = np.clip(col[None, None, :] * tex[..., None], 0, 255)
    out = base * (1 - cov[..., None]) + stripe * cov[..., None]
    res = np.dstack([np.clip(out, 0, 255).round().astype(np.uint8), a])
    return res


def build_all():
    rng = np.random.RandomState(222)
    res = {}
    for f in BASES:
        res[f] = build(f, rng)
    for f, src in MIRRORS.items():
        res[f] = res[src][:, ::-1].copy()
    return res


def save_all(res):
    d = OUT / "TERRAIN" / "PORTROADS.PCK"
    d.mkdir(parents=True, exist_ok=True)
    files = {}
    for f, a in sorted(res.items()):
        p = d / ("%d.png" % f)
        Image.fromarray(a, "RGBA").save(p)
        files["TERRAIN/PORTROADS.PCK/%d.png" % f] = p
    return files


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = save_all(build_all())
    print("кадров: %d -> %s" % (len(files), OUT))
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(files, "t222_lines", "t222_lines.py 23.10 полосы по маске классики, основы 9 и 11, 10 и 14 зеркалом",
                         "Vitali 23.10 (XP-000222 разметка, вариант А процедурно); лист art/_review/tickets_2026-10-23/t222_lines_frames.png",
                         "t222: жёлтая разметка PORTROADS 9-14 сплошная")
    return 0


if __name__ == "__main__":
    sys.exit(main())
