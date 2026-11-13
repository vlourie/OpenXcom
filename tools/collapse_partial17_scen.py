#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Частичное обрушение пятнадцатой партии (блоки с деревьями без порога 20+ частей): сценарии деревьев те же,
что у девятой (collapse_partial9_scen: T - ствол у земли, M - ствол этажом выше, P - столб), блоки -
collapse_pilot17_scen.

    py -3.13 tools\collapse_partial17_scen.py define   census/collapse/partial17/partial_scen.tsv и замок
    py -3.13 tools\collapse_partial17_scen.py run      модель против ожиданий: census/collapse/partial17/model_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_partial9_scen as Q

OUT = "census/collapse/partial17"


def modules():
    """Партия 17: (модуль, здание) для всех её блоков."""
    import collapse_pilot17_scen as P17
    return [(P17, b) for b in P17.BUILDINGS]


def use():
    PF = Q.use()
    PF.OUT = OUT
    PF.SCEN = OUT + "/partial_scen.tsv"
    PF.LOCK = OUT + "/partial_scen.lock.txt"
    PF.RESULT = OUT + "/model_result.tsv"
    PF.modules = modules
    return PF


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    PF = use()
    if sys.argv[1] == "define":
        PF.cmd_define()
        with open(PF.LOCK, "a", encoding=PF.ENC) as f:
            for p in ("tools/collapse_partial17_scen.py", "tools/collapse_partial9_scen.py",
                      "tools/collapse_pilot17_scen.py"):
                f.write("%s\t%s\n" % (p, PF.sha(p)))
    else:
        PF.cmd_run()
