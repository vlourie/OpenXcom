#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, двадцать третья партия: блоки без деревьев из того же отбора, что партия 22 (cand22).

Слово Vitali 27.10 «продолжай» (охват): бои переписи gen22 (зёрна 49-64) на террейнах с кандидатами без целого
размещения, в том числе из скриптов карт (вилла мага, Зимний дворец, детектив, Коралловый остров, Рагнарёк) и
текстуры глобуса; все новые целые блоки, которых нет в пилотах 0-21. Фильтры партий 10-21: базы, корабли, пещеры
и подземелье CRYPTEK, Марс нет, разметка без сомнений, под M0j5 на целом ничего не висит, скалы и земляной массы
нет. Листы видов scratchpad cp24/kinds22_1..3.png (80 видов, 27.10): мебель, казармы, лестницы, декор стоят на
полу; масса - кладка Белого замка WHITECASTLE_02 и стен Зимнего дворца WINTERWALL00/01 - не взята. Одноимённые
с другой моделью - имя ТЕРРЕЙН/БЛОК (NAME_AS). Отбор - scratchpad cp24/cand22.py, kinds22.py, pick22.py, dup22.py,
mk23.py. Модель M0j5 (collapse_v8); частичные - PFALL зданий (collapse_partial23_scen, как 20).

    py -3.13 tools\collapse_pilot23_scen.py define   census/collapse/pilot23/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot23"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('ASYLUM_FENCE', 'ASYLUM_FENCE_W03', 'городской блок ASYLUM_FENCE/ASYLUM_FENCE_W03', 'asylumfencew03'),
    ('CHEMTOWN', 'CHEMTOWN02', 'городской блок CHEMTOWN/CHEMTOWN02', 'chemtown02'),
    ('CHEMTOWNHOTPURSUITS', 'CHEMTOWN01B', 'городской блок CHEMTOWNHOTPURSUITS/CHEMTOWN01B', 'chemtown01b'),
    ('CULTA_PP', 'CULTA19', 'городской блок CULTA_PP/CULTA19', 'cultappculta19'),
    ('DESERTX', 'DESERTHUGE00', 'городской блок DESERTX/DESERTHUGE00', 'deserthuge00'),
    ('INDUSTRIALSLUM', 'INDUSTRIALSLUM13', 'городской блок INDUSTRIALSLUM/INDUSTRIALSLUM13', 'industrialslum13'),
    ('RURAL', 'VILBAN11', 'городской блок RURAL/VILBAN11', 'vilban11'),
    ('URBAN', 'EXPANDEDTERROR21', 'городской блок URBAN/EXPANDEDTERROR21', 'expandedterror21'),
    ('URBANWAR', 'EXPANDEDTERROR26', 'городской блок URBANWAR/EXPANDEDTERROR26', 'expandedterror26'),
    ('URBANWAR', 'MADURBAN12', 'городской блок URBANWAR/MADURBAN12', 'urbanwarmadurban12'),
    ('URBANWAR', 'URBAN08', 'городской блок URBANWAR/URBAN08', 'urbanwarurban08'),
    ('URBAN_WASTE', 'URBANWASTE57', 'городской блок URBAN_WASTE/URBANWASTE57', 'urbanwaste57'),
    ('WINTER_WALL', 'WINTERWALL02', 'городской блок WINTER_WALL/WINTERWALL02', 'winterwall02'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок DESERTX/DESERTHUGE00': (30, 30),
    'городской блок RURAL/VILBAN11': (20, 20),
    'городской блок URBAN/EXPANDEDTERROR21': (20, 20),
    'городской блок URBANWAR/EXPANDEDTERROR26': (20, 20),
    'городской блок URBANWAR/MADURBAN12': (20, 20),
    'городской блок URBANWAR/URBAN08': (20, 20),
    'городской блок URBAN_WASTE/URBANWASTE57': (20, 20),
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
    'городской блок CULTA_PP/CULTA19': 'CULTA_PP/CULTA19',
    'городской блок URBANWAR/MADURBAN12': 'URBANWAR/MADURBAN12',
    'городской блок URBANWAR/URBAN08': 'URBANWAR/URBAN08',
}


def load():
    """Как collapse_pilot9_scen.load: целые блоки карт своего террейна (collapse_census.all_blocks)."""
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot23_scen.py", PS.sha("tools/collapse_pilot23_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v8 as E
    E.install()                                   # M0j5, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
