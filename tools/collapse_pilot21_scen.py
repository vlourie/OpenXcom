#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, двадцать первая партия: правительственная база GOVT_BASE_DEFENSE (тикет XP-000294).

Тикет XP-000294, слово Vitali 23.10 «фонари добавлять»: двухсекционный уличный фонарь ROADSGREEN:15 (z0) и
ROADSGREEN:16 (z1, без пола) - нижнюю снесли, верхняя висит. Террейн GOVT_BASE_DEFENSE отбор партий 10-20 отсекал
по слову BASE (фильтр баз игрока), а это наземная карта. Здесь все его целые блоки, кроме GOVBASE_D_08 (бункер
пилота 0), по тем же фильтрам: разметка без сомнений, под M0j5 на целом ничего не висит, скалы нет. Лист видов
scratchpad cp23/kinds21_1.png (27 видов, 23.10): мебель, стены, ящики, плакаты, голова фонаря - массы нет.
Фонари - колонны ветки D (collapse_v5.tree_structure5, как столбы партии 9). Отбор - scratchpad cp23/cand21.py,
kinds21.py, mk21make.py, mk21.py. Модель M0j5 (collapse_v8); частичные - PFALL зданий (collapse_partial21_scen).

    py -3.13 tools\collapse_pilot21_scen.py define   census/collapse/pilot21/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot21"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_01', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_01', 'govbased01'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_05', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_05', 'govbased05'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_06', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_06', 'govbased06'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_07', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_07', 'govbased07'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_09', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_09', 'govbased09'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_11', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_11', 'govbased11'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_12', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_12', 'govbased12'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_13', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_13', 'govbased13'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_14', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_14', 'govbased14'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_15', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_15', 'govbased15'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_16', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_16', 'govbased16'),
    ('GOVT_BASE_DEFENSE', 'GOVBASE_D_NS_00', 'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_NS_00', 'govbasedns00'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_05': (20, 20),
    'городской блок GOVT_BASE_DEFENSE/GOVBASE_D_07': (20, 20),
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot21_scen.py", PS.sha("tools/collapse_pilot21_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v8 as E
    E.install()                                   # M0j5, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
