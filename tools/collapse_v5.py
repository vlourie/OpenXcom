#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0h обрушения зданий: модель M0h - расчёт связанной плиты вместо пролёта отдельной клетки.
Движок не трогается; M0f (collapse_v3), M0g (collapse_v4) и их замки не меняются.

Рецензия 0g: Y убрать; S и B переработать через модель плиты (связность покрытия, отверстия, опоры, консоли;
потеря всех опор или отделение части сквозным разрывом - обвал); настил, тент и скаты - свои правила; ствол -
по явной роли и цепочке частей; сначала контролируемые конструкции, потом реальные здания.

M0h = M0f без S, N, B (и без Y M0g) плюс Z и V:
  Z - плита. Покрытие этажа (пол и крепления скатов и тентов) - одна конструкция:
      * опора - пол на несущем под собой (как M0f: стена края, несущий предмет, массив), крепление ската и
        тента, угол рамы Q;
      * пролёт - прямая балка по x или y между опорами длиной до L, как M0f, но отверстие в плите балку не
        рвёт, если его можно обойти: ряд пустых клеток по оси перекрыт, когда соседняя параллельная линия
        плиты цела над всем рядом и ещё по клетке с концов. Сквозной разрыв (обойти нельзя) балку рвёт;
      * концы балки - только опоры и клетки, уже взятые балкой (как B M0f), порядок 2;
      * консоль - до C от опоры или клетки на балке: по прямой с тем же обходом отверстий или по связному
        покрытию. Плита без опор, отделённый разрывом кусок без своих опор - не держится ничем;
      * НАСТИЛ (клетка, не входящая в целом блоке ни в один сплошной квадрат пола 3x3) - не плита: балка
        только по прямой без обхода, консоль только от опоры - как M0f;
      * тип покрытия из целого блока (collapse_v3.floor_types): кровля над помещением - пролёт L_ROOF,
        навес над улицей без стоек - консоль C_CANOPY (стойки - несущее под плитой навеса), как S/N M0f;
      * тент (M) и скаты (A) - свои правила M0f без изменений.
  V - ствол дерева по цепочке: колонна дерева начинается частью с ролью TRUNK или частью у земли, которая
      доходит до верха своей клетки (LOFT, слой 10 или 11), и продолжается вверх, пока каждая часть
      доходит до верха клетки. Мелкий предмет у корня (не до верха клетки) стволом не становится; часть над
      ним - кусок кроны, привязанный к ближайшим стволам по правилам M0f. Общая крона - UNSUPPORTED (судья).

    py -3.13 tools\collapse_v5.py selfcheck      без Z и V = M0f бит в бит; целые блоки: M0h против M0f
    py -3.13 tools\collapse_v5.py synth          контролируемые конструкции (stage0h/synth_truth.tsv)
