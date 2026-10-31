#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, семнадцатая партия: блоки с деревьями из боёв переписи партии 17 (cand17, охват).

Слово Vitali 23.10 «Охват»: бои переписи на террейнах с участками, ни разу не встреченными целыми (зёрна 17-32),
все целые блоки, которых нет в пилотах 4-16. Фильтры партий 10-16: базы, корабли, пещеры, Марс нет, разметка без
сомнений, под M0j5 на целом ничего не висит, скалы и земляной массы нет. Листы видов scratchpad cp22/kinds17_1..2.png
(45 видов, 23.10): мебель, ящики, декор, кладка стоят на полу; масса - скальные откосы DESERTBITS:10 (DSRTREFI_08),
земляные откосы FORESTSWAMPBITS:10/14 (BRAINFOREST00) - не взята. Одноимённые с той же моделью, что уже в пилоте,
не берутся; с другой - имя ТЕРРЕЙН/БЛОК (NAME_AS). Отбор - scratchpad cp22/cand17.py, kinds17.py, pick17.py,
dup17.py, mk17.py. Модель M0j5 (collapse_v8) с веткой D; частичные - сценарии деревьев (collapse_partial17_scen,
как 15). Блоки без деревьев - партия 18.

    py -3.13 tools\collapse_pilot17_scen.py define   census/collapse/pilot17/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot17"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('URBANJUNKUFO', 'URBANJUNK05', 'городской блок URBANJUNKUFO/URBANJUNK05', 'urbanjunkufourbanjunk05'),
    ('URBANJUNKUFO', 'URBANJUNK08', 'городской блок URBANJUNKUFO/URBANJUNK08', 'urbanjunkufourbanjunk08'),
    ('URBANJUNKUFO', 'URBANJUNK38', 'городской блок URBANJUNKUFO/URBANJUNK38', 'urbanjunkufourbanjunk38'),
    ('URBANJUNKUFO', 'URBANJUNK40', 'городской блок URBANJUNKUFO/URBANJUNK40', 'urbanjunkufourbanjunk40'),
    ('URBANJUNKUFO', 'URBANJUNK42', 'городской блок URBANJUNKUFO/URBANJUNK42', 'urbanjunkufourbanjunk42'),
    ('URBANJUNKWOODUFO', 'URBANJUNK26', 'городской блок URBANJUNKWOODUFO/URBANJUNK26', 'urbanjunk26'),
    ('URBANJUNKWOODUFO', 'URBANJUNK28', 'городской блок URBANJUNKWOODUFO/URBANJUNK28', 'urbanjunk28'),
    ('URBANJUNKWOODUFO', 'URBANJUNK30', 'городской блок URBANJUNKWOODUFO/URBANJUNK30', 'urbanjunkwoodufourbanjunk30'),
    ('URBANJUNKWOODUFO', 'URBANJUNK37', 'городской блок URBANJUNKWOODUFO/URBANJUNK37', 'urbanjunkwoodufourbanjunk37'),
    ('URBANJUNKWOODUFO', 'URBANJUNKDIO_07', 'городской блок URBANJUNKWOODUFO/URBANJUNKDIO_07', 'urbanjunkdio07'),
    ('WESTOWN_TROPICAL', 'WESTOWN_21', 'городской блок WESTOWN_TROPICAL/WESTOWN_21', 'westowntropicalwestown21'),
    ('WESTOWN_TROPICAL', 'WESTOWN_22', 'городской блок WESTOWN_TROPICAL/WESTOWN_22', 'westown22'),
    ('FOREST2BLACK', 'SOLFORESTHUGE01', 'природный блок FOREST2BLACK/SOLFORESTHUGE01', 'forest2blacksolforesthuge01'),
    ('FORESTRED', 'FINNIKFOREST04', 'природный блок FORESTRED/FINNIKFOREST04', 'forestredfinnikforest04'),
    ('FORESTSWAMP', 'FORESTSWAMP00', 'природный блок FORESTSWAMP/FORESTSWAMP00', 'forestswampforestswamp00'),
    ('FORESTSWAMP', 'FORESTSWAMP06', 'природный блок FORESTSWAMP/FORESTSWAMP06', 'forestswampforestswamp06'),
    ('FORESTSWAMP', 'FORESTSWAMP16', 'природный блок FORESTSWAMP/FORESTSWAMP16', 'forestswampforestswamp16'),
    ('FORESTSWAMP', 'FORESTSWAMP18', 'природный блок FORESTSWAMP/FORESTSWAMP18', 'forestswampforestswamp18'),
    ('FORESTSWAMP', 'FOREST_ROAD_XX00', 'природный блок FORESTSWAMP/FOREST_ROAD_XX00', 'forestswampforestroadxx00'),
    ('FORESTSWAMP_WASTE', 'FOREST07', 'природный блок FORESTSWAMP_WASTE/FOREST07', 'forestswampwasteforest07'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP08', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP08', 'forestswampwasteforestswamp08'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP11', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP11', 'forestswampwasteforestswamp11'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP12', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP12', 'forestswampwasteforestswamp12'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP14', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP14', 'forestswampwasteforestswamp14'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP18', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP18', 'forestswampwasteforestswamp18'),
    ('FORESTSWAMP_WASTE', 'SOLFOREST14', 'природный блок FORESTSWAMP_WASTE/SOLFOREST14', 'forestswampwastesolforest14'),
    ('JUNGLESTYX', 'JUNGLE13', 'природный блок JUNGLESTYX/JUNGLE13', 'junglestyxjungle13'),
    ('PLAINS_ERODED', 'PLAINS11', 'природный блок PLAINS_ERODED/PLAINS11', 'plainserodedplains11'),
    ('STYXSWAMP', 'FORESTSWAMP01', 'природный блок STYXSWAMP/FORESTSWAMP01', 'styxswampforestswamp01'),
    ('STYXSWAMP', 'FORESTSWAMP02', 'природный блок STYXSWAMP/FORESTSWAMP02', 'styxswampforestswamp02'),
    ('STYXSWAMP', 'FORESTSWAMP07', 'природный блок STYXSWAMP/FORESTSWAMP07', 'styxswampforestswamp07'),
    ('STYXSWAMP', 'FORESTSWAMP10', 'природный блок STYXSWAMP/FORESTSWAMP10', 'styxswampforestswamp10'),
    ('STYXSWAMP', 'FORESTSWAMP11', 'природный блок STYXSWAMP/FORESTSWAMP11', 'styxswampforestswamp11'),
    ('STYXSWAMP', 'FORESTSWAMP14', 'природный блок STYXSWAMP/FORESTSWAMP14', 'styxswampforestswamp14'),
    ('WESTOWN_GRASS', 'PLAINS09', 'природный блок WESTOWN_GRASS/PLAINS09', 'westowngrassplains09'),
    ('WESTOWN_GRASS', 'PLAINS11', 'природный блок WESTOWN_GRASS/PLAINS11', 'westowngrassplains11'),
    ('WESTOWN_GRASS', 'PLAINS12', 'природный блок WESTOWN_GRASS/PLAINS12', 'westowngrassplains12'),
    ('WESTOWN_TROPICAL', 'PLAINS11', 'природный блок WESTOWN_TROPICAL/PLAINS11', 'westowntropicalplains11'),
    ('WESTOWN_TROPICAL', 'PLAINS12', 'природный блок WESTOWN_TROPICAL/PLAINS12', 'westowntropicalplains12'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок URBANJUNKUFO/URBANJUNK38': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK40': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK42': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK26': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK28': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK30': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK37': (20, 20),
    'природный блок FOREST2BLACK/SOLFORESTHUGE01': (30, 30),
    'природный блок FORESTSWAMP/FORESTSWAMP18': (20, 20),
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP08': (20, 20),
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP11': (20, 20),
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP12': (20, 20),
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP18': (20, 20),
    'природный блок PLAINS_ERODED/PLAINS11': (20, 20),
    'природный блок STYXSWAMP/FORESTSWAMP01': (20, 20),
    'природный блок STYXSWAMP/FORESTSWAMP02': (20, 20),
    'природный блок STYXSWAMP/FORESTSWAMP07': (20, 20),
    'природный блок STYXSWAMP/FORESTSWAMP10': (20, 20),
    'природный блок STYXSWAMP/FORESTSWAMP11': (20, 20),
    'природный блок WESTOWN_GRASS/PLAINS11': (20, 20),
    'природный блок WESTOWN_GRASS/PLAINS12': (20, 20),
    'природный блок WESTOWN_TROPICAL/PLAINS11': (20, 20),
    'природный блок WESTOWN_TROPICAL/PLAINS12': (20, 20),
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
    'городской блок URBANJUNKUFO/URBANJUNK05': 'URBANJUNKUFO/URBANJUNK05',
    'городской блок URBANJUNKUFO/URBANJUNK08': 'URBANJUNKUFO/URBANJUNK08',
    'городской блок URBANJUNKUFO/URBANJUNK38': 'URBANJUNKUFO/URBANJUNK38',
    'городской блок URBANJUNKUFO/URBANJUNK40': 'URBANJUNKUFO/URBANJUNK40',
    'городской блок URBANJUNKUFO/URBANJUNK42': 'URBANJUNKUFO/URBANJUNK42',
    'городской блок URBANJUNKWOODUFO/URBANJUNK30': 'URBANJUNKWOODUFO/URBANJUNK30',
    'городской блок URBANJUNKWOODUFO/URBANJUNK37': 'URBANJUNKWOODUFO/URBANJUNK37',
    'городской блок WESTOWN_TROPICAL/WESTOWN_21': 'WESTOWN_TROPICAL/WESTOWN_21',
    'природный блок FOREST2BLACK/SOLFORESTHUGE01': 'FOREST2BLACK/SOLFORESTHUGE01',
    'природный блок FORESTRED/FINNIKFOREST04': 'FORESTRED/FINNIKFOREST04',
    'природный блок FORESTSWAMP/FORESTSWAMP00': 'FORESTSWAMP/FORESTSWAMP00',
    'природный блок FORESTSWAMP/FORESTSWAMP06': 'FORESTSWAMP/FORESTSWAMP06',
    'природный блок FORESTSWAMP/FORESTSWAMP16': 'FORESTSWAMP/FORESTSWAMP16',
    'природный блок FORESTSWAMP/FORESTSWAMP18': 'FORESTSWAMP/FORESTSWAMP18',
    'природный блок FORESTSWAMP/FOREST_ROAD_XX00': 'FORESTSWAMP/FOREST_ROAD_XX00',
    'природный блок FORESTSWAMP_WASTE/FOREST07': 'FORESTSWAMP_WASTE/FOREST07',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP08': 'FORESTSWAMP_WASTE/FORESTSWAMP08',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP11': 'FORESTSWAMP_WASTE/FORESTSWAMP11',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP12': 'FORESTSWAMP_WASTE/FORESTSWAMP12',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP14': 'FORESTSWAMP_WASTE/FORESTSWAMP14',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP18': 'FORESTSWAMP_WASTE/FORESTSWAMP18',
    'природный блок FORESTSWAMP_WASTE/SOLFOREST14': 'FORESTSWAMP_WASTE/SOLFOREST14',
    'природный блок JUNGLESTYX/JUNGLE13': 'JUNGLESTYX/JUNGLE13',
    'природный блок PLAINS_ERODED/PLAINS11': 'PLAINS_ERODED/PLAINS11',
    'природный блок STYXSWAMP/FORESTSWAMP01': 'STYXSWAMP/FORESTSWAMP01',
    'природный блок STYXSWAMP/FORESTSWAMP02': 'STYXSWAMP/FORESTSWAMP02',
    'природный блок STYXSWAMP/FORESTSWAMP07': 'STYXSWAMP/FORESTSWAMP07',
    'природный блок STYXSWAMP/FORESTSWAMP10': 'STYXSWAMP/FORESTSWAMP10',
    'природный блок STYXSWAMP/FORESTSWAMP11': 'STYXSWAMP/FORESTSWAMP11',
    'природный блок STYXSWAMP/FORESTSWAMP14': 'STYXSWAMP/FORESTSWAMP14',
    'природный блок WESTOWN_GRASS/PLAINS09': 'WESTOWN_GRASS/PLAINS09',
    'природный блок WESTOWN_GRASS/PLAINS11': 'WESTOWN_GRASS/PLAINS11',
    'природный блок WESTOWN_GRASS/PLAINS12': 'WESTOWN_GRASS/PLAINS12',
    'природный блок WESTOWN_TROPICAL/PLAINS11': 'WESTOWN_TROPICAL/PLAINS11',
    'природный блок WESTOWN_TROPICAL/PLAINS12': 'WESTOWN_TROPICAL/PLAINS12',
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot17_scen.py", PS.sha("tools/collapse_pilot17_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v8 as E
    E.install()                                   # M0j5, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
