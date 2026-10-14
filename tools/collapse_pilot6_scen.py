#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, шестая партия: 8 зданий из целых блоков карт (не НЛО, не корабли игрока, не базы).

Правило сценариев то же, что у пилота 0m (collapse_pilot_scen.scenarios: ONE, HOLE, CORNER, SIDE, ALL); список
зданий, участки и файлы свои - сценарии и замки 0m, pilot3, pilot4 и pilot5 не меняются. Модель M0j4
(collapse_v7d.install).

Отбор как у пятой партии (census/collapse/pilot4/pick_all.tsv), с одним послаблением: у здания 1-2 записи
предметов слота o выше z0 не просмотрены (нет rev и нет разметки), и все они - предметы на полу своей клетки:
COMMERCE:54 (кондиционер), COMBITS:12 (антенна), BARN:4 (тюки сена), URBITS_INDUSLUM:2 и URBAN:54 (вытяжная
труба). Модель держит их как авто-роль OBJECT - полом клетки, это и верно; разметка v2 не меняется (лист
кадров и мест - scratchpad cp5/auto_sheet.py). Остальное как у пятой: без стоп-условий, на целом ничего не
висит, блок стоит целиком в сейвах переписи на своём террейне. Участок здания - весь блок.

    py -3.13 tools\collapse_pilot6_scen.py define   census/collapse/pilot6/pilot_scen.tsv и замок
    py -3.13 tools\collapse_pilot6_scen.py run      результат census/collapse/pilot6/pilot_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS

OUT = "census/collapse/pilot6"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ("COMRCURBAN", "COMRCURBAN50", "дом торгового квартала COMRCURBAN50", "comrcurban50"),
    ("COMRCURBAN", "COMRCURBAN51", "дом торгового квартала COMRCURBAN51", "comrcurban51"),
    ("COMRCURBAN", "COMRCURBAN22", "дом торгового квартала COMRCURBAN22", "comrcurban22"),
    ("URBAN", "URBANDIO03", "дом города URBANDIO03", "urbandio03"),
    ("INDUSTRIALSLUM", "INDUSTRIALSLUMDIO27", "дом трущоб INDUSTRIALSLUMDIO27", "induslum27"),
    ("CULTA", "CULTA19", "дом фермы CULTA19", "culta19"),
    ("CULTA", "CULTA31", "дом фермы CULTA31", "culta31"),
    ("CULTA", "CULT_NEW16", "дом фермы CULT_NEW16", "cultnew16"),
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot6_scen.py", PS.sha("tools/collapse_pilot6_scen.py")))


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
