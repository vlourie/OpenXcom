#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, двадцатая партия: блоки без деревьев из того же отбора, что партия 19 (cand19).

Слово Vitali 23.10 «Охват»: бои переписи на террейнах с кандидатами без целого размещения (зёрна 33-48),
все целые блоки, которых нет в пилотах 4-19. Фильтры партий 10-18: базы, корабли, пещеры, Марс нет, разметка без
сомнений, под M0j5 на целом ничего не висит, скалы и земляной массы нет. Листы видов scratchpad cp23/kinds19_1..3.png
(82 вида, 23.10): мебель, ящики, декор, колонны стоят на полу или держат друг друга; масса (кладка ATLANTDESERT,
откосы FORESTBITSWASTE, холмы ISLANDURBAN2, скалы ISLANDURBAN3) не взята. Одноимённые с той же моделью, что уже в
пилоте, не берутся; с другой - имя ТЕРРЕЙН/БЛОК (NAME_AS). Отбор - scratchpad cp23/cand19.py, kinds19.py,
pick19.py, dup19.py, mk20.py. Модель M0j5 (collapse_v8); частичные - PFALL зданий (collapse_partial20_scen, как 18).
RICE_FARM/ALT_BARN_10 не взят: это «сарай» пилота 3 (dup19 сверяет занятые блоки только с пилотами 4-18).

    py -3.13 tools\collapse_pilot20_scen.py define   census/collapse/pilot20/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot20"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('INDUSTRIALSLUM', 'INDUSTRIALSLUM33', 'городской блок INDUSTRIALSLUM/INDUSTRIALSLUM33', 'industrialslum33'),
    ('INDUSTRIALSLUM', 'INDUSTRIALSLUM34', 'городской блок INDUSTRIALSLUM/INDUSTRIALSLUM34', 'industrialslum34'),
    ('INDUSTRIALSLUM', 'INDUSTRIALSLUM35', 'городской блок INDUSTRIALSLUM/INDUSTRIALSLUM35', 'industrialslum35'),
    ('INDUSTRIALSLUM', 'INDUSTRIALSLUMDIO04', 'городской блок INDUSTRIALSLUM/INDUSTRIALSLUMDIO04', 'industrialslumdio04'),
    ('INDUSTRIALSLUM', 'INDUSTRIALSLUMDIO05', 'городской блок INDUSTRIALSLUM/INDUSTRIALSLUMDIO05', 'industrialslumdio05'),
    ('ISLANDURBAN', 'ISLANDURBAN02', 'городской блок ISLANDURBAN/ISLANDURBAN02', 'islandurban02'),
    ('ISLANDURBAN', 'ISLANDURBAN07', 'городской блок ISLANDURBAN/ISLANDURBAN07', 'islandurban07'),
    ('ISLANDURBAN', 'ISLANDURBANDIO01', 'городской блок ISLANDURBAN/ISLANDURBANDIO01', 'islandurbandio01'),
    ('ISLANDURBAN', 'ISLANDURBANDIO03', 'городской блок ISLANDURBAN/ISLANDURBANDIO03', 'islandurbandio03'),
    ('RURAL', 'VILBAN51', 'городской блок RURAL/VILBAN51', 'vilban51'),
    ('URBAN', 'EXPANDEDTERROR17', 'городской блок URBAN/EXPANDEDTERROR17', 'urbanexpandedterror17'),
    ('URBAN', 'EXPANDEDTERROR20', 'городской блок URBAN/EXPANDEDTERROR20', 'urbanexpandedterror20'),
    ('URBAN', 'MADURBAN32', 'городской блок URBAN/MADURBAN32', 'urbanmadurban32'),
    ('URBAN', 'MADURBAN35', 'городской блок URBAN/MADURBAN35', 'urbanmadurban35'),
    ('URBAN', 'NEURBAN01B', 'городской блок URBAN/NEURBAN01B', 'urbanneurban01b'),
    ('URBAN', 'URBANDIO01', 'городской блок URBAN/URBANDIO01', 'urbanurbandio01'),
    ('URBAN', 'URBANDIO05MYHOUSE', 'городской блок URBAN/URBANDIO05MYHOUSE', 'urbandio05myhouse'),
    ('URBAN', 'URBANDIOHUGE01', 'городской блок URBAN/URBANDIOHUGE01', 'urbandiohuge01'),
    ('URBAN', 'URBANSANYASKILLPRO01', 'городской блок URBAN/URBANSANYASKILLPRO01', 'urbanurbansanyaskillpro01'),
    ('URBANJUNKUFO', 'URBANJUNK25', 'городской блок URBANJUNKUFO/URBANJUNK25', 'urbanjunkufourbanjunk25'),
    ('URBANJUNKUFO', 'URBANJUNK44', 'городской блок URBANJUNKUFO/URBANJUNK44', 'urbanjunk44'),
    ('URBANJUNKUFO', 'URBANJUNKDIO_03', 'городской блок URBANJUNKUFO/URBANJUNKDIO_03', 'urbanjunkufourbanjunkdio03'),
    ('URBANWAR', 'EXPANDEDTERROR20', 'городской блок URBANWAR/EXPANDEDTERROR20', 'urbanwarexpandedterror20'),
    ('URBANWAR', 'MADURBAN33', 'городской блок URBANWAR/MADURBAN33', 'urbanwarmadurban33'),
    ('URBANWAR', 'MADURBAN34', 'городской блок URBANWAR/MADURBAN34', 'urbanwarmadurban34'),
    ('URBAN_WASTE', 'URBANWASTE08', 'городской блок URBAN_WASTE/URBANWASTE08', 'urbanwaste08'),
    ('URBAN_WASTE', 'URBANWASTE44', 'городской блок URBAN_WASTE/URBANWASTE44', 'urbanwaste44'),
    ('WESTOWN_GRASS', 'WESTOWN_09', 'городской блок WESTOWN_GRASS/WESTOWN_09', 'westowngrasswestown09'),
    ('WESTOWN_TROPICAL', 'WESTOWN_00', 'городской блок WESTOWN_TROPICAL/WESTOWN_00', 'westown00'),
    ('WESTOWN_TROPICAL', 'WESTOWN_09', 'городской блок WESTOWN_TROPICAL/WESTOWN_09', 'westowntropicalwestown09'),
    ('CULTA', 'CULTAFARM02', 'природный блок CULTA/CULTAFARM02', 'cultacultafarm02'),
    ('CULTA', 'CULTAFARM20', 'природный блок CULTA/CULTAFARM20', 'cultacultafarm20'),
    ('CULTA_PP', 'CULTA18', 'природный блок CULTA_PP/CULTA18', 'cultappculta18'),
    ('CULTA_PP', 'CULTAFARM05', 'природный блок CULTA_PP/CULTAFARM05', 'cultappcultafarm05'),
    ('CULTA_PP', 'CULTAFARM06', 'природный блок CULTA_PP/CULTAFARM06', 'cultappcultafarm06'),
    ('CULTA_PP', 'CULTAFARM20', 'природный блок CULTA_PP/CULTAFARM20', 'cultappcultafarm20'),
    ('CULTA_PP', 'CULTAFARM21', 'природный блок CULTA_PP/CULTAFARM21', 'cultappcultafarm21'),
    ('CULTA_PP', 'CULTAFARM22', 'природный блок CULTA_PP/CULTAFARM22', 'cultappcultafarm22'),
    ('CULTA_UBER', 'CULTASOLHUGE01', 'природный блок CULTA_UBER/CULTASOLHUGE01', 'cultaubercultasolhuge01'),
    ('DESERT2RED', 'DESERT08', 'природный блок DESERT2RED/DESERT08', 'desert2reddesert08'),
    ('DESERT2RED', 'DESERT10', 'природный блок DESERT2RED/DESERT10', 'desert2reddesert10'),
    ('DESERTTEMPLE', 'ATLANTDESERT02', 'природный блок DESERTTEMPLE/ATLANTDESERT02', 'atlantdesert02'),
    ('DESERTTEMPLE', 'ATLANTDESERT03', 'природный блок DESERTTEMPLE/ATLANTDESERT03', 'atlantdesert03'),
    ('DESERTTEMPLE', 'ATLANTDESERT04', 'природный блок DESERTTEMPLE/ATLANTDESERT04', 'atlantdesert04'),
    ('DESERTTEMPLE', 'ATLANTDESERT05', 'природный блок DESERTTEMPLE/ATLANTDESERT05', 'atlantdesert05'),
    ('DESERTTEMPLE', 'ATLANTDESERT06', 'природный блок DESERTTEMPLE/ATLANTDESERT06', 'atlantdesert06'),
    ('DESERTTEMPLE', 'ATLANTDESERT07', 'природный блок DESERTTEMPLE/ATLANTDESERT07', 'atlantdesert07'),
    ('DESERTTEMPLE', 'ATLANTDESERT08', 'природный блок DESERTTEMPLE/ATLANTDESERT08', 'atlantdesert08'),
    ('DESERTTEMPLE', 'ATLANTDESERT09', 'природный блок DESERTTEMPLE/ATLANTDESERT09', 'atlantdesert09'),
    ('FORESTSWAMP_WASTE', 'FOREST11', 'природный блок FORESTSWAMP_WASTE/FOREST11', 'forestswampwasteforest11'),
    ('RICE_FARM', 'ALT_BARN_9', 'природный блок RICE_FARM/ALT_BARN_9', 'altbarn9'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок ISLANDURBAN/ISLANDURBAN02': (20, 20),
    'городской блок ISLANDURBAN/ISLANDURBANDIO01': (20, 20),
    'городской блок ISLANDURBAN/ISLANDURBANDIO03': (20, 20),
    'городской блок RURAL/VILBAN51': (20, 20),
    'городской блок URBAN/EXPANDEDTERROR17': (20, 20),
    'городской блок URBAN/EXPANDEDTERROR20': (20, 20),
    'городской блок URBAN/MADURBAN32': (20, 20),
    'городской блок URBAN/MADURBAN35': (20, 20),
    'городской блок URBAN/NEURBAN01B': (20, 20),
    'городской блок URBAN/URBANDIO01': (20, 20),
    'городской блок URBAN/URBANDIO05MYHOUSE': (30, 30),
    'городской блок URBAN/URBANDIOHUGE01': (30, 30),
    'городской блок URBAN/URBANSANYASKILLPRO01': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK25': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK44': (20, 20),
    'городской блок URBANWAR/EXPANDEDTERROR20': (20, 20),
    'городской блок URBANWAR/MADURBAN33': (20, 20),
    'городской блок URBANWAR/MADURBAN34': (20, 20),
    'городской блок URBAN_WASTE/URBANWASTE08': (20, 20),
    'городской блок WESTOWN_GRASS/WESTOWN_09': (20, 20),
    'городской блок WESTOWN_TROPICAL/WESTOWN_00': (20, 20),
    'городской блок WESTOWN_TROPICAL/WESTOWN_09': (20, 20),
    'природный блок CULTA_PP/CULTAFARM22': (20, 20),
    'природный блок CULTA_UBER/CULTASOLHUGE01': (30, 30),
    'природный блок DESERT2RED/DESERT10': (20, 20),
    'природный блок FORESTSWAMP_WASTE/FOREST11': (20, 20),
    'природный блок RICE_FARM/ALT_BARN_9': (10, 20),
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
    'городской блок URBAN/EXPANDEDTERROR17': 'URBAN/EXPANDEDTERROR17',
    'городской блок URBAN/EXPANDEDTERROR20': 'URBAN/EXPANDEDTERROR20',
    'городской блок URBAN/MADURBAN32': 'URBAN/MADURBAN32',
    'городской блок URBAN/MADURBAN35': 'URBAN/MADURBAN35',
    'городской блок URBAN/NEURBAN01B': 'URBAN/NEURBAN01B',
    'городской блок URBAN/URBANDIO01': 'URBAN/URBANDIO01',
    'городской блок URBAN/URBANSANYASKILLPRO01': 'URBAN/URBANSANYASKILLPRO01',
    'городской блок URBANJUNKUFO/URBANJUNK25': 'URBANJUNKUFO/URBANJUNK25',
    'городской блок URBANJUNKUFO/URBANJUNKDIO_03': 'URBANJUNKUFO/URBANJUNKDIO_03',
    'городской блок URBANWAR/EXPANDEDTERROR20': 'URBANWAR/EXPANDEDTERROR20',
    'городской блок URBANWAR/MADURBAN33': 'URBANWAR/MADURBAN33',
    'городской блок URBANWAR/MADURBAN34': 'URBANWAR/MADURBAN34',
    'городской блок WESTOWN_GRASS/WESTOWN_09': 'WESTOWN_GRASS/WESTOWN_09',
    'городской блок WESTOWN_TROPICAL/WESTOWN_09': 'WESTOWN_TROPICAL/WESTOWN_09',
    'природный блок CULTA/CULTAFARM02': 'CULTA/CULTAFARM02',
    'природный блок CULTA/CULTAFARM20': 'CULTA/CULTAFARM20',
    'природный блок CULTA_PP/CULTA18': 'CULTA_PP/CULTA18',
    'природный блок CULTA_PP/CULTAFARM05': 'CULTA_PP/CULTAFARM05',
    'природный блок CULTA_PP/CULTAFARM06': 'CULTA_PP/CULTAFARM06',
    'природный блок CULTA_PP/CULTAFARM20': 'CULTA_PP/CULTAFARM20',
    'природный блок CULTA_PP/CULTAFARM21': 'CULTA_PP/CULTAFARM21',
    'природный блок CULTA_PP/CULTAFARM22': 'CULTA_PP/CULTAFARM22',
    'природный блок CULTA_UBER/CULTASOLHUGE01': 'CULTA_UBER/CULTASOLHUGE01',
    'природный блок DESERT2RED/DESERT08': 'DESERT2RED/DESERT08',
    'природный блок DESERT2RED/DESERT10': 'DESERT2RED/DESERT10',
    'природный блок FORESTSWAMP_WASTE/FOREST11': 'FORESTSWAMP_WASTE/FOREST11',
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot20_scen.py", PS.sha("tools/collapse_pilot20_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v8 as E
    E.install()                                   # M0j5, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
