#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000438: машина «Восьмёрка» (CADILLAC 3-13) - контур целой машины лесенкой x4 (вариант A XP-000358 резал холст по маскам классики
NEAREST). Вариант A (Vitali 30.10), процедурно, без видеокарты, R-121:

  1. Силуэт объединения классики (раскладка MAPS/CADILLAC.MAP, порядок рисования движка) -> многоугольник: контур ступенек по x4-маске,
     вершины Дугласа-Пекера, сторона - прямая наименьших квадратов, угол прижат к 2:1, 1:1, вертикали, горизонтали (t417_container_gen.fit_polygon),
     с защитой вершины (острый угол двух почти параллельных сторон не вытягивается шипом: вершина остаётся в пределах MAXV от точки контура).
  2. Многоугольник растеризуется x4 со сглаживанием (сверхдискретизация x8) - новая альфа; внутри контура альфа 255.
  3. Цвет и фактура - прежние (кадры CADILLAC.PCK установки, холст по раскладке); за прежней маской (край вышел наружу на доли пикселя
     классики) цвет тянется от ближайшего пикселя маски.
  4. Нарезка: клетке достаются пиксели её маски классики (как раньше: перекрытия несут одни и те же пиксели); пиксель кромки (альфа меньше 255)
     рисует ровно одна клетка - из тех, чья маска классики его накрывает, а новый пиксель за маской - ближайшая по маске классики клетка,
     в окне которой он лежит (иначе два полупрозрачных слоя дают нитку, R-289).

    py -3.13 tools\hdart\t438_proc.py build        кадры -> art/tickets/t438/cand/<кадр>.png, проверки, лист t438_cand.png
В мод ничего не ставит (арт - сначала показать Vitali).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

import cv2                                   # noqa: E402
import numpy as np                           # noqa: E402
from PIL import Image                        # noqa: E402
from scipy import ndimage as ndi             # noqa: E402

import t358_build as tb                      # noqa: E402
import t417_container_gen as g               # noqa: E402
import ticket_scene as ts                    # noqa: E402

K = 4
SET = "CADILLAC"
OUT = os.path.join(ROOT, "art", "tickets", "t438", "cand")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
EPS = 3.0            # допуск Дугласа-Пекера, пикс x4 (0.75 пикс классики)
MAXV = 10.0          # вершина не дальше стольких пикс x4 от точки контура


def fit(mask1, eps=EPS):
    """g.fit_polygon с защитой вершин -> (вершины в базовых пикселях, число вернувшихся к точке контура)."""
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
        d = g.snap_dir(d)
        if ((pts[-1] - pts[0]) @ d) < 0:
            d = -d
        nrm = np.array([d[1], -d[0]])
        p = cen + nrm * 3.0
        if a[int(np.clip(p[1], 0, a.shape[0] - 1)), int(np.clip(p[0], 0, a.shape[1] - 1))] > 0:
            nrm = -nrm
        segs.append(dict(c=cen + nrm * 0.5, d=d, p0=pts[0], p1=pts[-1]))
    verts, fb = [], 0
    for i in range(len(segs)):
        s0, s1 = segs[i - 1], segs[i]
        A = np.array([s0["d"], -s1["d"]]).T
        ref = (s0["p1"] + s1["p0"]) / 2
        if abs(np.linalg.det(A)) < 1e-3:
            p = (s0["c"] + s1["c"]) / 2
        else:
            t = np.linalg.solve(A, s1["c"] - s0["c"])
            p = s0["c"] + s0["d"] * t[0]
        if np.hypot(*(p - ref)) > MAXV:
            fb += 1
            p = ref                                     # спрямлять нечем - точка контура
        verts.append(p)
    return np.array(verts) / K, fb


def classic_pieces(sc):
    """-> rgb холста, union-маска k=1, словарь кадр -> маска k=1 на холсте."""
    rgb, m, own = tb.classic_canvas(sc)
    return rgb, m, own


