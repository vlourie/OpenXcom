#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0d обрушения зданий: v3 поверх v2 - дерево, обшивка, пролёт и консоль по типу конструкции,
обвал относительно исходного состояния, отчёт по этажам. Движок не трогается, модель v2 не меняется (только роли).

ТЗ - docs/research/building-collapse-task-2026-10-07.md, отчёт - building-collapse-stage0d-2026-10-07.md.
evaluate3 без своих флагов даёт ровно evaluate2 (py -3.13 tools\collapse_v3.py selfcheck).

Свои флаги evaluate3 (поверх флагов v2, по умолчанию база "RUA"):
  D - модель дерева: основание (предмет на z0), колонна ствола (предметы над ним в той же клетке без пола),
      куски кроны (предметы выше земли без пола, не в колонне) привязаны к ОДНОЙ колонне: рядом по
      Чебышёву 1 на том же этаже, при нескольких - по смещению, выученному на однозначных случаях
      (census\collapse\stage0d\tree_offsets.tsv), иначе ближайшая, при равенстве держат ВСЕ равные.
      Кусок без колонны рядом, но рядом с уже привязанным куском кроны того же этажа, наследует колонны
      этого куска ("по кроне", волнами) - дальний край широкой кроны пальмы.
      Кусок держится, только если цела колонна его дерева до его этажа. Соседнее дерево не держит.
      Кусок у несущей стены своей клетки - крепление, остаётся по правилам v2.
  H - обшивка (роль HULL) не несущая: корабль на наземной карте считается отдельно (модель корпуса).
  S - пролёт и консоль по типу пола (тип - по целому блоку, см. collapse_spans.py):
        кровля над помещением (ничего на клетке и выше) - пролёт до 16 (лёгкая кровля амбара);
        кровля над улицей (навес) - консоль 0 от прямой опоры: клетка за стеной уже консоль в клетку;
        остальное - как v2 (консоль 2, пролёт 12).
  K - (v2) гипотеза E04: нагруженный пол держится только прямо или балкой.
  Q - (v2) гипотеза: угол рамы - клетка с прямыми опорами соседей и по x, и по y считается прямой (один шаг).
  N - навес на живых стойках (canopy_posted): связная группа кровли над улицей, под которой после
      разрушения стоит держащийся несущий предмет, - плита на стойках; без стоек остаётся консоль 0 (S).
  G - корпус как связное тело (hull_parts/hull_hold): блоки-суда по переписи census\collapse\ships\
      conn_blocks.tsv (группы craft, ufo-суда; вид ufo носят и здания - по виду не включать, R-260).
      Держится тело, касающееся z0; у блока без z0 - самое большое тело.
  J - всё судно одно жёсткое тело: шасси, стойки и груз тоже части корпуса (R-261). Опасность:
      груз может «приклеить» отломанное к корпусу.
  O - G и для всех блоков террейнов группы 3 (census\collapse\ships\terrain_groups.tsv: орбита,
      лайнеры, космический грузовик, BLANKSPACE; z0 - палуба или невидимая плита).
  W - невесомость на ORBIT_* и BLANKSPACE (гипотеза): самое большое тело СРЕДИ НЕ ДЕРЖАЩИХСЯ держит
      себя само (не плита z0 - R-258). Оторванное «уплывает» и считается не держащимся.
Роли (несущие COLUMN/TRUSS и др.) - список REVIEWED в collapse_v2.py: этап 0d дописал туда NUKE2 10 (TRUSS).

Обвал относительно исходного состояния: падает только то, что было опёрто на целом блоке или карте
и потеряло опору. Висящее до боя - отдельная категория («висит до боя»), его модель не роняет.

    py -3.13 tools\collapse_v3.py selfcheck
    py -3.13 tools\collapse_v3.py trees                       перепись деревьев, смещения кроны
    py -3.13 tools\collapse_v3.py floors --terrain T --block B --remove "o:5:5:0" [--flags RUADHS]
    py -3.13 tools\collapse_v3.py expect FILE [вариант ...]
    py -3.13 tools\collapse_v3.py onmap --terrain T --block B --remove ... [--flags ...]
