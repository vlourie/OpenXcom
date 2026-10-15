#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""photo_base: геометрия оригинала, проверка формы и управляемая альфа PHOTO-базы. Синтетика, без карт
и видеокарты: кадр 16x20 и ответ «модели» x4 на серой подложке.

  * guide: дырка в 9 пикселей - прорезь, в 1 пиксель - шум и заливается; ножка в пиксель - тонкая часть;
  * conformity: ответ без ножки - FAIL по тонкому; прорезь, закрашенная телом, - FAIL; та же прорезь,
    закрашенная подложкой или её тенью, - прорезь сохранена (матт до закрытого кармана не доходит);
  * managed_alpha: тело цвета подложки в ядре не выедается (R-089), а попадает в core_panel; тень подложки в прорези - прозрачно; серая распорка той же яркости рядом с
    прорезью - остаётся (R-062); карман подложки над тёмным оригиналом - прозрачно;
  * decontaminate: полупрозрачная кромка без подложки.

    py -3.13 tools/test_photo_base.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import photo_base as pb                 # noqa: E402

FAIL = []
PANEL = np.array([176, 176, 182], np.float32)
RED = (200, 40, 40)
GREY = (114, 114, 118)                  # 0.65 яркости подложки - как распорки PORTROADS 66
LIGHT = (225, 215, 205)
DARK = (30, 26, 24)


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def frame():
    """Кадр 16x20: тело 2..13 x 2..15 красное; прорезь 7..9 x 6..8; шумовая дырка (11,4); серая распорка
    x=6 рядом с прорезью; светлое пятно 9..12 x 11..14; тёмное пятно 3..5 x 11..14; ножка x=4, y=16..18."""
    a = np.zeros((20, 16, 4), np.uint8)
    a[2:16, 2:14] = RED + (255,)
    a[6:9, 7:10] = 0
    a[4, 11] = 0
    a[5:10, 6] = GREY + (255,)
    a[11:15, 9:13] = LIGHT + (255,)
    a[11:15, 3:6] = DARK + (255,)
    a[16:19, 4] = RED + (255,)
    return Image.fromarray(a, "RGBA")


def render(fr, leg=True, opening="shadow", light="panel", dark="panel"):
    """Ответ x4 на подложке: тело как у кадра; opening - чем закрашена прорезь (shadow - тень подложки,
    panel - подложка, body - телом); light/dark - чем нарисованы пятна (panel - подложкой, иначе как есть)."""
    a = np.asarray(fr).copy()
    rgb = np.where(a[..., 3:4] > 0, a[..., :3], PANEL.astype(np.uint8)).astype(np.uint8)
    if opening == "shadow":
        rgb[6:9, 7:10] = (PANEL * 0.75).astype(np.uint8)
    elif opening == "body":
        rgb[6:9, 7:10] = RED
    rgb[4, 11] = RED                                    # шумовую дырку модель закрашивает - так и надо
    if not leg:
        rgb[16:19, 4] = PANEL.astype(np.uint8)
    if light == "panel":
        rgb[11:15, 9:13] = PANEL.astype(np.uint8)
    if dark == "panel":
        rgb[11:15, 3:6] = PANEL.astype(np.uint8)
    up = np.repeat(np.repeat(rgb, 4, 0), 4, 1)
    pad = np.zeros((up.shape[0] + 32, up.shape[1] + 32, 3), np.uint8) + PANEL.astype(np.uint8)
    pad[16:-16, 16:-16] = up
    return Image.fromarray(pad, "RGB")


fr = frame()
g = pb.guide(fr)
check("прорезь 3x3 найдена (%d пикселей)" % g["open_px"], g["open_px"] == 9)
check("дырка в пиксель - шум, залита", bool(g["m"][4, 11]))
check("ножка в пиксель - тонкая часть", bool(g["thin"][17, 4]))
check("тело толщиной 12 - не тонкое", not g["thin"][9, 12])


def run(hd):
    m_raw, bg, _own = pb.render_matte(hd)
    rgb, m_al, info = pb.fit(hd, m_raw, fr)
    return rgb, m_al, info, bg


# 1. форма: без ножки, закрашенная прорезь, прорезь подложкой
ok = pb.cut(fr, render(fr, leg=True, opening="shadow", light="body", dark="body"))[1]
check("ответ как оригинал - геометрия PASS (%s %s)" % (ok["geometry"], ok["geometry_why"]), ok["geometry"] == "PASS")
check("тень подложки в прорези - прорезь сохранена (%.2f)" % ok["holes_kept"], ok["holes_kept"] > 0.9)
r = pb.cut(fr, render(fr, leg=False, light="body", dark="body"))[1]
check("ножки нет - FAIL по тонкому (%s)" % r["geometry_why"], r["geometry"] == "FAIL" and "thin" in r["geometry_why"])
# контроль: после правки пропорций (как у A) ножка «на месте» - растянутое тело её закрывает
rgb2, m2, info2, bg2 = run(render(fr, leg=False, light="body", dark="body"))
r2 = pb.conformity(g, m2, info2, 100.0, rgb2, bg2)
check("контроль: в пропорциях после правки пропажа не видна (%s)" % (r2["thin_cover"],), r2["thin_cover"] > 0.9)
r = pb.cut(fr, render(fr, opening="body", light="body", dark="body"))[1]
check("прорезь закрашена телом - FAIL по прорезям (%s)" % r["geometry_why"], r["geometry"] == "FAIL" and "holes" in r["geometry_why"])

# 2. альфа
rgb, m_al, info, bg = run(render(fr, opening="shadow", light="panel", dark="panel"))
alpha, tri, cut_px = pb.managed_alpha(g, rgb, m_al, bg)


def at(y, x):
    """Пиксель кадра k=1 -> среднее альфы его клетки x4."""
    return float(alpha[y * 4:y * 4 + 4, x * 4:x * 4 + 4].mean())


check("светлое тело, нарисованное подложкой, в ядре не выедено (%.2f)" % at(12, 10), at(12, 10) > 0.99)
q = pb.qa(g, pb.decontaminate(rgb, alpha, bg), alpha, tri, bg)
check("и попало в core_panel (%.3f)" % q["core_panel"], q["core_panel"] > 0.03 and q["alpha"] == "REVIEW")
check("тень подложки в прорези - прозрачно (%.2f)" % at(7, 8), at(7, 8) < 0.05)
check("серая распорка рядом с прорезью - остаётся (%.2f)" % at(7, 6), at(7, 6) > 0.9)
check("карман подложки над тёмным оригиналом - прозрачно (%.2f, вырезано %d)" % (at(12, 4), cut_px), at(12, 4) < 0.05)
check("снаружи силуэта - прозрачно", at(0, 0) == 0.0)

# контроль R-062: тот же серый, если бы правило тени шло и по кольцу вокруг прорези, выгрызался бы
B = np.asarray(bg, np.float32)
grey = np.asarray(GREY, np.float32)
t = np.clip((grey @ B) / float(B @ B), pb.SHADOW_MIN, 1.0)
check("контроль: по правилу тени серая распорка неотличима от подложки (%.1f)" % float(np.abs(grey - t * B).max()),
      float(np.abs(grey - t * B).max()) < 12)

# 3. кромка без подложки
C = 0.5 * np.array(RED, np.float32) + 0.5 * B
F = pb.decontaminate(C[None, None], np.array([[0.5]], np.float32), bg)[0, 0]
check("кромка 50%% на подложке -> цвет тела (%s)" % F.round().tolist(), float(np.abs(F - np.array(RED)).max()) < 1.5)

print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