def hd_canvas(sc):
    """Холст x4 из текущих HD кадров установки: цвет, маска (альфа>0)."""
    img = np.zeros((tb.CH * K, tb.CW * K, 3), np.float32)
    msk = np.zeros((tb.CH * K, tb.CW * K), bool)
    for it in tb.ITEMS:
        f = it[4]
        ox, oy = tb.pos(it)
        a = np.asarray(sc.hd(SET, f)).astype(np.float32)
        sl = (slice(oy * K, oy * K + 40 * K), slice(ox * K, ox * K + 32 * K))
        m = a[..., 3] > 0
        reg = img[sl]
        reg[m] = a[..., :3][m]
        msk[sl] |= m
    return img, msk


def build_frames(sc):
    rgb1, m1, own1 = classic_pieces(sc)
    verts, fb = fit(m1)
    H4, W4 = tb.CH * K, tb.CW * K
    alpha = g.raster_aa(verts, (H4, W4)).astype(np.float32)
    img, hmask = hd_canvas(sc)
    # цвет за прежней маской - от ближайшего пикселя маски
    dist, (iy, ix) = ndi.distance_transform_edt(~hmask, return_indices=True)
    full = img[iy, ix]
    own = {it[4]: tb.mask_up(own1[it[4]]) for it in tb.ITEMS}
    order = [it[4] for it in tb.ITEMS]
    # окна кадров
    win = {}
    for it in tb.ITEMS:
        ox, oy = tb.pos(it)
        w = np.zeros((H4, W4), bool)
        w[oy * K:oy * K + 40 * K, ox * K:ox * K + 32 * K] = True
        win[it[4]] = w
    # расстояние до маски классики каждой клетки (для новых пикселей за маской)
    dcl = {f: ndi.distance_transform_edt(~own[f]) for f in order}
    cover = np.zeros((H4, W4), np.int32)
    for f in order:
        cover += own[f]
    edge = (alpha > 0) & ((alpha < 0.999) | (cover == 0))             # пиксели с единственным владельцем
    solid = (alpha >= 0.999) & (cover > 0)                            # сплошные внутри маски: все кадры маски (как было)
    owner = np.full((H4, W4), -1, np.int32)
    best = np.full((H4, W4), 1e9, np.float32)
    for f in order:
        cand = edge & win[f]
        # только кадры, чья маска накрывает пиксель (если такие есть); иначе - ближайшая по маске, в чьём окне пиксель лежит
        pref = np.where(cover > 0, own[f], True)
        cand &= pref
        d = np.where(own[f], 0.0, dcl[f]).astype(np.float32)
        better = cand & (d < best - 1e-6)
        owner[better] = f
        best[better] = d[better]
    frames = {}
    for it in tb.ITEMS:
        f = it[4]
        ox, oy = tb.pos(it)
        keep = (solid & own[f]) | (edge & (owner == f))
        a = np.where(keep, alpha, 0.0)
        # у сплошных пикселей альфа 1; у кромки - AA
        o = np.zeros((H4, W4, 4), np.uint8)
        o[..., :3] = np.where(keep[..., None], np.clip(full, 0, 255), 0).astype(np.uint8)
        o[..., 3] = np.rint(a * 255).astype(np.uint8)
        frames[f] = Image.fromarray(o, "RGBA").crop((ox * K, oy * K, ox * K + 32 * K, oy * K + 40 * K))
    return frames, verts, fb, alpha, full


def assemble(frames, bg=None):
    W, H = tb.CW * K, tb.CH * K
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0) if bg is None else tuple(bg) + (255,))
    for it in tb.ITEMS:
        ox, oy = tb.pos(it)
        im.alpha_composite(frames[it[4]], (ox * K, oy * K))
    return im