"""
import argparse
import collections
import hashlib
import json
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402
import collapse_v2 as V                           # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("census", "collapse", "stage0d")
OFFSETS = OUT + "/tree_offsets.tsv"
V3_FLAGS = set("DHSNGJOW")
TERRAIN_GROUPS_TSV = "census/collapse/ships/terrain_groups.tsv"
L_ROOF = 16
C_CANOPY = 0
CLOSED = {"wall", "window", "hard", "door", "block", "edgewall"}
VESSELS_TSV = "census/collapse/ships/conn_blocks.tsv"
VESSEL_GROUPS = {"craft", "ufo-суда"}
HULL_CLS = {"hard", "wall", "window", "block", "column", "edgewall", "truss", "door"}

VARIANTS = {
    "v2:R+A": "RA", "v2:R+U+A": "RUA",
    "D": "RUAD", "DH": "RUADH", "DHS": "RUADHS", "DHSK": "RUADHSK",
}


def split_flags(flags):
    return "".join(c for c in flags if c not in V3_FLAGS), set(c for c in flags if c in V3_FLAGS)


# ------------------------------------------------------------------ тип пола

def exterior(blk, z, removed=frozenset()):
    """Клетки уровня z, достижимые от края блока без пересечения стен, окон, дверей и сплошных предметов."""
    lv = blk.lv[z]
    w = {xy for xy, key in lv["w"].items() if blk.parts[key]["cls"] in CLOSED and key not in removed}
    n = {xy for xy, key in lv["n"].items() if blk.parts[key]["cls"] in CLOSED and key not in removed}
    solid = {xy for xy, key in lv["o"].items() if blk.parts[key]["cls"] in CLOSED and key not in removed}
    seen, q = set(), deque()
    for x in range(blk.sx):
        if (x, 0) not in n:
            q.append((x, 0))
        q.append((x, blk.sy - 1))
    for y in range(blk.sy):
        if (0, y) not in w:
            q.append((0, y))
        q.append((blk.sx - 1, y))
    while q:
        xy = q.popleft()
        if xy in seen or xy in solid:
            continue
        seen.add(xy)
        x, y = xy
        if x + 1 < blk.sx and (x + 1, y) not in w:
            q.append((x + 1, y))
        if x > 0 and (x, y) not in w:
            q.append((x - 1, y))
        if y + 1 < blk.sy and (x, y + 1) not in n:
            q.append((x, y + 1))
        if y > 0 and (x, y) not in n:
            q.append((x, y - 1))
    return seen


def floor_types(blk):
    """Тип каждого пола выше земли по ЦЕЛОМУ блоку: ('улица'|'помещ', 'кровля'|'нагружен').
    Тип - свойство конструкции, поэтому считается до разрушения и в бою не меняется."""
    if getattr(blk, "_ftypes", None) is not None:
        return blk._ftypes
    ext = {z: exterior(blk, z) for z in range(blk.sz)}
    occ = collections.defaultdict(set)              # (x, y) -> этажи, где есть хоть что-то
    for (k, x, y, z) in blk.parts:
        occ[(x, y)].add(z)
    out = {}
    for z in range(1, blk.sz):
        lv = blk.lv[z]
        for xy, key in lv["f"].items():
            x, y = xy
            on = [lv["w"].get(xy), lv["w"].get((x + 1, y)), lv["n"].get(xy), lv["n"].get((x, y + 1)), lv["o"].get(xy)]
            above = any(zz > z for zz in occ[xy])
            out[key] = ("улица" if xy in ext[z - 1] else "помещ", "нагружен" if any(on) or above else "кровля")
    blk._ftypes = out
    return out


def canopy_posted(blk, removed, carry):
    """Навесы на своих стойках (флаг N, гипотеза этапа 0d): связная по полу группа целых клеток кровли
    над улицей одного этажа, под которой ПОСЛЕ разрушения стоит хоть один несущий предмет, который
    сам держится (в carry основного прогона). Такая группа - плита на стойках и держится как пол v2.
    Навес без живых стоек висит только на стене - ему остаётся консоль 0 (S)."""
    ft = floor_types(blk)
    can = {key for key, (over, load) in ft.items() if over == "улица" and load == "кровля"}
    out = set()
    for z in range(1, blk.sz):
        lv, below = blk.lv[z], blk.lv[z - 1]
        cells = {xy for xy, key in lv["f"].items() if key in can and key not in removed}
        seen = set()
        for start in cells:
            if start in seen:
                continue
            comp, q = {start}, deque([start])
            seen.add(start)
            while q:
                x, y = q.popleft()
                for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nb in cells and nb not in seen:
                        seen.add(nb)
                        comp.add(nb)
                        q.append(nb)
            if any(below["o"].get(xy) in carry for xy in comp):
                out.update(lv["f"][xy] for xy in comp)
    return out


# ------------------------------------------------------------------ корпус корабля

_VESSELS = None


def vessels():
    """Блоки-суда: корабли игрока (craft) и суда пришельцев и техника (ufo-суда) по переписи разведки
    census/collapse/ships/conn_blocks.tsv. Вид ufo в Пиратках носят и здания-локации (вышка, лагерь
    бандитов, бункер) - к ним модель корпуса не применяется."""
    global _VESSELS
    if _VESSELS is None:
        _VESSELS = set()
        with open(VESSELS_TSV, encoding=ENC) as f:
            for ln in f.read().splitlines()[1:]:
                r = ln.split("\t")
                if len(r) > 3 and r[3] in VESSEL_GROUPS:
                    _VESSELS.add((r[0].upper(), r[2].upper()))
    return _VESSELS


_HULL_TERRAINS = None


def hull_terrains():
    """Флаг O: террейны группы 3 разведки (ships/terrain_groups.tsv: орбитальные станции, космический
    грузовик, лайнеры на воде, BLANKSPACE) - земли нет, z0 - палуба или невидимая плита; все их блоки
    считаются одним судном (G)."""
    global _HULL_TERRAINS
    if _HULL_TERRAINS is None:
        with open(TERRAIN_GROUPS_TSV, encoding=ENC) as f:
            _HULL_TERRAINS = {r[0].upper() for r in (ln.split("\t") for ln in f.read().splitlines()[1:])
                              if len(r) > 1 and r[1] == "3"}
    return _HULL_TERRAINS


def part_cells(key):
    """Клетки, которых касается часть: стена края - обе клетки по сторонам края."""
    k, x, y, z = key
    if k == "w":
        return ((x - 1, y, z), (x, y, z))
    if k == "n":
        return ((x, y - 1, z), (x, y, z))
    return ((x, y, z),)


def hull_parts(blk, removed=frozenset(), rigid=False):
    """Компоненты связности целых частей корабля (флаг G). Связь: части одной клетки; пол клетки
    с её стенами и несущими предметами этажом ниже (пол лежит на них); стена на стене того же края
    этажом ниже; предмет на несущем предмете ниже; соседние полы одного этажа; соседние несущие
    предметы одного этажа (обшивка, переборки). Мебель держится только своей клеткой."""
    live = [key for key in blk.parts if key not in removed]
    parent = {k: k for k in live}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # J: всё судно - одно тело, шасси, стойки и грузы тоже его части (у мелких аппаратов шасси - "object")
    hull = set(live) if rigid else {k for k in live if k[0] != "o" or blk.parts[k]["cls"] in HULL_CLS}
    bycell = collections.defaultdict(list)
    for key in live:
        for c in part_cells(key):
            bycell[c].append(key)
    for ks in bycell.values():
        for k in ks[1:]:
            union(ks[0], k)
    alive = set(live)
    for key in live:
        k, x, y, z = key
        if k == "f" and z > 0:
            for b in bycell.get((x, y, z - 1), ()):
                if b in hull:
                    union(key, b)
        elif k in "wn" and z > 0 and (k, x, y, z - 1) in alive:
            union(key, (k, x, y, z - 1))
        elif k == "o" and z > 0 and ("o", x, y, z - 1) in hull:
            union(key, ("o", x, y, z - 1))
        if k == "f" or key in hull and k == "o":
            for nb in ((x + 1, y), (x, y + 1)):
                other = (k,) + nb + (z,)
                if other in alive and (k == "f" or other in hull):
                    union(key, other)
    comps = collections.defaultdict(set)
    for key in live:
        comps[find(key)].add(key)
    return list(comps.values())


def orbit_terrains():
    """Флаг W: орбитальные террейны группы 3 (ORBIT_*, BLANKSPACE) - невесомость."""
    return {t for t in hull_terrains() if t.startswith("ORBIT") or t == "BLANKSPACE"}


def hull_hold(blk, removed=frozenset(), rigid=False, weightless=False):
    """Флаг G (гипотеза этапа 0d): корабль и НЛО - жёсткое тело, пролёты и консоли внутри корпуса
    не проверяются. Корабль на земле (в целом блоке есть части на z0) держит компонента, которая
    касается z0 после разрушения; корабль в воздухе (z0 блока пуст) держит самая большая компонента
    - сам корпус. Отломанное от держащей компоненты падает."""
    comps = hull_parts(blk, removed, rigid)
    landed = any(k[3] == 0 for k in blk.parts)
    if landed:
        held = [c for c in comps if any(k[3] == 0 for k in c)]
        # W (гипотеза): в невесомости корпус станции держит сам себя, хотя невидимой плиты z0 не касается;
        # оторванное от самого большого тела не падает, а уплывает - здесь оно всё равно «не держится»
        # самое большое среди тел, не касающихся плиты: сама плита z0-1 бывает больше станции
        free = [c for c in comps if c not in held]
        if weightless and free:
            held.append(max(free, key=len))
    else:
        held = [max(comps, key=len)] if comps else []
    out = set().union(*held) if held else set()
    # предмет стоит на предмете клеткой ниже (верх высокого предмета на своём низу, ящик на ящике) - держится,
    # если держится нижний; связь в одну сторону: мебель корпус не несёт
    for key in sorted((k for c in comps for k in c if k[0] == "o" and k[3] > 0), key=lambda k: k[3]):
        if key not in out and ("o", key[1], key[2], key[3] - 1) in out:
            out.add(key)
    return out


# ------------------------------------------------------------------ дерево

def load_offsets():
    out = {}
    if os.path.exists(OFFSETS):
        with open(OFFSETS, encoding=ENC) as f:
            lines = f.read().splitlines()
        head = lines[0].split("\t")
        for ln in lines[1:]:
            r = dict(zip(head, ln.split("\t")))
            out[(r["set"].upper(), int(r["idx"]))] = (int(r["dx"]), int(r["dy"]))
    return out


_OFFS = None


def offsets():
    global _OFFS
    if _OFFS is None:
        _OFFS = load_offsets()
    return _OFFS


# Дерево - колонна с основанием из набора растительности или с ролью ствола/кроны. Список по наборам оснований
# колонн на наземных картах (перепись stage0d/tree_bases.tsv); фонари, статуи, столбы ворот деревом не считаются:
# их стопка держится цепочкой, но кроны к ним не привязываются.
NATURE_TOKENS = ("FOREST", "JUNGLE", "CORAL", "SEAWEED", "MOUNT", "TROP", "PALM", "TREE", "BUSH", "SWAMP", "VINE",
                 "FLORA", "CACTUS")


def is_tree(blk, stack):
    s = blk.parts[stack[0]]["set"].upper()
    return any(t in s for t in NATURE_TOKENS) or any(blk.parts[k].get("role") in ("TRUNK", "CROWN") for k in stack)


def tree_structure(blk, cls, role):
    """Колонны и куски кроны по ЦЕЛОМУ блоку (структура не зависит от разрушения).
    Возвращает cols: (x, y) -> [ключ z0, z1, ...] и crowns: ключ -> (тип привязки, [(x, y) колонн])."""
    if getattr(blk, "_trees", None) is not None:
        return blk._trees
    floors = [set(blk.lv[z]["f"]) for z in range(blk.sz)]

    def lateral_ok(key):
        k, x, y, z = key
        return k == "o" and z >= 1 and (x, y) not in floors[z] and cls[key] not in V.BEARING and \
            role[key] not in V.SPECIAL and role[key] not in ("DOOR",)

    cols = {}
    for xy, key in blk.lv[0]["o"].items():
        if cls[key] in V.BEARING and role[key] not in ("TRUNK", "CROWN"):
            continue
        stack = [key]
        z = 1
        while z < blk.sz:
            up = blk.lv[z]["o"].get(xy)
            if up is None or not lateral_ok(up):
                break
            stack.append(up)
            z += 1
        if len(stack) > 1:
            cols[xy] = stack
    in_col = {k for st in cols.values() for k in st}
    trees = {xy for xy, st in cols.items() if is_tree(blk, st)}
    offs = offsets()
    crowns = {}
    for z in range(1, blk.sz):
        for xy, key in sorted(blk.lv[z]["o"].items()):
            if key in in_col or not lateral_ok(key):
                continue
            x, y = xy
            near = [c for c in trees if max(abs(c[0] - x), abs(c[1] - y)) <= 1 and len(cols[c]) > z - 1]
            p = blk.parts[key]
            if len(near) == 1:
                crowns[key] = ("один", near)
            elif len(near) > 1:
                o = offs.get((p["set"].upper(), p["idx"]))
                if o and (x + o[0], y + o[1]) in near:
                    crowns[key] = ("выучено", [(x + o[0], y + o[1])])
                else:
                    d = {c: (c[0] - x) ** 2 + (c[1] - y) ** 2 for c in near}
                    m = min(d.values())
                    best = [c for c in near if d[c] == m]
                    crowns[key] = ("ближайшая" if len(best) == 1 else "неясно", best)
            else:
                below = blk.lv[z - 1]["o"].get(xy)
                if below in crowns:
                    crowns[key] = ("над кроной", crowns[below][1])
                else:
                    near2 = [c for c in trees if max(abs(c[0] - x), abs(c[1] - y)) <= 2 and len(cols[c]) > z - 1]
                    if len(near2) == 1:
                        crowns[key] = ("через клетку", near2)
                    else:
                        crowns[key] = ("без ствола", [])
        # этап 0d: дальний кусок кроны (листья пальмы за 3 клетки от ствола) - продолжение соседнего куска
        # той же кроны на этом этаже; соседи от разных деревьев - держат все (как «неясно»)
        lone = {xy: key for xy, key in blk.lv[z]["o"].items() if crowns.get(key, ("",))[0] == "без ствола"}
        while lone:
            got = {}
            for (x, y), key in lone.items():
                cs = set()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        k2 = blk.lv[z]["o"].get((x + dx, y + dy))
                        if k2 in crowns and crowns[k2][1] and (x + dx, y + dy) not in lone:
                            cs.update(crowns[k2][1])
                if cs:
                    got[(x, y)] = ("по кроне", sorted(cs))
            if not got:
                break
            for xy, v in got.items():
                crowns[lone.pop(xy)] = v
    blk._trees = (cols, crowns)
    return blk._trees


def tree_hold(blk, removed, cls, role, carry):
    """Какие части деревьев держатся: колонна - цепочкой от основания; кусок кроны - колонной своего
    дерева до своего этажа. Кусок у несущей стены своей клетки - не трогаем (крепление v2)."""
    cols, crowns = tree_structure(blk, cls, role)
    held_to = {}                                     # колонна -> верхний этаж непрерывной цепочки
    held = set()
    for xy, st in cols.items():
        top = -1
        for z, key in enumerate(st):
            if key in removed:
                break
            top = z
            held.add(key)
        held_to[xy] = top
    def on_wall(key):
        k, x, y, z = key
        lv = blk.lv[z]
        walls = [lv["w"].get((x, y)), lv["w"].get((x + 1, y)), lv["n"].get((x, y)), lv["n"].get((x, y + 1))]
        return any(w in carry and w not in removed for w in walls if w)

    managed = {k for st in cols.values() for k in st[1:] if not on_wall(k)}
    for key, (how, cs) in crowns.items():
        if not cs or on_wall(key):                   # без ствола и у стены - по правилам v2
            continue
        managed.add(key)
        if key in removed:
            continue
        need = min(key[3], max(len(cols[c]) - 1 for c in cs))
        if all(held_to[c] >= need for c in cs):
            held.add(key)
    return managed, held & managed


def cmd_trees(a):
    """Перепись деревьев по всем блокам: колонны, куски кроны по типу привязки; смещения кроны по записи
    из однозначных случаев - в tree_offsets.tsv."""
    roles = V.load_roles()
    global _OFFS
    _OFFS = {}
    learn = collections.defaultdict(collections.Counter)
    stat = collections.Counter()
    bases = collections.Counter()
    rows = []
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None or blk.sz < 2:
            continue
        V.apply_roles(blk, roles)
        fl = "RUA"
        cls = {key: V.eff_cls(key, p, fl) for key, p in blk.parts.items()}
        role = {key: p.get("role", "") for key, p in blk.parts.items()}
        cols, crowns = tree_structure(blk, cls, role)
        if not cols and not crowns:
            continue
        stat["блоков со стопками"] += 1
        stat["стопок (колонн)"] += len(cols)
        for xy, st in cols.items():
            tree = is_tree(blk, st)
            stat["  из них деревьев"] += tree
            bases[(blk.parts[st[0]]["set"].upper(), tree)] += 1
        for key, (how, cs) in crowns.items():
            stat["крона: " + how] += 1
            p = blk.parts[key]
            if how == "один":
                learn[(p["set"].upper(), p["idx"])][(cs[0][0] - key[1], cs[0][1] - key[2])] += 1
            if how in ("без ствола", "неясно"):
                rows.append((tname, bname, key[1], key[2], key[3], p["set"], p["idx"], how,
                             " ".join("%d,%d" % c for c in cs)))
    off_rows = []
    for (s, i), c in sorted(learn.items()):
        (dx, dy), n = c.most_common(1)[0]
        tot = sum(c.values())
        off_rows.append((s, i, dx, dy, n, tot, "%.2f" % (n / tot)))
    cc.write_tsv(OFFSETS, ["set", "idx", "dx", "dy", "n", "total", "share"], off_rows)
    cc.write_tsv(OUT + "/tree_bases.tsv", ["set", "tree", "columns"],
                 [(s, int(t), n) for (s, t), n in bases.most_common()])
    cc.write_tsv(OUT + "/tree_unassigned.tsv", ["terrain", "block", "x", "y", "z", "set", "idx", "how", "cols"], rows)
    for k, v in sorted(stat.items()):
        print("%-28s %d" % (k, v))
    print("смещений записано", len(off_rows), "->", OFFSETS)
    _OFFS = None


# ------------------------------------------------------------------ evaluate3

def evaluate3(blk, removed=frozenset(), flags="RUA", **kw):
    f2, f3 = split_flags(flags)
    saved = {}
    if "H" in f3:
        for key, p in blk.parts.items():
            if p.get("role") == "HULL":
                saved[key] = p["role"]
                p["role"] = "HULL_NB"
    try:
        sup, info = V.evaluate2(blk, removed, f2, **kw)
        carry = set(blk.carry)
        if "S" in f3:
            ft = floor_types(blk)
            kw_roof = dict(kw, L=max(kw.get("L", 12), L_ROOF))
            kw_can = dict(kw, C=C_CANOPY)
            s_roof, _ = V.evaluate2(blk, removed, f2, **kw_roof)
            s_can, _ = V.evaluate2(blk, removed, f2, **kw_can)
            posted = canopy_posted(blk, removed, carry) if "N" in f3 else set()
            for key, (over, load) in ft.items():
                if key in removed or load != "кровля":
                    continue
                if over == "улица" and key in posted:
                    pick = sup                                # навес на своих стойках - плита, как v2
                else:
                    pick = s_roof if over == "помещ" else s_can
                if key in pick:
                    sup.add(key)
                else:
                    sup.discard(key)
            V.evaluate2(blk, removed, f2, **kw)       # вернуть blk.carry основного прогона
        if "D" in f3:
            cls = {key: V.eff_cls(key, p, f2) for key, p in blk.parts.items()}
            role = {key: p.get("role", "") for key, p in blk.parts.items()}
            managed, held = tree_hold(blk, removed, cls, role, carry)
            sup -= managed
            sup |= held
        if "G" in f3 and ((blk.terrain.upper(), blk.name.upper()) in vessels() or
                          "O" in f3 and blk.terrain.upper() in hull_terrains()):
            sup = hull_hold(blk, removed, "J" in f3,
                            "W" in f3 and blk.terrain.upper() in orbit_terrains())
    finally:
        for key, r in saved.items():
            blk.parts[key]["role"] = r
    return sup, info


# ------------------------------------------------------------------ отчёт по этажам

def compress(keys):
    """Ключи (k, x, y, z) -> строка 'f:0-4:3:1 w:5:2:1' (подряд по x в строке)."""
    by = collections.defaultdict(list)
    for k, x, y, z in keys:
        by[(k, z, y)].append(x)
    out = []
    for (k, z, y), xs in sorted(by.items()):
        xs.sort()
        run = [xs[0], xs[0]]
        for x in xs[1:] + [None]:
            if x is not None and x == run[1] + 1:
                run[1] = x
                continue
            out.append("%s:%s:%d:%d" % (k, str(run[0]) if run[0] == run[1] else "%d-%d" % tuple(run), y, z))
            if x is not None:
                run = [x, x]
    return " ".join(out)


def chain_depth(blk, removed, fallen):
    """Звено цепочки: 1 - часть в клетке удалённого или соседней (по стороне, сверху, снизу);
    дальше - через уже упавшие."""
    cells = collections.defaultdict(set)
    for key in fallen:
        cells[(key[1], key[2], key[3])].add(key)
    depth = {}
    q = deque()
    seeds = {(k[1], k[2], k[3]) for k in removed}
    for (x, y, z) in seeds:
        for nb in ((x, y, z), (x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)):
            for key in cells.get(nb, ()):
                if key not in depth:
                    depth[key] = 1
                    q.append(key)
    while q:
        key = q.popleft()
        x, y, z = key[1], key[2], key[3]
        for nb in ((x, y, z), (x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)):
            for k2 in cells.get(nb, ()):
                if k2 not in depth:
                    depth[k2] = depth[key] + 1
                    q.append(k2)
    for key in fallen:
        depth.setdefault(key, 0)                     # 0 - не связано с удалённым соседством
    return depth


def floor_report(blk, removed, flags, unverified=frozenset()):
    """По этажам: удалено -> потеряло опору непосредственно (звено 1) -> обрушилось по цепочке (звено 2+)
    -> сохранилось; висевшее до боя и непроверенное - отдельно."""
    sup0, _ = evaluate3(blk, frozenset(), flags)
    sup, _ = evaluate3(blk, frozenset(removed), flags)
    hung = {k for k in blk.parts if k[3] > 0 and k not in sup0}
    fallen = {k for k in sup0 if k not in sup and k not in removed and k[3] > 0}
    depth = chain_depth(blk, removed, fallen)
    lines = []
    for z in range(blk.sz - 1, -1, -1):
        rz = [k for k in removed if k[3] == z]
        d1 = [k for k in fallen if k[3] == z and depth[k] == 1]
        dn = [k for k in fallen if k[3] == z and depth[k] != 1]
        stay = [k for k in blk.parts if k[3] == z and k in sup and k not in removed]
        hz = [k for k in hung if k[3] == z]
        if not (rz or d1 or dn or hz):
            continue
        lines.append("этаж z=%d" % z)
        if rz:
            lines.append("  удалено (%d): %s" % (len(rz), compress(rz)))
        if d1:
            lines.append("  потеряло опору непосредственно (%d): %s" % (len(d1), compress(d1)))
        if dn:
            lines.append("  обрушилось по цепочке (%d): %s" % (len(dn), compress(dn)))
        lines.append("  сохранилось: %d частей%s" % (len(stay), (" (" + ", ".join(
            "%s %d" % (s, sum(1 for k in stay if k[0] == s)) for s in cc.KINDS if any(k[0] == s for k in stay)) + ")")
            if stay else ""))
        if hz:
            lines.append("  висело до боя, не трогается (%d): %s" % (len(hz), compress(hz)))
        uz = [k for k in fallen if k[3] == z and (k[1], k[2], k[3]) in unverified]
        if uz:
            lines.append("  из упавших в непроверенных клетках (%d): %s" % (len(uz), compress(uz)))
    return lines, {"removed": len(removed), "fallen_direct": sum(1 for k in fallen if depth[k] == 1),
                   "fallen_chain": sum(1 for k in fallen if depth[k] != 1), "hung_before": len(hung)}


def load_one(terrain, block, roles):
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args(), only_block=block, only_terrain=terrain):
        if blk is not None:
            return V.apply_roles(blk, roles)
    raise SystemExit("нет блока %s/%s" % (terrain, block))


def cmd_floors(a):
    roles = V.load_roles()
    blk = load_one(a.terrain, a.block, roles)
    rm = cc.select(blk, a.remove)
    lines, s = floor_report(blk, rm, a.flags)
    print("блок %s/%s, флаги %s, удалить: %s" % (a.terrain, a.block, a.flags, a.remove))
    print("\n".join(lines))
    print(s)


# ------------------------------------------------------------------ сценарии

def run_expect(path, pick, roles):
    expect = V.read_expect(path)
    blocks = V.load_blocks(expect, roles)
    res = collections.defaultdict(dict)
    for v in pick:
        fl = VARIANTS.get(v, v)
        for e in expect:
            blk = blocks[(e["terrain"].upper(), e["block"].upper())]
            sup0, _ = evaluate3(blk, frozenset(), fl)
            rm = cc.select(blk, e["remove"])
            sup, _ = evaluate3(blk, frozenset(rm), fl)
            mf = cc.select(blk, e.get("must_fall", "")) - rm
            ms = cc.select(blk, e.get("must_stand", "")) - rm
            stood = sorted(k for k in mf if k in sup and k in sup0)
            fell = sorted(k for k in ms if k not in sup and k in sup0)
            hf = sum(1 for k in mf if k not in sup0)
            hs = sum(1 for k in ms if k not in sup0)
            verdict = "PASS" if not stood and not fell else "FAIL"
            if not mf and not ms:
                verdict = "EMPTY"
            elif verdict == "PASS" and (hf or hs):
                verdict = "PASS*"
            res[e["id"]][v] = {"verdict": verdict, "stood": len(stood), "must_fall": len(mf), "fell": len(fell),
                               "must_stand": len(ms), "hung_before": hf + hs,
                               "stood_keys": compress(stood[:40]), "fell_keys": compress(fell[:40])}
    return expect, res


def cmd_expect(a):
    roles = V.load_roles()
    pick = a.variants or list(VARIANTS)
    with open(a.file, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    lock = os.path.splitext(a.file)[0] + ".lock.txt"
    if os.path.exists(lock):
        with open(lock, encoding=ENC) as f:
            txt = f.read()
        print("хэш", "совпадает с замком" if sha in txt else "НЕ СОВПАДАЕТ С ЗАМКОМ %s" % lock)
    else:
        print("замка нет:", lock)
    expect, res = run_expect(a.file, pick, roles)
    print("вердикт устояло/должно упасть упало/должно стоять h висело с начала")
    print("%-6s " % "id" + " ".join("%-18s" % v for v in pick))
    for e in expect:
        print("%-6s " % e["id"] + " ".join("%-18s" % ("%s %d/%d %d/%d h%d" % (
            r["verdict"], r["stood"], r["must_fall"], r["fell"], r["must_stand"], r["hung_before"]))
            for r in (res[e["id"]][v] for v in pick)))
    npass = {v: sum(res[e["id"]][v]["verdict"].startswith("PASS") for e in expect) for v in pick}
    print("PASS:", npass)
    tag = os.path.splitext(os.path.basename(a.file))[0]
    with open(OUT + "/expect3_%s.json" % tag, "w", encoding=ENC) as f:
        json.dump({"file": a.file, "sha256": sha, "variants": {v: VARIANTS.get(v, v) for v in pick},
                   "pass": npass, "result": res}, f, ensure_ascii=False, indent=1)
    if a.detail:
        for e in expect:
            for v in pick:
                r = res[e["id"]][v]
                if r["verdict"] == "FAIL":
                    print("%s %s устояло: %s | упало: %s" % (e["id"], v, r["stood_keys"], r["fell_keys"]))


# ------------------------------------------------------------------ на собранных картах

def cmd_onmap(a):
    """Сценарий блока на собранных картах боёв, где блок найден: удаление сдвигается на место блока,
    расчёт идёт по всей карте с соседями. Части вне проверенных клеток - отдельной строкой."""
    import collapse_battles as cb
    roles = V.load_roles()
    d = cb.Data(V.game_args())
    blk = load_one(a.terrain, a.block, roles)
    src_dir = V.OUT + "/source"
    names = sorted(n[:-4] + ".sav" for n in os.listdir(src_dir) if n.endswith(".pkl"))
    found = 0
    for name in names:
        ver_path = V.OUT + "/verified/" + name[:-4] + ".pkl"
        if not os.path.exists(ver_path):
            continue
        import pickle
        with open(ver_path, "rb") as f:
            ver = pickle.load(f)
        if not any(b.upper() == a.block.upper() for (_, b) in ver.values()):
            continue
        m, src = V.load_map(d, name, roles)
        pls = cb.find_placements(m, [blk], 0.5)
        for jac, _, b, ox, oy, oz, mm, nmap in pls:
            found += 1
            rm = {(k, x + ox, y + oy, z + oz) for (k, x, y, z) in cc.select(blk, a.remove)}
            rm &= set(m.parts)
            unver = {(x, y, z) for (x, y, z) in ((k[1], k[2], k[3]) for k in m.parts) if (x, y, z) not in ver}
            print("== %s  блок в (%d,%d,%d), совпадение %.2f, удалено на карте %d" % (name, ox, oy, oz, jac, len(rm)))
            lines, s = floor_report(m, rm, a.flags, unverified=unver)
            if a.local:                                  # только части в пределах блока +2 клетки
                pass
            print("\n".join(lines))
            print(s)
            sup0, _ = evaluate3(blk, frozenset(), a.flags)
            sup1, _ = evaluate3(blk, frozenset(cc.select(blk, a.remove)), a.flags)
            fb = {(k, x + ox, y + oy, z + oz) for (k, x, y, z) in blk.parts
                  if (k, x, y, z) in sup0 and (k, x, y, z) not in sup1}
            supm0, _ = evaluate3(m, frozenset(), a.flags)
            supm1, _ = evaluate3(m, frozenset(rm), a.flags)
            fm = {k for k in m.parts if k in supm0 and k not in supm1 and k not in rm}
            print("  против отдельного блока: упало только на карте %s | только в блоке %s" % (
                compress(sorted(fm - fb)) or "-", compress(sorted(fb - fm - rm)) or "-"))
    if not found:
        print("блок не найден ни на одной собранной карте")


# ------------------------------------------------------------------ самопроверка

def cmd_selfcheck(a):
    roles = V.load_roles()
    expect = V.read_expect("census/collapse/expect_v2.tsv")
    blocks = V.load_blocks(expect, roles)
    bad = 0
    for e in expect:
        blk = blocks[(e["terrain"].upper(), e["block"].upper())]
        rm = frozenset(cc.select(blk, e["remove"]))
        for fl in ("", "RA", "RUA", "RTPAK"):
            s2, i2 = V.evaluate2(blk, rm, fl)
            s3, i3 = evaluate3(blk, rm, fl)
            if s2 != s3 or i2 != i3:
                bad += 1
                print("РАСХОЖДЕНИЕ", e["id"], fl, len(s2 ^ s3))
    print("selfcheck v3 без своих флагов = v2:", "OK" if not bad else "РАСХОЖДЕНИЙ %d" % bad)
    return 1 if bad else 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selfcheck")
    sub.add_parser("trees")
    for name in ("floors", "onmap"):
        s = sub.add_parser(name)
        s.add_argument("--terrain", required=True)
        s.add_argument("--block", required=True)
        s.add_argument("--remove", required=True)
        s.add_argument("--flags", default="RUADHS")
        s.add_argument("--local", action="store_true")
    s = sub.add_parser("expect")
    s.add_argument("file")
    s.add_argument("variants", nargs="*")
    s.add_argument("--detail", action="store_true")
    a = ap.parse_args()
    return {"selfcheck": cmd_selfcheck, "trees": cmd_trees, "floors": cmd_floors, "expect": cmd_expect,
            "onmap": cmd_onmap}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
