#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, третья партия зданий: сценарии и проверка моделью «M0j3, разметка v2».

Правило сценариев то же, что у пилота 0m (collapse_pilot_scen.scenarios: ONE, HOLE, CORNER, SIDE, ALL), но
список зданий и файлы свои - сценарии и замок 0m не меняются. НЛО, корабли игрока и базы в пилот не берутся.

Здания:
  * амбар бандитов 1 и 2 - CULTA_PP, два шаблона STR_LOC_BANDIT_TOWN_25 (пристройка вдоль y и вдоль x); дом
    10x10 в углу блока одинаковый до записи, у шаблонов разные только наружные стены пристройки;
  * сарай - RICE_FARM / ALT_BARN_10, пол 4x3 на z1 по стенам z0.

Ожидаемые FAIL (род принятого в 0m угла - правило X и перемычка k, консоль кладки): у амбаров бандитов
снятая стена у ворот z1 роняет перемычку над воротами, CORNER z2 - угол перекрытия, HOLE z2 - перегородка
на снятом полу. Модель не правится, FAIL пишется как есть.

    py -3.13 tools\collapse_pilot3_scen.py define   census/collapse/pilot3/pilot_scen.tsv и замок
    py -3.13 tools\collapse_pilot3_scen.py run      результат census/collapse/pilot3/pilot_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS

OUT = "census/collapse/pilot3"
PILOT = [("CULTA_PP", "STR_LOC_BANDIT_TOWN_25@38,8-49,31", "амбар бандитов 1"),
         ("CULTA_PP", "STR_LOC_BANDIT_TOWN_25@8,38-31,49", "амбар бандитов 2"),
         ("RICE_FARM", "ALT_BARN_10", "сарай")]
BOX = {"амбар бандитов 1": (2, 11, 2, 11), "амбар бандитов 2": (2, 11, 2, 11), "сарай": (7, 10, 6, 8)}
# метка в логе игры и в OXCE_COLLAPSE_REMOVE ("метка:номера") - одно слово
LABEL_EN = {"амбар бандитов 1": "banditbarn1", "амбар бандитов 2": "banditbarn2", "сарай": "riceshed"}


def use():
    """Переключает collapse_pilot_scen на список и файлы этой партии."""
    PS.OUT = OUT
    PS.SCEN = OUT + "/pilot_scen.tsv"
    PS.LOCK = OUT + "/pilot_scen.lock.txt"
    PS.RESULT = OUT + "/pilot_result.tsv"
    PS.PILOT = PILOT
    return PS


def cmd_define():
    use()
    PS.cmd_define()
    # замок 0m пишет sha правила сценариев (collapse_pilot_scen.py); список зданий живёт здесь - и его тоже
    with open(PS.LOCK, "a", encoding=PS.ENC) as f:
        f.write("%s\t%s\n" % ("tools/collapse_pilot3_scen.py", PS.sha("tools/collapse_pilot3_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
    else:
        use()
        PS.cmd_run()
