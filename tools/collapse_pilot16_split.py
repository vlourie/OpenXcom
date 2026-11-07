#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Шестнадцатая партия (блоки без деревьев без порога 20+ частей): разбор провалов и решение «игрокам / эксп.» -
правило девятой партии (collapse_pilot9_split), свои файлы: census/collapse/pilot16/pilot_result.tsv,
census/collapse/partial16/model_result.tsv.

    py -3.13 tools\collapse_pilot16_split.py     census/collapse/pilot16/split.tsv и список на экран
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot9_split as S9

S9.RESULT = "census/collapse/pilot16/pilot_result.tsv"
S9.PARTIAL = "census/collapse/partial16/model_result.tsv"
S9.OUT = "census/collapse/pilot16/split.tsv"


def main():
    import collapse_pilot16_scen as P16
    sys.modules["collapse_pilot9_scen"] = P16          # список зданий партии берёт разбор девятой
    S9.main()


if __name__ == "__main__":
    main()
