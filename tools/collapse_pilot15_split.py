#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пятнадцатая партия (блоки с деревьями без порога 20+ частей): разбор провалов и решение «игрокам / эксп.» -
правило девятой партии (collapse_pilot9_split), свои файлы: census/collapse/pilot15/pilot_result.tsv,
census/collapse/partial15/model_result.tsv.

    py -3.13 tools\collapse_pilot15_split.py     census/collapse/pilot15/split.tsv и список на экран
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot9_split as S9

S9.RESULT = "census/collapse/pilot15/pilot_result.tsv"
S9.PARTIAL = "census/collapse/partial15/model_result.tsv"
S9.OUT = "census/collapse/pilot15/split.tsv"


def main():
    import collapse_pilot15_scen as P15
    sys.modules["collapse_pilot9_scen"] = P15          # список зданий партии берёт разбор девятой
    S9.main()


if __name__ == "__main__":
    main()
