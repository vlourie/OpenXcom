#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, пятая партия: 13 зданий из целых блоков карт (не НЛО, не корабли игрока, не базы).

Правило сценариев то же, что у пилота 0m (collapse_pilot_scen.scenarios: ONE, HOLE, CORNER, SIDE, ALL); список
зданий, участки и файлы свои - сценарии и замки 0m, pilot3 и pilot4 не меняются. Модель M0j4 (collapse_v7d.install).

Отбор (scratchpad cp5/pick_all.py, census/collapse/pilot4/pick_all.tsv): целый блок, 20+ частей выше z0, все
предметы слота o выше z0 просмотрены (rev или разметка), нет неопределённой разметки, на целом ничего не висит,
нет стоп-условий выгрузки (судно, деревья, ROOF/TARP/RUN/HANGER, HULL, STRUCTURE), блок стоит целиком в сейвах
переписи census/collapse/battles (у каждого - на своём террейне). Участок здания - весь
блок. Разметки типа перекрытия (ctype) у этих зданий нет: модель её и не читает.

    py -3.13 tools\collapse_pilot5_scen.py define   census/collapse/pilot5/pilot_scen.tsv и замок
    py -3.13 tools\collapse_pilot5_scen.py run      результат census/collapse/pilot5/pilot_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS

OUT = "census/collapse/pilot5"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ("URBAN", "MADURBAN24", "дом города MADURBAN24", "madurban24"),
    ("URBAN", "MADURBAN25", "дом города MADURBAN25", "madurban25"),
    ("URBAN", "MADURBAN26", "дом города MADURBAN26", "madurban26"),
    ("CULTA", "CULTAFARM03", "дом фермы CULTAFARM03", "cultafarm03"),
    ("CULTA", "CULTAFARM05", "дом фермы CULTAFARM05", "cultafarm05"),
    ("CULTA", "CULT_NEW17", "дом фермы CULT_NEW17", "cultnew17"),
    ("RURAL", "VILBAN55", "дом деревни VILBAN55", "vilban55"),
    ("URBANJUNKUFO", "URBANJUNK36", "дом свалки URBANJUNK36", "urbanjunk36"),
    ("CHEMTOWN", "CHEMTOWN11", "цех химгорода CHEMTOWN11", "chemtown11"),
    ("CHEMTOWN", "CHEMTOWN12", "цех химгорода CHEMTOWN12", "chemtown12"),
    ("CHEMTOWN", "CHEMTOWN13", "цех химгорода CHEMTOWN13", "chemtown13"),
    ("CHEMTOWNGHOUL", "CHEMTOWN91", "дом химгорода CHEMTOWN91", "chemtown91"),
    ("CHEMTOWNGHOUL", "CHEMTOWN92", "дом химгорода CHEMTOWN92", "chemtown92"),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {}
BOX = {ru: (0, SIZE.get(bn, 10) - 1, 0, SIZE.get(bn, 10) - 1) for tn, bn, ru, en in BUILDINGS}


def load():
    """Как collapse_pilot_scen.load, но здания - целые блоки карт (collapse_census.all_blocks), а не 0h/0i."""
    import collapse_ctype as CT
    import collapse_v2 as V
    import collapse_census as cc
    import collapse_attach_v2 as A2
    C = A2.use()
    roles = V.load_roles()
    args = V.game_args()
    out = []
    for tn, bn, label in PILOT:
        got = [blk for _, _, _, _, blk, err, _ in cc.all_blocks(args, only_block=bn, only_terrain=tn) if blk]
        if len(got) != 1:
            raise SystemExit("блок %s/%s: найдено %d" % (tn, bn, len(got)))
        blk = got[0]
        if (blk.sx, blk.sy) != (BOX[label][1] + 1, BOX[label][3] + 1):
            raise SystemExit("блок %s/%s: размер %dx%d не совпал с участком" % (tn, bn, blk.sx, blk.sy))
        V.apply_roles(blk, roles)
        C.apply_marks(blk)
        out.append((tn, bn, label, blk))
    return C, CT, out


def use():
    """Переключает collapse_pilot_scen на список, загрузку и файлы этой партии."""
    PS.OUT = OUT
    PS.SCEN = OUT + "/pilot_scen.tsv"
    PS.LOCK = OUT + "/pilot_scen.lock.txt"
    PS.RESULT = OUT + "/pilot_result.tsv"
    PS.PILOT = PILOT
    PS.load = load
    return PS


def cmd_define():
    use()
    PS.cmd_define()
    with open(PS.LOCK, "a", encoding=PS.ENC) as f:
        f.write("%s\t%s\n" % ("tools/collapse_pilot5_scen.py", PS.sha("tools/collapse_pilot5_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v7d as D
    D.install()                                   # M0j4, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
    else:
        use()
        PS.cmd_run()
