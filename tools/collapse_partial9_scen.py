#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Частичное обрушение девятой партии (лес и столбы): сценарии деревьев, ожидание по структуре ветки D.

Ветка D (collapse_v5.tree_structure5) делит части деревьев на колонны (ствол или стопка от земли, снизу вверх) и
куски кроны с их стволами. Сценарий снимает одну часть колонны, ожидание пишется ДО прогона модели:
  * T - ствол дерева у земли (основание колонны, а у «ствола на земле» - первая часть над полом z0);
  * M - ствол дерева на этаж выше (у колонны от 3 частей);
  * P - столб (колонна не дерево: фонарный и прочий столб, стопка от земли), у земли.
Должно упасть: части колонны выше среза; куски кроны, у которых среди стволов есть этот, а этаж, до которого ствол
обязан стоять (этаж куска, но не выше верха самого высокого из его стволов), не ниже среза. Должно стоять: части
колонны ниже среза, другие колонны целиком, куски кроны без этого ствола и с этажом ниже среза. Часть, у которой в
клетке есть стена, - свободная (держится стеной по ядру), в ожидание не идёт; всё вне деревьев - тоже свободное.
Деревьев с самой большой кроной - до 3 сценариев T, 1 M, столбов - до 2 P на блок.

Вердикт и формат - как у collapse_partial_scen (PFALL с must_fall и must_stand), сторона - T, M или P, полоса -
клетка колонны. Участок для бойцов стенда - клетки этажа z0 в квадрате 5x5 вокруг колонны.

    py -3.13 tools\collapse_partial9_scen.py define   census/collapse/partial9/partial_scen.tsv и замок
    py -3.13 tools\collapse_partial9_scen.py run      модель M0j4 против ожиданий: census/collapse/partial9/model_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_partial_scen as PF

OUT = "census/collapse/partial9"
MAX_T, MAX_M, MAX_P = 3, 1, 2


def modules():
    """Партия 9: (модуль, здание) для всех её блоков."""
    import collapse_pilot9_scen as P9
    return [(P9, b) for b in P9.BUILDINGS]


def by_wall(blk, k):
    """В клетке части есть стена (своя западная и северная или соседская с той же стороны клетки)."""
    _, x, y, z = k
    lv = blk.lv[z]
    return any(c in lv[s] for s, c in (("w", (x, y)), ("w", (x + 1, y)), ("n", (x, y)), ("n", (x, y + 1))))


def scenarios(PS, CT, C, blk):
    """[(сторона, z, клетки участка, полоса, снятое, должно упасть, должно стоять)]."""
    import collapse_pilot9_scen as P9
    cols, crowns, tree_xy = P9.trees(C, blk)
    need = {k: (min(k[3], max(len(cols[c]) - 1 for c in cs)), cs) for k, (how, cs) in crowns.items() if cs}

    def one(xy, cut):
        st = cols[xy]
        fall = {k for k in st[cut + 1:] if not by_wall(blk, k)}
        stand = {k for k in st[:cut]}
        for c, other in cols.items():
            if c != xy:
                stand.update(k for k in other if not by_wall(blk, k))
        for k, (nd, cs) in need.items():
            if by_wall(blk, k):
                continue
            if xy in cs and nd >= cut:
                fall.add(k)
            else:
                stand.add(k)
        stand -= fall
        x, y = xy
        cells = sorted((cx, cy) for cx in range(x - 2, x + 3) for cy in range(y - 2, y + 3)
                       if 0 <= cx < blk.sx and 0 <= cy < blk.sy)
        return 0, cells, {xy}, {st[cut]}, fall, stand

    def size(xy):
        return sum(1 for k, (nd, cs) in need.items() if xy in cs)

    def base(xy):
        return 0 if cols[xy][0][0] == "o" else 1

    res = []
    tr = sorted(tree_xy, key=lambda xy: (-size(xy), xy))
    for side, pool, cut, lim in (("T", tr, base, MAX_T),
                                 ("M", [xy for xy in tr if len(cols[xy]) >= base(xy) + 3], lambda xy: base(xy) + 1,
                                  MAX_M),
                                 ("P", sorted(xy for xy in cols if xy not in tree_xy), base, MAX_P)):
        n = 0
        for xy in pool:
            if n >= lim:
                break
            z, cells, strip, rm, fall, stand = one(xy, cut(xy))
            if fall:
                res.append((side, z, cells, strip, rm, fall, stand))
                n += 1
    return res


def use():
    PF.OUT = OUT
    PF.SCEN = OUT + "/partial_scen.tsv"
    PF.LOCK = OUT + "/partial_scen.lock.txt"
    PF.RESULT = OUT + "/model_result.tsv"
    PF.modules = modules
    PF.scenarios = scenarios
    return PF


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    use()
    if sys.argv[1] == "define":
        PF.cmd_define()
        with open(PF.LOCK, "a", encoding=PF.ENC) as f:
            for p in ("tools/collapse_partial9_scen.py", "tools/collapse_pilot9_scen.py"):
                f.write("%s\t%s\n" % (p, PF.sha(p)))
    else:
        PF.cmd_run()
