#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PCK читается так же, как его читает игра: кадры подряд, из TAB только их число (SurfaceSet::loadPck).

У BARN.PCK Пираток таблица смещений устарела (BARN.TAB 1993 года при PCK 2023-го). По смещениям
кадры 19-28 выходили пустыми, и генератор честно рисовал пустоту на месте полов и обломков.

    py tools\\test_read_pck.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "hdart"), HERE]

import xcom_sprites as xs                               # noqa: E402

T = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "TERRAIN")


def main():
    pck, tab = os.path.join(T, "BARN.PCK"), os.path.join(T, "BARN.TAB")
    if not os.path.exists(pck):
        print("нет %s - нечего проверять" % pck)
        return 1
    frames = xs.read_pck(pck, tab)
    n_tab = len(xs.read_tab(tab))
    filled = [f for f in range(19, 29) if frames[f] and any(v for row in frames[f] for v in row)]
    ok = len(frames) == n_tab == 29 and len(filled) == 10
    print("%s  BARN: кадров %d (по TAB %d), непустых среди 19-28: %d из 10"
          % ("ok " if ok else "BAD", len(frames), n_tab, len(filled)))
    print("итог: %s" % ("всё верно" if ok else "ОШИБКА"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
