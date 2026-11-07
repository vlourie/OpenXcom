#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка aligned_recolor_v2 без установки игры (специалист 02.10: AR2 = AR1 с границами 0.70).

  - границы 0.70 и выше проходят, ниже 0.70 - нет (не проверено), ровно 0.70 - проходит
  - все остальные условия - как у AR1: на сетке очков при границах >= 0.80 решения AR1 и AR2 совпадают
  - контроль: AR1 на тех же очках с границами 0.70-0.80 молчит
  - довод всегда STRONG (и без строгой перекраски наборов), детектор AR2, тип ALIGNED_RECOLOR
  - перемешанные цвета внутри силуэта довода не дают; параметры кроме границ - как у AR1
"""
import itertools
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
sys.path.insert(0, HERE)
import aligned_recolor_v1 as ar1                                 # noqa: E402
import aligned_recolor_v2 as ar2                                 # noqa: E402
import test_aligned_recolor_v1 as t1                             # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def sc(border, sil=0.98, fmax=0.95, resid=0.05, colors=10, shift=(0, 1)):
    return {"shift": list(shift), "silhouette": sil, "fmax": fmax, "base_colors": colors, "topology": border,
            "residual": resid}


def test_border():
    for b, want in ((0.85, True), (0.80, True), (0.75, True), (0.70, True), (0.699, False), (0.65, False),
                    (0.50, False)):
        ok, why = ar2.passes(sc(b), 1, 1)
        check("границы %.3f: AR2 %s" % (b, "проходит" if want else "не проходит (%s)" % "; ".join(why)),
              ok == want and (want or any(w.startswith("границ") for w in why)))
    ok1, _ = ar1.passes(sc(0.75), 1, 1)
    check("контроль: AR1 на границах 0.75 молчит", not ok1)


def test_same_as_ar1():
    diff = 0
    n = 0
    for b, s, f, r, c, sh, g in itertools.product((0.80, 0.9), (0.90, 0.92, 0.99), (0.79, 0.80, 0.9),
                                                    (0.1, 0.2, 0.21), (5, 6, 9), ((0, 0), (1, 0)), (1, 31)):
        x = sc(b, s, f, r, c, sh)
        o1, w1 = ar1.passes(x, g, 1)
        o2, w2 = ar2.passes(x, g, 1)
        n += 1
        diff += (o1 != o2) or (sorted(w1) != sorted(w2))
    check("при границах >= 0.80 решения и причины AR1 и AR2 совпадают (%d сочетаний, расхождений %d)" % (n, diff),
          diff == 0)


def test_params():
    same = {k: v for k, v in ar1.PARAMS.items() if k not in ("AR_BORDER", "level", "type_level")}
    check("параметры кроме границ - как у AR1", all(ar2.PARAMS[k] == v for k, v in same.items()))
    check("порог границ ровно 0.70, тип AR1, детектор AR2",
          ar2.AR_BORDER == 0.70 and ar2.TYPE == ar1.TYPE and ar2.DETECTOR == "AR2")


def test_pair():
    A, B = t1.sprite(t1.PAL_A), ar1.shift(t1.sprite(t1.PAL_B), 1, 1)
    ctx = t1.FakeCtx({"S1:1": A, "S2:5": B, "S1:2": t1.sprite(t1.PAL_B)})
    for strict in (False, True):
        es = ar2.pair(ctx, t1.FakeSi(strict), "S1:1", "S2:5")
        check("пара (строгая перекраска наборов %s): один довод STRONG, AR2, %s" % (strict, ar2.TYPE),
              len(es) == 1 and es[0]["level"] == "STRONG" and es[0]["detector"] == "AR2" and
              es[0]["type"] == ar2.TYPE and es[0]["rule"] == "AR2" and "подтип открыт" in es[0]["evidence"])
    check("пара: без сдвига довода нет", ar2.pair(ctx, t1.FakeSi(True), "S1:1", "S1:2") == [])
    P = B.copy()
    m = P[..., 3] > 0
    P[m] = P[m][np.random.default_rng(3).permutation(int(m.sum()))]
    check("пара: перемешанный кадр - довода нет", ar2.pair(ctx, t1.FakeSi(True), "S1:1", "S2:5", B=P) == [])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_border()
    test_same_as_ar1()
    test_params()
    test_pair()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
