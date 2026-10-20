#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, восьмая партия (п. 8 docs/research/building-collapse-ideas-2026-10-19.md): дома с деревьями.

Отбор как у седьмой партии (census/collapse/pilot4/pick_all.tsv), но единственное стоп-условие здания - деревья
(ветка D: стволы и кроны collapse_v5.tree_structure5): без баз и природы, на целом ничего не висит, нет
неопределённой разметки, блок стоит целиком в сейвах переписи на своём террейне, не в пилотах 3-7, у здания 20+
частей выше z0 не из деревьев (scratchpad cp12/cand8.py). Непросмотренные предметы слота o выше z0 - 71 вид листа
cp12/kinds8.png: мебель, декор, ящики, бочки, кусты в кадках (JUNGLE:73/74/77), фонарь COMROADS:16; у всех,
кроме двух стопок ящиков INDUSLUM:43 (INDUSTRIALSLUM01), пол в своей клетке есть.

Ветку D в движок не переносим: уронить ствол с кроной - новая механика, нужно слово Vitali. Деревья выходят из
модели целиком - их части не входят в части блока, в бою не падают и не считаются снятыми; движок знает их
только как свои записи участка (список keep, foreignParts). Перенос честен, только если остальное здание от
деревьев не зависит, а деревья - от здания: это проверяет collapse_pilot_export.py check (TREES_OUT).

URBANJUNKDIO_02 из списка снят: кусты o:6,2..4,1 под кроной ствола 7,3 полная модель держит деревом, а правило
tree_parts их не ловит (не колонна от земли, не крона) - перенос расходится с evaluate7c.

Сценарии - правило пилота 0m (collapse_pilot_scen.scenarios), из снятого убраны части деревьев. Модель M0j4.

    py -3.13 tools\collapse_pilot8_scen.py define   census/collapse/pilot8/pilot_scen.tsv и замок
    py -3.13 tools\collapse_pilot8_scen.py run      результат census/collapse/pilot8/pilot_result.tsv
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS

OUT = "census/collapse/pilot8"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ("COMRCURBAN", "COMRCURBAN54", "дом торгового квартала COMRCURBAN54", "comrcurban54"),
    ("COMRCURBAN", "COMRCURBAN41", "дом торгового квартала COMRCURBAN41", "comrcurban41"),
    ("COMRCURBAN", "COMRCURBAN13", "дом торгового квартала COMRCURBAN13", "comrcurban13"),
    ("CHEMTOWN", "CHEMTOWN04", "дом химгорода CHEMTOWN04", "chemtown04"),
    ("INDUSTRIALSLUM", "INDUSTRIALSLUM10", "дом трущоб INDUSTRIALSLUM10", "induslum10"),
    ("CHEMTOWN_OPENROADS", "CHEMTOWN20R", "дом химгорода CHEMTOWN20R", "chemtown20r"),
    ("URBAN", "EXPANDEDTERROR14", "дом города EXPANDEDTERROR14", "expterror14"),
    ("COMRCURBAN", "COMRCURBAN06", "торговый квартал COMRCURBAN06", "comrcurban06"),
    ("URBANJUNKUFO", "URBANJUNK10", "дом свалки URBANJUNK10", "urbanjunk10"),
    ("COMRCURBAN", "COMRCURBAN58", "дом торгового квартала COMRCURBAN58", "comrcurban58"),
    ("COMRCURBAN", "COMRCURBAN_MEY_01", "дом торгового квартала COMRCURBAN_MEY_01", "comrcurbanmey01"),
    ("URBAN", "URBANMY", "квартал URBANMY", "urbanmy"),
    ("INDUSTRIALSLUM", "INDUSTRIALSLUM01", "квартал трущоб INDUSTRIALSLUM01", "induslum01"),
    ("COMRCURBAN", "COMRCURBAN23", "дом торгового квартала COMRCURBAN23", "comrcurban23"),
    ("COMRCURBAN", "COMRCURBAN_MEY_02", "торговый квартал COMRCURBAN_MEY_02", "comrcurbanmey02"),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {bn: 20 for bn in ("COMRCURBAN06", "URBANMY", "INDUSTRIALSLUM01", "COMRCURBAN_MEY_02")}
BOX = {ru: (0, SIZE.get(bn, 10) - 1, 0, SIZE.get(bn, 10) - 1) for tn, bn, ru, en in BUILDINGS}
TREES_OUT = set(LABEL_EN)            # здания, у которых деревья вынесены из модели (collapse_pilot_export)


def tree_parts(C, blk):
    """Части деревьев блока: колонны (стволы и стопки от земли) и кроны ветки D (collapse_v5.tree_structure5) при
    разметке модели. Крона «без ствола» - не дерево: фонарь на стене COMROADS:16, вывеска, предмет на этаже без пола
    в клетке; в полной модели она падает вместе с домом (collapse_pilot_export check: 7 зданий из 16), поэтому
    остаётся в модели обычной частью."""
    import collapse_v2 as V
    import collapse_v3 as T
    import collapse_v5 as H
    f2 = "".join(c for c in C.MODEL if c not in T.V3_FLAGS).replace("V", "")
    with C.marked_roles(blk):
        cls = {k: V.eff_cls(k, p, f2) for k, p in blk.parts.items()}
        role = {k: p.get("role", "") for k, p in blk.parts.items()}
        cols, crowns = H.tree_structure5(blk, cls, role)
    return {k for st in cols.values() for k in st} | {k for k, how in crowns.items() if how[0] != "без ствола"}


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


_scenarios = PS.scenarios


def scenarios(CT, blk):
    """Правило пилота 0m без частей деревьев в снятом; сценарий, у которого снятое опустело, выпадает."""
    import collapse_attach_v2 as A2
    tree = tree_parts(A2.use(), blk)
    res = []
    for sc, z, cells, rm, ex in _scenarios(CT, blk):
        rm = [k for k in rm if k not in tree]
        if rm:
            res.append((sc, z, cells, rm, ex))
    return res


def use():
    """Переключает collapse_pilot_scen на список, загрузку и файлы этой партии."""
    PS.OUT = OUT
    PS.SCEN = OUT + "/pilot_scen.tsv"
    PS.LOCK = OUT + "/pilot_scen.lock.txt"
    PS.RESULT = OUT + "/pilot_result.tsv"
    PS.PILOT = PILOT
    PS.load = load
    PS.scenarios = scenarios
    return PS


def cmd_define():
    use()
    PS.cmd_define()
    with open(PS.LOCK, "a", encoding=PS.ENC) as f:
        f.write("%s\t%s\n" % ("tools/collapse_pilot8_scen.py", PS.sha("tools/collapse_pilot8_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v7d as D
    D.install()                                   # M0j4, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
    else:
        use()
        PS.cmd_run()
