#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, седьмая партия: 31 здание из целых блоков карт (не НЛО, не корабли игрока, не базы).

Правило сценариев то же, что у пилота 0m (collapse_pilot_scen.scenarios: ONE, HOLE, CORNER, SIDE, ALL); список
зданий, участки и файлы свои - сценарии и замки 0m, pilot3-6 не меняются. Модель M0j4 (collapse_v7d.install).

Отбор как у шестой партии (census/collapse/pilot4/pick_all.tsv: без стоп-условий, на целом ничего не висит, нет
неопределённой разметки, блок стоит целиком в сейвах переписи на своём террейне), с шире послаблением: у здания
3-50 непросмотренных записей предметов слота o выше z0, и все они - предметы на полу своей клетки. Лист видов
(93 вида, scratchpad cp9/kinds_sheet.py): мебель (столы, стулья, кровати, шкафы, телевизоры, лампы, кресла,
ванны), ящики, тюки сена BARN:4, кондиционер COMMERCE:54, антенна COMBITS:12, вытяжная труба URBAN:54, лестницы
(BARN_JUNK:15, MADDECOR:48/49, URBAN:21/22/48/49/55/56). У каждой записи пол в своей клетке есть. Модель держит
их как авто-роль OBJECT - полом клетки, этаж они не несут (у лестницы и в разметке роль STAIRS не несущая);
разметка v2 не меняется. MOUNTBD09 из списка снят: горный склон, не здание. Блоки, что стоят на нескольких
террейнах (URBANWAR, CULTA_PP), берутся по разу. Участок здания - весь блок.

    py -3.13 tools\collapse_pilot7_scen.py define   census/collapse/pilot7/pilot_scen.tsv и замок
    py -3.13 tools\collapse_pilot7_scen.py run      результат census/collapse/pilot7/pilot_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS

OUT = "census/collapse/pilot7"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ("URBANJUNKUFO", "URBANJUNK15", "дом свалки URBANJUNK15", "urbanjunk15"),
    ("CULTA", "CULTA16", "дом фермы CULTA16", "culta16"),
    ("CULTA", "CULTAFARM00", "ферма CULTAFARM00", "cultafarm00"),
    ("CULTA", "CULTAFARM14", "ферма CULTAFARM14", "cultafarm14"),
    ("URBAN", "MADURBAN37", "дом города MADURBAN37", "madurban37"),
    ("URBAN", "MADURBAN38", "дом города MADURBAN38", "madurban38"),
    ("URBAN", "MADURBAN10", "дом города MADURBAN10", "madurban10"),
    ("URBAN", "MADURBAN33", "квартал MADURBAN33", "madurban33"),
    ("URBAN", "MADURBAN36", "дом города MADURBAN36", "madurban36"),
    ("URBAN", "URBAN05", "квартал URBAN05", "urban05"),
    ("URBANWAR", "URBAN15", "дом города URBAN15", "urban15"),
    ("URBAN", "MADURBAN20", "дом города MADURBAN20", "madurban20"),
    ("URBAN", "MADURBAN21", "дом города MADURBAN21", "madurban21"),
    ("URBAN", "URBAN18", "дом города URBAN18", "urban18"),
    ("COMRCURBAN", "COMRCURBAN40", "дом торгового квартала COMRCURBAN40", "comrcurban40"),
    ("URBAN", "EXPANDEDTERROR13", "дом города EXPANDEDTERROR13", "expterror13"),
    ("COMRCURBAN", "COMRCURBAN11", "торговый квартал COMRCURBAN11", "comrcurban11"),
    ("URBAN", "URBANDIO02", "квартал URBANDIO02", "urbandio02"),
    ("URBAN", "SOLBAN40", "дом города SOLBAN40", "solban40"),
    ("COMRCURBAN", "COMRCURBAN53", "дом торгового квартала COMRCURBAN53", "comrcurban53"),
    ("URBAN", "URBAN19", "дом города URBAN19", "urban19"),
    ("COMRCURBAN", "COMRCURBAN25", "дом торгового квартала COMRCURBAN25", "comrcurban25"),
    ("URBAN", "MADURBAN12", "квартал MADURBAN12", "madurban12"),
    ("COMRCURBAN", "COMRCURBAN46", "дом торгового квартала COMRCURBAN46", "comrcurban46"),
    ("URBAN", "MADURBAN11", "квартал MADURBAN11", "madurban11"),
    ("URBAN", "MADURBAN13", "квартал MADURBAN13", "madurban13"),
    ("URBAN", "URBAN06", "квартал URBAN06", "urban06"),
    ("COMRCURBAN", "COMRCURBAN45", "дом торгового квартала COMRCURBAN45", "comrcurban45"),
    ("URBAN", "MADURBAN31", "квартал MADURBAN31", "madurban31"),
    ("URBANWAR", "MADURBAN30", "квартал MADURBAN30", "madurban30"),
    ("URBAN", "EXPANDEDTERROR24", "квартал EXPANDEDTERROR24", "expterror24"),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {bn: 20 for bn in ("CULTAFARM00", "CULTAFARM14", "MADURBAN33", "URBAN05", "COMRCURBAN11", "URBANDIO02",
                          "MADURBAN12", "MADURBAN11", "MADURBAN13", "URBAN06", "MADURBAN31", "MADURBAN30",
                          "EXPANDEDTERROR24")}
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot7_scen.py", PS.sha("tools/collapse_pilot7_scen.py")))


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
