#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""relation_probe: перекраска по функции цвета, а не по яркости; пара без набора-двойника - не довод.

    py -3.13 tools/test_relation_probe.py
Синтетика, без карт и установки.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import relation_probe as rp     # noqa: E402
import obj_families as of       # noqa: E402


def frame(seed, ramp):
    """Кадр 32x40: куст из двух рамп (листва 0..4, ягоды 5..6), цвета по ramp."""
    rng = np.random.default_rng(seed)
    idx = np.zeros((40, 32), np.int64) - 1
    idx[8:36, 6:26] = rng.integers(0, 5, (28, 20))
    idx[rng.random((40, 32)) < 0.05] = -1
    idx[(idx >= 0) & (rng.random((40, 32)) < 0.08)] = 5 + rng.integers(0, 2)
    a = np.zeros((40, 32, 4), np.uint8)
    for i, c in enumerate(ramp):
        a[idx == i] = c + (255,)
    return a


GREEN = [(4, 40, 0), (16, 68, 4), (28, 84, 8), (56, 112, 20), (88, 140, 32), (12, 36, 96), (80, 120, 172)]
BLACK = [(5, 4, 9), (12, 9, 16), (15, 12, 19), (24, 21, 28), (35, 31, 37), (90, 10, 30), (205, 30, 45)]


def pair_of(A, B, iou=1.0):
    ma, ca = rp.codes(A)
    mb, cb = rp.codes(B)
    m = ma & mb
    f_ab = rp.func_map(ca[m], cb[m])[0]
    f_ba = rp.func_map(cb[m], ca[m])[0]
    bad = (ma ^ mb).sum()
    return {"1_geometry": {"iou": iou}, "4_palette": {"f_ab": f_ab, "f_ba": f_ba, "explained": f_ab,
                                                     "unexplained_px": int(bad), "unexplained_parts": 1},
            "5_mcd": {"vox_same": True, "phys_diff": []}}


def main():
    fails = []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    A, B = frame(1, GREEN), frame(1, BLACK)
    rel = of.relation(rp.of_feats(A), rp.of_feats(B))
    p = pair_of(A, B)
    check("тёмная перекраска с яркими ягодами: функция цвета 1.0 в обе стороны",
          p["4_palette"]["f_ab"] == 1.0 and p["4_palette"]["f_ba"] == 1.0)
    check("контроль: яркость obj_families её не принимает (corr или edge ниже порога)",
          rel[0] is None and (rel[2] < of.CORR or rel[3] < of.EDGE))
    k, lvl, _ = rp.candidate(p, {"share_strict": 1.0, "strict_recolor_frames": 9, "compared": 9, "global_f_ab": 1.0})
    check("перекраска + набор-двойник + MCD тот же - RECOLOR_OF STRONG", (k, lvl) == ("RECOLOR_OF", "STRONG"))
    check("перекраска без набора-двойника - только CANDIDATE", rp.candidate(p)[:2] == ("RECOLOR_OF", "CANDIDATE"))
    C = frame(2, BLACK)                     # тот же силуэт по маске? нет - другой рисунок, частичная функция
    C[..., 3] = A[..., 3]
    C[A[..., 3] > 0, :3] = np.where(np.random.default_rng(3).random(((A[..., 3] > 0).sum(), 1)) < 0.8,
                                    B[A[..., 3] > 0, :3], C[A[..., 3] > 0, :3])
    q = pair_of(A, C)
    check("частичная функция (0.6-0.98) без набора-двойника - NONE, не «состояние»",
          0.6 <= q["4_palette"]["f_ab"] < 0.98 and rp.candidate(q)[0] == "NONE")
    k2 = rp.candidate(q, {"share_strict": 0.92, "strict_recolor_frames": 34, "compared": 37, "global_f_ab": 0.93})
    check("та же частичная функция при наборе-двойнике - RECOLOR_WITH_LOCAL_EDIT CANDIDATE",
          k2[:2] == ("RECOLOR_WITH_LOCAL_EDIT", "CANDIDATE"))
    k3 = rp.candidate(q, {"share_strict": 0.37, "strict_recolor_frames": 0, "compared": 40, "global_f_ab": 0.37})
    check("набор того же номера, но не перекраска - NONE", k3[0] == "NONE")
    # много-к-одному: B выводится из A, обратно нет - для набора это перекраска
    D = A.copy()
    m = D[..., 3] > 0
    D[m & (D[..., 0] == 16)] = (4, 40, 0, 255)
    r = pair_of(A, D)
    check("сведение двух оттенков в один: f_ab 1.0, f_ba < 1", r["4_palette"]["f_ab"] == 1.0 and r["4_palette"]["f_ba"] < 1.0)
    print("итог:", "все проверки прошли" if not fails else "провалено %d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
