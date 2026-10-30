#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000417: жёлтый контейнер PORTROADS 81-86 (2x3: ряд0 85 86 / ряд1 84 83 / ряд2 82 81) - пилот B+C (Vitali 30.10:
«края должны быть ровные не лесенкой!»). В МОД НИЧЕГО НЕ СТАВИТ без `install --yes` и слова Vitali: кадры -
art/tickets/t417/cand/s<зерно>/PORTROADS_<кадр>.png, листы - art/_review/tickets_2026-10-30/t417_*.png.

Рецепт:
  B. весь контейнер ОДНОЙ картинкой: холст классики 80x64 (кадры по смещениям движка (x-y)*16, (x+y)*8) bicubic x16 на подложке
     pick_background -> Qwen-Image-2.1 strict (путь t404/t405: 40 шагов, cfg 4, 1 Мп), ракурс и свет - только
     battle_view.prompt_block("object"), 3 зерна. Нарезка по клеткам: у соседей одни и те же пиксели общей картинки - шва нет.
  C. внешний контур - ровные линии, а не ступенька классики x4 (R-121): силуэт объединения классики -> многоугольник (Дуглас-Пекер
     по контуру, потом каждая сторона - прямая наименьших квадратов, угол прижат к 2:1, 1:1, 1:2, вертикали, горизонтали, стороны
     сдвинуты на границу пикселей); многоугольник растеризуется x4 со сглаживанием (сверхдискретизация x8, фильтр-коробка).
     Сглаживается ТОЛЬКО внешний край: везде внутри контура альфа 255, в том числе на стыках клеток (R-439/R-247).
     Пиксель кромки (альфа меньше 255) рисует ровно одна клетка (иначе два полупрозрачных слоя дадут нитку, R-289); владелец -
     по решётке клеток (ромб-территория со сдвигом вверх на 16 px: решётка периодична вдоль оси контейнера, поэтому у контейнера
     2x4 (пара 84/83 дважды, PORTUFO17/37) кромка не удваивается и не рвётся).
  D. проверки: сборка кадров движком == общая картинка; просвет на стыках (rim_alpha-подобно: альфа сложения внутри контура
     ниже 250 и расхождение с целью); шов (средний скачок яркости между соседними пикселями РАЗНЫХ клеток: классика x4 /
     HD сейчас / зёрна); прямота кромки (отклонение края от прямой, пикс x4); контейнер 2x4 - стыки рядов 0|1, 1|2, 2|3.

    py -3.13 tools\hdart\t417_container_gen.py preview
    py -3 tools\gpuq.py add --name t417-container --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t417_container_gen.py render
    py -3.13 tools\hdart\t417_container_gen.py build        # кадры по всем зёрнам, проверки (tsv)
    py -3.13 tools\hdart\t417_container_gen.py sheet        # листы t417_cand.png, t417_scene_portufo21/17.png
    py -3.13 tools\hdart\t417_container_gen.py install --seed N [--yes]   # по выбору Vitali, под очередью правок
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402

STEPS, CFG, MP, ZOOM, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 40, 3, 0.7
K = 4
SET = "PORTROADS"
SEEDS = [4171, 4172, 4173]
GEN = os.path.join(ROOT, "art", "tickets", "t417", "gen")
CAND = os.path.join(ROOT, "art", "tickets", "t417", "cand")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
# клетки в порядке рисования движка (y, потом x): (кадр, колонка, ряд); смещение окна кадра - ((c-r)*16, (c+r)*8)
C23 = [(85, 0, 0), (86, 1, 0), (84, 0, 1), (83, 1, 1), (82, 0, 2), (81, 1, 2)]
C24 = [(85, 0, 0), (86, 1, 0), (84, 0, 1), (83, 1, 1), (84, 0, 2), (83, 1, 2), (82, 0, 3), (81, 1, 3)]
FRAMES = [f for f, _c, _r in C23]
OWN_DX, OWN_DY = 0, -16            # ромб-территория клетки: центр пола кадра (16, 32) + (dx, dy)
LUM = np.array([0.299, 0.587, 0.114], np.float32)

WHAT = ("a large open-top yellow steel skip container: a wide shallow bowl-shaped bin painted bright golden yellow, with a "
        "thick rounded rim all around its top opening; inside, four sloping inner walls with thin vertical dark brown ribs "
        "and one diagonal brown brace on the far right wall, and a smooth lighter yellow flat floor; the two outer walls "
        "facing the viewer slope inward toward the bottom, the lower left one in dark brown shade")
NEG = ("closed lid, cargo box, shipping container with corrugated doors, wheels, ladder, wood grain, planks, text, labels, "
       "ground, extra objects, people, slab, stone slab, paving tiles, base plate, floor tiles, ground square")


# ---------------------------------------------------------------------------------------------------------
# раскладка
# ---------------------------------------------------------------------------------------------------------
def make_items(cells):
    """[(кадр, col, row)] -> (items, W, H): items - [{f, c, r, x, y}] с окнами в базовых пикселях холста, W x H - холст."""
    off = [((c - r) * 16, (c + r) * 8) for _f, c, r in cells]
    x0 = min(o[0] for o in off)
    y0 = min(o[1] for o in off)
    items = [dict(f=f, c=c, r=r, x=o[0] - x0, y=o[1] - y0) for (f, c, r), o in zip(cells, off)]
    return items, max(i["x"] for i in items) + 32, max(i["y"] for i in items) + 40


