#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, девятая партия: лес и столбы (слово Vitali 20.10, после п. 8 docs/research/building-collapse-ideas-2026-10-19.md).

Ветка D (ствол держит крону, collapse_v5.tree_structure5 и collapse_v4.tree_hold4) перенесена в движок: перебитый
ствол роняет свою крону, срубленный столб - то, что на нём. Отбор (scratchpad cp14/cand9.py): единственное
стоп-условие блока по переписи census/collapse/pilot4/pick_all.tsv - деревья; на целом ничего не висит, нет
неопределённой разметки; блок стоит целиком в сейвах переписи на своём террейне; не в пилотах 4-8; природа можно
(лес), базы, корабли, пещеры и Марс - нет; у блока нет непросмотренных предметов слота o выше z0 вне деревьев
(виды листа партии 7). Вышло 32 блока: 21 лес (FOREST) и 11 городских (COMRCURBAN, RURAL VILBAN36).

Без участка в 4+ клетки (лес) сценариев пилота 0m нет: деревья проверяют частичные сценарии collapse_partial9_scen
(срубить ствол у земли, перебить ствол, срубить столб). Сценарии 0m городских блоков - правило пилота как есть.
Модель M0j4.

    py -3.13 tools\collapse_pilot9_scen.py define   census/collapse/pilot9/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS

OUT = "census/collapse/pilot9"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ("COMRCURBAN", "COMRCURBAN20", "двор торгового квартала COMRCURBAN20", "comrcurban20"),
    ("COMRCURBAN", "COMRCURBAN21", "двор торгового квартала COMRCURBAN21", "comrcurban21"),
    ("COMRCURBAN", "COMRCURBAN24", "двор торгового квартала COMRCURBAN24", "comrcurban24"),
    ("COMRCURBAN", "COMRCURBAN26", "двор торгового квартала COMRCURBAN26", "comrcurban26"),
    ("COMRCURBAN", "COMRCURBAN27", "двор торгового квартала COMRCURBAN27", "comrcurban27"),
    ("COMRCURBAN", "COMRCURBAN29", "двор торгового квартала COMRCURBAN29", "comrcurban29"),
    ("COMRCURBAN", "COMRCURBAN34", "двор торгового квартала COMRCURBAN34", "comrcurban34"),
    ("COMRCURBAN", "COMRCURBAN35", "двор торгового квартала COMRCURBAN35", "comrcurban35"),
    ("COMRCURBAN", "COMRCURBAN36", "двор торгового квартала COMRCURBAN36", "comrcurban36"),
    ("COMRCURBAN", "COMRCURBAN37", "двор торгового квартала COMRCURBAN37", "comrcurban37"),
    ("COMRCURBAN", "COMRCURBAN47", "двор торгового квартала COMRCURBAN47", "comrcurban47"),
    ("RURAL", "VILBAN36", "двор деревни VILBAN36", "vilban36"),
    ("FOREST", "CIVFOREST00", "лес CIVFOREST00", "civforest00"),
    ("FOREST", "FINNIKFOREST00", "лес FINNIKFOREST00", "finnikforest00"),
    ("FOREST", "FINNIKFOREST04", "лес FINNIKFOREST04", "finnikforest04"),
    ("FOREST", "FINNIKFOREST05", "лес FINNIKFOREST05", "finnikforest05"),
    ("FOREST", "FINNIKFOREST06", "лес FINNIKFOREST06", "finnikforest06"),
    ("FOREST", "FOREST05", "лес FOREST05", "forest05"),
    ("FOREST", "FOREST06", "лес FOREST06", "forest06"),
    ("FOREST", "FOREST07", "лес FOREST07", "forest07"),
    ("FOREST", "FOREST08", "лес FOREST08", "forest08"),
    ("FOREST", "FOREST_ROAD_SN00", "лесная дорога FOREST_ROAD_SN00", "forestroadsn00"),
    ("FOREST", "FOREST_ROAD_SN01", "лесная дорога FOREST_ROAD_SN01", "forestroadsn01"),
    ("FOREST", "FOREST_ROAD_SN02", "лесная дорога FOREST_ROAD_SN02", "forestroadsn02"),
    ("FOREST", "FOREST_ROAD_WE00", "лесная дорога FOREST_ROAD_WE00", "forestroadwe00"),
    ("FOREST", "FOREST_ROAD_WE01", "лесная дорога FOREST_ROAD_WE01", "forestroadwe01"),
    ("FOREST", "FOREST_ROAD_WE02", "лесная дорога FOREST_ROAD_WE02", "forestroadwe02"),
    ("FOREST", "FOREST_ROAD_XX00", "лесная дорога FOREST_ROAD_XX00", "forestroadxx00"),
    ("FOREST", "SOLFOREST12", "лес SOLFOREST12", "solforest12"),
    ("FOREST", "SOLFOREST13", "лес SOLFOREST13", "solforest13"),
    ("FOREST", "SOLFOREST14", "лес SOLFOREST14", "solforest14"),
    ("FOREST", "SOLFOREST16", "лес SOLFOREST16", "solforest16"),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {bn: 20 for bn in ("COMRCURBAN24", "COMRCURBAN26", "COMRCURBAN27", "CIVFOREST00")}
BOX = {ru: (0, SIZE.get(bn, 10) - 1, 0, SIZE.get(bn, 10) - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)


def trees(C, blk):
    """Колонны и кроны ветки D (collapse_v5.tree_structure5) при разметке модели и какие колонны - деревья."""
    import collapse_v2 as V
    import collapse_v3 as T
    import collapse_v5 as H
    f2 = "".join(c for c in C.MODEL if c not in T.V3_FLAGS).replace("V", "")
    with C.marked_roles(blk):
        cls = {k: V.eff_cls(k, p, f2) for k, p in blk.parts.items()}
        role = {k: p.get("role", "") for k, p in blk.parts.items()}
        cols, crowns = H.tree_structure5(blk, cls, role)
    return cols, crowns, {xy for xy, st in cols.items() if T.is_tree(blk, st)}


def load():
    """Как collapse_pilot_scen.load, но здания - целые блоки карт (collapse_census.all_blocks), а не 0h/0i."""
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
        f.write("%s\t%s\n" % ("tools/collapse_pilot9_scen.py", PS.sha("tools/collapse_pilot9_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v7d as D
    D.install()                                   # M0j4, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
