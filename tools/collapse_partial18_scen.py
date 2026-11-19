#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Частичное обрушение шестнадцатой партии (блоки без деревьев без порога 20+ частей): правило PFALL зданий, как у восьмой партии.

Партии 9-13 проверялись сценариями деревьев (collapse_partial9_scen); в шестнадцатой деревьев нет, а слой связей
M0j5 держит плиту вбок - её ловит именно PFALL зданий: правило, ожидание и вердикт из collapse_partial_scen как есть,
из снятого, «должно упасть» и «должно стоять» убраны части деревьев (collapse_pilot8_scen.tree_parts), как в
collapse_partial8_scen. Замок ставится до первого прогона модели и держит sha скриптов.

    py -3.13 tools\collapse_partial18_scen.py define   census/collapse/partial18/partial_scen.tsv и замок
    py -3.13 tools\collapse_partial18_scen.py run      модель против ожиданий: census/collapse/partial18/model_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_partial_scen as PF

OUT = "census/collapse/partial18"


def modules():
    """Партия 18: (модуль, здание) для всех её блоков."""
    import collapse_pilot18_scen as P18
    return [(P18, b) for b in P18.BUILDINGS]


_scenarios = PF.scenarios


def scenarios(PS, CT, C, blk):
    """Правило PFALL без частей деревьев; сценарий, у которого снятое опустело, выпадает."""
    import collapse_pilot8_scen as P8
    tree = P8.tree_parts(C, blk)
    res = []
    for side, z, cells, strip, rm, fall, stand in _scenarios(PS, CT, C, blk):
        rm = {k for k in rm if k not in tree}
        if rm:
            res.append((side, z, cells, strip, rm, {k for k in fall if k not in tree},
                        {k for k in stand if k not in tree}))
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
            for p in ("tools/collapse_partial18_scen.py", "tools/collapse_pilot18_scen.py"):
                f.write("%s\t%s\n" % (p, PF.sha(p)))
    else:
        PF.cmd_run()
