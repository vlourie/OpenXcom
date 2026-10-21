#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, пятнадцатая партия: блоки с деревьями без порога 20+ частей выше z0 (cand15, по максимуму).

Слово Vitali 21.10 «делай по максимуму»: все целые блоки из сейвов переписи, которых нет в пилотах 4-14, без
порога 20+ частей (он был для зданий; у леса 1-3 дерева). Фильтры партий 10-14: базы, корабли, пещеры, Марс нет,
разметка без сомнений, под M0j5 на целом ничего не висит, скалы и земляной массы нет. Листы видов
scratchpad cp16/kinds15_1..9.png (257 видов, 21.10): мебель, декор, баки, леса, растения стоят на полу своей
клетки; масса - скальные откосы BRAINFOREST00, холмы ISLANDURBAN08, скалы U_PLANET_VOID, ICEKING_VILLAGE_W_00 -
не взята. Одноимённые с той же моделью, что уже в пилоте, не берутся; с другой - имя ТЕРРЕЙН/БЛОК (NAME_AS).
Отбор - scratchpad cp16/cand15.py, kinds15.py, gen15.py, dup15.py, mk15.py. Модель M0j5 (collapse_v8) с веткой D;
частичные - сценарии деревьев (collapse_partial15_scen, как 9-13). Блоки без деревьев - партия 16.

    py -3.13 tools\collapse_pilot15_scen.py define   census/collapse/pilot15/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot15"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('COMRCURBAN', 'COMRCURBAN02', 'городской блок COMRCURBAN/COMRCURBAN02', 'comrcurban02'),
    ('COMRCURBAN', 'COMRCURBAN31', 'городской блок COMRCURBAN/COMRCURBAN31', 'comrcurban31'),
    ('COMRCURBAN', 'COMRCURBAN32', 'городской блок COMRCURBAN/COMRCURBAN32', 'comrcurban32'),
    ('COMRCURBAN', 'COMRCURBAN39', 'городской блок COMRCURBAN/COMRCURBAN39', 'comrcurban39'),
    ('COMRCURBAN', 'COMRCURBAN44', 'городской блок COMRCURBAN/COMRCURBAN44', 'comrcurban44'),
    ('COMRCURBAN', 'COMRCURBAN55', 'городской блок COMRCURBAN/COMRCURBAN55', 'comrcurban55'),
    ('ISLANDURBAN', 'ISLANDURBAN12', 'городской блок ISLANDURBAN/ISLANDURBAN12', 'islandurban12'),
    ('ISLANDURBAN', 'ISLANDURBAN13', 'городской блок ISLANDURBAN/ISLANDURBAN13', 'islandurban13'),
    ('ISLANDURBAN', 'ISLANDURBAN14', 'городской блок ISLANDURBAN/ISLANDURBAN14', 'islandurban14'),
    ('URBANJUNKUFO', 'URBANJUNK17', 'городской блок URBANJUNKUFO/URBANJUNK17', 'urbanjunkufourbanjunk17'),
    ('URBANJUNKUFO', 'URBANJUNK20', 'городской блок URBANJUNKUFO/URBANJUNK20', 'urbanjunkufourbanjunk20'),
    ('URBANJUNKUFO', 'URBANJUNK27', 'городской блок URBANJUNKUFO/URBANJUNK27', 'urbanjunk27'),
    ('URBANJUNKUFO', 'URBANJUNK35', 'городской блок URBANJUNKUFO/URBANJUNK35', 'urbanjunkufourbanjunk35'),
    ('URBANJUNKUFO', 'URBANJUNK37', 'городской блок URBANJUNKUFO/URBANJUNK37', 'urbanjunk37'),
    ('URBANJUNKUFO', 'URBANJUNK45', 'городской блок URBANJUNKUFO/URBANJUNK45', 'urbanjunkufourbanjunk45'),
    ('URBANJUNKUFO', 'URBANJUNK_ROAD_01c', 'городской блок URBANJUNKUFO/URBANJUNK_ROAD_01c', 'urbanjunkufourbanjunkroad01c'),
    ('URBANJUNKUFO', 'URBANJUNK_ROAD_01d', 'городской блок URBANJUNKUFO/URBANJUNK_ROAD_01d', 'urbanjunkufourbanjunkroad01d'),
    ('URBANJUNKWOODUFO', 'URBANJUNK17', 'городской блок URBANJUNKWOODUFO/URBANJUNK17', 'urbanjunkwoodufourbanjunk17'),
    ('URBANJUNKWOODUFO', 'URBANJUNK20', 'городской блок URBANJUNKWOODUFO/URBANJUNK20', 'urbanjunkwoodufourbanjunk20'),
    ('URBANJUNKWOODUFO', 'URBANJUNK24', 'городской блок URBANJUNKWOODUFO/URBANJUNK24', 'urbanjunk24'),
    ('URBANJUNKWOODUFO', 'URBANJUNK35', 'городской блок URBANJUNKWOODUFO/URBANJUNK35', 'urbanjunkwoodufourbanjunk35'),
    ('URBANJUNKWOODUFO', 'URBANJUNK45', 'городской блок URBANJUNKWOODUFO/URBANJUNK45', 'urbanjunkwoodufourbanjunk45'),
    ('URBANJUNKWOODUFO', 'URBANJUNK_ROAD_01c', 'городской блок URBANJUNKWOODUFO/URBANJUNK_ROAD_01c', 'urbanjunkwoodufourbanjunkroad01c'),
    ('URBANJUNKWOODUFO', 'URBANJUNK_ROAD_01d', 'городской блок URBANJUNKWOODUFO/URBANJUNK_ROAD_01d', 'urbanjunkwoodufourbanjunkroad01d'),
    ('WESTOWN_GRASS', 'WESTOWN_21', 'городской блок WESTOWN_GRASS/WESTOWN_21', 'westowngrasswestown21'),
    ('WESTOWN_ROCKY', 'WESTOWN_21', 'городской блок WESTOWN_ROCKY/WESTOWN_21', 'westownrockywestown21'),
    ('WESTOWN_WASTE', 'WESTOWN_21', 'городской блок WESTOWN_WASTE/WESTOWN_21', 'westownwastewestown21'),
    ('CANYON_OF_DEATH', 'PLAINS06', 'природный блок CANYON_OF_DEATH/PLAINS06', 'canyonofdeathplains06'),
    ('CANYON_OF_DEATH', 'PLAINS07', 'природный блок CANYON_OF_DEATH/PLAINS07', 'canyonofdeathplains07'),
    ('CANYON_OF_DEATH', 'PLAINS08', 'природный блок CANYON_OF_DEATH/PLAINS08', 'canyonofdeathplains08'),
    ('CANYON_OF_DEATH', 'PLAINS09', 'природный блок CANYON_OF_DEATH/PLAINS09', 'canyonofdeathplains09'),
    ('CANYON_OF_DEATH', 'PLAINS10', 'природный блок CANYON_OF_DEATH/PLAINS10', 'canyonofdeathplains10'),
    ('FOREST', 'FOREST10', 'природный блок FOREST/FOREST10', 'forestforest10'),
    ('FOREST2BLACK', 'FOREST10', 'природный блок FOREST2BLACK/FOREST10', 'forest2blackforest10'),
    ('FORESTRED', 'FINNIKFOREST03', 'природный блок FORESTRED/FINNIKFOREST03', 'forestredfinnikforest03'),
    ('FORESTRED', 'FOREST05', 'природный блок FORESTRED/FOREST05', 'forestredforest05'),
    ('FORESTRED', 'FOREST10', 'природный блок FORESTRED/FOREST10', 'forestredforest10'),
    ('FORESTRED', 'SOLFOREST12', 'природный блок FORESTRED/SOLFOREST12', 'forestredsolforest12'),
    ('FORESTSNOW', 'FOREST10', 'природный блок FORESTSNOW/FOREST10', 'forestsnowforest10'),
    ('FORESTSWAMP', 'FORESTSWAMP10', 'природный блок FORESTSWAMP/FORESTSWAMP10', 'forestswampforestswamp10'),
    ('FORESTSWAMP', 'FORESTSWAMP14', 'природный блок FORESTSWAMP/FORESTSWAMP14', 'forestswamp14'),
    ('FORESTSWAMP_WASTE', 'FOREST10', 'природный блок FORESTSWAMP_WASTE/FOREST10', 'forestswampwasteforest10'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP10', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP10', 'forestswampwasteforestswamp10'),
    ('JUNGLE', 'JUNGLE03', 'природный блок JUNGLE/JUNGLE03', 'junglejungle03'),
    ('JUNGLE', 'JUNGLE04', 'природный блок JUNGLE/JUNGLE04', 'junglejungle04'),
    ('JUNGLE', 'JUNGLE05', 'природный блок JUNGLE/JUNGLE05', 'junglejungle05'),
    ('JUNGLE', 'JUNGLE06', 'природный блок JUNGLE/JUNGLE06', 'junglejungle06'),
    ('JUNGLE', 'JUNGLE07', 'природный блок JUNGLE/JUNGLE07', 'junglejungle07'),
    ('JUNGLE', 'JUNGLE08', 'природный блок JUNGLE/JUNGLE08', 'junglejungle08'),
    ('JUNGLE', 'JUNGLE09', 'природный блок JUNGLE/JUNGLE09', 'junglejungle09'),
    ('JUNGLE', 'JUNGLESOL01', 'природный блок JUNGLE/JUNGLESOL01', 'junglejunglesol01'),
    ('JUNGLE', 'JUNGLESOL02', 'природный блок JUNGLE/JUNGLESOL02', 'junglejunglesol02'),
    ('JUNGLE2BLACK', 'JUNGLE03', 'природный блок JUNGLE2BLACK/JUNGLE03', 'jungle2blackjungle03'),
    ('JUNGLE2BLACK', 'JUNGLE04', 'природный блок JUNGLE2BLACK/JUNGLE04', 'jungle2blackjungle04'),
    ('JUNGLE2BLACK', 'JUNGLE05', 'природный блок JUNGLE2BLACK/JUNGLE05', 'jungle2blackjungle05'),
    ('JUNGLE2BLACK', 'JUNGLE06', 'природный блок JUNGLE2BLACK/JUNGLE06', 'jungle2blackjungle06'),
    ('JUNGLE2BLACK', 'JUNGLE07', 'природный блок JUNGLE2BLACK/JUNGLE07', 'jungle2blackjungle07'),
    ('JUNGLE2BLACK', 'JUNGLE08', 'природный блок JUNGLE2BLACK/JUNGLE08', 'jungle2blackjungle08'),
    ('JUNGLE2BLACK', 'JUNGLE09', 'природный блок JUNGLE2BLACK/JUNGLE09', 'jungle2blackjungle09'),
    ('JUNGLE2BLACK', 'JUNGLESOL01', 'природный блок JUNGLE2BLACK/JUNGLESOL01', 'jungle2blackjunglesol01'),
    ('JUNGLE2BLACK', 'JUNGLESOL02', 'природный блок JUNGLE2BLACK/JUNGLESOL02', 'jungle2blackjunglesol02'),
    ('JUNGLE2NEO', 'JUNGLE03', 'природный блок JUNGLE2NEO/JUNGLE03', 'jungle2neojungle03'),
    ('JUNGLE2NEO', 'JUNGLE04', 'природный блок JUNGLE2NEO/JUNGLE04', 'jungle2neojungle04'),
    ('JUNGLE2NEO', 'JUNGLE05', 'природный блок JUNGLE2NEO/JUNGLE05', 'jungle2neojungle05'),
    ('JUNGLE2NEO', 'JUNGLE06', 'природный блок JUNGLE2NEO/JUNGLE06', 'jungle2neojungle06'),
    ('JUNGLE2NEO', 'JUNGLE07', 'природный блок JUNGLE2NEO/JUNGLE07', 'jungle2neojungle07'),
    ('JUNGLE2NEO', 'JUNGLE08', 'природный блок JUNGLE2NEO/JUNGLE08', 'jungle2neojungle08'),
    ('JUNGLE2NEO', 'JUNGLE09', 'природный блок JUNGLE2NEO/JUNGLE09', 'jungle2neojungle09'),
    ('JUNGLE2NEO', 'JUNGLESOL01', 'природный блок JUNGLE2NEO/JUNGLESOL01', 'jungle2neojunglesol01'),
    ('JUNGLE2NEO', 'JUNGLESOL02', 'природный блок JUNGLE2NEO/JUNGLESOL02', 'jungle2neojunglesol02'),
    ('JUNGLESTYX', 'JUNGLE03', 'природный блок JUNGLESTYX/JUNGLE03', 'junglestyxjungle03'),
    ('JUNGLESTYX', 'JUNGLE04', 'природный блок JUNGLESTYX/JUNGLE04', 'junglestyxjungle04'),
    ('JUNGLESTYX', 'JUNGLE05', 'природный блок JUNGLESTYX/JUNGLE05', 'junglestyxjungle05'),
    ('JUNGLESTYX', 'JUNGLE06', 'природный блок JUNGLESTYX/JUNGLE06', 'junglestyxjungle06'),
    ('JUNGLESTYX', 'JUNGLE07', 'природный блок JUNGLESTYX/JUNGLE07', 'junglestyxjungle07'),
    ('JUNGLESTYX', 'JUNGLE08', 'природный блок JUNGLESTYX/JUNGLE08', 'junglestyxjungle08'),
    ('JUNGLESTYX', 'JUNGLE09', 'природный блок JUNGLESTYX/JUNGLE09', 'junglestyxjungle09'),
    ('JUNGLESTYX', 'JUNGLESOL01', 'природный блок JUNGLESTYX/JUNGLESOL01', 'junglestyxjunglesol01'),
    ('JUNGLESTYX', 'JUNGLESOL02', 'природный блок JUNGLESTYX/JUNGLESOL02', 'junglestyxjunglesol02'),
    ('JUNGLETEMPLE', 'MUJUNGLE06', 'природный блок JUNGLETEMPLE/MUJUNGLE06', 'mujungle06'),
    ('JUNGLETEMPLE', 'MUJUNGLE16', 'природный блок JUNGLETEMPLE/MUJUNGLE16', 'jungletemplemujungle16'),
    ('JUNGLETEMPLE_2', 'MUJUNGLE16', 'природный блок JUNGLETEMPLE_2/MUJUNGLE16', 'jungletemple2mujungle16'),
    ('JUNGLETEMPLE_2', 'MUJUNGLE_ROAD_SN01', 'природный блок JUNGLETEMPLE_2/MUJUNGLE_ROAD_SN01', 'mujungleroadsn01'),
    ('JUNGLETEMPLE_2', 'MUJUNGLE_ROAD_SN02', 'природный блок JUNGLETEMPLE_2/MUJUNGLE_ROAD_SN02', 'mujungleroadsn02'),
    ('STYXSWAMP', 'FORESTSWAMPSHORE_W02', 'природный блок STYXSWAMP/FORESTSWAMPSHORE_W02', 'forestswampshorew02'),
    ('STYXSWAMP', 'FORESTSWAMPSHORE_W03', 'природный блок STYXSWAMP/FORESTSWAMPSHORE_W03', 'forestswampshorew03'),
    ('STYXSWAMP', 'FORESTSWAMPSHORE_W04', 'природный блок STYXSWAMP/FORESTSWAMPSHORE_W04', 'forestswampshorew04'),
    ('WESTOWN_GRASS', 'PLAINS06', 'природный блок WESTOWN_GRASS/PLAINS06', 'westowngrassplains06'),
    ('WESTOWN_GRASS', 'PLAINS07', 'природный блок WESTOWN_GRASS/PLAINS07', 'westowngrassplains07'),
    ('WESTOWN_GRASS', 'PLAINS08', 'природный блок WESTOWN_GRASS/PLAINS08', 'westowngrassplains08'),
    ('WESTOWN_GRASS', 'PLAINS10', 'природный блок WESTOWN_GRASS/PLAINS10', 'westowngrassplains10'),
    ('WESTOWN_ROCKY', 'PLAINS06', 'природный блок WESTOWN_ROCKY/PLAINS06', 'westownrockyplains06'),
    ('WESTOWN_ROCKY', 'PLAINS07', 'природный блок WESTOWN_ROCKY/PLAINS07', 'westownrockyplains07'),
    ('WESTOWN_ROCKY', 'PLAINS08', 'природный блок WESTOWN_ROCKY/PLAINS08', 'westownrockyplains08'),
    ('WESTOWN_ROCKY', 'PLAINS09', 'природный блок WESTOWN_ROCKY/PLAINS09', 'westownrockyplains09'),
    ('WESTOWN_ROCKY', 'PLAINS10', 'природный блок WESTOWN_ROCKY/PLAINS10', 'westownrockyplains10'),
    ('WESTOWN_ROCKY', 'PLAINS12', 'природный блок WESTOWN_ROCKY/PLAINS12', 'plains12'),
    ('WESTOWN_WASTE', 'PLAINS06', 'природный блок WESTOWN_WASTE/PLAINS06', 'westownwasteplains06'),
    ('WESTOWN_WASTE', 'PLAINS07', 'природный блок WESTOWN_WASTE/PLAINS07', 'westownwasteplains07'),
    ('WESTOWN_WASTE', 'PLAINS08', 'природный блок WESTOWN_WASTE/PLAINS08', 'westownwasteplains08'),
    ('WESTOWN_WASTE', 'PLAINS09', 'природный блок WESTOWN_WASTE/PLAINS09', 'westownwasteplains09'),
    ('WESTOWN_WASTE', 'PLAINS10', 'природный блок WESTOWN_WASTE/PLAINS10', 'westownwasteplains10'),
    ('WESTOWN_WASTE', 'PLAINS11', 'природный блок WESTOWN_WASTE/PLAINS11', 'plains11'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок URBANJUNKUFO/URBANJUNK27': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK37': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK24': (20, 20),
    'природный блок FOREST/FOREST10': (20, 20),
    'природный блок FOREST2BLACK/FOREST10': (20, 20),
    'природный блок FORESTRED/FOREST10': (20, 20),
    'природный блок FORESTSNOW/FOREST10': (20, 20),
    'природный блок FORESTSWAMP/FORESTSWAMP10': (20, 20),
    'природный блок FORESTSWAMP_WASTE/FOREST10': (20, 20),
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP10': (20, 20),
    'природный блок WESTOWN_ROCKY/PLAINS12': (20, 20),
    'природный блок WESTOWN_WASTE/PLAINS11': (20, 20),
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
    'городской блок URBANJUNKUFO/URBANJUNK17': 'URBANJUNKUFO/URBANJUNK17',
    'городской блок URBANJUNKUFO/URBANJUNK20': 'URBANJUNKUFO/URBANJUNK20',
    'городской блок URBANJUNKUFO/URBANJUNK35': 'URBANJUNKUFO/URBANJUNK35',
    'городской блок URBANJUNKUFO/URBANJUNK45': 'URBANJUNKUFO/URBANJUNK45',
    'городской блок URBANJUNKUFO/URBANJUNK_ROAD_01c': 'URBANJUNKUFO/URBANJUNK_ROAD_01c',
    'городской блок URBANJUNKUFO/URBANJUNK_ROAD_01d': 'URBANJUNKUFO/URBANJUNK_ROAD_01d',
    'городской блок URBANJUNKWOODUFO/URBANJUNK17': 'URBANJUNKWOODUFO/URBANJUNK17',
    'городской блок URBANJUNKWOODUFO/URBANJUNK20': 'URBANJUNKWOODUFO/URBANJUNK20',
    'городской блок URBANJUNKWOODUFO/URBANJUNK35': 'URBANJUNKWOODUFO/URBANJUNK35',
    'городской блок URBANJUNKWOODUFO/URBANJUNK45': 'URBANJUNKWOODUFO/URBANJUNK45',
    'городской блок URBANJUNKWOODUFO/URBANJUNK_ROAD_01c': 'URBANJUNKWOODUFO/URBANJUNK_ROAD_01c',
    'городской блок URBANJUNKWOODUFO/URBANJUNK_ROAD_01d': 'URBANJUNKWOODUFO/URBANJUNK_ROAD_01d',
    'городской блок WESTOWN_GRASS/WESTOWN_21': 'WESTOWN_GRASS/WESTOWN_21',
    'городской блок WESTOWN_ROCKY/WESTOWN_21': 'WESTOWN_ROCKY/WESTOWN_21',
    'городской блок WESTOWN_WASTE/WESTOWN_21': 'WESTOWN_WASTE/WESTOWN_21',
    'природный блок CANYON_OF_DEATH/PLAINS06': 'CANYON_OF_DEATH/PLAINS06',
    'природный блок CANYON_OF_DEATH/PLAINS07': 'CANYON_OF_DEATH/PLAINS07',
    'природный блок CANYON_OF_DEATH/PLAINS08': 'CANYON_OF_DEATH/PLAINS08',
    'природный блок CANYON_OF_DEATH/PLAINS09': 'CANYON_OF_DEATH/PLAINS09',
    'природный блок CANYON_OF_DEATH/PLAINS10': 'CANYON_OF_DEATH/PLAINS10',
    'природный блок FOREST/FOREST10': 'FOREST/FOREST10',
    'природный блок FOREST2BLACK/FOREST10': 'FOREST2BLACK/FOREST10',
    'природный блок FORESTRED/FINNIKFOREST03': 'FORESTRED/FINNIKFOREST03',
    'природный блок FORESTRED/FOREST05': 'FORESTRED/FOREST05',
    'природный блок FORESTRED/FOREST10': 'FORESTRED/FOREST10',
    'природный блок FORESTRED/SOLFOREST12': 'FORESTRED/SOLFOREST12',
    'природный блок FORESTSNOW/FOREST10': 'FORESTSNOW/FOREST10',
    'природный блок FORESTSWAMP/FORESTSWAMP10': 'FORESTSWAMP/FORESTSWAMP10',
    'природный блок FORESTSWAMP_WASTE/FOREST10': 'FORESTSWAMP_WASTE/FOREST10',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP10': 'FORESTSWAMP_WASTE/FORESTSWAMP10',
    'природный блок JUNGLE/JUNGLE03': 'JUNGLE/JUNGLE03',
    'природный блок JUNGLE/JUNGLE04': 'JUNGLE/JUNGLE04',
    'природный блок JUNGLE/JUNGLE05': 'JUNGLE/JUNGLE05',
    'природный блок JUNGLE/JUNGLE06': 'JUNGLE/JUNGLE06',
    'природный блок JUNGLE/JUNGLE07': 'JUNGLE/JUNGLE07',
    'природный блок JUNGLE/JUNGLE08': 'JUNGLE/JUNGLE08',
    'природный блок JUNGLE/JUNGLE09': 'JUNGLE/JUNGLE09',
    'природный блок JUNGLE/JUNGLESOL01': 'JUNGLE/JUNGLESOL01',
    'природный блок JUNGLE/JUNGLESOL02': 'JUNGLE/JUNGLESOL02',
    'природный блок JUNGLE2BLACK/JUNGLE03': 'JUNGLE2BLACK/JUNGLE03',
    'природный блок JUNGLE2BLACK/JUNGLE04': 'JUNGLE2BLACK/JUNGLE04',
    'природный блок JUNGLE2BLACK/JUNGLE05': 'JUNGLE2BLACK/JUNGLE05',
    'природный блок JUNGLE2BLACK/JUNGLE06': 'JUNGLE2BLACK/JUNGLE06',
    'природный блок JUNGLE2BLACK/JUNGLE07': 'JUNGLE2BLACK/JUNGLE07',
    'природный блок JUNGLE2BLACK/JUNGLE08': 'JUNGLE2BLACK/JUNGLE08',
    'природный блок JUNGLE2BLACK/JUNGLE09': 'JUNGLE2BLACK/JUNGLE09',
    'природный блок JUNGLE2BLACK/JUNGLESOL01': 'JUNGLE2BLACK/JUNGLESOL01',
    'природный блок JUNGLE2BLACK/JUNGLESOL02': 'JUNGLE2BLACK/JUNGLESOL02',
    'природный блок JUNGLE2NEO/JUNGLE03': 'JUNGLE2NEO/JUNGLE03',
    'природный блок JUNGLE2NEO/JUNGLE04': 'JUNGLE2NEO/JUNGLE04',
    'природный блок JUNGLE2NEO/JUNGLE05': 'JUNGLE2NEO/JUNGLE05',
    'природный блок JUNGLE2NEO/JUNGLE06': 'JUNGLE2NEO/JUNGLE06',
    'природный блок JUNGLE2NEO/JUNGLE07': 'JUNGLE2NEO/JUNGLE07',
    'природный блок JUNGLE2NEO/JUNGLE08': 'JUNGLE2NEO/JUNGLE08',
    'природный блок JUNGLE2NEO/JUNGLE09': 'JUNGLE2NEO/JUNGLE09',
    'природный блок JUNGLE2NEO/JUNGLESOL01': 'JUNGLE2NEO/JUNGLESOL01',
    'природный блок JUNGLE2NEO/JUNGLESOL02': 'JUNGLE2NEO/JUNGLESOL02',
    'природный блок JUNGLESTYX/JUNGLE03': 'JUNGLESTYX/JUNGLE03',
    'природный блок JUNGLESTYX/JUNGLE04': 'JUNGLESTYX/JUNGLE04',
    'природный блок JUNGLESTYX/JUNGLE05': 'JUNGLESTYX/JUNGLE05',
    'природный блок JUNGLESTYX/JUNGLE06': 'JUNGLESTYX/JUNGLE06',
    'природный блок JUNGLESTYX/JUNGLE07': 'JUNGLESTYX/JUNGLE07',
    'природный блок JUNGLESTYX/JUNGLE08': 'JUNGLESTYX/JUNGLE08',
    'природный блок JUNGLESTYX/JUNGLE09': 'JUNGLESTYX/JUNGLE09',
    'природный блок JUNGLESTYX/JUNGLESOL01': 'JUNGLESTYX/JUNGLESOL01',
    'природный блок JUNGLESTYX/JUNGLESOL02': 'JUNGLESTYX/JUNGLESOL02',
    'природный блок JUNGLETEMPLE/MUJUNGLE16': 'JUNGLETEMPLE/MUJUNGLE16',
    'природный блок JUNGLETEMPLE_2/MUJUNGLE16': 'JUNGLETEMPLE_2/MUJUNGLE16',
    'природный блок WESTOWN_GRASS/PLAINS06': 'WESTOWN_GRASS/PLAINS06',
    'природный блок WESTOWN_GRASS/PLAINS07': 'WESTOWN_GRASS/PLAINS07',
    'природный блок WESTOWN_GRASS/PLAINS08': 'WESTOWN_GRASS/PLAINS08',
    'природный блок WESTOWN_GRASS/PLAINS10': 'WESTOWN_GRASS/PLAINS10',
    'природный блок WESTOWN_ROCKY/PLAINS06': 'WESTOWN_ROCKY/PLAINS06',
    'природный блок WESTOWN_ROCKY/PLAINS07': 'WESTOWN_ROCKY/PLAINS07',
    'природный блок WESTOWN_ROCKY/PLAINS08': 'WESTOWN_ROCKY/PLAINS08',
    'природный блок WESTOWN_ROCKY/PLAINS09': 'WESTOWN_ROCKY/PLAINS09',
    'природный блок WESTOWN_ROCKY/PLAINS10': 'WESTOWN_ROCKY/PLAINS10',
    'природный блок WESTOWN_WASTE/PLAINS06': 'WESTOWN_WASTE/PLAINS06',
    'природный блок WESTOWN_WASTE/PLAINS07': 'WESTOWN_WASTE/PLAINS07',
    'природный блок WESTOWN_WASTE/PLAINS08': 'WESTOWN_WASTE/PLAINS08',
    'природный блок WESTOWN_WASTE/PLAINS09': 'WESTOWN_WASTE/PLAINS09',
    'природный блок WESTOWN_WASTE/PLAINS10': 'WESTOWN_WASTE/PLAINS10',
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot15_scen.py", PS.sha("tools/collapse_pilot15_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v8 as E
    E.install()                                   # M0j5, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