"""
import collections
import hashlib
import json
import os
import sys
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402
import collapse_v2 as V                           # noqa: E402
import collapse_v3 as T                           # noqa: E402
import collapse_pilot as P                        # noqa: E402
import collapse_v4 as G                           # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0h"
M0F = P.MODEL                                     # RUADHSNQIMGOWB
MODEL = "RUADHQIMGOWZV"                           # M0h
CANDIDATE_RULES = "ZVQIM"
ORIG_E2 = V.evaluate2


def alt_flags(model, e):
    """Модель без правила e. Без Z - полы по правилам M0f (S, N, B)."""
    f = model.replace(e, "")
    if e == "Z":
        f += "SNB"
    return f


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ------------------------------------------------------------------ плита (Z)

def light_intact(blk, z):
    """Настил: клетки пола целого блока на этаже z, не входящие ни в один сплошной квадрат пола 3x3."""
    cache = blk.__dict__.setdefault("_light5", {})
    if z not in cache:
        cache[z] = V.light_floors(set(blk.lv[z]["f"]))
    return cache[z]


def walk(xy, d, med, ends, slab, bridge, lim):
    """Расстояние от xy по прямой в сторону d до первой клетки ends, не дальше lim, или None. Пустые клетки
    по пути перекрываются, если bridge и соседняя параллельная линия плиты цела над всем пустым рядом и по
    клетке с концов (отверстие, а не сквозной разрыв)."""
    dx, dy = d
    x, y = xy
    dist = 0
    while True:
        x += dx
        y += dy
        dist += 1
        if dist > lim:
            return None
        if (x, y) in ends:
            return dist
        if (x, y) in med:
            continue
        if not bridge:
            return None
        run = [(x, y)]
        cx, cy = x, y
        while True:
            cx += dx
            cy += dy
            if dist + len(run) > lim:
                return None
            if (cx, cy) in med or (cx, cy) in ends:
                break
            run.append((cx, cy))
        cover = [(x - dx, y - dy)] + run + [(cx, cy)]
        px, py = dy, dx
        if not any(all((a + px * s, b + py * s) in slab for a, b in cover) for s in (1, -1)):
            return None
        x, y = cx, cy
        dist += len(run)
        if (x, y) in ends:
            return dist


def beam_len(xy, med, ends, slab, bridge, lim):
    if xy in ends:
        return 0
    best = None
    for ax in ((1, 0), (0, 1)):
        a = walk(xy, ax, med, ends, slab, bridge, lim)
        if a is None:
            continue
        b = walk(xy, (-ax[0], -ax[1]), med, ends, slab, bridge, lim)
        if b is None:
            continue
        best = a + b if best is None else min(best, a + b)
    return best


def slab_floors(blk, z, live, below, carry, floors, direct, ranch, direct_b, C, L):
    """Плита этажа z: какие клетки пола держатся. Возвращает okf, расстояние консоли от опоры (как info M0f)
    и длину балки."""
    ft = T.floor_types(blk)
    light = light_intact(blk, z)
    fkey = live["f"]
    med = floors | ranch
    slab = {xy for xy in floors if xy not in light}
    # навес над улицей: связная группа клеток навеса со стойкой под собой - плита со стойками (N M0f)
    can = {xy for xy in floors if ft.get(fkey[xy]) == ("улица", "кровля")}
    posted, seen = set(), set()
    for s in can:
        if s in seen:
            continue
        comp, q = {s}, deque([s])
        seen.add(s)
        while q:
            x, y = q.popleft()
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in can and nb not in seen:
                    seen.add(nb)
                    comp.add(nb)
                    q.append(nb)
        if any(below["o"].get(xy) in carry for xy in comp):
            posted |= comp

    def lim_l(xy):
        t = ft.get(fkey.get(xy))
        return max(L, T.L_ROOF) if t == ("помещ", "кровля") else L

    def lim_c(xy):
        return T.C_CANOPY if xy in can and xy not in posted else C

    held = set(direct_b)
    best_l = {}
    for _ in range(2):
        base = set(held)
        for xy in floors:
            nl = beam_len(xy, med, base, slab, xy in slab, lim_l(xy))
            if nl is not None and (xy not in best_l or nl < best_l[xy]):
                best_l[xy] = nl
            if nl is not None and nl <= lim_l(xy):
                held.add(xy)
    okf = {xy for xy in floors if xy in held}
    # консоль: плита - от опор и клеток на балке, по прямой с обходом отверстий или по связному покрытию;
    # настил - только от опоры, по покрытию (как M0f)
    geo_held = V.consoles(held & med, floors, C)
    geo_dir = V.consoles(direct_b, floors, C)
    for xy in floors - okf:
        c = lim_c(xy)
        if xy in slab:
            if geo_held.get(xy) is not None and geo_held[xy] <= c:
                okf.add(xy)
                continue
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                w = walk(xy, d, med, held, slab, True, c)
                if w is not None and w <= c:
                    okf.add(xy)
                    break
        elif geo_dir.get(xy) is not None and geo_dir[xy] <= c:
            okf.add(xy)
    return okf, geo_dir, best_l


def evaluate2z(blk, removed=frozenset(), flags="", C=2, L=12, mass_rule=True, order=2, carry_rule="any",
               run_c=2, roof_reach=1, **kw):
    """collapse_v2.evaluate2 с плитой Z вместо расчёта полов. Без Z - исходный evaluate2."""
    if "Z" not in flags:
        return ORIG_E2(blk, removed, flags, C=C, L=L, mass_rule=mass_rule, order=order, carry_rule=carry_rule,
                       run_c=run_c, roof_reach=roof_reach, **kw)
    A = "A" in flags
    cls = {key: V.eff_cls(key, p, flags) for key, p in blk.parts.items()}
    role = {key: p.get("role", "") for key, p in blk.parts.items()}
    bearing = lambda key: cls[key] in V.BEARING      # noqa: E731
    special = (lambda key: role[key] in V.SPECIAL) if A else (lambda key: False)   # noqa: E731
    sup, carry, info = set(), set(), {}
    hangers = []
    for z in range(blk.sz):
        lvl = blk.lv[z]
        live = {k: {xy: key for xy, key in lvl[k].items() if key not in removed} for k in cc.KINDS}
        if z == 0:
            for k in cc.KINDS:
                sup.update(live[k].values())
                carry.update(key for key in live[k].values() if bearing(key))
            continue
        below = blk.lv[z - 1]
        props = set()
        for (x, y), key in below["w"].items():
            if key in carry:
                props.update(((x, y), (x - 1, y)))
        for (x, y), key in below["n"].items():
            if key in carry:
                props.update(((x, y), (x, y - 1)))
        for (x, y), key in below["o"].items():
            if key in carry:
                props.add((x, y))
                for dx, dy in cc.EDGE_NB.get(blk.parts[key]["rec"]["big_wall"], ()):
                    props.add((x + dx, y + dy))
        floors = set(live["f"])
        mass = {xy for xy, key in live["o"].items() if bearing(key)}
        msup = set()
        for xy in mass:
            under = below["o"].get(xy)
            if under in carry or (xy in floors and xy in props):
                msup.add(xy)
        if mass_rule:
            q = deque(msup)
            while q:
                x, y = q.popleft()
                for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nb in mass and nb not in msup:
                        msup.add(nb)
                        q.append(nb)
        direct = floors & (props | msup)
        roofc = {xy: key for xy, key in live["o"].items() if A and role[key] in ("ROOF", "TARP")}
        ranch = set()
        for (x, y), key in roofc.items():
            edges = [below["w"].get((x, y)), below["w"].get((x + 1, y)),
                     below["n"].get((x, y)), below["n"].get((x, y + 1)), below["o"].get((x, y))]
            if any(e in carry for e in edges if e) or \
                    (below["o"].get((x, y)) in sup and role.get(below["o"].get((x, y))) in ("ROOF", "TARP")):
                ranch.add((x, y))
        direct_b = direct | ranch
        if "Q" in flags:
            direct_b |= {(x, y) for (x, y) in floors - direct_b
                         if ((x + 1, y) in direct_b or (x - 1, y) in direct_b) and
                         ((x, y + 1) in direct_b or (x, y - 1) in direct_b)}
        okf, dist, best_l = slab_floors(blk, z, live, below, carry, floors, direct, ranch, direct_b, C, L)
        for xy in floors:
            info[live["f"][xy]] = (xy in direct, dist.get(xy), best_l.get(xy))
            if xy in okf:
                sup.add(live["f"][xy])
        lint = V.lintels(live, below, carry, bearing) if "I" in flags else set()
        for k, sides in (("w", lambda x, y: ((x, y), (x - 1, y))),
                         ("n", lambda x, y: ((x, y), (x, y - 1)))):
            for (x, y), key in live[k].items():
                under = below[k].get((x, y))
                if any(s in okf for s in sides(x, y)) or under in carry or key in lint:
                    sup.add(key)
                    if bearing(key) and (carry_rule == "any" or under in carry or key in lint or
                                         any(s in direct for s in sides(x, y))):
                        carry.add(key)
        furn = {xy for xy, key in live["o"].items() if cls[key] == "furniture" and not special(key)}
        fsup = set()
        for (x, y), key in live["o"].items():
            if special(key):
                continue
            under = below["o"].get((x, y))
            walls = [live["w"].get((x, y)), live["w"].get((x + 1, y)),
                     live["n"].get((x, y)), live["n"].get((x, y + 1))]
            if (x, y) in okf or (x, y) in msup or \
                    under in carry or (under in sup and cls[under] == "furniture") or \
                    any(w in carry for w in walls if w):
                sup.add(key)
                if bearing(key) and (carry_rule == "any" or under in carry or
                                     (x, y) in direct or (x, y) in msup):
                    carry.add(key)
                if (x, y) in furn:
                    fsup.add((x, y))
        q = deque(fsup | {xy for xy, key in live["o"].items() if key in sup and bearing(key)})
        while q:
            x, y = q.popleft()
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in furn and nb not in fsup:
                    fsup.add(nb)
                    sup.add(live["o"][nb])
                    q.append(nb)
        if not A:
            continue
        anch = set(ranch) | {xy for xy in roofc if xy in okf or xy in msup}
        dr = V.consoles(anch, set(roofc), roof_reach)
        for xy, d in dr.items():
            if d <= roof_reach:
                sup.add(roofc[xy])
        if "M" in flags:
            tset = {xy for xy, key in roofc.items() if role[key] == "TARP"}
            for xy in tset:
                nl = cc.beam(xy, tset, anch & tset)
                if nl is not None and nl <= V.L_TARP:
                    sup.add(roofc[xy])
        runc = {xy: key for xy, key in live["o"].items() if role[key] == "RUN"}
        ra = set()
        for (x, y), key in runc.items():
            under = below["o"].get((x, y))
            walls = [live["w"].get((x, y)), live["w"].get((x + 1, y)),
                     live["n"].get((x, y)), live["n"].get((x, y + 1))]
            nbo = [live["o"].get(nb) for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))]
            if (x, y) in okf or (x, y) in msup or under in carry or \
                    (under in sup and cls[under] == "furniture") or any(w in carry for w in walls if w) or \
                    any(o in carry for o in nbo if o):
                ra.add((x, y))
        rset = set(runc)
        rheld = set(ra) | {xy for xy in rset if (cc.beam(xy, rset, ra) or 99) <= L and cc.beam(xy, rset, ra) is not None}
        dr = V.consoles(rheld, rset, run_c)
        for xy, d in dr.items():
            if d <= run_c:
                sup.add(runc[xy])
        hangers += [(xy, z, key) for xy, key in live["o"].items() if role[key] == "HANGER"]
    for (x, y), z, key in hangers:
        above = blk.lv[z + 1]["f"].get((x, y)) if z + 1 < blk.sz else None
        walls = [blk.lv[z]["w"].get((x, y)), blk.lv[z]["w"].get((x + 1, y)),
                 blk.lv[z]["n"].get((x, y)), blk.lv[z]["n"].get((x, y + 1))]
        if (above and above in sup and above not in removed) or any(w in carry for w in walls if w):
            sup.add(key)
    blk.carry = carry
    return sup, info


# ------------------------------------------------------------------ ствол (V)

def reaches_top(p):
    lay = p["rec"]["layers"]
    return bool(lay[11] or lay[10])


def tree_structure5(blk, cls, role):
    """collapse_v3.tree_structure с поиском ствола по цепочке (V). Стопка строится как в M0f; не-деревья
    не меняются. У стопки дерева, чьё основание на z0 - не ствол (не TRUNK и не доходит до верха клетки):
      * следующая часть - ствол, а в клетке z0 есть пол: основание - мелочь у корня, ствол стоит на земле
        (первым элементом колонны - пол z0, мелочь у корня ничего не держит);
      * иначе, если в радиусе 1 есть колонна дерева со стволом в основании - это не колонна: части над
        мелочью - куски кроны, привязанные к стволам по правилам M0f (K-04);
      * иначе - как M0f (стопка лиан и украшений без ствола рядом).
    Свой кэш: структура M0f остаётся в blk._trees."""
    if getattr(blk, "_trees5", None) is not None:
        return blk._trees5
    floors = [set(blk.lv[z]["f"]) for z in range(blk.sz)]

    def lateral_ok(key):
        k, x, y, z = key
        return k == "o" and z >= 1 and (x, y) not in floors[z] and cls[key] not in V.BEARING and \
            role[key] not in V.SPECIAL and role[key] not in ("DOOR",)

    def trunk(key):
        return role[key] == "TRUNK" or (role[key] != "CROWN" and reaches_top(blk.parts[key]))

    stacks = {}
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
            stacks[xy] = stack
    tree_xy = {xy for xy, st in stacks.items() if T.is_tree(blk, st)}
    rooted = {xy for xy in tree_xy if trunk(stacks[xy][0])}
    cols, how = {}, {}
    for xy, st in stacks.items():
        if xy not in tree_xy or xy in rooted:
            cols[xy] = st
            how[xy] = "M0f" if xy not in tree_xy else "ствол"
        elif trunk(st[1]) and blk.lv[0]["f"].get(xy) is not None:
            cols[xy] = [blk.lv[0]["f"][xy]] + st[1:]
            how[xy] = "ствол на земле"
        elif any(max(abs(c[0] - xy[0]), abs(c[1] - xy[1])) == 1 for c in rooted):
            how[xy] = "крона над мелочью"
        else:
            cols[xy] = st
            how[xy] = "M0f без ствола рядом"
    blk._trees5_how = how
    saved_cols = cols
    tree_cols = {xy for xy in cols if xy in tree_xy}

    # привязка кроны - копия collapse_v3.tree_structure, по колоннам-цепочкам
    def attach():
        in_col = {k for st in saved_cols.values() for k in st}
        trees = tree_cols
        offs = T.offsets()
        crowns = {}
        for z in range(1, blk.sz):
            for xy, key in sorted(blk.lv[z]["o"].items()):
                if key in in_col or not lateral_ok(key):
                    continue
                x, y = xy
                near = [c for c in trees if max(abs(c[0] - x), abs(c[1] - y)) <= 1 and len(saved_cols[c]) > z - 1]
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
                        near2 = [c for c in trees if max(abs(c[0] - x), abs(c[1] - y)) <= 2 and
                                 len(saved_cols[c]) > z - 1]
                        if len(near2) == 1:
                            crowns[key] = ("через клетку", near2)
                        else:
                            crowns[key] = ("без ствола", [])
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
        return crowns

    crowns = attach()
    blk._trees5 = (cols, crowns)
    return blk._trees5


# ------------------------------------------------------------------ evaluate5

def evaluate5(blk, removed=frozenset(), flags=MODEL, tie="all"):
    """M0h. Без Z и V - collapse_v3.evaluate3 (M0f при флагах M0f)."""
    removed = frozenset(removed)
    old_e2, old_ts, old_th = V.evaluate2, T.tree_structure, T.tree_hold
    V.evaluate2 = evaluate2z
    if "V" in flags:
        T.tree_structure = tree_structure5
    T.tree_hold = lambda b, r, c, ro, ca: G.tree_hold4(b, r, c, ro, ca, tie)
    try:
        return T.evaluate3(blk, removed, flags.replace("V", ""))
    finally:
        V.evaluate2, T.tree_structure, T.tree_hold = old_e2, old_ts, old_th


def shared_crowns5(blk):
    cls = {key: V.eff_cls(key, p, "RUA") for key, p in blk.parts.items()}
    role = {key: p.get("role", "") for key, p in blk.parts.items()}
    cols, crowns = tree_structure5(blk, cls, role)
    return {key: cs for key, (how, cs) in crowns.items() if len(cs) > 1}


# ------------------------------------------------------------------ судья

class Base5(G.Base4):
    """Судья M0g (Base4) с evaluate5: край, неизвестные роли, висевшее до боя, лёгкий настил на балке, общая
    крона, граница здания - UNSUPPORTED."""

    def __init__(self, blk, disp, vessel=False, ver=None, foot=None, model=MODEL):
        self.blk, self.disp, self.vessel, self.ver, self.foot, self.model = blk, disp, vessel, ver, foot, model
        self.sup0, info = evaluate5(blk, frozenset(), model)
        self.light = P.light_beam(blk, self.sup0, info)
        self.by_cell = collections.defaultdict(list)
        for key in blk.parts:
            for c in T.part_cells(key):
                self.by_cell[c].append(key)
        self.alt0 = {e: evaluate5(blk, frozenset(), alt_flags(model, e))[0] for e in CANDIDATE_RULES}
        self.any0 = evaluate5(blk, frozenset(), model, tie="any")[0]
        if foot is not None:
            self.set_foot(foot)

    def set_foot(self, foot):
        self.foot = foot
        self.ext = frozenset(k for k in self.blk.parts if (k[1], k[2], k[3]) not in foot)
        self.iso0 = evaluate5(self.blk, self.ext, self.model)[0]
        return self

    def judge(self, removed, extra=()):
        old4, oldc = G.evaluate4, G.CANDIDATE_RULES
        model = self.model

        def ev(blk, rm, flags=model, tie="all"):
            for e in CANDIDATE_RULES:
                if flags == model.replace(e, ""):
                    flags = alt_flags(model, e)
            return evaluate5(blk, rm, flags, tie)
        G.evaluate4, G.CANDIDATE_RULES = ev, CANDIDATE_RULES
        try:
            return G.Base4.judge(self, removed, extra)
        finally:
            G.evaluate4, G.CANDIDATE_RULES = old4, oldc


# ------------------------------------------------------------------ самопроверка

def cmd_selfcheck():
    """1) evaluate5 с флагами M0f = collapse_v3.evaluate3 (M0f) на всех целых блоках и на 300 повреждениях;
    2) M0h против M0f на целых блоках: что держит одна и не держит другая, по типу части."""
    roles = V.load_roles()
    os.makedirs(OUT, exist_ok=True)
    bad = 0
    nblk = 0
    diff = collections.Counter()
    rows = []
    t0 = time.time()
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None:
            continue
        V.apply_roles(blk, roles)
        nblk += 1
        a = T.evaluate3(blk, frozenset(), M0F)[0]
        b = evaluate5(blk, frozenset(), M0F)[0]
        if a != b:
            bad += 1
            print("РАСХОЖДЕНИЕ M0f", tname, bname, len(a ^ b))
        h = evaluate5(blk, frozenset(), MODEL)[0]
        lost = sorted(k for k in a - h if k[3] > 0)
        got = sorted(k for k in h - a if k[3] > 0)
        for k in lost:
            diff[("M0h роняет", k[0], blk.parts[k].get("role", ""))] += 1
        for k in got:
            diff[("M0h держит", k[0], blk.parts[k].get("role", ""))] += 1
        if lost or got:
            rows.append([tname, bname, len(lost), len(got), T.compress(lost)[:400], T.compress(got)[:400]])
    cc.write_tsv(OUT + "/selfcheck_intact.tsv", ["terrain", "block", "M0h_drops", "M0h_holds",
                                                 "drops", "holds"], rows)
    res = {"blocks": nblk, "M0f_equal": bad == 0, "M0f_mismatch_blocks": bad,
           "blocks_differ": len(rows), "by_kind": {" ".join(k): v for k, v in sorted(diff.items())},
           "sec": round(time.time() - t0)}
    with open(OUT + "/selfcheck.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 1 if bad else 0


# ------------------------------------------------------------------ контролируемые конструкции

TRUTH = OUT + "/synth_truth.tsv"
LOCK = OUT + "/rules.lock.txt"
LOCKED = ["tools/collapse_v5.py", "tools/collapse_census.py", "tools/collapse_v2.py", "tools/collapse_v3.py",
          "tools/collapse_v4.py", "tools/collapse_pilot.py", TRUTH, "census/collapse/stage0c/roles.tsv",
          "census/collapse/stage0d/tree_offsets.tsv"]
SX, SY, SZ = 18, 14, 2


def rec(kind):
    base = {"layers": [True] + [False] * 11, "nl": 1, "ufo_door": 0, "stop_los": 0, "no_floor": 0,
            "big_wall": 0, "door": 0, "tu_walk": 4, "armor": 30, "die": 0, "alt": 0, "t_level": 0, "type": 0}
    if kind in ("wall", "column"):
        base.update(layers=[True] * 12, nl=12, stop_los=1, armor=50 if kind == "wall" else 60)
    return base


def rng(s):
    a, _, b = s.partition("-")
    return range(int(a), int(b or a) + 1)


def cells(spec):
    out = set()
    for tok in spec.split():
        if tok == "-":
            continue
        xs, ys = tok.split(":")
        out |= {(x, y) for x in rng(xs) for y in rng(ys)}
    return out


def parts(spec):
    """'f:6-7:6 w:11:3-10' -> ключи (k, x, y, z): пол - этаж 1, стены и колонны - этаж 0."""
    out = set()
    for tok in spec.split():
        if tok == "-":
            continue
        k, xs, ys = tok.split(":")
        out |= {(k, x, y, 1 if k == "f" else 0) for x in rng(xs) for y in rng(ys)}
    return frozenset(out)


def synth_block(build):
    blk = cc.Block("SYNTH", "terrain", build, SX, SY, SZ)

    def put(k, x, y, z, kind, role):
        blk.add(k, x, y, z, "SYNTH", 0, rec(kind))
        blk.parts[(k, x, y, z)]["role"] = role
        blk.parts[(k, x, y, z)]["rev"] = True

    for x in range(SX):
        for y in range(SY):
            put("f", x, y, 0, "floor", "FLOOR")
    slab, walls, cols = set(), [], []
    if build in ("room8", "balcony"):
        slab = cells("3-10:3-10")
        walls = [("w", 3, y) for y in range(3, 11)] + [("w", 11, y) for y in range(3, 11)] + \
                [("n", x, 3) for x in range(3, 11)] + [("n", x, 11) for x in range(3, 11)]
        if build == "balcony":
            slab |= cells("11-12:5-8")
    elif build == "cols":
        slab = cells("3-12:5-8")
        cols = [(x, y) for x in (3, 6, 9, 12) for y in (5, 8)]
    elif build in ("slab3", "slab2"):
        ys = range(5, 8) if build == "slab3" else range(5, 7)
        slab = {(x, y) for x in range(3, 15) for y in ys}
        walls = [("w", 3, y) for y in ys] + [("w", 15, y) for y in ys]
    elif build == "mushroom":
        slab = cells("6-8:6-8")
        cols = [(7, 7)]
    else:
        raise SystemExit("неизвестная конструкция " + build)
    for x, y in slab:
        put("f", x, y, 1, "floor", "FLOOR")
    for k, x, y in walls:
        put(k, x, y, 0, "wall", "WALL")
    for x, y in cols:
        put("o", x, y, 0, "column", "COLUMN")
    return blk


SYNTH_MODELS = [
    ("M0h", lambda blk, rm: evaluate5(blk, rm, MODEL)[0]),
    ("M0f", lambda blk, rm: T.evaluate3(blk, rm, M0F)[0]),
    ("M0g", lambda blk, rm: G.evaluate4(blk, rm, G.MODEL)[0]),
    ("ничего не ронять", None),
]


def read_lock():
    out = {}
    with open(LOCK, encoding=ENC) as f:
        for line in f:
            p = line.rstrip("\n").split(" sha256 ")
            if len(p) == 2:
                out[p[0]] = p[1]
    return out


def cmd_lock():
    if os.path.exists(LOCK):
        raise SystemExit("замок уже есть: " + LOCK)
    lines = ["версия модели M0h обрушения, записано %s - до прогона контролируемых конструкций, реальных зданий "
             "и новых карт" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "флаги %s (collapse_v5.evaluate5: M0f без S, N, B плюс Z плита и V ствол по цепочке; Y M0g не входит)"
             % MODEL,
             "параметры: C=2 L=12 order=2 L_ROOF=16 C_CANOPY=0 L_TARP=6; настил - клетка вне сплошного квадрата "
             "пола 3x3 целого блока",
             "правда контролируемых конструкций написана до первого прогона: %s" % TRUTH]
    lines += ["%s sha256 %s" % (p, sha(p)) for p in LOCKED]
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def cmd_synth():
    lock = read_lock()
    bad = [p for p in LOCKED if lock.get(p) != sha(p)]
    if bad:
        raise SystemExit("замок нарушен: " + ", ".join(bad))
    with open(TRUTH, encoding=ENC) as f:
        head, *body = [line.rstrip("\n").split("\t") for line in f if line.strip()]
    rows, tot = [], collections.defaultdict(lambda: collections.Counter())
    for r in body:
        t = dict(zip(head, r))
        must, unsure, rm = cells(t["must_fall"]), cells(t["unsure"]), parts(t["remove"])
        group = "рушится" if must else "стоит"
        for name, fn in SYNTH_MODELS:
            blk = synth_block(t["build"])
            V.evaluate2 = ORIG_E2
            slab = {xy for xy, key in blk.lv[1]["f"].items() if key not in rm}
            if fn is None:
                fell = set()
            else:
                sup = fn(blk, rm)
                fell = {xy for xy in slab if blk.lv[1]["f"][xy] not in sup}
            stand = slab - must - unsure
            false = sorted(stand & fell)
            missed = sorted(must - fell)
            c = tot[(name, group)]
            c["сценариев"] += 1
            c["верно"] += not false and not missed
            c["ложных обвалов"] += len(false)
            c["пропущенных обвалов"] += len(missed)
            c["клеток должно стоять"] += len(stand)
            c["клеток должно упасть"] += len(must)
            c["неясных упало"] += len(unsure & fell)
            c["неясных всего"] += len(unsure)
            rows.append([t["id"], group, name, "да" if not false and not missed else "нет", len(false),
                         len(missed), len(unsure & fell), len(unsure),
                         " ".join("%d:%d" % xy for xy in false), " ".join("%d:%d" % xy for xy in missed)])
    cc.write_tsv(OUT + "/synth.tsv", ["id", "group", "model", "ok", "false_falls", "missed_falls",
                                      "unsure_fell", "unsure", "false_cells", "missed_cells"], rows)
    res = {"models": {m: MODEL if m == "M0h" else M0F if m == "M0f" else G.MODEL if m == "M0g" else "-"
                      for m, _ in SYNTH_MODELS},
           "by_model_group": {"%s / %s" % k: dict(v) for k, v in sorted(tot.items())}}
    with open(OUT + "/synth.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    for r in rows:
        if r[3] == "нет":
            print("  ", *r)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selfcheck":
        sys.exit(cmd_selfcheck())
    if cmd == "lock":
        sys.exit(cmd_lock())
    if cmd == "synth":
        sys.exit(cmd_synth())
    print(__doc__)
