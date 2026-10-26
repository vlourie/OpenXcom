#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, девятнадцатая партия: блоки с деревьями из боёв переписи партии 19 (cand19, охват).

Слово Vitali 23.10 «Охват»: бои переписи на террейнах с кандидатами без целого размещения (зёрна 33-48, миссии,
где террейн ещё не поднимали), все целые блоки, которых нет в пилотах 4-18. Фильтры партий 10-18: базы, корабли,
пещеры, Марс нет, разметка без сомнений, под M0j5 на целом ничего не висит, скалы и земляной массы нет. Листы видов
scratchpad cp23/kinds19_1..3.png (82 вида, 23.10): мебель, ящики, декор, колонны стоят на полу; масса - кладка
храма ATLANTDESERT без пола, откосы FORESTBITSWASTE:10/14, холмы ISLANDURBAN2, скалы ISLANDURBAN3 - не взята.
Одноимённые с той же моделью, что уже в пилоте, не берутся; с другой - имя ТЕРРЕЙН/БЛОК (NAME_AS). Отбор -
scratchpad cp23/cand19.py, kinds19.py, pick19.py, dup19.py, mk19.py. Модель M0j5 (collapse_v8) с веткой D;
частичные - сценарии деревьев (collapse_partial19_scen, как 17). Блоки без деревьев - партия 20.

    py -3.13 tools\collapse_pilot19_scen.py define   census/collapse/pilot19/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot19"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('URBANJUNKUFO', 'URBANJUNK02', 'городской блок URBANJUNKUFO/URBANJUNK02', 'urbanjunkufourbanjunk02'),
    ('URBANJUNKUFO', 'URBANJUNK04', 'городской блок URBANJUNKUFO/URBANJUNK04', 'urbanjunkufourbanjunk04'),
    ('URBANJUNKUFO', 'URBANJUNK22', 'городской блок URBANJUNKUFO/URBANJUNK22', 'urbanjunkufourbanjunk22'),
    ('URBANJUNKUFO', 'URBANJUNK24', 'городской блок URBANJUNKUFO/URBANJUNK24', 'urbanjunkufourbanjunk24'),
    ('URBANJUNKUFO', 'URBANJUNK41', 'городской блок URBANJUNKUFO/URBANJUNK41', 'urbanjunkufourbanjunk41'),
    ('URBANJUNKUFO', 'URBANJUNK43', 'городской блок URBANJUNKUFO/URBANJUNK43', 'urbanjunk43'),
    ('URBANJUNKUFO', 'URBANJUNK46', 'городской блок URBANJUNKUFO/URBANJUNK46', 'urbanjunkufourbanjunk46'),
    ('URBANJUNKUFO', 'URBANJUNKDIO_07', 'городской блок URBANJUNKUFO/URBANJUNKDIO_07', 'urbanjunkufourbanjunkdio07'),
    ('URBANJUNKWOODUFO', 'URBANJUNK27', 'городской блок URBANJUNKWOODUFO/URBANJUNK27', 'urbanjunkwoodufourbanjunk27'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP20', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP20', 'forestswampwasteforestswamp20'),
    ('FORESTSWAMP_WASTE', 'FOREST_ROAD_SN00', 'природный блок FORESTSWAMP_WASTE/FOREST_ROAD_SN00', 'forestswampwasteforestroadsn00'),
    ('FORESTSWAMP_WASTE', 'FOREST_ROAD_SN01', 'природный блок FORESTSWAMP_WASTE/FOREST_ROAD_SN01', 'forestswampwasteforestroadsn01'),
    ('FORESTSWAMP_WASTE', 'FOREST_ROAD_SN02', 'природный блок FORESTSWAMP_WASTE/FOREST_ROAD_SN02', 'forestswampwasteforestroadsn02'),
    ('JUNGLETEMPLE', 'MUJUNGLE_ROAD_SN01', 'природный блок JUNGLETEMPLE/MUJUNGLE_ROAD_SN01', 'jungletemplemujungleroadsn01'),
    ('JUNGLETEMPLE', 'MUJUNGLE_ROAD_SN02', 'природный блок JUNGLETEMPLE/MUJUNGLE_ROAD_SN02', 'jungletemplemujungleroadsn02'),
    ('PLAINS_ARBOREAL', 'PLAINSSOLHUGE00', 'природный блок PLAINS_ARBOREAL/PLAINSSOLHUGE00', 'plainsarborealplainssolhuge00'),
    ('PLAINS_DEAD', 'PLAINS12', 'природный блок PLAINS_DEAD/PLAINS12', 'plainsdeadplains12'),
    ('PLAINS_ERODED', 'PLAINSSOLHUGE00', 'природный блок PLAINS_ERODED/PLAINSSOLHUGE00', 'plainserodedplainssolhuge00'),
    ('PLAINS_TROPICAL', 'PLAINSSOLHUGE00', 'природный блок PLAINS_TROPICAL/PLAINSSOLHUGE00', 'plainstropicalplainssolhuge00'),
    ('STYXSWAMP', 'FORESTSWAMP18', 'природный блок STYXSWAMP/FORESTSWAMP18', 'styxswampforestswamp18'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок URBANJUNKUFO/URBANJUNK22': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK24': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK41': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK43': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK27': (20, 20),
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP20': (20, 20),
    'природный блок PLAINS_ARBOREAL/PLAINSSOLHUGE00': (30, 30),
    'природный блок PLAINS_DEAD/PLAINS12': (20, 20),
    'природный блок PLAINS_ERODED/PLAINSSOLHUGE00': (30, 30),
    'природный блок PLAINS_TROPICAL/PLAINSSOLHUGE00': (30, 30),
    'природный блок STYXSWAMP/FORESTSWAMP18': (20, 20),
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
    'городской блок URBANJUNKUFO/URBANJUNK02': 'URBANJUNKUFO/URBANJUNK02',
    'городской блок URBANJUNKUFO/URBANJUNK04': 'URBANJUNKUFO/URBANJUNK04',
    'городской блок URBANJUNKUFO/URBANJUNK22': 'URBANJUNKUFO/URBANJUNK22',
    'городской блок URBANJUNKUFO/URBANJUNK24': 'URBANJUNKUFO/URBANJUNK24',
    'городской блок URBANJUNKUFO/URBANJUNK41': 'URBANJUNKUFO/URBANJUNK41',
    'городской блок URBANJUNKUFO/URBANJUNK46': 'URBANJUNKUFO/URBANJUNK46',
    'городской блок URBANJUNKUFO/URBANJUNKDIO_07': 'URBANJUNKUFO/URBANJUNKDIO_07',
    'городской блок URBANJUNKWOODUFO/URBANJUNK27': 'URBANJUNKWOODUFO/URBANJUNK27',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP20': 'FORESTSWAMP_WASTE/FORESTSWAMP20',
    'природный блок FORESTSWAMP_WASTE/FOREST_ROAD_SN00': 'FORESTSWAMP_WASTE/FOREST_ROAD_SN00',
    'природный блок FORESTSWAMP_WASTE/FOREST_ROAD_SN01': 'FORESTSWAMP_WASTE/FOREST_ROAD_SN01',
    'природный блок FORESTSWAMP_WASTE/FOREST_ROAD_SN02': 'FORESTSWAMP_WASTE/FOREST_ROAD_SN02',
    'природный блок JUNGLETEMPLE/MUJUNGLE_ROAD_SN01': 'JUNGLETEMPLE/MUJUNGLE_ROAD_SN01',
    'природный блок JUNGLETEMPLE/MUJUNGLE_ROAD_SN02': 'JUNGLETEMPLE/MUJUNGLE_ROAD_SN02',
    'природный блок PLAINS_ARBOREAL/PLAINSSOLHUGE00': 'PLAINS_ARBOREAL/PLAINSSOLHUGE00',
    'природный блок PLAINS_DEAD/PLAINS12': 'PLAINS_DEAD/PLAINS12',
    'природный блок PLAINS_ERODED/PLAINSSOLHUGE00': 'PLAINS_ERODED/PLAINSSOLHUGE00',
    'природный блок PLAINS_TROPICAL/PLAINSSOLHUGE00': 'PLAINS_TROPICAL/PLAINSSOLHUGE00',
    'природный блок STYXSWAMP/FORESTSWAMP18': 'STYXSWAMP/FORESTSWAMP18',
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot19_scen.py", PS.sha("tools/collapse_pilot19_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v8 as E
    E.install()                                   # M0j5, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
