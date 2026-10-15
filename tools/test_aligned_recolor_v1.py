#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка aligned_recolor_v1 на синтетике, без установки игры (V5_PREP, специалист 02.10).

  - перекраска со сдвигом на 1-2 пикселя находится, прямо и в отражении; контроль - без сдвига AR1 молчит (область R4)
  - сдвиг больше AR_SHIFT не находится
  - цвета, перемешанные внутри силуэта, не проходят (перемешанный контроль)
  - малая местная правка проходит, большая - нет (остаток)
  - общий силуэт не проходит; уровень STRONG только при строгой перекраске наборов, тип - всегда кандидат подтипа
  - пороги не ниже R4
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import aligned_recolor_v1 as ar                                  # noqa: E402
import relation_discovery_v4 as v4                               # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


PAL_A = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30), (200, 30, 200), (30, 200, 200),
         (120, 120, 120), (250, 250, 250)]
PAL_B = [(90, 10, 10), (10, 90, 10), (10, 10, 90), (90, 90, 10), (90, 10, 90), (10, 90, 90), (50, 50, 50),
         (180, 180, 180)]


def sprite(pal, x0=8, y0=8, w=16, h=24, asym=True):
    """Кадр 40x32: прямоугольник из 8 цветных полос и (asym) выступ справа сверху - силуэт несимметричен."""
    a = np.zeros((40, 32, 4), np.uint8)
    for i in range(h):
        a[y0 + i, x0:x0 + w, :3] = pal[(i // 3) % len(pal)]
        a[y0 + i, x0:x0 + w, 3] = 255
    if asym:
        a[y0:y0 + 6, x0 + w:x0 + w + 4, :3] = pal[0]
        a[y0:y0 + 6, x0 + w:x0 + w + 4, 3] = 255
    return a


def test_shift():
    m = np.zeros((4, 5), np.uint8)
    m[1, 1] = 7
    s = ar.shift(m, 2, 1)
    check("сдвиг: пиксель уехал на dx 2, dy 1", s[2, 3] == 7 and s.sum() == 7)
    check("сдвиг за край - пусто", ar.shift(m, 5, 0).sum() == 0 and ar.shift(m, -2, 0).sum() == 0)


def test_found():
    A, B = sprite(PAL_A), sprite(PAL_B)
    sc0 = ar.scores(A, B)
    ok0, why0 = ar.passes(sc0, 1, 1)
    check("контроль: перекраска без сдвига - не AR1 (область R4)", not ok0 and any("нулевой" in w for w in why0))
    for dx, dy in ((1, 0), (0, -1), (2, 2), (-2, 1)):
        Bs = ar.shift(B, dx, dy)
        sc = ar.scores(A, Bs)
        ok, why = ar.passes(sc, 1, 1)
        check("перекраска со сдвигом %+d,%+d найдена (силуэт %.3f, остаток %.3f)" % (dx, dy, sc["silhouette"],
                                                                                   sc["residual"]),
              ok and sc["shift"] == [-dx, -dy] and not sc["flip"])
    Bm = ar.shift(np.ascontiguousarray(B[:, ::-1]), 1, 0)
    sc = ar.scores(A, Bm)
    ok, _ = ar.passes(sc, 1, 1)
    check("отражённая перекраска со сдвигом найдена", ok and sc["flip"])
    sc = ar.scores(A, ar.shift(B, 3, 0))
    ok, why = ar.passes(sc, 1, 1)
    check("сдвиг 3 > AR_SHIFT не найден (силуэт %.3f)" % sc["silhouette"], not ok)


def test_controls():
    A, B = sprite(PAL_A), ar.shift(sprite(PAL_B), 1, 0)
    P = B.copy()
    m = P[..., 3] > 0
    px = P[m]
    P[m] = px[np.random.default_rng(7).permutation(len(px))]
    ok, why = ar.passes(ar.scores(A, P), 1, 1)
    check("перемешанные цвета внутри силуэта не проходят (%s)" % "; ".join(why), not ok)
    E = B.copy()
    E[10:12, 12:16, :3] = (7, 7, 7)                     # малая правка: 8 пикселей
    ok, why = ar.passes(ar.scores(A, E), 1, 1)
    check("малая местная правка проходит", ok)
    E = B.copy()
    E[9:26, 9:24, :3] = (7, 7, 7)                       # большая правка: больше половины тела
    sc = ar.scores(A, E)
    ok, why = ar.passes(sc, 1, 1)
    check("большая правка не проходит (%s)" % "; ".join(why), not ok)
    ok, why = ar.passes(ar.scores(A, B), ar.AR_GENERIC + 1, 1)
    check("общий силуэт не проходит", not ok and any("общий" in w for w in why))


def test_thresholds():
    check("пороги не ниже R4: силуэт %.2f, функция %.2f, границы %.2f" % (ar.AR_IOU, ar.AR_FUNC, ar.AR_BORDER),
          ar.AR_IOU >= v4.R4_NEAR and ar.AR_FUNC >= v4.R4D_FUNC and ar.AR_BORDER >= v4.R4D_BORDER and
          ar.MIN_COLORS >= v4.MIN_COLORS and ar.AR_GENERIC <= v4.R4D_GENERIC)
    check("диапазон сдвига мал и фиксирован", ar.AR_SHIFT == 2 and len(ar.SHIFTS) == 25)


class FakeIx:
    def exact(self, k):
        return set()

    def mirror(self, k):
        return set()


class FakeCtx:
    def __init__(self, arr):
        self.arr, self.ix = arr, FakeIx()

    def rgba(self, k):
        return self.arr.get(k.upper())


class FakeSi:
    def __init__(self, strict):
        self.strict = strict

    def generic(self, k):
        return 1

    def pair_stats(self, s, t):
        return {"common": 20, "geo": 1.0, "strict": 1.0 if self.strict else 0.1}


def test_pair():
    ctx = FakeCtx({"S1:1": sprite(PAL_A), "S2:5": ar.shift(sprite(PAL_B), 1, 1), "S1:2": sprite(PAL_B)})
    es = ar.pair(ctx, FakeSi(False), "S1:1", "S2:5")
    check("пара: довод CANDIDATE без строгой перекраски наборов", len(es) == 1 and es[0]["level"] == "CANDIDATE"
          and es[0]["type"] == ar.TYPE and es[0]["detector"] == "AR1")
    es = ar.pair(ctx, FakeSi(True), "S1:1", "S2:5")
    check("пара: STRONG при строгой перекраске наборов", len(es) == 1 and es[0]["level"] == "STRONG"
          and es[0]["rule"] == "AR1s")
    check("пара: без сдвига довода нет", ar.pair(ctx, FakeSi(True), "S1:1", "S1:2") == [])
    P = ctx.arr["S2:5"].copy()
    m = P[..., 3] > 0
    P[m] = P[m][np.random.default_rng(3).permutation(int(m.sum()))]
    check("пара: подмена перемешанным кадром - довода нет", ar.pair(ctx, FakeSi(True), "S1:1", "S2:5", B=P) == [])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_shift()
    test_found()
    test_controls()
    test_thresholds()
    test_pair()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
