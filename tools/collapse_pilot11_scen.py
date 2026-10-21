#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, одиннадцатая партия: кандидаты партии 10 с разобранными видами предметов.

Отбор как у партии 10 (cand10.tsv), но у этих блоков были непросмотренные предметы слота o выше z0 вне деревьев. Разбор
21.10 - лист scratchpad cp15/kinds10.png (80 видов у кандидатов, которым не хватало не больше трёх видов): мебель, декор,
ящики, урны, статуи, лестницы, кусты и низкие деревья на холмах леса стоят на полу своей клетки - модель держит их
правилом по умолчанию. Не взяты блоки с каменной и земляной массой (скалы DESERTROCKS_RED, MOUNTTROP, MOUNTGRASS 40/66/67,
засыпка METROBITS:30, CYBERWAREBITS:30, DOOM_BASE:60, METRO1:94, SIETCH_DARK:9): срез горы удивил бы игрока. Одноимённые
с той же моделью, что уже в пилоте, не берутся; с другой - имя ТЕРРЕЙН/БЛОК (NAME_AS). Отбор - scratchpad cp15/kinds10.py,
pick11.py, dup11.py, mk11.py. Модель M0j4 с веткой D.

    py -3.13 tools\collapse_pilot11_scen.py define   census/collapse/pilot11/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot11"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('CHEMTOWNGHOUL', 'CHEMTOWN04', 'городской блок CHEMTOWNGHOUL/CHEMTOWN04', 'chemtownghoulchemtown04'),
    ('LAMIA_VILLAGE', 'LAM_VILLAGE_CANAL03', 'городской блок LAMIA_VILLAGE/LAM_VILLAGE_CANAL03', 'lamvillagecanal03'),
    ('MUMMY_VILLAGE_SETTLEMENT', 'MUM_VILLAGE_MIDDLE10', 'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_MIDDLE10', 'mumvillagemiddle10'),
    ('MUMMY_VILLAGE_SETTLEMENT', 'MUM_VILLAGE_MIDDLE11', 'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_MIDDLE11', 'mumvillagemiddle11'),
    ('PORTTFTD5', 'PORTUFO09', 'городской блок PORTTFTD5/PORTUFO09', 'portufo09'),
    ('PORTTFTD5', 'PORTUFO37', 'городской блок PORTTFTD5/PORTUFO37', 'portufo37'),
    ('URBANJUNKUFO', 'URBANJUNK21', 'городской блок URBANJUNKUFO/URBANJUNK21', 'urbanjunkufourbanjunk21'),
    ('URBANJUNKUFO', 'URBANJUNKDIO_02', 'городской блок URBANJUNKUFO/URBANJUNKDIO_02', 'urbanjunkufourbanjunkdio02'),
    ('URBANJUNKWOODUFO', 'URBANJUNK21', 'городской блок URBANJUNKWOODUFO/URBANJUNK21', 'urbanjunkwoodufourbanjunk21'),
    ('URBANJUNKWOODUFO', 'URBANJUNK41', 'городской блок URBANJUNKWOODUFO/URBANJUNK41', 'urbanjunk41'),
    ('URBANJUNKWOODUFO', 'URBANJUNKDIO_02', 'городской блок URBANJUNKWOODUFO/URBANJUNKDIO_02', 'urbanjunkwoodufourbanjunkdio02'),
    ('URBANLUX', 'EXPANDEDTERROR14', 'городской блок URBANLUX/EXPANDEDTERROR14', 'urbanluxexpandedterror14'),
    ('URBANWAR', 'EXPANDEDTERROR17', 'городской блок URBANWAR/EXPANDEDTERROR17', 'expandedterror17'),
    ('URBANWAR', 'URBANDIO01', 'городской блок URBANWAR/URBANDIO01', 'urbandio01'),
    ('URBAN_WASTE', 'URBANWASTE64', 'городской блок URBAN_WASTE/URBANWASTE64', 'urbanwaste64'),
    ('U_PLANET_VOID', 'UPLANETV_22', 'городской блок U_PLANET_VOID/UPLANETV_22', 'uplanetv22'),
    ('U_PLANET_VOID', 'UPLANETV_NS_01', 'городской блок U_PLANET_VOID/UPLANETV_NS_01', 'uplanetvns01'),
    ('FOREST', 'FINNIKFOREST02', 'природный блок FOREST/FINNIKFOREST02', 'forestfinnikforest02'),
    ('FOREST', 'FINNIKFOREST03', 'природный блок FOREST/FINNIKFOREST03', 'forestfinnikforest03'),
    ('FOREST', 'FOREST11', 'природный блок FOREST/FOREST11', 'forestforest11'),
    ('FOREST2BLACK', 'FINNIKFOREST02', 'природный блок FOREST2BLACK/FINNIKFOREST02', 'forest2blackfinnikforest02'),
    ('FOREST2BLACK', 'FINNIKFOREST03', 'природный блок FOREST2BLACK/FINNIKFOREST03', 'forest2blackfinnikforest03'),
    ('FOREST2BLACK', 'FOREST11', 'природный блок FOREST2BLACK/FOREST11', 'forest2blackforest11'),
    ('FORESTRED', 'FINNIKFOREST02', 'природный блок FORESTRED/FINNIKFOREST02', 'forestredfinnikforest02'),
    ('FORESTRED', 'FOREST11', 'природный блок FORESTRED/FOREST11', 'forestredforest11'),
    ('FORESTSNOW', 'FINNIKFOREST02', 'природный блок FORESTSNOW/FINNIKFOREST02', 'forestsnowfinnikforest02'),
    ('FORESTSNOW', 'FINNIKFOREST03', 'природный блок FORESTSNOW/FINNIKFOREST03', 'forestsnowfinnikforest03'),
    ('FORESTSNOW', 'FOREST11', 'природный блок FORESTSNOW/FOREST11', 'forestsnowforest11'),
    ('FORESTSNOW', 'SOLFORESTHUGE01', 'природный блок FORESTSNOW/SOLFORESTHUGE01', 'solforesthuge01'),
    ('FORESTSWAMP', 'FINNIKFOREST02', 'природный блок FORESTSWAMP/FINNIKFOREST02', 'forestswampfinnikforest02'),
    ('FORESTSWAMP', 'FINNIKFOREST03', 'природный блок FORESTSWAMP/FINNIKFOREST03', 'forestswampfinnikforest03'),
    ('FORESTSWAMP', 'FORESTSWAMP12', 'природный блок FORESTSWAMP/FORESTSWAMP12', 'forestswamp12'),
    ('FORESTSWAMP', 'FORESTSWAMP17', 'природный блок FORESTSWAMP/FORESTSWAMP17', 'forestswamp17'),
    ('FORESTSWAMP_WASTE', 'FINNIKFOREST02', 'природный блок FORESTSWAMP_WASTE/FINNIKFOREST02', 'forestswampwastefinnikforest02'),
    ('FORESTSWAMP_WASTE', 'FINNIKFOREST03', 'природный блок FORESTSWAMP_WASTE/FINNIKFOREST03', 'forestswampwastefinnikforest03'),
    ('MOUNTBD_ARBOREAL', 'MOUNTBD07', 'природный блок MOUNTBD_ARBOREAL/MOUNTBD07', 'mountbdarborealmountbd07'),
    ('MOUNTBD_ARBOREAL', 'MOUNTBD08', 'природный блок MOUNTBD_ARBOREAL/MOUNTBD08', 'mountbdarborealmountbd08'),
    ('MOUNTBD_DEAD', 'MOUNTBD07', 'природный блок MOUNTBD_DEAD/MOUNTBD07', 'mountbddeadmountbd07'),
    ('MOUNTBD_DEAD', 'MOUNTBD08', 'природный блок MOUNTBD_DEAD/MOUNTBD08', 'mountbddeadmountbd08'),
    ('MOUNTBD_ERODED', 'MOUNTBD07', 'природный блок MOUNTBD_ERODED/MOUNTBD07', 'mountbderodedmountbd07'),
    ('MOUNTBD_ERODED', 'MOUNTBD08', 'природный блок MOUNTBD_ERODED/MOUNTBD08', 'mountbderodedmountbd08'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок PORTTFTD5/PORTUFO37': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK21': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK21': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK41': (20, 20),
    'городской блок URBANWAR/EXPANDEDTERROR17': (20, 20),
    'городской блок URBANWAR/URBANDIO01': (20, 20),
    'природный блок FOREST/FOREST11': (20, 20),
    'природный блок FOREST2BLACK/FOREST11': (20, 20),
    'природный блок FORESTRED/FOREST11': (20, 20),
    'природный блок FORESTSNOW/FOREST11': (20, 20),
    'природный блок FORESTSNOW/SOLFORESTHUGE01': (30, 30),
    'природный блок FORESTSWAMP/FORESTSWAMP12': (20, 20),
    'природный блок FORESTSWAMP/FORESTSWAMP17': (20, 20),
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
    'городской блок CHEMTOWNGHOUL/CHEMTOWN04': 'CHEMTOWNGHOUL/CHEMTOWN04',
    'городской блок URBANJUNKUFO/URBANJUNK21': 'URBANJUNKUFO/URBANJUNK21',
    'городской блок URBANJUNKUFO/URBANJUNKDIO_02': 'URBANJUNKUFO/URBANJUNKDIO_02',
    'городской блок URBANJUNKWOODUFO/URBANJUNK21': 'URBANJUNKWOODUFO/URBANJUNK21',
    'городской блок URBANJUNKWOODUFO/URBANJUNKDIO_02': 'URBANJUNKWOODUFO/URBANJUNKDIO_02',
    'городской блок URBANLUX/EXPANDEDTERROR14': 'URBANLUX/EXPANDEDTERROR14',
    'природный блок FOREST/FINNIKFOREST02': 'FOREST/FINNIKFOREST02',
    'природный блок FOREST/FINNIKFOREST03': 'FOREST/FINNIKFOREST03',
    'природный блок FOREST/FOREST11': 'FOREST/FOREST11',
    'природный блок FOREST2BLACK/FINNIKFOREST02': 'FOREST2BLACK/FINNIKFOREST02',
    'природный блок FOREST2BLACK/FINNIKFOREST03': 'FOREST2BLACK/FINNIKFOREST03',
    'природный блок FOREST2BLACK/FOREST11': 'FOREST2BLACK/FOREST11',
    'природный блок FORESTRED/FINNIKFOREST02': 'FORESTRED/FINNIKFOREST02',
    'природный блок FORESTRED/FOREST11': 'FORESTRED/FOREST11',
    'природный блок FORESTSNOW/FINNIKFOREST02': 'FORESTSNOW/FINNIKFOREST02',
    'природный блок FORESTSNOW/FINNIKFOREST03': 'FORESTSNOW/FINNIKFOREST03',
    'природный блок FORESTSNOW/FOREST11': 'FORESTSNOW/FOREST11',
    'природный блок FORESTSWAMP/FINNIKFOREST02': 'FORESTSWAMP/FINNIKFOREST02',
    'природный блок FORESTSWAMP/FINNIKFOREST03': 'FORESTSWAMP/FINNIKFOREST03',
    'природный блок FORESTSWAMP_WASTE/FINNIKFOREST02': 'FORESTSWAMP_WASTE/FINNIKFOREST02',
    'природный блок FORESTSWAMP_WASTE/FINNIKFOREST03': 'FORESTSWAMP_WASTE/FINNIKFOREST03',
    'природный блок MOUNTBD_ARBOREAL/MOUNTBD07': 'MOUNTBD_ARBOREAL/MOUNTBD07',
    'природный блок MOUNTBD_ARBOREAL/MOUNTBD08': 'MOUNTBD_ARBOREAL/MOUNTBD08',
    'природный блок MOUNTBD_DEAD/MOUNTBD07': 'MOUNTBD_DEAD/MOUNTBD07',
    'природный блок MOUNTBD_DEAD/MOUNTBD08': 'MOUNTBD_DEAD/MOUNTBD08',
    'природный блок MOUNTBD_ERODED/MOUNTBD07': 'MOUNTBD_ERODED/MOUNTBD07',
    'природный блок MOUNTBD_ERODED/MOUNTBD08': 'MOUNTBD_ERODED/MOUNTBD08',
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot11_scen.py", PS.sha("tools/collapse_pilot11_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v7d as D
    D.install()                                   # M0j4, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
