#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, четвёртая партия: 20 зданий из целых блоков карт (не НЛО, не корабли игрока, не базы).

Правило сценариев то же, что у пилота 0m (collapse_pilot_scen.scenarios: ONE, HOLE, CORNER, SIDE, ALL); список
зданий, участки и файлы свои - сценарии и замки 0m и pilot3 не меняются. Модель M0j4 (collapse_v7d.install).

Отбор (scratchpad cp5/pick_all.py, census/collapse/pilot4/pick_all.tsv): целый блок, 20+ частей выше z0, все
предметы слота o выше z0 просмотрены (rev или разметка), нет неопределённой разметки, на целом ничего не висит,
нет стоп-условий выгрузки (судно, деревья, ROOF/TARP/RUN/HANGER, HULL, STRUCTURE), блок стоит целиком в сейвах
переписи census/collapse/battles (кроме дома притона - сейвы притона проверяются стендом). Участок здания - весь
блок. Разметки типа перекрытия (ctype) у этих зданий нет: модель её и не читает.

    py -3.13 tools\collapse_pilot4_scen.py define   census/collapse/pilot4/pilot_scen.tsv и замок
    py -3.13 tools\collapse_pilot4_scen.py run      результат census/collapse/pilot4/pilot_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS

OUT = "census/collapse/pilot4"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ("URBAN", "URBAN14", "дом города URBAN14", "urban14"),
    ("URBAN", "URBAN17", "дом города URBAN17", "urban17"),
    ("URBAN", "URBAN99", "дом города URBAN99", "urban99"),
    ("URBAN", "URBANDIO04", "дом города URBANDIO04", "urbandio04"),
    ("URBAN", "MADURBAN19", "дом города MADURBAN19", "madurban19"),
    ("URBAN", "MADURBAN22", "дом города MADURBAN22", "madurban22"),
    ("URBAN", "MADURBAN23", "дом города MADURBAN23", "madurban23"),
    ("URBAN", "MADURBAN27", "квартал MADURBAN27", "madurban27"),
    ("URBAN", "MADURBAN28", "квартал MADURBAN28", "madurban28"),
    ("CULTA", "CULTA18", "дом фермы CULTA18", "culta18"),
    ("CULTA", "CULTAFARM21", "дом фермы CULTAFARM21", "cultafarm21"),
    ("CULTA", "CULTA17", "постройка фермы CULTA17", "culta17"),
    ("CULTA", "CULTAFARM06", "постройка фермы CULTAFARM06", "cultafarm06"),
    ("CULTA", "CULTA30", "постройка фермы CULTA30", "culta30"),
    ("CULTA", "CULTASOL01", "постройка фермы CULTASOL01", "cultasol01"),
    ("RURAL", "VILBAN50", "дом деревни VILBAN50", "vilban50"),
    ("WESTOWN_ROCKY", "WESTOWN_16", "дом городка WESTOWN_16", "westown16"),
    ("URBANJUNKUFO", "URBANJUNK11", "дом свалки URBANJUNK11", "urbanjunk11"),
    ("CHEMTOWNGHOUL", "CHEMTOWN94", "дом химгорода CHEMTOWN94", "chemtown94"),
    ("STR_LOC_CRACKHOUSE", "CULTHOUSE05", "притон CULTHOUSE05", "culthouse05"),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {"MADURBAN27": 20, "MADURBAN28": 20}
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot4_scen.py", PS.sha("tools/collapse_pilot4_scen.py")))


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
