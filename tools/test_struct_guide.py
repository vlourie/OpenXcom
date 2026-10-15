#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""struct_guide: регулярная лесенка в 1 пиксель -> ровная линия; нерегулярная форма (уступ, зубцы, прут,
лестница 3x3, дыра) остаётся пиксель в пиксель как nearest. Без модели и без данных игры.

    py -3.13 tools/test_struct_guide.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import struct_guide as sg               # noqa: E402

FAIL = []
S = 8


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def cov(mask):
    h, w = mask.shape
    return sg.coverage([sg.smooth_loop(L) for L in sg.loops(mask)], w, h, S)


def near(mask):
    return np.repeat(np.repeat(mask.astype(np.float32), S, 0), S, 1)


def same(mask):
    return float(np.abs(cov(mask) - near(mask)).max()) < 1e-6


def analytic(h, w, inside):
    ys, xs = np.mgrid[0:h * S * 4, 0:w * S * 4]
    pts = inside((xs + 0.5) / (S * 4), (ys + 0.5) / (S * 4))
    return pts.reshape(h * S, 4, w * S, 4).mean((1, 3))


# 1. диагональ 45: тело под лесенкой, линия через середины ступеней y = x - 0.5
n = 16
m = np.fromfunction(lambda y, x: y >= x, (n, n)).astype(bool)
c = cov(m)
ref = analytic(n, n, lambda x, y: y >= x - 0.5)
inner = np.zeros_like(c, bool)
inner[S:-S, S:-S] = True                 # край картинки - ступень у рамки, не проверяем
err_s = float(np.abs(c - ref)[inner].mean())
err_n = float(np.abs(near(m) - ref)[inner].mean())
check("диагональ 45: ближе к линии, чем nearest (%.4f против %.4f)" % (err_s, err_n), err_s < err_n * 0.2)

