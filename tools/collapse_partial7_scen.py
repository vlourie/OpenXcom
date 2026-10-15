#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Частичное обрушение седьмой партии: то же правило PFALL, что у collapse_partial_scen (партии 4-6), свои файлы.

Правило, ожидание и вердикт не меняются - берутся из collapse_partial_scen как есть; здесь только список зданий
(все 31 здание collapse_pilot7_scen) и каталог census/collapse/partial7. Замок партий 4-6
(census/collapse/partial/partial_scen.lock.txt) не трогается. Замок этой партии ставится до первого прогона модели
и держит sha обоих скриптов.

    py -3.13 tools\collapse_partial7_scen.py define   census/collapse/partial7/partial_scen.tsv и замок
    py -3.13 tools\collapse_partial7_scen.py run      модель M0j4 против ожиданий: census/collapse/partial7/model_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_partial_scen as PF

OUT = "census/collapse/partial7"


def modules():
    """Партия 7: (модуль, здание) для всех её зданий."""
    import collapse_pilot7_scen as P7
    return [(P7, b) for b in P7.BUILDINGS]


def use():
    PF.OUT = OUT
    PF.SCEN = OUT + "/partial_scen.tsv"
    PF.LOCK = OUT + "/partial_scen.lock.txt"
    PF.RESULT = OUT + "/model_result.tsv"
    PF.modules = modules
    return PF


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    use()
    if sys.argv[1] == "define":
        PF.cmd_define()
        with open(PF.LOCK, "a", encoding=PF.ENC) as f:
            f.write("%s\t%s\n" % ("tools/collapse_partial7_scen.py", PF.sha("tools/collapse_partial7_scen.py")))
    else:
        PF.cmd_run()
