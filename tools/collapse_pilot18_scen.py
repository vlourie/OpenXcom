#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, восемнадцатая партия: блоки без деревьев из того же отбора, что партия 17 (cand17).

Слово Vitali 23.10 «Охват»: бои переписи на террейнах с участками, ни разу не встреченными целыми (зёрна 17-32),
все целые блоки, которых нет в пилотах 4-17. Фильтры партий 10-16: базы, корабли, пещеры, Марс нет, разметка без
сомнений, под M0j5 на целом ничего не висит, скалы и земляной массы нет. Листы видов scratchpad cp22/kinds17_1..2.png
(45 видов, 23.10): мебель, ящики, декор, кладка стоят на полу или держат друг друга; масса (DESERTBITS:10,
FORESTSWAMPBITS:10/14) не взята. Одноимённые с той же моделью, что уже в пилоте, не берутся; с другой - имя
ТЕРРЕЙН/БЛОК (NAME_AS). Отбор - scratchpad cp22/cand17.py, kinds17.py, pick17.py, dup17.py, mk18.py.
Модель M0j5 (collapse_v8); частичные - PFALL зданий (collapse_partial18_scen, как 16). RICE_FARM/ALT_BARN_10 убран
руками: это «сарай» пилота 3 (отбор сверял занятые блоки только с пилотами 4-16).

    py -3.13 tools\collapse_pilot18_scen.py define   census/collapse/pilot18/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot18"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('CHEMTOWNGHOUL', 'CHEMTOWN09', 'городской блок CHEMTOWNGHOUL/CHEMTOWN09', 'chemtownghoulchemtown09'),
    ('CHEMTOWNGHOUL', 'CHEMTOWN11', 'городской блок CHEMTOWNGHOUL/CHEMTOWN11', 'chemtownghoulchemtown11'),
    ('CHEMTOWNGHOUL', 'CHEMTOWN12', 'городской блок CHEMTOWNGHOUL/CHEMTOWN12', 'chemtownghoulchemtown12'),
    ('COMRCURBAN', 'COMRCURBAN07', 'городской блок COMRCURBAN/COMRCURBAN07', 'comrcurban07'),
    ('COMRCURBAN', 'COMRCURBAN08', 'городской блок COMRCURBAN/COMRCURBAN08', 'comrcurban08'),
    ('COMRCURBAN', 'COMRCURBAN12', 'городской блок COMRCURBAN/COMRCURBAN12', 'comrcurban12'),
    ('COMRCURBAN', 'COMRCURBAN42', 'городской блок COMRCURBAN/COMRCURBAN42', 'comrcurban42'),
    ('COMRCURBAN', 'COMRCURBAN52', 'городской блок COMRCURBAN/COMRCURBAN52', 'comrcurban52'),
    ('IDT_SNOWVILLAGE', 'IDT_SNOWVILLAGE02', 'городской блок IDT_SNOWVILLAGE/IDT_SNOWVILLAGE02', 'idtsnowvillage02'),
    ('IDT_SNOWVILLAGE', 'IDT_SNOWVILLAGE03', 'городской блок IDT_SNOWVILLAGE/IDT_SNOWVILLAGE03', 'idtsnowvillage03'),
    ('IDT_SNOWVILLAGE', 'IDT_SNOWVILLAGE15', 'городской блок IDT_SNOWVILLAGE/IDT_SNOWVILLAGE15', 'idtsnowvillage15'),
    ('INDUSTRIALSLUM', 'INDUSTRIALSLUM03', 'городской блок INDUSTRIALSLUM/INDUSTRIALSLUM03', 'industrialslum03'),
    ('INDUSTRIALSLUM', 'INDUSTRIALSLUMDIO15', 'городской блок INDUSTRIALSLUM/INDUSTRIALSLUMDIO15', 'industrialslumdio15'),
    ('INDUSTRIALSLUM', 'INDUSTRIALSLUMDIO29', 'городской блок INDUSTRIALSLUM/INDUSTRIALSLUMDIO29', 'industrialslumdio29'),
    ('NUKE_CITY_NORAD_5', 'NUKE01', 'городской блок NUKE_CITY_NORAD_5/NUKE01', 'nuke01'),
    ('RURAL', 'VILBAN24', 'городской блок RURAL/VILBAN24', 'vilban24'),
    ('URBAN', 'MADURBAN29', 'городской блок URBAN/MADURBAN29', 'urbanmadurban29'),
    ('URBAN', 'MADURBAN34', 'городской блок URBAN/MADURBAN34', 'madurban34'),
    ('URBAN', 'NEURBAN04', 'городской блок URBAN/NEURBAN04', 'urbanneurban04'),
    ('URBAN', 'URBAN08', 'городской блок URBAN/URBAN08', 'urban08'),
    ('URBAN', 'URBAN09d', 'городской блок URBAN/URBAN09d', 'urbanurban09d'),
    ('URBAN', 'URBANBR', 'городской блок URBAN/URBANBR', 'urbanurbanbr'),
    ('URBANJUNKUFO', 'URBANJUNK06', 'городской блок URBANJUNKUFO/URBANJUNK06', 'urbanjunkufourbanjunk06'),
    ('URBANJUNKUFO', 'URBANJUNK07', 'городской блок URBANJUNKUFO/URBANJUNK07', 'urbanjunkufourbanjunk07'),
    ('URBANJUNKUFO', 'URBANJUNK09', 'городской блок URBANJUNKUFO/URBANJUNK09', 'urbanjunkufourbanjunk09'),
    ('URBANJUNKUFO', 'URBANJUNK13', 'городской блок URBANJUNKUFO/URBANJUNK13', 'urbanjunkufourbanjunk13'),
    ('URBANJUNKUFO', 'URBANJUNK32', 'городской блок URBANJUNKUFO/URBANJUNK32', 'urbanjunkufourbanjunk32'),
    ('URBANJUNKUFO', 'URBANJUNKDIO_06', 'городской блок URBANJUNKUFO/URBANJUNKDIO_06', 'urbanjunkufourbanjunkdio06'),
    ('URBANJUNKWOODUFO', 'URBANJUNK07', 'городской блок URBANJUNKWOODUFO/URBANJUNK07', 'urbanjunkwoodufourbanjunk07'),
    ('URBANJUNKWOODUFO', 'URBANJUNK09', 'городской блок URBANJUNKWOODUFO/URBANJUNK09', 'urbanjunkwoodufourbanjunk09'),
    ('URBANLUX', 'EXPANDEDTERROR13', 'городской блок URBANLUX/EXPANDEDTERROR13', 'urbanluxexpandedterror13'),
    ('URBANLUX', 'MADURBAN23', 'городской блок URBANLUX/MADURBAN23', 'urbanluxmadurban23'),
    ('URBANLUX', 'URBAN15', 'городской блок URBANLUX/URBAN15', 'urbanluxurban15'),
    ('URBANWAR', 'EXPANDEDTERROR19', 'городской блок URBANWAR/EXPANDEDTERROR19', 'urbanwarexpandedterror19'),
    ('URBANWAR', 'MADURBAN11', 'городской блок URBANWAR/MADURBAN11', 'urbanwarmadurban11'),
    ('URBANWAR', 'MADURBAN23', 'городской блок URBANWAR/MADURBAN23', 'urbanwarmadurban23'),
    ('URBANWAR', 'MADURBAN29', 'городской блок URBANWAR/MADURBAN29', 'urbanwarmadurban29'),
    ('URBANWAR', 'MADURBAN32', 'городской блок URBANWAR/MADURBAN32', 'madurban32'),
    ('URBANWAR', 'URBAN05', 'городской блок URBANWAR/URBAN05', 'urbanwarurban05'),
    ('URBANWAR', 'URBAN09d', 'городской блок URBANWAR/URBAN09d', 'urbanwarurban09d'),
    ('URBANWAR', 'URBANBR', 'городской блок URBANWAR/URBANBR', 'urbanwarurbanbr'),
    ('URBANWAR', 'URBANDIO02', 'городской блок URBANWAR/URBANDIO02', 'urbanwarurbandio02'),
    ('URBANWAR', 'URBANMY', 'городской блок URBANWAR/URBANMY', 'urbanwarurbanmy'),
    ('URBAN_WASTE', 'URBANWASTE01', 'городской блок URBAN_WASTE/URBANWASTE01', 'urbanwaste01'),
    ('URBAN_WASTE', 'URBANWASTE07', 'городской блок URBAN_WASTE/URBANWASTE07', 'urbanwaste07'),
    ('URBAN_WASTE', 'URBANWASTE11', 'городской блок URBAN_WASTE/URBANWASTE11', 'urbanwaste11'),
    ('URBAN_WASTE', 'URBANWASTE13', 'городской блок URBAN_WASTE/URBANWASTE13', 'urbanwaste13'),
    ('URBAN_WASTE', 'URBANWASTE14', 'городской блок URBAN_WASTE/URBANWASTE14', 'urbanwaste14'),
    ('URBAN_WASTE', 'URBANWASTE19', 'городской блок URBAN_WASTE/URBANWASTE19', 'urbanwaste19'),
    ('URBAN_WASTE', 'URBANWASTE22', 'городской блок URBAN_WASTE/URBANWASTE22', 'urbanwaste22'),
    ('URBAN_WASTE', 'URBANWASTE30', 'городской блок URBAN_WASTE/URBANWASTE30', 'urbanwaste30'),
    ('URBAN_WASTE', 'URBANWASTE37', 'городской блок URBAN_WASTE/URBANWASTE37', 'urbanwaste37'),
    ('URBAN_WASTE', 'URBANWASTE38', 'городской блок URBAN_WASTE/URBANWASTE38', 'urbanwaste38'),
    ('URBAN_WASTE', 'URBANWASTE39', 'городской блок URBAN_WASTE/URBANWASTE39', 'urbanwaste39'),
    ('URBAN_WASTE', 'URBANWASTE42', 'городской блок URBAN_WASTE/URBANWASTE42', 'urbanwaste42'),
    ('URBAN_WASTE', 'URBANWASTE43', 'городской блок URBAN_WASTE/URBANWASTE43', 'urbanwaste43'),
    ('URBAN_WASTE', 'URBANWASTE55', 'городской блок URBAN_WASTE/URBANWASTE55', 'urbanwaste55'),
    ('URBAN_WASTE', 'URBANWASTE61', 'городской блок URBAN_WASTE/URBANWASTE61', 'urbanwaste61'),
    ('URBAN_WASTE', 'URBANWASTE62', 'городской блок URBAN_WASTE/URBANWASTE62', 'urbanwaste62'),
    ('URBAN_WASTE', 'URBANWASTEROAD_CROSS06', 'городской блок URBAN_WASTE/URBANWASTEROAD_CROSS06', 'urbanwasteroadcross06'),
    ('URBAN_WASTE', 'URBANWASTEROAD_WE07', 'городской блок URBAN_WASTE/URBANWASTEROAD_WE07', 'urbanwasteroadwe07'),
    ('WESTOWN_GRASS', 'WESTOWN_16', 'городской блок WESTOWN_GRASS/WESTOWN_16', 'westowngrasswestown16'),
    ('WESTOWN_TROPICAL', 'WESTOWN_05', 'городской блок WESTOWN_TROPICAL/WESTOWN_05', 'westowntropicalwestown05'),
    ('WESTOWN_TROPICAL', 'WESTOWN_16', 'городской блок WESTOWN_TROPICAL/WESTOWN_16', 'westowntropicalwestown16'),
    ('CULTA', 'CULTAFARM04', 'природный блок CULTA/CULTAFARM04', 'cultacultafarm04'),
    ('CULTA', 'CULTAFARM22', 'природный блок CULTA/CULTAFARM22', 'cultacultafarm22'),
    ('CULTA', 'CULTASOLHUGE01', 'природный блок CULTA/CULTASOLHUGE01', 'cultasolhuge01'),
    ('CULTA', 'CULT_NEW18', 'природный блок CULTA/CULT_NEW18', 'cultacultnew18'),
    ('CULTA_PP', 'CULTA30', 'природный блок CULTA_PP/CULTA30', 'cultappculta30'),
    ('CULTA_PP', 'CULTA31', 'природный блок CULTA_PP/CULTA31', 'cultappculta31'),
    ('CULTA_PP', 'CULTAFARM00', 'природный блок CULTA_PP/CULTAFARM00', 'cultappcultafarm00'),
    ('CULTA_PP', 'CULTAFARM02', 'природный блок CULTA_PP/CULTAFARM02', 'cultappcultafarm02'),
    ('CULTA_PP', 'CULTAFARM03', 'природный блок CULTA_PP/CULTAFARM03', 'cultappcultafarm03'),
    ('CULTA_PP', 'CULTAFARM04', 'природный блок CULTA_PP/CULTAFARM04', 'cultappcultafarm04'),
    ('CULTA_PP', 'CULTASOL01', 'природный блок CULTA_PP/CULTASOL01', 'cultappcultasol01'),
    ('CULTA_PP', 'CULT_NEW17', 'природный блок CULTA_PP/CULT_NEW17', 'cultappcultnew17'),
    ('CULTA_PP', 'CULT_NEW18', 'природный блок CULTA_PP/CULT_NEW18', 'cultappcultnew18'),
    ('CULTA_UBER', 'CULTA16', 'природный блок CULTA_UBER/CULTA16', 'cultauberculta16'),
    ('CULTA_UBER', 'CULTA17', 'природный блок CULTA_UBER/CULTA17', 'cultauberculta17'),
    ('CULTA_UBER', 'CULTA18', 'природный блок CULTA_UBER/CULTA18', 'cultauberculta18'),
    ('CULTA_UBER', 'CULTA19', 'природный блок CULTA_UBER/CULTA19', 'cultauberculta19'),
    ('CULTA_UBER', 'CULTA30', 'природный блок CULTA_UBER/CULTA30', 'cultauberculta30'),
    ('CULTA_UBER', 'CULTA31', 'природный блок CULTA_UBER/CULTA31', 'cultauberculta31'),
    ('CULTA_UBER', 'CULTAFARM00', 'природный блок CULTA_UBER/CULTAFARM00', 'cultaubercultafarm00'),
    ('CULTA_UBER', 'CULTAFARM01', 'природный блок CULTA_UBER/CULTAFARM01', 'cultafarm01'),
    ('CULTA_UBER', 'CULTAFARM02', 'природный блок CULTA_UBER/CULTAFARM02', 'cultaubercultafarm02'),
    ('CULTA_UBER', 'CULTAFARM03', 'природный блок CULTA_UBER/CULTAFARM03', 'cultaubercultafarm03'),
    ('CULTA_UBER', 'CULTAFARM04', 'природный блок CULTA_UBER/CULTAFARM04', 'cultaubercultafarm04'),
    ('CULTA_UBER', 'CULTAFARM05', 'природный блок CULTA_UBER/CULTAFARM05', 'cultaubercultafarm05'),
    ('CULTA_UBER', 'CULTAFARM07', 'природный блок CULTA_UBER/CULTAFARM07', 'cultafarm07'),
    ('CULTA_UBER', 'CULTAFARM14', 'природный блок CULTA_UBER/CULTAFARM14', 'cultaubercultafarm14'),
    ('CULTA_UBER', 'CULTAFARM20', 'природный блок CULTA_UBER/CULTAFARM20', 'cultafarm20'),
    ('CULTA_UBER', 'CULTAFARM22', 'природный блок CULTA_UBER/CULTAFARM22', 'cultaubercultafarm22'),
    ('CULTA_UBER', 'CULT_FINNIK00', 'природный блок CULTA_UBER/CULT_FINNIK00', 'cultfinnik00'),
    ('CULTA_UBER', 'CULT_NEW16', 'природный блок CULTA_UBER/CULT_NEW16', 'cultaubercultnew16'),
    ('CULTA_UBER', 'CULT_NEW17', 'природный блок CULTA_UBER/CULT_NEW17', 'cultaubercultnew17'),
    ('CULTA_UBER', 'CULT_NEW18', 'природный блок CULTA_UBER/CULT_NEW18', 'cultaubercultnew18'),
    ('DESERTREFINERY', 'DSRTREFI_05', 'природный блок DESERTREFINERY/DSRTREFI_05', 'dsrtrefi05'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок COMRCURBAN/COMRCURBAN07': (20, 20),
    'городской блок COMRCURBAN/COMRCURBAN08': (20, 20),
    'городской блок COMRCURBAN/COMRCURBAN12': (20, 20),
    'городской блок COMRCURBAN/COMRCURBAN42': (20, 20),
    'городской блок INDUSTRIALSLUM/INDUSTRIALSLUMDIO29': (20, 20),
    'городской блок URBAN/MADURBAN29': (20, 20),
    'городской блок URBAN/MADURBAN34': (20, 20),
    'городской блок URBAN/NEURBAN04': (20, 20),
    'городской блок URBAN/URBAN08': (20, 20),
    'городской блок URBAN/URBAN09d': (20, 20),
    'городской блок URBAN/URBANBR': (20, 20),
    'городской блок URBANWAR/EXPANDEDTERROR19': (20, 20),
    'городской блок URBANWAR/MADURBAN11': (20, 20),
    'городской блок URBANWAR/MADURBAN29': (20, 20),
    'городской блок URBANWAR/MADURBAN32': (20, 20),
    'городской блок URBANWAR/URBAN05': (20, 20),
    'городской блок URBANWAR/URBAN09d': (20, 20),
    'городской блок URBANWAR/URBANBR': (20, 20),
    'городской блок URBANWAR/URBANDIO02': (20, 20),
    'городской блок URBANWAR/URBANMY': (20, 20),
    'городской блок URBAN_WASTE/URBANWASTE14': (20, 20),
    'городской блок URBAN_WASTE/URBANWASTE22': (20, 20),
    'городской блок URBAN_WASTE/URBANWASTE30': (20, 20),
    'городской блок URBAN_WASTE/URBANWASTE61': (20, 20),
    'городской блок URBAN_WASTE/URBANWASTE62': (30, 30),
    'городской блок WESTOWN_TROPICAL/WESTOWN_05': (20, 20),
    'природный блок CULTA/CULTAFARM22': (20, 20),
    'природный блок CULTA/CULTASOLHUGE01': (30, 30),
    'природный блок CULTA_PP/CULTAFARM00': (20, 20),
    'природный блок CULTA_UBER/CULTAFARM00': (20, 20),
    'природный блок CULTA_UBER/CULTAFARM07': (20, 20),
    'природный блок CULTA_UBER/CULTAFARM14': (20, 20),
    'природный блок CULTA_UBER/CULTAFARM22': (20, 20),
    'природный блок DESERTREFINERY/DSRTREFI_05': (20, 20),
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
    'городской блок CHEMTOWNGHOUL/CHEMTOWN09': 'CHEMTOWNGHOUL/CHEMTOWN09',
    'городской блок CHEMTOWNGHOUL/CHEMTOWN11': 'CHEMTOWNGHOUL/CHEMTOWN11',
    'городской блок CHEMTOWNGHOUL/CHEMTOWN12': 'CHEMTOWNGHOUL/CHEMTOWN12',
    'городской блок URBAN/MADURBAN29': 'URBAN/MADURBAN29',
    'городской блок URBAN/NEURBAN04': 'URBAN/NEURBAN04',
    'городской блок URBAN/URBAN09d': 'URBAN/URBAN09d',
    'городской блок URBAN/URBANBR': 'URBAN/URBANBR',
    'городской блок URBANJUNKUFO/URBANJUNK06': 'URBANJUNKUFO/URBANJUNK06',
    'городской блок URBANJUNKUFO/URBANJUNK07': 'URBANJUNKUFO/URBANJUNK07',
    'городской блок URBANJUNKUFO/URBANJUNK09': 'URBANJUNKUFO/URBANJUNK09',
    'городской блок URBANJUNKUFO/URBANJUNK13': 'URBANJUNKUFO/URBANJUNK13',
    'городской блок URBANJUNKUFO/URBANJUNK32': 'URBANJUNKUFO/URBANJUNK32',
    'городской блок URBANJUNKUFO/URBANJUNKDIO_06': 'URBANJUNKUFO/URBANJUNKDIO_06',
    'городской блок URBANJUNKWOODUFO/URBANJUNK07': 'URBANJUNKWOODUFO/URBANJUNK07',
    'городской блок URBANJUNKWOODUFO/URBANJUNK09': 'URBANJUNKWOODUFO/URBANJUNK09',
    'городской блок URBANLUX/EXPANDEDTERROR13': 'URBANLUX/EXPANDEDTERROR13',
    'городской блок URBANLUX/MADURBAN23': 'URBANLUX/MADURBAN23',
    'городской блок URBANLUX/URBAN15': 'URBANLUX/URBAN15',
    'городской блок URBANWAR/EXPANDEDTERROR19': 'URBANWAR/EXPANDEDTERROR19',
    'городской блок URBANWAR/MADURBAN11': 'URBANWAR/MADURBAN11',
    'городской блок URBANWAR/MADURBAN23': 'URBANWAR/MADURBAN23',
    'городской блок URBANWAR/MADURBAN29': 'URBANWAR/MADURBAN29',
    'городской блок URBANWAR/URBAN05': 'URBANWAR/URBAN05',
    'городской блок URBANWAR/URBAN09d': 'URBANWAR/URBAN09d',
    'городской блок URBANWAR/URBANBR': 'URBANWAR/URBANBR',
    'городской блок URBANWAR/URBANDIO02': 'URBANWAR/URBANDIO02',
    'городской блок URBANWAR/URBANMY': 'URBANWAR/URBANMY',
    'городской блок WESTOWN_GRASS/WESTOWN_16': 'WESTOWN_GRASS/WESTOWN_16',
    'городской блок WESTOWN_TROPICAL/WESTOWN_05': 'WESTOWN_TROPICAL/WESTOWN_05',
    'городской блок WESTOWN_TROPICAL/WESTOWN_16': 'WESTOWN_TROPICAL/WESTOWN_16',
    'природный блок CULTA/CULTAFARM04': 'CULTA/CULTAFARM04',
    'природный блок CULTA/CULTAFARM22': 'CULTA/CULTAFARM22',
    'природный блок CULTA/CULT_NEW18': 'CULTA/CULT_NEW18',
    'природный блок CULTA_PP/CULTA30': 'CULTA_PP/CULTA30',
    'природный блок CULTA_PP/CULTA31': 'CULTA_PP/CULTA31',
    'природный блок CULTA_PP/CULTAFARM00': 'CULTA_PP/CULTAFARM00',
    'природный блок CULTA_PP/CULTAFARM02': 'CULTA_PP/CULTAFARM02',
    'природный блок CULTA_PP/CULTAFARM03': 'CULTA_PP/CULTAFARM03',
    'природный блок CULTA_PP/CULTAFARM04': 'CULTA_PP/CULTAFARM04',
    'природный блок CULTA_PP/CULTASOL01': 'CULTA_PP/CULTASOL01',
    'природный блок CULTA_PP/CULT_NEW17': 'CULTA_PP/CULT_NEW17',
    'природный блок CULTA_PP/CULT_NEW18': 'CULTA_PP/CULT_NEW18',
    'природный блок CULTA_UBER/CULTA16': 'CULTA_UBER/CULTA16',
    'природный блок CULTA_UBER/CULTA17': 'CULTA_UBER/CULTA17',
    'природный блок CULTA_UBER/CULTA18': 'CULTA_UBER/CULTA18',
    'природный блок CULTA_UBER/CULTA19': 'CULTA_UBER/CULTA19',
    'природный блок CULTA_UBER/CULTA30': 'CULTA_UBER/CULTA30',
    'природный блок CULTA_UBER/CULTA31': 'CULTA_UBER/CULTA31',
    'природный блок CULTA_UBER/CULTAFARM00': 'CULTA_UBER/CULTAFARM00',
    'природный блок CULTA_UBER/CULTAFARM02': 'CULTA_UBER/CULTAFARM02',
    'природный блок CULTA_UBER/CULTAFARM03': 'CULTA_UBER/CULTAFARM03',
    'природный блок CULTA_UBER/CULTAFARM04': 'CULTA_UBER/CULTAFARM04',
    'природный блок CULTA_UBER/CULTAFARM05': 'CULTA_UBER/CULTAFARM05',
    'природный блок CULTA_UBER/CULTAFARM14': 'CULTA_UBER/CULTAFARM14',
    'природный блок CULTA_UBER/CULTAFARM22': 'CULTA_UBER/CULTAFARM22',
    'природный блок CULTA_UBER/CULT_NEW16': 'CULTA_UBER/CULT_NEW16',
    'природный блок CULTA_UBER/CULT_NEW17': 'CULTA_UBER/CULT_NEW17',
    'природный блок CULTA_UBER/CULT_NEW18': 'CULTA_UBER/CULT_NEW18',
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot18_scen.py", PS.sha("tools/collapse_pilot18_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v8 as E
    E.install()                                   # M0j5, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