def classic_frame_k1(sc, f):
    return Image.fromarray(np.asarray(sc.classic(SET, f))[::4, ::4].copy(), "RGBA")


def compose_k1(sc, items, W, H):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for it in items:
        im.alpha_composite(classic_frame_k1(sc, it["f"]), (it["x"], it["y"]))
    return im


def padded_box(img, pad=PAD):
    bb = img.split()[3].getbbox()
    return (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))


# ---------------------------------------------------------------------------------------------------------
# B. промпт и генерация
# ---------------------------------------------------------------------------------------------------------
def prompt():
    import battle_view as bv
    import ticket_q21_probe as q
    import probe_object as po
    pb = bv.prompt_block("object")
    text = (q.PANEL_HINT.replace("{what}", WHAT) + bv._sentence(pb["positive"]) + " "
            + q.KEEP.replace("{noun}", "object").replace("{what}", WHAT) + q.TAIL_OBJ)
    neg = po.NEGATIVE + ", " + q.SLAB_NEG + ", " + pb["negative"] + ", " + NEG
    return text, neg


def model_input(sc):
    import probe_object as po
    items, W, H = make_items(C23)
    full = compose_k1(sc, items, W, H)
    box = padded_box(full)
    frame = full.crop(box)
    panel = po.pick_background(frame)
    src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
    flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
    flat.alpha_composite(src)
    return full, box, frame, flat


def do_preview(a=None):
    import ticket_scene as ts
    sc = ts.Scene()
    full, box, frame, flat = model_input(sc)
    os.makedirs(os.path.join(GEN, "raw"), exist_ok=True)
    flat.convert("RGB").save(os.path.join(GEN, "raw", "input.png"))
    t, n = prompt()
    print("холст %dx%d, габарит %s, вход %s\nPROMPT: %s\nNEG: %s" % (full.width, full.height, box, flat.size, t, n))


def do_render(a=None):
    import argparse as ap_
    import ticket_scene as ts
    import probe_object as po
    sc = ts.Scene()
    full, box, frame, flat = model_input(sc)
    os.makedirs(os.path.join(GEN, "raw"), exist_ok=True)
    ns = ap_.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS, qwen21_cfg=CFG,
                       qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    args = ap_.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    text, neg = prompt()
    print("PROMPT:", text, "\nNEG:", neg, flush=True)
    po.gen_fire.NEGATIVE = neg
    t0 = time.time()
    for n, seed in enumerate(SEEDS, 1):
        dst = os.path.join(GEN, "raw", "%d.png" % seed)
        if os.path.exists(dst):
            print("[%d/%d] зерно %d уже есть" % (n, len(SEEDS), seed), flush=True)
            continue
        hd = po.gen_fire.run_pass(painter, args, text, flat.convert("RGB"), seed)
        po.gen_hd.save_png(hd, dst)
        print("[%d/%d] зерно %d готово, %.0f с" % (n, len(SEEDS), seed, time.time() - t0), flush=True)


# ---------------------------------------------------------------------------------------------------------
# C. контур: ровные линии
# ---------------------------------------------------------------------------------------------------------
SNAP = [0.0, 0.5, -0.5, 1.0, -1.0, 2.0, -2.0, None]            # dy/dx; None - вертикаль
SNAP_TOL_DEG = 7.0


def snap_dir(d):
    """Единичное направление, прижатое к ближайшему из SNAP (если ближе SNAP_TOL_DEG), иначе как есть."""
    a = np.degrees(np.arctan2(d[1], d[0])) % 180.0
    best, bd = a, 1e9
    for s in SNAP:
        sa = 90.0 if s is None else np.degrees(np.arctan(s)) % 180.0
        df = min(abs(a - sa), 180.0 - abs(a - sa))
        if df < bd:
            best, bd = sa, df
    if bd <= SNAP_TOL_DEG:
        a = best
    r = np.radians(a)
    return np.array([np.cos(r), np.sin(r)])


