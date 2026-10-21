#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Защита R-430: педия кораблей противника рисуется тем же генератором, что фото кораблей игрока.

Фото кораблей игрока в педии сделаны pedia_batch.py -> pedia_ab.py --model new (Qwen-Image-2.1 DiffSynth,
img2img силой 0.95, негатив NEG_CINE). Свой стиль и свой конвейер (diffusers edit с нуля, S2-S4 21.10)
выбивались из раздела дважды. Тест сверяет исходник gen_ufo_pedia.draw21 с pedia_batch без видеокарты.

    py -3 tools\\test_ufo_pedia_style.py
"""
import inspect
import os
import re
import sys

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart")
sys.path.insert(0, HERE)

import gen_ufo_pedia as g  # noqa: E402


def main():
    src = inspect.getsource(g.draw21)
    assert "pedia_ab.New(" in src, "draw21 обязан рисовать pedia_ab.New - как педия кораблей игрока"
    assert "pb.NEG_CINE" in src, "draw21 обязан брать негатив стиля NEG_CINE из pedia_batch"
    with open(os.path.join(HERE, "pedia_batch.py"), encoding="utf-8-sig") as f:
        pb_src = f.read()
    m = re.search(r"strength = ([0-9.]+) if ship else", pb_src)
    assert m, "в pedia_batch.spec_for не найдена сила кораблей"
    main_src = inspect.getsource(g.main)
    d = re.search(r'"--strengths", default="([0-9.,]+)"', main_src)
    assert d and m.group(1) in d.group(1).split(","), \
        "сила кораблей pedia_batch %s должна быть среди --strengths draw21 (%s)" % (m.group(1), d and d.group(1))
    print("OK: draw21 = pedia_ab.New + NEG_CINE, сила %s" % m.group(1))


if __name__ == "__main__":
    main()
