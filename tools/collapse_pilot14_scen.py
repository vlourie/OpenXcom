#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, четырнадцатая партия: пары п. 9, где под M0j5 на целом ничего не висит (cand14).

Кандидаты - блоки из сейвов, которые M0j4 считала висящими, а M0j5 (устойчивость по связям) держит; четвёртый лист.
Разбор 21.10 - листы scratchpad cp16/kinds14_1..6.png (172 вида у 36 кандидатов): мебель, декор, ванны, лампы,
лестницы, клумбы, сено стоят на полу своей клетки - модель держит их
правилом по умолчанию. Не взяты блоки с каменной и земляной массой (как в партиях 11-13, и ещё земля сада
MANSIONGARDEN:10 и MANSIONGARDEN_MAG:10 - грунт вокруг подвала особняков EMANSION): срез грунта удивил бы
игрока. Одноимённые
с той же моделью, что уже в пилоте, не берутся; с другой - имя ТЕРРЕЙН/БЛОК (NAME_AS). Отбор - scratchpad cp16/kinds14.py,
gen14.py, dup14.py, mk14.py. Модель M0j5 (collapse_v8) с веткой D. INDUSTRIALSLUM/INDUSTRIALSLUMDIO07 не взят:
под M0j5 на целом блоке висят 3 стены (collapse_v8.hanging).

    py -3.13 tools\collapse_pilot14_scen.py define   census/collapse/pilot14/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot14"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('CHEMTOWN', 'CHEMTOWN03', 'городской блок CHEMTOWN/CHEMTOWN03', 'chemtownchemtown03'),
    ('CHEMTOWN', 'CHEMTOWN06', 'городской блок CHEMTOWN/CHEMTOWN06', 'chemtownchemtown06'),
    ('CHEMTOWNGHOUL', 'CHEMTOWN03', 'городской блок CHEMTOWNGHOUL/CHEMTOWN03', 'chemtownghoulchemtown03'),
    ('CHEMTOWNGHOUL', 'CHEMTOWN06', 'городской блок CHEMTOWNGHOUL/CHEMTOWN06', 'chemtownghoulchemtown06'),
    ('CHEMTOWNGHOUL', 'CHEMTOWN10', 'городской блок CHEMTOWNGHOUL/CHEMTOWN10', 'chemtown10'),
    ('CHEMTOWNGHOUL', 'CHEMTOWN93', 'городской блок CHEMTOWNGHOUL/CHEMTOWN93', 'chemtown93'),
    ('CHEMTOWNGHOUL', 'CHEMTOWN96', 'городской блок CHEMTOWNGHOUL/CHEMTOWN96', 'chemtown96'),
    ('MUMMY_VILLAGE_SETTLEMENT', 'MUM_VILLAGE_W01', 'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_W01', 'mumvillagew01'),
    ('PORTTFTD5', 'PORTUFO27', 'городской блок PORTTFTD5/PORTUFO27', 'portufo27'),
    ('RURAL', 'VILBAN14', 'городской блок RURAL/VILBAN14', 'vilban14'),
    ('URBAN', 'EXPANDEDTERROR16', 'городской блок URBAN/EXPANDEDTERROR16', 'urbanexpandedterror16'),
    ('URBAN', 'URBAN09', 'городской блок URBAN/URBAN09', 'urbanurban09'),
    ('URBANLUX', 'EXPANDEDTERROR16', 'городской блок URBANLUX/EXPANDEDTERROR16', 'urbanluxexpandedterror16'),
    ('URBANWAR', 'EXPANDEDTERROR16', 'городской блок URBANWAR/EXPANDEDTERROR16', 'urbanwarexpandedterror16'),
    ('URBANWAR', 'EXPANDEDTERROR23', 'городской блок URBANWAR/EXPANDEDTERROR23', 'expandedterror23'),
    ('URBANWAR', 'URBAN09', 'городской блок URBANWAR/URBAN09', 'urbanwarurban09'),
    ('URBAN_WASTE', 'URBANWASTE51', 'городской блок URBAN_WASTE/URBANWASTE51', 'urbanwaste51'),
    ('URBAN_WASTE', 'URBANWASTE52', 'городской блок URBAN_WASTE/URBANWASTE52', 'urbanwaste52'),
    ('URBAN_WASTE', 'URBANWASTE60', 'городской блок URBAN_WASTE/URBANWASTE60', 'urbanwaste60'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_W01': (10, 20),
    'городской блок RURAL/VILBAN14': (20, 20),
    'городской блок URBAN/URBAN09': (20, 20),
    'городской блок URBANWAR/EXPANDEDTERROR23': (20, 20),
    'городской блок URBANWAR/URBAN09': (20, 20),
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
    'городской блок CHEMTOWN/CHEMTOWN03': 'CHEMTOWN/CHEMTOWN03',
    'городской блок CHEMTOWN/CHEMTOWN06': 'CHEMTOWN/CHEMTOWN06',
    'городской блок CHEMTOWNGHOUL/CHEMTOWN03': 'CHEMTOWNGHOUL/CHEMTOWN03',
    'городской блок CHEMTOWNGHOUL/CHEMTOWN06': 'CHEMTOWNGHOUL/CHEMTOWN06',
    'городской блок URBAN/EXPANDEDTERROR16': 'URBAN/EXPANDEDTERROR16',
    'городской блок URBAN/URBAN09': 'URBAN/URBAN09',
    'городской блок URBANLUX/EXPANDEDTERROR16': 'URBANLUX/EXPANDEDTERROR16',
    'городской блок URBANWAR/EXPANDEDTERROR16': 'URBANWAR/EXPANDEDTERROR16',
    'городской блок URBANWAR/URBAN09': 'URBANWAR/URBAN09',
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot14_scen.py", PS.sha("tools/collapse_pilot14_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v8 as E
    E.install()                                   # M0j5, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
