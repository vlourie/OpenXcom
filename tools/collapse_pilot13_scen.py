#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, тринадцатая партия: остаток кандидатов партии 10 после третьего листа видов предметов.

Как партии 11 и 12 (кандидаты cand10.tsv с непросмотренными предметами слота o выше z0 вне деревьев), третий лист.
Разбор 21.10 - лист scratchpad cp15/kinds13.png (299 видов у 28 оставшихся кандидатов): мебель, декор, вазы, свечи,
надгробия, лестницы и ступени пирамиды, каменная кладка храма стоят на полу своей клетки - модель держит их
правилом по умолчанию. Не взяты блоки с каменной и земляной массой (как в партиях 11 и 12, и ещё горные наборы MOUNT,
MOUNTMUD, MOUNTSAND, MOUNTSNOW2, MOUNTMOON, SIBERIABASE, CAVEBLACK, SIETCH_DARK кроме крошки 17/36/77, лунные кубы
COMPLEXBITSMOON 0-3): срез горы удивил бы игрока. Одноимённые
с той же моделью, что уже в пилоте, не берутся; с другой - имя ТЕРРЕЙН/БЛОК (NAME_AS). Отбор - scratchpad cp15/kinds13.py,
pick13.py, dup13.py, mk13.py. Модель M0j4 с веткой D.

    py -3.13 tools\collapse_pilot13_scen.py define   census/collapse/pilot13/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot13"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('CHEMTOWNGHOUL', 'CHEMTOWN95', 'городской блок CHEMTOWNGHOUL/CHEMTOWN95', 'chemtown95'),
    ('LAMIA_VILLAGE', 'LAM_VILLAGE_MIDDLE06', 'городской блок LAMIA_VILLAGE/LAM_VILLAGE_MIDDLE06', 'lamvillagemiddle06'),
    ('MUMMY_VILLAGE_SETTLEMENT', 'MUM_VILLAGE_MIDDLE06', 'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_MIDDLE06', 'mumvillagemiddle06'),
    ('NECROPOLIS', 'NECROPOLIS_12', 'городской блок NECROPOLIS/NECROPOLIS_12', 'necropolis12'),
    ('U_PLANET_VOID', 'UPLANETV_28', 'городской блок U_PLANET_VOID/UPLANETV_28', 'uplanetv28'),
    ('JUNGLETEMPLE', 'MUJUNGLE04', 'природный блок JUNGLETEMPLE/MUJUNGLE04', 'mujungle04'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot13_scen.py", PS.sha("tools/collapse_pilot13_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v7d as D
    D.install()                                   # M0j4, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
