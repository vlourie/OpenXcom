#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, двенадцатая партия: кандидаты партии 10 со вторым листом разобранных видов предметов.

Как партия 11 (кандидаты cand10.tsv с непросмотренными предметами слота o выше z0 вне деревьев), второй лист. Разбор
21.10 - лист scratchpad cp15/kinds12.png (128 видов у кандидатов, которым не хватало до восьми видов): мебель, декор,
ящики, грибы и цветы, лестницы, статуи, гребни дюн и валуны на вершинах гор стоят на полу своей клетки - модель держит их
правилом по умолчанию. Не взяты блоки с каменной и земляной массой (как в партии 11, и ещё лава LAM_BASE:60, скалы
MOUNTROCK и MOUNTWASTE2 40/66/67/68): срез горы удивил бы игрока. Одноимённые
с той же моделью, что уже в пилоте, не берутся; с другой - имя ТЕРРЕЙН/БЛОК (NAME_AS). Отбор - scratchpad cp15/kinds12.py,
pick12.py, dup12.py, mk12.py. Модель M0j4 с веткой D.

    py -3.13 tools\collapse_pilot12_scen.py define   census/collapse/pilot12/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot12"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('ISLANDURBAN', 'ISLANDURBAN09', 'городской блок ISLANDURBAN/ISLANDURBAN09', 'islandurban09'),
    ('LAMIA_VILLAGE', 'LAM_VILLAGE_MIDDLE_BIG01', 'городской блок LAMIA_VILLAGE/LAM_VILLAGE_MIDDLE_BIG01', 'lamvillagemiddlebig01'),
    ('LAMIA_VILLAGE', 'LAM_VILLAGE_MIDDLE_BIG03', 'городской блок LAMIA_VILLAGE/LAM_VILLAGE_MIDDLE_BIG03', 'lamvillagemiddlebig03'),
    ('MUMMY_VILLAGE_SETTLEMENT', 'MUM_VILLAGE_MIDDLE05', 'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_MIDDLE05', 'mumvillagemiddle05'),
    ('MUMMY_VILLAGE_SETTLEMENT', 'MUM_VILLAGE_MIDDLE07', 'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_MIDDLE07', 'mumvillagemiddle07'),
    ('MUMMY_VILLAGE_SETTLEMENT', 'MUM_VILLAGE_MIDDLE_BIG03', 'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_MIDDLE_BIG03', 'mumvillagemiddlebig03'),
    ('MUMMY_VILLAGE_SETTLEMENT', 'MUM_VILLAGE_NW01', 'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_NW01', 'mumvillagenw01'),
    ('PORTTFTD5', 'PORTUFO20', 'городской блок PORTTFTD5/PORTUFO20', 'portufo20'),
    ('URBANWAR', 'NEURBAN04', 'городской блок URBANWAR/NEURBAN04', 'neurban04'),
    ('U_PLANET_VOID', 'UPLANETV_27', 'городской блок U_PLANET_VOID/UPLANETV_27', 'uplanetv27'),
    ('U_PLANET_VOID', 'UPLANETV_NS_00', 'городской блок U_PLANET_VOID/UPLANETV_NS_00', 'uplanetvns00'),
    ('DESERT', 'DESERT14', 'природный блок DESERT/DESERT14', 'desertdesert14'),
    ('DESERTREFINERY', 'DESERT14', 'природный блок DESERTREFINERY/DESERT14', 'desertrefinerydesert14'),
    ('MOUNTBD_MUD', 'MOUNTBD07', 'природный блок MOUNTBD_MUD/MOUNTBD07', 'mountbdmudmountbd07'),
    ('MOUNTBD_MUD', 'MOUNTBD08', 'природный блок MOUNTBD_MUD/MOUNTBD08', 'mountbdmudmountbd08'),
    ('MOUNTBD_SANDY', 'MOUNTBD07', 'природный блок MOUNTBD_SANDY/MOUNTBD07', 'mountbdsandymountbd07'),
    ('MOUNTBD_SANDY', 'MOUNTBD08', 'природный блок MOUNTBD_SANDY/MOUNTBD08', 'mountbdsandymountbd08'),
    ('MOUNTBD_SNOW', 'MOUNTBD07', 'природный блок MOUNTBD_SNOW/MOUNTBD07', 'mountbdsnowmountbd07'),
    ('MOUNTBD_SNOW', 'MOUNTBD08', 'природный блок MOUNTBD_SNOW/MOUNTBD08', 'mountbdsnowmountbd08'),
    ('MOUNTBD_TROPICAL', 'MOUNTBD07', 'природный блок MOUNTBD_TROPICAL/MOUNTBD07', 'mountbdtropicalmountbd07'),
    ('MOUNTBD_TROPICAL', 'MOUNTBD08', 'природный блок MOUNTBD_TROPICAL/MOUNTBD08', 'mountbdtropicalmountbd08'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок LAMIA_VILLAGE/LAM_VILLAGE_MIDDLE_BIG01': (20, 20),
    'городской блок LAMIA_VILLAGE/LAM_VILLAGE_MIDDLE_BIG03': (20, 20),
    'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_MIDDLE_BIG03': (20, 20),
    'городской блок PORTTFTD5/PORTUFO20': (20, 20),
    'городской блок URBANWAR/NEURBAN04': (20, 20),
    'природный блок DESERT/DESERT14': (20, 20),
    'природный блок DESERTREFINERY/DESERT14': (20, 20),
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
    'природный блок DESERT/DESERT14': 'DESERT/DESERT14',
    'природный блок DESERTREFINERY/DESERT14': 'DESERTREFINERY/DESERT14',
    'природный блок MOUNTBD_MUD/MOUNTBD07': 'MOUNTBD_MUD/MOUNTBD07',
    'природный блок MOUNTBD_MUD/MOUNTBD08': 'MOUNTBD_MUD/MOUNTBD08',
    'природный блок MOUNTBD_SANDY/MOUNTBD07': 'MOUNTBD_SANDY/MOUNTBD07',
    'природный блок MOUNTBD_SANDY/MOUNTBD08': 'MOUNTBD_SANDY/MOUNTBD08',
    'природный блок MOUNTBD_SNOW/MOUNTBD07': 'MOUNTBD_SNOW/MOUNTBD07',
    'природный блок MOUNTBD_SNOW/MOUNTBD08': 'MOUNTBD_SNOW/MOUNTBD08',
    'природный блок MOUNTBD_TROPICAL/MOUNTBD07': 'MOUNTBD_TROPICAL/MOUNTBD07',
    'природный блок MOUNTBD_TROPICAL/MOUNTBD08': 'MOUNTBD_TROPICAL/MOUNTBD08',
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot12_scen.py", PS.sha("tools/collapse_pilot12_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v7d as D
    D.install()                                   # M0j4, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
