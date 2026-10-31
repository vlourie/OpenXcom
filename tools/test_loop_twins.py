#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/loop_twins.py (R-338): близнецы петель анимации и их HD.

    py -3.13 tools/test_loop_twins.py
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import loop_twins as lt                                             # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def frame(v):
    a = np.zeros((40, 32), np.uint8)
    a[10:20, 10:20] = v
    return a


def png(p, v):
    a = np.zeros((160, 128, 4), np.uint8)
    a[40:80, 40:80] = (v, v, v, 255)
    Image.fromarray(a, "RGBA").save(p)


# 1. группы: кадры 1 и 2 одинаковы и стоят в одной петле; 3 тоже одинаков, но петли с ними нет
frames = [frame(5), frame(7), frame(7), frame(7), frame(9)]
recs = [[1, 2, 2, 2, 2, 2, 2, 2], [0, 0, 0, 0, 0, 0, 0, 0], [3, 3, 3, 3, 3, 3, 3, 3], [4, 0, 4, 0, 4, 0, 4, 0]]
g = lt.twin_groups(recs, frames)
check("близнецы петли найдены, основа - кадр, который показывается чаще (2)", g == [(2, [1])])
check("одинаковая классика без общей петли не группа (кадр 3)", all(3 not in [b] + t for b, t in g))
check("разная классика в петле не группа (0 и 4)", all(0 not in [b] + t for b, t in g))
g2 = lt.twin_groups([[1, 2, 1, 2, 1, 2, 1, 2]], frames)
check("при равном числе мест основа - младший", g2 == [(1, [2])])

# 2. HD: разный - ловится (контроль), одинаковый с вариантами - нет
with tempfile.TemporaryDirectory() as d:
    pack = Path(d)
    png(pack / "1.png", 100)
    png(pack / "2.png", 110)
    eq, diff = lt.same_hd(pack, 2, 1)
    check("контроль: разный HD близнецов ловится", not eq and diff and diff > 0)
    png(pack / "1.png", 110)
    eq, _ = lt.same_hd(pack, 2, 1)
    check("одинаковый HD - ровно", eq)
    png(pack / "2.v1.png", 120)
    eq, _ = lt.same_hd(pack, 2, 1)
    check("вариант только у основы - не ровно", not eq)
    png(pack / "1.v1.png", 120)
    eq, _ = lt.same_hd(pack, 2, 1)
    check("варианты одинаковы - ровно", eq)

# 3. настоящий случай: NUKE_CITY_2 запись 10, петля 11,12x7 - в обеих копиях мода, где набор есть
files = lt.game_files()
for label, root in lt.COPIES.items():
    if (Path(root) / "NUKE_CITY_2.PCK").is_dir():
        check("NUKE_CITY_2 без мигания (%s)" % label, lt.scan(root, {"NUKE_CITY_2"}, files) == [])

print("ИТОГ:", "FAIL " + ", ".join(FAIL) if FAIL else "все проверки прошли")
sys.exit(1 if FAIL else 0)
