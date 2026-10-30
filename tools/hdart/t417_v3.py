#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000417, круг 2: нарезка общей картинки на кадры по ОПОРАМ КЛАССИКИ с плавным переходом на стыках.

Почему не территории по решётке (t417_container_gen.slice_frames): пиксели средней пары 84/83 в 2x4 рисуются дважды (ряд 1 и ряд 2), и любой
пиксель вне её классической опоры ложится вторым рядом чужим куском (ступенька дна с вертикальным краем по окну кадра).
Классика уже решает это: опоры кадров (где кадр непрозрачен) почти не пересекаются (перекрытие 50-100 пикселей на стык, 2-3 пикселя шириной)
и любая раскладка (2x3, 2x4) - это та же рисовка по порядку движка. Здесь то же:
  - кадр f рисует только свою опору (классическая маска x4 + кайма у внешней кромки, где альфа многоугольника меньше 1);
  - цвет кадра в точке r - пиксель общей картинки J на (положение кадра + r): в раскладке самой картинки результат ТОЧНО её же;
  - в зоне перекрытия двух рядов (верхний кадр рисуется раньше и непрозрачен, нижний - позже) альфа нижнего плавно растёт 0 -> 1
    (расстояния до зон «только верхний» и «только нижний»): там, где соседние ряды не одинаковы (копия 84/83 во втором ряду),
    рисунок переходит один в другой без шва; в раскладке самой картинки обе стороны одинаковы и переход незаметен;
  - альфа внешней кромки - от многоугольника (R-121): ровная линия со сглаживанием; внутри 255.

    py -3.13 tools\hdart\t417_v3.py build [--long24]      кадры -> art/tickets/t417/cand/s<зерно>v3[_24]/
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
import cv2                              # noqa: E402
from PIL import Image                   # noqa: E402
import t417_container_gen as g          # noqa: E402

K = g.K
EDGE_DIL = int(os.environ.get("T417_EDIL", "8"))          # кайма опоры у внешней кромки, пикс x4
RAMP_K = float(os.environ.get("T417_RAMPK", "1.0"))   # крутизна перехода (1 = линейно)


def supports(sc):
    return {f: np.kron((np.asarray(g.classic_frame_k1(sc, f))[..., 3] > 0).astype(np.uint8), np.ones((K, K), np.uint8)) > 0
            for f in g.FRAMES}


def shift(a, dx, dy):
    """b[y, x] = a[y + dy, x + dx] (за краем False)."""
    out = np.zeros_like(a)
    h, w = a.shape
    ys, xs = slice(max(0, dy), min(h, h + dy)), slice(max(0, dx), min(w, w + dx))
    yd, xd = slice(max(0, -dy), min(h, h - dy)), slice(max(0, -dx), min(w, w - dx))
    out[yd, xd] = a[ys, xs]
    return out


def ramps(S):
    """w[f] (160x128, 0..1): альфа кадра f в зоне перекрытия с кадрами верхних рядов (по раскладкам 2x3 и 2x4)."""
    up = {f: np.zeros((40 * K, 32 * K), bool) for f in g.FRAMES}
    for cells in (g.C23, g.C24):
        items, _W, _H = g.make_items(cells)
        for j, itj in enumerate(items):
            for i in range(j):
                iti = items[i]
                if iti["r"] >= itj["r"]:
                    continue                                  # тот же ряд: общая картинка одна и та же - перехода нет
                dx, dy = (itj["x"] - iti["x"]) * K, (itj["y"] - iti["y"]) * K     # положение j относительно i
                if abs(dx) >= 32 * K or abs(dy) >= 40 * K:
                    continue
                up[itj["f"]] |= shift(S[iti["f"]], dx, dy)  # маска опоры i в координатах кадра j: q -> q + (dx, dy)
    w = {}
    for f in g.FRAMES:
        zone = S[f] & up[f]
        ux = up[f] & ~S[f]                                    # только верхний
        lx = S[f] & ~up[f]                                    # только нижний (этот кадр)
        out = np.ones(S[f].shape, np.float32)
        if zone.any() and ux.any() and lx.any():
            dU = cv2.distanceTransform((~ux).astype(np.uint8), cv2.DIST_L2, 3)
            dL = cv2.distanceTransform((~lx).astype(np.uint8), cv2.DIST_L2, 3)
            ww = dU / np.maximum(dU + dL, 1e-6)
            if RAMP_K != 1.0:
                ww = np.clip((ww - 0.5) * RAMP_K + 0.5, 0, 1)
            out[zone] = ww[zone]
        w[f] = out
    return w