def checks(frames, alpha, verts):
    asm = np.asarray(assemble(frames)).astype(np.float32)
    diff = np.abs(asm[..., 3] / 255.0 - alpha)
    inner = (alpha >= 0.999)
    gap = int((inner & (asm[..., 3] < 250)).sum())
    print("сборка движком против многоугольника: пикселей с расхождением альфы > 0.02: %d (макс %.3f); просвет внутри контура: %d" % (
        int((diff > 0.02).sum()), float(diff.max()), gap))
    # прямота кромки
    dev = g.straightness(asm[..., 3] / 255.0, verts)
    worst = max((d[2] for d in dev), default=0.0)
    print("прямота кромки: сторон %d, макс. отклонение от прямой %.2f пикс x4" % (len(dev), worst))
    return diff, dev


def build():
    sc = ts.Scene()
    os.makedirs(OUT, exist_ok=True)
    frames, verts, fb, alpha, full = build_frames(sc)
    for f, im in frames.items():
        im.save(os.path.join(OUT, "%d.png" % f))
    print("многоугольник: %d вершин, вернулись к точке контура: %d; кадров %d -> %s" % (len(verts), fb, len(frames), OUT))
    diff, dev = checks(frames, alpha, verts)
    now = {it[4]: sc.hd(SET, it[4]) for it in tb.ITEMS}
    return sc, frames, now, verts


def sheet(sc, frames, now):
    from PIL import ImageDraw
    cls = {it[4]: sc.classic(SET, it[4]) for it in tb.ITEMS}
    bgc = (203, 214, 235)

    def comp(getf, z=1.0):
        im = Image.new("RGBA", (tb.CW * K, tb.CH * K), bgc + (255,))
        for it in tb.ITEMS:
            ox, oy = tb.pos(it)
            fr = getf(it[4])
            im.alpha_composite(fr, (ox * K, oy * K))
        return im

    c_im, n_im, k_im = comp(lambda f: cls[f]), comp(lambda f: now[f]), comp(lambda f: frames[f])
    a, b, c = c_im.convert("RGB"), n_im.convert("RGB"), k_im.convert("RGB")
    # крупные куски контура x3: крыша/плавник, капот-нос, колёса
    boxes = [("крыша и плавник", (290, 50, 460, 170)), ("нос и бампер", (50, 200, 220, 320)), ("колёса и низ", (150, 270, 320, 390))]
    z = 3
    rows = []
    for t, bx in boxes:
        row = []
        for im in (a, b, c):
            row.append(im.crop(bx).resize(((bx[2] - bx[0]) * z, (bx[3] - bx[1]) * z), Image.NEAREST if im is a else Image.LANCZOS))
        rows.append((t, row))
    W3 = a.width
    sheet_w = 3 * W3 + 4 * 8
    # верх: три картинки целиком
    top_h = a.height
    detail_h = sum(r[1][0].height + 34 for r in rows)
    out = Image.new("RGB", (sheet_w, top_h + 40 + detail_h + 20), (12, 12, 14))
    fnt = ts.font(22)
    d = ImageDraw.Draw(out)
    for i, (t, im) in enumerate((("классика x4", a), ("HD сейчас (вариант A XP-000358)", b), ("кандидат: контур отрезками", c))):
        out.paste(im, (8 + i * (W3 + 8), 36))
        d.text((16 + i * (W3 + 8), 6), t, fill=(255, 220, 0), font=fnt)
    y = top_h + 48
    for t, row in rows:
        d.text((16, y), "контур крупно x%d: %s" % (z, t), fill=(255, 220, 0), font=fnt)
        x = 8
        for im in row:
            out.paste(im, (x, y + 30))
            x += W3 + 8
        y += row[0].height + 34
    os.makedirs(REV, exist_ok=True)
    out.save(os.path.join(REV, "t438_cand.png"))
    print("лист", os.path.join(REV, "t438_cand.png"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        sys.stdout.reconfigure(encoding="utf-8")
        _sc, _fr, _now, _v = build()
        sheet(_sc, _fr, _now)
    else:
        print(__doc__)
