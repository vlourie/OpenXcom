#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""obj_families: семейство собирается вокруг канонического кадра, а не цепочкой соседей
(docs/HD_PIPELINE_V2.md, раздел 3 и тест T1).

  * T1: A~B, B~C, A!~C - семейство A+B, C на проверку с причиной indirect_chain, мостов нет;
  * слабое зеркало (свет на своей стороне) - на проверку weak_mirror, а не в семейство;
  * решение человека: HUMAN_APPROVED вводит кандидата, HUMAN_REJECTED выводит даже прямого;
  * связь на синтетических кадрах: перекраска и зеркало опознаются, чужая форма - нет.
Контрольный опыт: прежняя склейка связными компонентами кладёт C в семейство - T1 это ловит.

    py -3.13 tools/test_obj_families.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import obj_families as of               # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def direct_from(table):
    def direct(c, r):
        kind = table.get((min(c, r), max(c, r)))
        return (kind, 0.95, 0.9, 0.9, 10.0) if kind else (None, 0.5, 0.1, 0.1, 10.0)
    return direct


def t1():
    edges = [(1, 2, "recolor"), (2, 3, "recolor")]
    fams = of.assemble([1, 2, 3], edges, direct_from({(1, 2): "recolor", (2, 3): "recolor"}))
    check("T1: одно семейство на компоненту", len(fams) == 1)
    fm = fams[0]
    check("T1: канонический - самый частый (1)", fm["canonical"] == 1)
    check("T1: B в семействе напрямую", [m[0] for m in fm["members"]] == [2])
    check("T1: C не в семействе", 3 not in [m[0] for m in fm["members"]])
    rv = {r: why for r, _k, _e, why, _v in fm["review"]}
    check("T1: C на проверку, причина indirect_chain", rv.get(3) == "indirect_chain")
    check("T1: через кого C связан - записано", fm["review"][0][4] == ["recolor 2"])


def weak():
    fams = of.assemble([1, 2], [(1, 2, "mirror_weak")], direct_from({(1, 2): "mirror_weak"}))
    fm = fams[0]
    check("слабое зеркало не входит само", not fm["members"])
    check("слабое зеркало - на проверку weak_mirror", fm["review"][0][3] == "weak_mirror")


def human():
    edges = [(1, 2, "recolor"), (2, 3, "recolor")]
    table = {(1, 2): "recolor", (2, 3): "recolor"}
    fams = of.assemble([1, 2, 3], edges, direct_from(table),
                       {(1, 3): (of.APPROVED, "recolor"), (1, 2): (of.REJECTED, "")})
    fm = fams[0]
    mem = {m[0]: m[3] for m in fm["members"]}
    check("HUMAN_APPROVED вводит C", mem.get(3) == of.APPROVED)
    check("HUMAN_REJECTED выводит B, хотя связь прямая", 2 not in mem and fm["rejected"] == [2])
    check("на проверку не осталось ничего", not fm["review"])


def sprite(shape, colors, flip=False):
    """Кадр 32x40: фигура по маске, яркость растёт слева направо, цвет - множитель по каналам."""
    a = np.zeros((40, 32, 4), np.uint8)
    yy, xx = np.mgrid[0:40, 0:32]
    lum = 60 + xx * 5 + (yy % 7) * 6
    for ch in range(3):
        a[..., ch] = np.clip(lum * colors[ch], 0, 255)
    a[..., 3] = np.where(shape, 255, 0)
    if flip:
        a = a[:, ::-1].copy()
    return Image.fromarray(a, "RGBA")


def relation():
    yy, xx = np.mgrid[0:40, 0:32]
    boot = (xx > 4) & (xx < 20) & (yy > 5) & (yy < 36) | (xx >= 20) & (xx < 28) & (yy > 26) & (yy < 36)
    round_ = (xx - 16) ** 2 + (yy - 20) ** 2 < 120
    blue = of.feats(sprite(boot, (0.6, 0.7, 1.0)))
    red = of.feats(sprite(boot, (1.0, 0.5, 0.4)))
    flipped = of.feats(sprite(boot, (0.6, 0.7, 1.0), flip=True))
    other = of.feats(sprite(round_, (0.6, 0.7, 1.0)))
    check("перекраска опознана", of.pair_relation([blue], [red], True)[0] == "recolor")
    check("зеркало опознано", of.pair_relation([blue], [flipped], True)[0] == "mirror")
    r = of.pair_relation([blue], [other], True)
    check("другая форма - не связь, числа есть", r[0] is None and 0 < r[1] < of.IOU)
    check("разное число кусков - не связь", of.pair_relation([blue], [blue, red], True)[0] is None)


def control():
    """Прежний алгоритм: связная компонента = семейство. T1 обязан его забраковать."""
    par = {1: 1, 2: 2, 3: 3}
    for r, q in ((1, 2), (2, 3)):
        par[max(par[r], par[q])] = min(par[r], par[q])
    old_members = [r for r in par if par[r] == 1 or par[par[r]] == 1]
    check("контроль: прежняя склейка кладёт C в семейство (T1 это видит)", 3 in old_members)


t1()
weak()
human()
relation()
control()
print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
