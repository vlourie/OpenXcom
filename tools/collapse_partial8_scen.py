#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Частичное обрушение восьмой партии: то же правило PFALL, что у collapse_partial_scen (партии 4-6), свои файлы.

Правило, ожидание и вердикт не меняются - берутся из collapse_partial_scen как есть; здесь список зданий (все 15
зданий collapse_pilot8_scen), каталог census/collapse/partial8 и одно отличие партии: деревья вне модели, поэтому
из снятого, «должно упасть» и «должно стоять» убраны части деревьев (collapse_pilot8_scen.tree_parts) - в бою они
не падают и снятыми не считаются. Замок ставится до первого прогона модели и держит sha обоих скриптов.

    py -3.13 tools\collapse_partial8_scen.py define   census/collapse/partial8/partial_scen.tsv и замок
    py -3.13 tools\collapse_partial8_scen.py run      модель M0j4 против ожиданий: census/collapse/partial8/model_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_partial_scen as PF

OUT = "census/collapse/partial8"


def modules():
    """Партия 8: (модуль, здание) для всех её зданий."""
    import collapse_pilot8_scen as P8
    return [(P8, b) for b in P8.BUILDINGS]


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
            f.write("%s\t%s\n" % ("tools/collapse_partial8_scen.py", PF.sha("tools/collapse_partial8_scen.py")))
    else:
        PF.cmd_run()
