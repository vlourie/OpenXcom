#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Двадцать первая партия (правительственная база GOVT_BASE_DEFENSE, тикет XP-000294): разбор провалов и решение «игрокам / эксп.» -
правило девятой партии (collapse_pilot9_split), свои файлы: census/collapse/pilot21/pilot_result.tsv,
census/collapse/partial21/model_result.tsv.

    py -3.13 tools\collapse_pilot21_split.py     census/collapse/pilot21/split.tsv и список на экран
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot9_split as S9

S9.RESULT = "census/collapse/pilot21/pilot_result.tsv"
S9.PARTIAL = "census/collapse/partial21/model_result.tsv"
S9.OUT = "census/collapse/pilot21/split.tsv"


def main():
    import collapse_pilot21_scen as P21
    sys.modules["collapse_pilot9_scen"] = P21          # список зданий партии берёт разбор девятой
    S9.main()


if __name__ == "__main__":
    main()
