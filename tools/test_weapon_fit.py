#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверки tools/hdart/weapon_fit.gates (R-210: приёмка числом, а не только листом).

Синтетика: оригинал - ствол с отверстием; результат - тот же силуэт x4. Каждая порча обязана дать свой провал:
шире на 5 % - SIZE_W, дуло сдвинуто на 2 пикселя базы - MUZZLE, отверстие закрыто - HOLE, потеря части - DROP,
светлая кайма вокруг тёмного тела - RIM. Чистый результат - без провалов.
Данные: принятый АК (art/items/ak-final) проходит, отклонённый ak-v4 - нет (DROP и THIN); нет файлов - пропуск.
Запуск: py -3.13 tools/test_weapon_fit.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "hdart"))

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import weapon_fit as wf                 # noqa: E402

K = 4
fails_total = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails_total.append(name)


def gun():
    """Оригинал 32x48: вертикальный ствол дулом вверх, коробка с окном 2x2, рукоять вправо-вниз."""
    m = np.zeros((48, 32), bool)
    m[4:30, 10:13] = True               # ствол
    m[18:32, 8:18] = True               # коробка
    m[22:24, 12:14] = False             # окно
    m[30:42, 14:19] = True              # рукоять
    rgb = np.zeros((48, 32, 3), np.float32)
    rgb[m] = (60, 62, 70)
    return rgb, m


def up(m, rgb):
    a = np.repeat(np.repeat(m.astype(np.float32), K, 0), K, 1)
    c = np.repeat(np.repeat(rgb, K, 0), K, 1)
    return a, c


def run(a_full, c_full, m, mz="top", bg=None):
    box = wf.bbox(m)
    x0, y0, x1, y1 = box
    pal = np.unique(np.asarray([[60, 62, 70]], np.float32), axis=0)
    rep, fails = wf.gates(a_full[y0 * K:y1 * K, x0 * K:x1 * K], c_full[y0 * K:y1 * K, x0 * K:x1 * K], m, box, K,
                          mz, bg, pal, full=a_full, org=(x0 * K, y0 * K))
    return rep, fails


def has(fails, key):
    return any(f.startswith(key) for f in fails)


def synthetic():
    rgb, m = gun()
    a, c = up(m, rgb)
    _r, f = run(a, c, m)
    check("чистый результат - без провалов (%s)" % f, not f)
    # шире на 5 %: справа дописано
    a2 = a.copy()
    x0, y0, x1, y1 = wf.bbox(m)
    wide = int(round((x1 - x0) * K * 0.05)) + 1
    a2[(y0 + 20) * K:(y0 + 26) * K, x1 * K:x1 * K + wide] = 1
    _r, f = run(a2, c, m)
    check("шире на 5 %% за габаритом - SIZE_W (%s)" % f, has(f, "SIZE_W"))
    # контроль: без full вылезшее срезано кропом, SIZE молчит - так было до 04.10
    x0, y0, x1, y1 = wf.bbox(m)
    pal = np.asarray([[60, 62, 70]], np.float32)
    f0 = wf.gates(a2[y0 * K:y1 * K, x0 * K:x1 * K], c[y0 * K:y1 * K, x0 * K:x1 * K], m, (x0, y0, x1, y1), K, "top",
                  None, pal)[1]
    check("контроль: без full вылезшее не видно (%s)" % f0, not has(f0, "SIZE_W"))
    # дуло: верх ствола срезан на 2 пикселя базы и надставлен сбоку - размер тот же, дуло не на месте
    a3 = a.copy()
    a3[4 * K:6 * K, 10 * K:13 * K] = 0
    a3[4 * K:6 * K, 16 * K:17 * K] = 1
    _r, f = run(a3, c, m)
    check("дуло сдвинуто - MUZZLE (%s)" % f, has(f, "MUZZLE"))
    # отверстие закрыто
    a4 = a.copy()
    a4[22 * K:24 * K, 12 * K:14 * K] = 1
    _r, f = run(a4, c, m)
    check("окно закрыто - HOLE (%s)" % f, has(f, "HOLE"))
    # рукоять потеряна
    a5 = a.copy()
    a5[33 * K:42 * K, :] = 0
    a5[41 * K:42 * K, 14 * K:19 * K] = 1                       # низ на месте - размер тот же
    _r, f = run(a5, c, m, mz="top")
    check("рукоять потеряна - DROP (%s)" % f, has(f, "DROP"))
    # светлая кайма: кромка силуэта светлее тела
    c6 = c.copy()
    core = a > 0.5
    for r_ in (1, 2):
        core = core & np.roll(a > 0.5, r_, 0) & np.roll(a > 0.5, -r_, 0) & np.roll(a > 0.5, r_, 1) & \
            np.roll(a > 0.5, -r_, 1)
    c6[(a > 0.5) & ~core] = (200, 200, 205)
    _r, f = run(a, c6, m)
    check("светлая кайма - RIM (%s)" % f, has(f, "RIM"))
    # сырой уже на 7 % (правый край тела пуст), итог срезан маской до габарита оригинала: брак остаётся браком
    a7 = a.copy()
    x0, y0, x1, y1 = wf.bbox(m)
    narrow = int(round((x1 - x0) * K * 0.07)) + 1
    a7[:, x1 * K - narrow:x1 * K] = 0
    _r, raw_f = run(a7, c, m)
    _r, fin_f = run(a, c, m)
    fin_f = wf.carry_raw_size(raw_f, fin_f)
    check("сырой уже на 7 %% - SIZE_W у сырого (%s)" % raw_f, has(raw_f, "SIZE_W"))
    check("итог срезан до габарита - SIZE_W перенесён в итог (%s)" % fin_f, has(fin_f, "SIZE_W"))
    # контроль: без переноса итог по размеру чистый - так было до 05.10
    check("контроль: итог сам по себе размер проходит", not has(run(a, c, m)[1], "SIZE_W"))


def ak():
    d = os.path.join(ROOT, "census/items/cards/originals/STR_RIFLE_AK")
    acc = os.path.join(ROOT, "art/items/ak-final/pack/BIGOBS.PCK/1168.STR_RIFLE_AK.png")
    rej = os.path.join(ROOT, "art/items/ak-v4/pack/BIGOBS.PCK/1168.STR_RIFLE_AK.png")
    if not (os.path.isdir(d) and os.path.exists(acc) and os.path.exists(rej)):
        print("skip АК: нет файлов")
        return
    src = [f for f in sorted(os.listdir(d)) if f.startswith("BIGOBS_1168__")][0]
    im = Image.open(os.path.join(d, src))
    idx = np.asarray(im)
    pal = np.asarray(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    rgb_o, m = pal[idx].astype(np.float32), idx != 0
    box = wf.bbox(m)
    x0, y0, x1, y1 = box
    paln = np.unique(rgb_o[m], axis=0)
    out = {}
    for name, p in (("accepted", acc), ("v4", rej)):
        fr = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)
        out[name] = wf.gates(fr[y0 * K:y1 * K, x0 * K:x1 * K, 3] / 255.0, fr[y0 * K:y1 * K, x0 * K:x1 * K, :3],
                             m, box, K, "top", None, paln)[1]
    check("принятый АК проходит (%s)" % out["accepted"], not out["accepted"])
    check("отклонённый ak-v4 не проходит (%s)" % out["v4"], has(out["v4"], "DROP") or has(out["v4"], "THIN"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    synthetic()
    ak()
    print("итог: %s" % ("PASS" if not fails_total else "FAIL %d" % len(fails_total)))
    sys.exit(1 if fails_total else 0)