# 2. изо-линия 2:1 (ступени R2 D1)
w2, h2 = 32, 16
m = np.fromfunction(lambda y, x: y >= x // 2, (h2, w2)).astype(bool)
c = cov(m)
ref = analytic(h2, w2, lambda x, y: y >= (x - 1.0) / 2.0)
inner = np.zeros_like(c, bool)
inner[S:-S, 2 * S:-2 * S] = True
err_s = float(np.abs(c - ref)[inner].mean())
err_n = float(np.abs(near(m) - ref)[inner].mean())
check("изо 2:1: ближе к линии, чем nearest (%.4f против %.4f)" % (err_s, err_n), err_s < err_n * 0.25)
check("изо 2:1: площадь сохранена (%.1f против %d)" % (c.sum() / S / S, m.sum()), abs(c.sum() / S / S - m.sum()) < 1.0)

# 3. нерегулярное - как было
m = np.zeros((20, 20), bool)
m[4:16, 3:17] = True
m[4:7, 8:11] = False                     # вырез 3x3 сверху
check("вырез 3x3 в крае - без изменений", same(m))
m = np.zeros((12, 24), bool)
m[5:11, 2:22] = True
m[2:5, 3:21:2] = True                    # гребёнка: зубцы в 1 пиксель через 1
check("зубцы в 1 пиксель - без изменений", same(m))
m = np.zeros((24, 12), bool)
m[18:22, 2:10] = True
m[3:18, 5] = True                        # прут в 1 пиксель
check("прут в 1 пиксель - без изменений", same(m))
m = np.zeros((10, 24), bool)
m[3:8, 2:12] = True
m[4:8, 12:22] = True                     # уступ в 1 пиксель на длинном крае
check("уступ в 1 пиксель на длинном крае - без изменений", same(m))
m = np.fromfunction(lambda y, x: y // 3 >= x // 3, (15, 15)).astype(bool)
check("лестница ступенями 3x3 - без изменений", same(m))
m = np.zeros((16, 16), bool)
m[2:14, 2:14] = True
m[6:9, 6:9] = False
check("дыра 3x3 - на месте", same(m) and len(sg.loops(m)) == 2)

# 4. длинный прямой край между лесенками остаётся прямым посередине
m = np.zeros((14, 40), bool)
for x in range(40):
    top = 2 + (x if x < 5 else 5 if x < 33 else 5 + (x - 32))
    m[min(top, 13):, x] = True
c = cov(m)
mid = c[:, 12 * S:26 * S]
check("прямой край между лесенками - прямой посередине", float(np.abs(mid - near(m)[:, 12 * S:26 * S]).max()) < 1e-6)

m = np.zeros((24, 12), bool)
t = 1
for k, inc in enumerate([0, 0, 1, 4, 1, 5, 1, 4, 0, 0]):      # рваный монотонный край: шаги 1, 4, 1, 5
    t += inc
    m[t:, k] = True
check("рваный край (шаги 1, 4, 1, 5) - без изменений", same(m))
# контроль: тот же край без проверки плавности сгладился бы
_r = sg.RATIO
sg.RATIO = 1e9
check("контроль: без проверки плавности рваный край меняется", not same(m))
sg.RATIO = _r

# 5. тонкая диагональ, связная только углами, - один контур, без разрывов
m = np.eye(12, dtype=bool)
check("диагональ углами - один контур (%d)" % len(sg.loops(m)), len(sg.loops(m)) == 1)
c = cov(m)
centres = [c[i * S + S // 2, i * S + S // 2] for i in range(1, 11)]
check("диагональ углами - середины пикселей покрыты", min(centres) > 0.5)

# 6. guide целиком: детерминирован, размер как у flat_input, подложка вне тела
fr = np.zeros((20, 16, 4), np.uint8)
fr[4:18, 3:13] = (180, 60, 40, 255)
fr[4:18, 3:6] = (60, 60, 200, 255)
fr[8, 8] = (10, 250, 10, 255)            # крапинка - вливается
img = Image.fromarray(fr, "RGBA")
g1, rep = sg.build(img, 4, (128, 128, 128))
g2, _ = sg.build(img, 4, (128, 128, 128))
check("guide детерминирован", np.array_equal(np.asarray(g1), np.asarray(g2)))
check("guide размером кадр x zoom", g1.size == (64, 80))
a = np.asarray(g1)
check("вне тела - подложка", tuple(a[0, 0]) == (128, 128, 128))
check("крапинка влилась: частей %d" % rep["parts"], rep["parts"] == 2 and tuple(a[8 * 4 + 2, 8 * 4 + 2]) != (10, 250, 10))

# 7. шахматка - фактура, сливается; тонкая диагональ другим цветом - деталь, остаётся
fr = np.zeros((14, 14, 4), np.uint8)
ch = np.fromfunction(lambda y, x: (y + x) % 2, (10, 10)).astype(bool)
fr[2:12, 2:12] = np.where(ch[..., None], (40, 60, 200, 255), (60, 90, 230, 255)).astype(np.uint8)
lab, cols, _m = sg.parts(Image.fromarray(fr, "RGBA"))
check("шахматка слилась в один цвет и у краёв тела (частей %d)" % len(cols), len(cols) == 1)
lab = np.zeros((12, 12), np.int32)
for i in range(1, 11):
    lab[i, i] = 1
check("диагональ в 1 пиксель другим цветом - на месте", (sg.dither(lab.copy()) == lab).all())

fr = np.zeros((24, 20, 4), np.uint8)
fr[2:22, 2:18] = (70, 70, 72, 255)
fr[3:21, 3:9] = (90, 90, 92, 255)
fr[10:20, 10:17] = (40, 40, 42, 255)
fr[14:17, 12:15] = (230, 190, 30, 255)   # жёлтый знак 3x3 на сером
lab, cols, _m = sg.parts(Image.fromarray(fr, "RGBA"), colors=3)
check("малый другой цвет - своя часть (%s)" % (cols,),
      any(c[0] > 180 and c[2] < 80 for c in cols))

print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