def fit_polygon(mask1, eps=5.0):
    """Силуэт k=1 (bool) -> (вершины многоугольника в базовых пикселях, стороны). Контур ступенек по x4-маске; вершины Дугласа-Пекера
    (eps пикс x4); сторона между вершинами - прямая наименьших квадратов по точкам контура, угол прижат к SNAP; прямая сдвинута
    наружу на 0.5 пикс x4 (контур идёт по центрам крайних пикселей, граница - на их краю); вершина - пересечение соседних прямых."""
    import cv2
    a = np.kron(mask1.astype(np.uint8), np.ones((K, K), np.uint8))
    cs, _ = cv2.findContours(a, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnt = max(cs, key=len)
    c = cnt[:, 0, :].astype(np.float64)
    ap = cv2.approxPolyDP(cnt, eps, True)[:, 0, :].astype(np.float64)
    idx = sorted({int(np.argmin(((c - v) ** 2).sum(1))) for v in ap})
    n = len(idx)
    segs = []
    for i in range(n):
        j0, j1 = idx[i], idx[(i + 1) % n]
        pts = c[j0:j1 + 1] if j1 > j0 else np.vstack([c[j0:], c[:j1 + 1]])
        if len(pts) < 2:
            continue
        cen = pts.mean(0)
        d = np.linalg.svd(pts - cen)[2][0] if len(pts) > 2 else pts[-1] - pts[0]
        d = d / np.hypot(*d)
        if ((pts[-1] - pts[0]) @ d) < 0:
            d = -d
        d = snap_dir(d)
        if ((pts[-1] - pts[0]) @ d) < 0:
            d = -d
        nrm = np.array([d[1], -d[0]])
        p = cen + nrm * 3.0
        if a[int(np.clip(p[1], 0, a.shape[0] - 1)), int(np.clip(p[0], 0, a.shape[1] - 1))] > 0:
            nrm = -nrm                                          # наружу
        segs.append(dict(c=cen + nrm * 0.5, d=d, L=float(np.hypot(*(pts[-1] - pts[0])) / K)))
    verts = []
    for i in range(len(segs)):
        s0, s1 = segs[i - 1], segs[i]
        A = np.array([s0["d"], -s1["d"]]).T
        if abs(np.linalg.det(A)) < 1e-3:
            p = (s0["c"] + s1["c"]) / 2
        else:
            t = np.linalg.solve(A, s1["c"] - s0["c"])
            p = s0["c"] + s0["d"] * t[0]
        verts.append(p)
    return np.array(verts) / K, segs


def raster_aa(verts, shape, ss=8):
    """Многоугольник (базовые пиксели) -> альфа x4 float 0..1: сверхдискретизация ss x ss на пиксель x4, фильтр-коробка."""
    import cv2
    h, w = shape
    big = np.zeros((h * ss, w * ss), np.uint8)
    cv2.fillPoly(big, [np.rint(verts * K * ss).astype(np.int32)], 255)
    return big.reshape(h, ss, w, ss).mean((1, 3)) / 255.0


def straightness(alpha, verts):
    """Отклонение кромки от прямой стороны многоугольника: вдоль каждой стороны (без 1 пикс базы у вершин) ищется уровень 0.5 альфы
    по нормали в пределах ±3 пикс x4. -> [(сторона, длина в базе, макс. отклонение в пикс x4)]."""
    out = []
    for i in range(len(verts)):
        p, q = verts[i - 1] * K, verts[i] * K
        d = q - p
        L = float(np.hypot(*d))
        if L < 16:
            continue
        d = d / L
        nm = np.array([d[1], -d[0]])
        ss = np.arange(-3.0, 3.01, 0.25)
        worst = 0.0
        for t in np.arange(4.0, L - 4.0, 1.0):
            c0 = p + d * t
            xs = np.floor(c0[0] + nm[0] * ss).astype(int)
            ys = np.floor(c0[1] + nm[1] * ss).astype(int)
            ok = (xs >= 0) & (ys >= 0) & (xs < alpha.shape[1]) & (ys < alpha.shape[0])
            vals = np.where(ok, alpha[np.clip(ys, 0, alpha.shape[0] - 1), np.clip(xs, 0, alpha.shape[1] - 1)], 0.0)
            sg = np.sign(vals - 0.5)
            ch = np.where(sg[:-1] * sg[1:] < 0)[0]
            if len(ch):
                worst = max(worst, float(abs(ss[ch[0]])))
        out.append((i, round(L / K, 1), round(worst, 2)))
    return out


# ---------------------------------------------------------------------------------------------------------
# нарезка по клеткам
# ---------------------------------------------------------------------------------------------------------
def classic_sils(sc, items, W, H):
    """Силуэты классики x4 (NEAREST) по клеткам в координатах холста: [bool (H*K, W*K)]."""
    out = []
    for it in items:
        m = np.zeros((H, W), bool)
        m[it["y"]:it["y"] + 40, it["x"]:it["x"] + 32] = np.asarray(classic_frame_k1(sc, it["f"]))[..., 3] > 0
        out.append(np.kron(m, np.ones((K, K), bool)))
    return out


class Lattice:
    """Решётка клеток раскладки: координаты пикселя x4 в клеточных (xc вдоль (16,8), yc вдоль (-16,8), центр клетки - целые), окно клетки
    (0,0) в холсте (ox, oy). Центр пола кадра (16, 32) сдвинут на (OWN_DX, OWN_DY): ромб-территория клетки сдвинута вверх, потому что
    у предмета на ромбе пола пиксели выше пола."""

    def __init__(self, items, shape):
        H4, W4 = shape
        yy, xx = np.mgrid[0:H4, 0:W4]
        self.X, self.Y = (xx + 0.5) / K, (yy + 0.5) / K
        it0 = items[0]
        self.ox = it0["x"] - (it0["c"] - it0["r"]) * 16
        self.oy = it0["y"] - (it0["c"] + it0["r"]) * 8
        u = (self.Y - self.oy - 32 - OWN_DY) / 8.0
        v = (self.X - self.ox - 16 - OWN_DX) / 16.0
        self.xc, self.yc = (u + v) / 2, (u - v) / 2
        self.cmax = max(i["c"] for i in items)
        self.rmax = max(i["r"] for i in items)

    def line_y(self, X, b):
        """Y (базовые пиксели) границы b (между рядами b-1 и b) на столбце X: прямая 2:1 решётки."""
        return self.oy + 32 + OWN_DY + 16 * (b - 0.5) + (X - self.ox - 16 - OWN_DX) / 2.0


def curve_offsets(canvas, lat, W, H, wmax=24, smooth=0.3):
    """Граница рядов - не прямая, а путь по картинке: стык контейнера 2x4 (пара 84/83 дважды) идёт по этой границе между копиями, и скачок
    через неё - |I(q) - I(q - s)| (s = шаг ряда (-16, 8)). Путь ищется динамикой по столбцам x4 (шаг по вертикали не больше 1 пикс x4 на
    столбец, смещение не больше wmax пикс x4 от прямой решётки) и минимизирует средний скачок. Путь задан для границы b=2 (ряд 1|ряд 2),
    границы b - его сдвиг на (b-2)*s. -> (массив w в пикс x4 по столбцам Xr x4, X0: индекс первого столбца, средний скачок пути и прямой)."""
    rgb = canvas[..., :3].astype(np.float32)
    A = canvas[..., 3] > 250
    H4, W4 = A.shape
    sx, sy = 64, 32                                              # s = (-16, 8) базы = (-64, 32) x4; I(q - s) = I(x + 64, y - 32)
    D = np.full((H4, W4), 255.0, np.float32)
    ok = A[sy:, :W4 - sx] & A[:H4 - sy, sx:]
    d = np.abs(rgb[sy:, :W4 - sx] - rgb[:H4 - sy, sx:]).mean(-1)
    D[sy:, :W4 - sx][ok] = d[ok]
    import cv2
    D = cv2.blur(D, (3, 3))
    xs = np.arange(W4 - sx)
    X = (xs + 0.5) / K
    base = lat.line_y(X, 2) * K                                  # y x4 прямой
    wr = np.arange(-wmax, wmax + 1)
    yy = np.rint(base[:, None] + wr[None, :]).astype(int)
    valid = (yy >= 0) & (yy < H4)
    cost = np.where(valid, D[np.clip(yy, 0, H4 - 1), xs[:, None]], 255.0)
    good = np.nonzero(cost[:, wmax] < 255)[0]                    # столбцы, где прямая внутри силуэта
    if len(good) == 0:
        return np.zeros(W4), 0, 0.0, 0.0
    i0_, i1_ = good.min(), good.max()
    cs = cost[i0_:i1_ + 1]
    n = len(cs)
    Dp = cs.copy()
    back = np.zeros((n, len(wr)), np.int32)
    pen = smooth * np.abs(np.arange(-1, 2))
    for i in range(1, n):
        cand = np.stack([np.roll(Dp[i - 1], 1) + pen[0], Dp[i - 1] + pen[1], np.roll(Dp[i - 1], -1) + pen[2]])
        cand[0, 0] = 1e9
        cand[2, -1] = 1e9
        k = np.argmin(cand, 0)
        back[i] = np.arange(len(wr)) + (k - 1)                    # откуда пришли: k=0 - из j-1, k=1 - из j, k=2 - из j+1
        Dp[i] = cs[i] + cand[k, np.arange(len(wr))]
    j = int(np.argmin(Dp[-1]))
    path = [j]
    for i in range(n - 1, 0, -1):
        j = int(back[i, j])
        path.append(j)
    path = np.array(path[::-1])
    w = np.zeros(W4)
    w[:] = np.nan
    w[i0_ + 0:i1_ + 1] = wr[path]
    # вне диапазона - значение края
    idx = np.nonzero(~np.isnan(w))[0]
    w[:idx.min()] = w[idx.min()]
    w[idx.max() + 1:] = w[idx.max()]
    straight = float(np.mean(cs[:, wmax]))
    best = float(np.mean(cs[np.arange(n), path]))
    return w, int(round(lat.ox * K)), best, straight


def territory_owners(items, al, sil, lat, w2, X0):
    """Владелец каждого пикселя многоугольника: клетка (c, r), чьё окно его содержит. Ряд r - по границам-путям (см. curve_offsets);
    колонка - по решётке. Пиксели, где такой клетки нет (за краем раскладки), - свободные: сплошные рисуют все клетки с силуэтом классики
    (одинаковые пиксели), кромку (альфа меньше 1) - ближайшая клетка из тех, чьё окно её содержит. -> (own int32: индекс клетки, -1 свободный,
    -2 вне контура; число запасных назначений кромки; число свободных сплошных)."""
    H4, W4 = al.shape
    X, Y = lat.X, lat.Y
    cc = np.clip(np.floor(lat.xc + 0.5).astype(int), 0, lat.cmax)
    # ряд: число границ b = 1..rmax, ниже которых лежит пиксель
    rr = np.zeros(al.shape, int)
    for b in range(1, lat.rmax + 1):
        # w2 индексируется столбцом x4 относительно окна клетки (0, 0): так одна и та же кривая работает в раскладках 2x3 и 2x4
        xr = np.clip(np.rint((X - lat.ox + 16 * (b - 2)) * K - 0.5).astype(int) + X0, 0, len(w2) - 1)
        yb = lat.line_y(X, b) + w2[xr] / K
        rr += (Y >= yb)
    idx = {(i["c"], i["r"]): n for n, i in enumerate(items)}
    own = np.full(al.shape, -2, np.int32)
    fb = 0
    covered = np.zeros(al.shape, bool)
    for s_ in sil:
        covered |= s_
    for y, x in zip(*np.nonzero(al > 0)):
        px, py = X[y, x], Y[y, x]
        k = idx.get((cc[y, x], rr[y, x]))
        if k is not None:
            it = items[k]
            if it["x"] <= px < it["x"] + 32 and it["y"] <= py < it["y"] + 40:
                own[y, x] = k
                continue
        own[y, x] = -1
    free = (own == -1)
    # свободная кромка (альфа меньше 1) - одному владельцу: ближайшая клетка по решётке среди тех, чьё окно содержит пиксель; свободные сплошные пиксели
    # несут все клетки (одинаковые пиксели общей картинки), см. slice_frames
    for y, x in zip(*np.nonzero(free & (al < 1.0))):
        px, py = X[y, x], Y[y, x]
        cand = [n for n, it in enumerate(items) if it["x"] <= px < it["x"] + 32 and it["y"] <= py < it["y"] + 40]
        if cand:
            own[y, x] = min(cand, key=lambda n: (items[n]["c"] - lat.xc[y, x]) ** 2 + (items[n]["r"] - lat.yc[y, x]) ** 2)
            fb += 1
    nfree = int(((own == -1) & (al >= 1.0)).sum())
    return own, fb, nfree


def slice_frames(canvas, al, items, sil, own):
    """Кадры клеток из общей картинки x4: клетка берёт пиксели своей территории и свободные сплошные пиксели (территории нет) своего окна.
    -> {кадр: PIL RGBA 128x160}."""
    out = {}
    for n, it in enumerate(items):
        win = np.zeros(own.shape, bool)
        win[it["y"] * K:(it["y"] + 40) * K, it["x"] * K:(it["x"] + 32) * K] = True
        m = (own == n) | ((own == -1) & (al >= 1.0) & win)
        piece = np.where(m[..., None], canvas, 0).astype(np.uint8)
        out[it["f"]] = Image.fromarray(piece, "RGBA").crop((it["x"] * K, it["y"] * K, it["x"] * K + 128, it["y"] * K + 160))
    return out


def prep(sc):
    """Раскладка 2x3 и цель: (items, W, H, verts, al, sil)."""
    items, W, H = make_items(C23)
    full = compose_k1(sc, items, W, H)
    verts, _segs = fit_polygon(np.asarray(full)[..., 3] > 0)
    al = raster_aa(verts, (H * K, W * K))
    return items, W, H, verts, al, classic_sils(sc, items, W, H)


# ---------------------------------------------------------------------------------------------------------
# холст x4 из ответа модели
# ---------------------------------------------------------------------------------------------------------
def body_rgb(sc, seed):
    """Ответ модели -> RGB холста x4: габарит по классике (cut_out), тон к классике (match_tone), цвет у кромки продлён из ядра."""
    import probe_object as po
    import obj_derive as od
    from PIL import ImageFilter
    items, W, H = make_items(C23)
    full = compose_k1(sc, items, W, H)
    box = padded_box(full)
    frame = full.crop(box)
    hd = Image.open(os.path.join(GEN, "raw", "%d.png" % seed)).convert("RGB")
    part = po.match_tone(po.cut_out(hd, frame, 0, SOFT), frame, TONE)
    cut = Image.new("RGBA", (W * K, H * K), (0, 0, 0, 0))
    cut.paste(part, (box[0] * K, box[1] * K))
    a = np.asarray(cut, np.float32)
    core = np.asarray(Image.fromarray(((a[..., 3] > 250) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(7))) > 0
    rgb = np.empty_like(a[..., :3])
    for c in range(3):
        rgb[..., c] = od.spread(a[..., c], core, 40)
    return lowfreq_tone(np.clip(rgb, 0, 255), full)


LF_AMOUNT, LF_SIGMA = 0.6, 12.0        # низкочастотный тон по классике: доля и гаусс (пикс x4)


def lowfreq_tone(rgb, full):
    """Тон по областям - от классики: у модели низ слева (коричневая тень классики) выходит жёлтым. К картинке добавляется доля LF_AMOUNT
    разницы размытых (маской нормированных) классики x4 и картинки: рисунок и резкость внутри не трогаются, меняется только цвет
    крупных областей."""
    import cv2
    cl = np.asarray(full).astype(np.float32)
    m = (cl[..., 3] > 0).astype(np.float32)
    m = np.kron(m, np.ones((K, K), np.float32))
    c4 = np.kron(cl[..., :3], np.ones((K, K, 1), np.float32))

    def lp(x, mm):
        num = cv2.GaussianBlur(x * mm[..., None], (0, 0), LF_SIGMA)
        den = cv2.GaussianBlur(mm, (0, 0), LF_SIGMA)[..., None]
        return num / np.maximum(den, 1e-3)
    a = np.asarray(rgb, np.float32)
    out = a + LF_AMOUNT * (lp(c4, m) - lp(a, m))
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def canvas_of(rgb, al):
    out = np.zeros(al.shape + (4,), np.uint8)
    out[..., :3] = np.where(al[..., None] > 0, rgb, 0)
    out[..., 3] = np.rint(al * 255).astype(np.uint8)
    return out


# ---------------------------------------------------------------------------------------------------------
# сборка движком и проверки
# ---------------------------------------------------------------------------------------------------------
def assemble(frames, items, W, H, k=K, bg=None):
    """Кадры -> холст, как рисует движок (порядок клеток как в items, alpha-over)."""
    im = Image.new("RGBA", (W * k, H * k), (0, 0, 0, 0) if bg is None else tuple(bg) + (255,))
    for it in items:
        f = frames[it["f"]]
        if f.width != 32 * k:
            f = f.resize((32 * k, 40 * k), Image.NEAREST)
        im.alpha_composite(f.convert("RGBA"), (it["x"] * k, it["y"] * k))
    return im


def owner_map(frames, items, W, H, k=K):
    own = np.full((H * k, W * k), -1, np.int32)
    for n, it in enumerate(items):
        f = frames[it["f"]]
        if f.width != 32 * k:
            f = f.resize((32 * k, 40 * k), Image.NEAREST)
        a = np.asarray(f)[..., 3] > 0
        own[it["y"] * k:it["y"] * k + 40 * k, it["x"] * k:it["x"] * k + 32 * k][a] = n
    return own


def seam_metric(frames, items, W, H, k=K, ref=None):
    """Шов: средняя абсолютная разница яркости соседних пикселей (по горизонтали и вертикали), которые рисуют РАЗНЫЕ клетки, оба сплошные.
    ref=None - владелец пикселя тот, кого оставил бы движок для этих кадров; ref - карта владельцев (owner_map классики): тогда каждый
    пиксель берётся из кадра владельца по классике (так считали в разборе: у классики 14.6) - шов по границам клеток классики.
    Для сравнения - та же разница у соседей одной клетки. -> (между клетками, внутри клетки, {(ряд a, ряд b): между})."""
    own = owner_map(frames, items, W, H, k) if ref is None else ref
    if ref is None:
        img = np.asarray(assemble(frames, items, W, H, k)).astype(np.float32)
    else:
        img = np.zeros((H * k, W * k, 4), np.float32)
        for n, it in enumerate(items):
            f = frames[it["f"]]
            if f.width != 32 * k:
                f = f.resize((32 * k, 40 * k), Image.NEAREST)
            reg = img[it["y"] * k:it["y"] * k + 40 * k, it["x"] * k:it["x"] * k + 32 * k]
            m = ref[it["y"] * k:it["y"] * k + 40 * k, it["x"] * k:it["x"] * k + 32 * k] == n
            reg[m] = np.asarray(f.convert("RGBA")).astype(np.float32)[m]
    L = img[..., :3] @ LUM
    solid = img[..., 3] > 250
    rows = np.array([it["r"] for it in items])
    between, within, byrows = [], [], {}
    for dy, dx in ((0, 1), (1, 0)):
        h, w = own.shape[0] - dy, own.shape[1] - dx
        ok = solid[:h, :w] & solid[dy:, dx:] & (own[:h, :w] >= 0) & (own[dy:, dx:] >= 0)
        o0, o1 = own[:h, :w], own[dy:, dx:]
        d = np.abs(L[:h, :w] - L[dy:, dx:])
        between.append(d[ok & (o0 != o1)])
        within.append(d[ok & (o0 == o1)])
        sel = ok & (o0 != o1)
        r0, r1 = rows[o0[sel]], rows[o1[sel]]
        for a_, b_, v in zip(np.minimum(r0, r1), np.maximum(r0, r1), d[sel]):
            byrows.setdefault((int(a_), int(b_)), []).append(float(v))
    b, w_ = np.concatenate(between), np.concatenate(within)
    return float(b.mean()), float(w_.mean()), {k_: float(np.mean(v)) for k_, v in byrows.items()}


def gaps(frames, items, W, H, target, k=K):
    """Просвет на стыках (rim_alpha-подобно): сборка кадров движком против цели. -> (пикселей внутри контура с альфой ниже 250,
    пикселей, где альфа сложения расходится с целью больше чем на 0.02, макс. расхождение)."""
    img = np.asarray(assemble(frames, items, W, H, k)).astype(np.float32)
    diff = np.abs(img[..., 3] / 255.0 - target)
    return int(((target >= 0.999) & (img[..., 3] < 250)).sum()), int((diff > 0.02).sum()), float(diff.max())


def target_alpha(sc, items, W, H):
    """Цель альфы x4 для раскладки: многоугольник из классики этой раскладки."""
    full = compose_k1(sc, items, W, H)
    v, _s = fit_polygon(np.asarray(full)[..., 3] > 0)
    return raster_aa(v, (H * K, W * K)), v


def edge_dev(frames, items, W, H, verts):
    """Прямота кромки собранной картинки: макс. отклонение от многоугольника по сторонам (пикс x4)."""
    img = np.asarray(assemble(frames, items, W, H, K)).astype(np.float32)
    return straightness(img[..., 3] / 255.0, verts)


def classic_frames(sc):
    return {f: sc.classic(SET, f) for f in FRAMES}


def hd_now_frames(sc):
    return {f: sc.hd(SET, f) for f in FRAMES}


def build_seed(sc, seed, pre, wmax=24):
    items, W, H, verts, al, sil = pre
    rgb = body_rgb(sc, seed)
    canvas = canvas_of(rgb, al)
    lat = Lattice(items, al.shape)
    w2, X0, best, straight = curve_offsets(canvas, lat, W, H, wmax)
    own, fb, nfree = territory_owners(items, al, sil, lat, w2, X0)
    frames = slice_frames(canvas, al, items, sil, own)
    info = dict(path_best=best, path_straight=straight, fallback=fb, free=nfree, wmax=wmax,
                wrange=(float(np.nanmin(w2)), float(np.nanmax(w2))), w2=w2, X0=X0)
    return canvas, frames, info


def do_build(a=None):
    import csv
    import ticket_scene as ts
    sc = ts.Scene()
    pre = prep(sc)
    items, W, H, verts, al, sil = pre
    items4, W4, H4 = make_items(C24)
    al4, verts4 = target_alpha(sc, items4, W4, H4)
    print("многоугольник контура: %d вершин: %s" % (len(verts), np.round(verts, 2).tolist()))
    cl = classic_frames(sc)
    cl4 = classic_frames(sc)
    now = hd_now_frames(sc)
    rows = []

    ref23 = owner_map(cl, items, W, H)
    ref24 = owner_map(cl4, items4, W4, H4)

    def measure(name, frames, seed=None):
        s23 = seam_metric(frames, items, W, H, ref=ref23)
        s24 = seam_metric(frames, items4, W4, H4)
        e23 = seam_metric(frames, items, W, H)
        dv = edge_dev(frames, items, W, H, verts)
        row = dict(name=name, seam23=s23[0], within23=s23[1], seam24=s24[0], within24=s24[1], engine23=e23[0],
                   edge=max(d[2] for d in dv) if dv else 0.0, joins24=s24[2])
        if seed is not None:
            row["gaps23"] = gaps(frames, items, W, H, al)
            row["gaps24"] = gaps(frames, items4, W4, H4, al4)
        rows.append(row)
        return row
    measure("классика x4", cl)
    measure("HD сейчас", now)
    for seed in SEEDS:
        if not os.path.exists(os.path.join(GEN, "raw", "%d.png" % seed)):
            print("нет ответа модели для зерна", seed)
            continue
        canvas, frames, info = build_seed(sc, seed, pre)
        print("зерно %d: путь стыка рядов - средний скачок %.1f (прямая решётки %.1f), смещение %.0f..%.0f пикс x4, запасных назначений кромки %d, "
              "свободных сплошных пикселей %d" % (seed, info["path_best"], info["path_straight"], info["wrange"][0], info["wrange"][1],
                                                  info["fallback"], info["free"]))
        d = os.path.join(CAND, "s%d" % seed)
        os.makedirs(d, exist_ok=True)
        for f, im in frames.items():
            im.save(os.path.join(d, "%s_%d.png" % (SET, f)))
        Image.fromarray(canvas, "RGBA").save(os.path.join(d, "_canvas.png"))
        cc = np.asarray(assemble(frames, items, W, H, K))[..., :3].astype(np.float32)
        vis = np.asarray(assemble(frames, items, W, H, K))[..., 3] > 250
        cdiff = float(np.abs(cc - canvas[..., :3].astype(np.float32))[vis].max())
        out_cl = 0
        for n, it in enumerate(items):
            alpha = np.asarray(frames[it["f"]])[..., 3] > 0
            reg = np.zeros(sil[n].shape, bool)
            reg[it["y"] * K:it["y"] * K + 160, it["x"] * K:it["x"] * K + 128] = alpha
            out_cl += int((reg & ~sil[n]).sum())
        r = measure("зерно %d" % seed, frames, seed)
        r["canvas_diff"] = cdiff
        r["out_classic"] = out_cl
    out = os.path.join(REV, "t417_checks.tsv")
    os.makedirs(REV, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["вариант", "шов 2x3 (по границам клеток классики)", "внутри клетки", "шов 2x4", "внутри 2x4", "шов 2x3 как рисует движок", "отклонение кромки, пикс x4",
                    "швы 2x4 по рядам (a,b: среднее)", "просвет 2x3 (дыр, расхождений, макс.)", "просвет 2x4", "сборка == холст, макс. RGB",
                    "пикселей кадров вне классики x4"])
        for r in rows:
            w.writerow([r["name"], "%.1f" % r["seam23"], "%.1f" % r["within23"], "%.1f" % r["seam24"], "%.1f" % r["within24"],
                        "%.1f" % r["engine23"], "%.2f" % r["edge"], "; ".join("%d-%d: %.1f" % (a_, b_, v) for (a_, b_), v in sorted(r["joins24"].items())),
                        r.get("gaps23", "-"), r.get("gaps24", "-"), r.get("canvas_diff", "-"), r.get("out_classic", "-")])
    for r in rows:
        print("%-14s шов 2x3 %.1f (внутри %.1f, движком %.1f) | 2x4 %.1f | кромка ±%.2f | швы 2x4 по рядам %s | просвет 2x3 %s 2x4 %s | сборка-холст %s | вне классики %s"
              % (r["name"], r["seam23"], r["within23"], r["engine23"], r["seam24"], r["edge"],
                 {"%d-%d" % k_: round(v, 1) for k_, v in sorted(r["joins24"].items())}, r.get("gaps23", "-"), r.get("gaps24", "-"),
                 r.get("canvas_diff", "-"), r.get("out_classic", "-")))
    print("таблица:", out)
    return rows


# ---------------------------------------------------------------------------------------------------------
# листы
# ---------------------------------------------------------------------------------------------------------
BGC = (30, 30, 34)


def seed_frames(seed):
    d = os.path.join(CAND, "s%d" % seed)
    return {f: Image.open(os.path.join(d, "%s_%d.png" % (SET, f))).convert("RGBA") for f in FRAMES}


def avail_seeds():
    return [s for s in SEEDS if os.path.exists(os.path.join(CAND, "s%d" % s, "%s_81.png" % SET))]


def zoom_crop(im, box_base, z):
    x0, y0, x1, y1 = box_base
    c = im.crop((x0 * K, y0 * K, x1 * K, y1 * K))
    return c.resize((c.width * z, c.height * z), Image.NEAREST)


def do_sheet(a=None):
    import ticket_scene as ts
    sc = ts.Scene()
    items, W, H = make_items(C23)
    items4, W4, H4 = make_items(C24)
    seeds = avail_seeds()
    variants = [("классика x4", classic_frames(sc)), ("HD сейчас", hd_now_frames(sc))] + [("зерно %d" % s, seed_frames(s)) for s in seeds]
    full = [(n, assemble(f, items, W, H, K, BGC)) for n, f in variants]
    top = [(n, im) for n, im in full]
    # вблизи: край (верхний левый 2:1 и крутой правый), шов в середине (граница рядов 0|1 и 1|2)
    zc = 2
    edge_l = [(n + ": край слева-сверху", zoom_crop(im, (12, 12, 52, 30), zc)) for n, im in full]
    edge_r = [(n + ": край справа", zoom_crop(im, (50, 18, 80, 48), zc)) for n, im in full]
    seam = [(n + ": шов, середина", zoom_crop(im, (24, 20, 60, 44), zc)) for n, im in full]
    ts.sheet(top + edge_l + edge_r + seam, os.path.join(REV, "t417_cand.png"), cols=len(variants))
    print("лист", os.path.join(REV, "t417_cand.png"))
    # 2x4 (PORTUFO17, 37): собранное из кадров движком
    p24 = [(n + ": 2x4", assemble(f, items4, W4, H4, K, BGC)) for n, f in variants]
    ts.sheet(p24, os.path.join(REV, "t417_2x4.png"), cols=len(variants))
    print("лист", os.path.join(REV, "t417_2x4.png"))
    # сцены
    keys = [(SET, f) for f in FRAMES]
    ov = {s: {(SET, f): im for f, im in seed_frames(s).items()} for s in seeds}
    for name, terrain, block, (w, h) in (("t417_scene_portufo21.png", "PORTTFTD5", "PORTUFO21", (150, 110)),
                                         ("t417_scene_portufo17.png", "PORTTFTD5", "PORTUFO17", (130, 110))):
        found = ts.find_cells(sc, terrain, block, keys)
        zmax = max(f[3] for f in found)
        zmin = min(f[3] for f in found)
        box = ts.window([(f[0], f[1], tuple(v * K for v in f[2])) for f in found], w, h, K)
        panels = []
        for title, mode, o in [("классика", "classic", None), ("HD сейчас", "hd", None)] + [("зерно %d" % s, "hd", ov[s]) for s in seeds]:
            im, _f = ts.Scene.render(sc, terrain, block, mode, override=o, k=K, maxz=zmin)
            panels.append((block + ": " + title, ts.crop_pad(im, box)))
        ts.sheet(panels, os.path.join(REV, name), cols=2)
        print("лист", os.path.join(REV, name))


# ---------------------------------------------------------------------------------------------------------
# установка (по выбору Vitali, под очередью правок)
# ---------------------------------------------------------------------------------------------------------
def do_install(a):
    if not a.seed:
        raise SystemExit("нужно --seed N: зерно, которое выбрал Vitali")
    d = os.path.join(CAND, "s%d" % a.seed)
    files = {}
    for f in FRAMES:
        p = os.path.join(d, "%s_%d.png" % (SET, f))
        im = Image.open(p)
        if im.size != (128, 160) or im.mode != "RGBA":
            raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
        files["TERRAIN/%s.PCK/%d.png" % (SET, f)] = p
    import build_hd_pack as bp
    man = bp.load()
    for rel, p in files.items():
        old = man["files"].get(rel, {}).get("sha256", "")[:10] or "нет в манифесте"
        print("  %-34s <- s%d/%s  (манифест %s)" % (rel, a.seed, os.path.basename(p), old))
    if not a.yes:
        raise SystemExit("сухой прогон, кадров %d; --yes - записать в мод (под очередью правок)" % len(files))
    import ticket_scene as ts
    n = ts.install_files(files, "t417_container_gen", "XP-000417: контейнер 2x3 одной картинкой, ровный контур",
                         "Vitali 30.10: вариант B+C по тикету XP-000417, зерно %d" % a.seed,
                         "t417: жёлтый контейнер PORTROADS 81-86 одной картинкой с ровным контуром (6 кадров, зерно %d)" % a.seed)
    print("установлено файлов:", n)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["preview", "render", "build", "sheet", "install"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    globals()["do_" + a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