def slice_v3(canvas, al, locs, S, W_):
    """canvas - RGBA x4 общей картинки (цвет), al - альфа многоугольника на её раскладке, locs - {кадр: (x, y) в базовых пикселях холста}."""
    H4, W4 = al.shape
    frames = {}
    for f in g.FRAMES:
        x0, y0 = locs[f][0] * K, locs[f][1] * K
        ys, xs = slice(y0, y0 + 40 * K), slice(x0, x0 + 32 * K)
        a_p = np.zeros((40 * K, 32 * K), np.float32)
        rgb = np.zeros((40 * K, 32 * K, 3), np.uint8)
        yy, xx = slice(max(0, y0), min(H4, y0 + 40 * K)), slice(max(0, x0), min(W4, x0 + 32 * K))
        a_p[yy.start - y0:yy.stop - y0, xx.start - x0:xx.stop - x0] = al[yy, xx]
        rgb[yy.start - y0:yy.stop - y0, xx.start - x0:xx.stop - x0] = canvas[yy, xx, :3]
        edge = (a_p > 0) & (a_p < 1.0)
        ez = cv2.dilate(edge.astype(np.uint8), np.ones((2 * EDGE_DIL + 1, 2 * EDGE_DIL + 1), np.uint8)) > 0
        dil = cv2.dilate(S[f].astype(np.uint8), np.ones((2 * EDGE_DIL + 1, 2 * EDGE_DIL + 1), np.uint8)) > 0
        sup = S[f] | (dil & ez & (a_p > 0))
        a = np.where(sup, a_p * W_[f], 0.0)
        out = np.zeros((40 * K, 32 * K, 4), np.uint8)
        out[..., :3] = np.where(a[..., None] > 0, rgb, 0)
        out[..., 3] = np.rint(a * 255).astype(np.uint8)
        frames[f] = Image.fromarray(out, "RGBA")
    return frames


def build(sc, seed, long24=False, wmax=None):
    pre = g.prep(sc, g.C24 if long24 else g.C23)
    items, W, H, verts, al, sil = pre
    rgb = g.body_rgb(sc, seed, g.C24 if long24 else g.C23, "_24" if long24 else "", al)
    canvas = g.canvas_of(rgb, al)
    locs = {}
    for it in items:
        locs.setdefault(it["f"], (it["x"], it["y"]))          # первое вхождение (84/83 - ряд 1)
    S = supports(sc)
    w = ramps(S)
    return canvas, slice_v3(canvas, al, locs, S, w)


def main():
    import ticket_scene as ts
    sys.stdout.reconfigure(encoding="utf-8")
    sc = ts.Scene()
    for seed in g.SEEDS_R2:
        for long24 in (False, True):
            suf = "_24" if long24 else ""
            if not os.path.exists(os.path.join(g.GEN, "raw", "%d%s.png" % (seed, suf))):
                continue
            canvas, frames = build(sc, seed, long24)
            d = os.path.join(g.CAND, "s%dv3%s%s" % (seed, os.environ.get("T417_TAG", ""), suf))
            os.makedirs(d, exist_ok=True)
            for f, im in frames.items():
                im.save(os.path.join(d, "%s_%d.png" % (g.SET, f)))
            print("s%dv3%s" % (seed, suf), "готово")


if __name__ == "__main__":
    main()
