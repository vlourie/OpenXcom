#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0i обрушения зданий: модель M0i. Движок не трогается; M0f, M0g, M0h (collapse_v3/v4/v5), их замки и
сценарии не меняются - M0i живёт только здесь.

Рецензия 0h: запрет "плита не держит кладку без основания" слишком широк - стена законно стоит на несущем
перекрытии. Различить опирание на плиту и случайное соседство, через которое модель подхватывает висящую кладку.
Фермы через клетку - опора, только если конструкция определена; иначе UNSUPPORTED. Четыре проверки: стена на
плите стоит; кладка без основания у соседней плиты опоры не получает; покрытие на фермах стоит и падает без
нужных ферм; перемычка стоит на целых опорах и падает без них.

M0i = M0h (RUADHQIMGOWZV) плюс:
  X - кладка без основания. Несущая часть (стена, массив, колонна), которая в ЦЕЛОМ блоке стояла на своём
      несущем снизу (стопка), а после разрушения его потеряла, держится только прямой опорой или плитой на
      балке (клетка взята пролётом между опорами), но не консолью от соседней плиты, не стеной сбоку и не
      мебелью под собой. Связь массива с массивом (правило массива M0f) остаётся. Клетка пола, взятая только
      консолью, под такой упавшей кладкой или над ней (кладка этажом ниже упала по X) - часть яруса: падает.
      Стена, которая и в целом блоке стояла на плите (не на своей стене), держится плитой как раньше.
  F - тип навеса над улицей (на стойках или нет) - по ЦЕЛОМУ блоку, как тип пола: стойки ядра, снесённые
      разрушением, не превращают навес в навес без стоек (R-12, плиты z3 у края ядра).
  k - перемычка (I) с углом: конец ряда стен без несущего под собой - несущая стена той же линии ИЛИ
      перпендикулярная несущая стена в точке стыка (угол), если она стоит на несущем или на плите, взятой
      прямо или балкой. Дверь и проём опорой не служат. Длина ряда - до LINTEL (4), как I.
  c - консоль плиты от клетки, взятой балкой (середина пролёта), - не дальше 1 клетки; от прямой опоры -
      C (2), как раньше. Правило выбрано по разбору R-32 (материал разработки 0h), отдельной правды в
      синтетике у него нет - нужна проверка на новом слепом наборе.
Судья (Base6): всё, что UNSUPPORTED у M0h, плюс исход, зависящий от непросмотренной опоры: прогон без U
(непросмотренные COLUMN/TRUSS - несущие) даёт другой обвал - конструкция не определена (R-24).

    py -3.13 tools\collapse_v6.py selfcheck   без X F k c = M0h бит в бит; целые блоки: M0i против M0h
    py -3.13 tools\collapse_v6.py lock        замок модели и правды синтетики (до прогона)
    py -3.13 tools\collapse_v6.py synth       контролируемые конструкции (stage0i/synth_truth.tsv)
    py -3.13 tools\collapse_v6.py dev         33 сценария 0h как разработка: модель и судья отдельно
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
import collapse_v5 as H                           # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0i"
M0H = H.MODEL                                     # RUADHQIMGOWZV
MODEL = M0H + "XFkc"                              # M0i
NEW_RULES = "XFkc"
CANDIDATE_RULES = H.CANDIDATE_RULES + NEW_RULES
C_BEAM = 1                                        # c: консоль от клетки на балке
ORIG_E2 = V.evaluate2


def alt_flags(model, e):
    return H.alt_flags(model, e)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ------------------------------------------------------------------ плита (Z с F и c)

def canopy_posted_intact(blk, z, carry0):
    """F: навесы над улицей этажа z, у которых в ЦЕЛОМ блоке под плитой стоит несущий предмет."""
    cache = blk.__dict__.setdefault("_posted6", {})
    key = (z, id(carry0))
    if key in cache:
        return cache[key]
    ft = T.floor_types(blk)
    fk = blk.lv[z]["f"]
    below = blk.lv[z - 1]
    can = {xy for xy, k in fk.items() if ft.get(k) == ("улица", "кровля")}
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
        if any(below["o"].get(xy) in carry0 for xy in comp):
            posted |= comp
    cache[key] = posted
    return posted


def slab_floors6(blk, z, live, below, carry, floors, direct, ranch, direct_b, C, L, flags, carry0):
    """collapse_v5.slab_floors с F и c. Возвращает okf, расстояние консоли от опоры, длину балки и held -
    клетки, взятые прямо или балкой (без консоли)."""
    ft = T.floor_types(blk)
    light = H.light_intact(blk, z)
    fkey = live["f"]
    med = floors | ranch
    slab = {xy for xy in floors if xy not in light}
    can = {xy for xy in floors if ft.get(fkey[xy]) == ("улица", "кровля")}
    if "F" in flags and carry0 is not None:
        posted = canopy_posted_intact(blk, z, carry0) & can
    else:
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
            nl = H.beam_len(xy, med, base, slab, xy in slab, lim_l(xy))
            if nl is not None and (xy not in best_l or nl < best_l[xy]):
                best_l[xy] = nl
            if nl is not None and nl <= lim_l(xy):
                held.add(xy)
    okf = {xy for xy in floors if xy in held}
    geo_held = V.consoles(held & med, floors, C)
    geo_dir = V.consoles(direct_b, floors, C)
    half = "c" in flags
    for xy in floors - okf:
        c = lim_c(xy)
        if xy in slab:
            if half:
                cb = min(c, C_BEAM)
                if (geo_dir.get(xy) is not None and geo_dir[xy] <= c) or \
                        (geo_held.get(xy) is not None and geo_held[xy] <= cb):
                    okf.add(xy)
                    continue
                for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    w1 = H.walk(xy, d, med, direct_b, slab, True, c)
                    w2 = H.walk(xy, d, med, held, slab, True, cb)
                    if (w1 is not None and w1 <= c) or (w2 is not None and w2 <= cb):
                        okf.add(xy)
                        break
                continue
            if geo_held.get(xy) is not None and geo_held[xy] <= c:
                okf.add(xy)
                continue
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                w = H.walk(xy, d, med, held, slab, True, c)
                if w is not None and w <= c:
                    okf.add(xy)
                    break
        elif geo_dir.get(xy) is not None and geo_dir[xy] <= c:
            okf.add(xy)
    return okf, geo_dir, best_l, held


# ------------------------------------------------------------------ перемычка с углом (k)

def lintels6(live, below, carry, bearing, strong):
    """I с углом. Опорный конец - несущая стена той же линии на несущем, или перпендикулярная несущая стена в
    точке стыка, стоящая на несущем или на плите (strong: клетки, взятые прямо или балкой). w тянется по y
    (стык ряда - точки (x, y)), n - по x."""
    def based(k, xy, key):
        if not bearing(key):
            return False
        if below[k].get(xy) in carry:
            return True
        x, y = xy
        sides = ((x, y), (x - 1, y)) if k == "w" else ((x, y), (x, y - 1))
        return any(s in strong for s in sides)

    base = {k: {xy for xy, key in live[k].items() if based(k, xy, key)} for k in ("w", "n")}

    def corner(k, px, py):
        if k == "w":                      # n-стены, сходящиеся в точке (px, py)
            return (px - 1, py) in base["n"] or (px, py) in base["n"]
        return (px, py - 1) in base["w"] or (px, py) in base["w"]

    out = set()
    for k, (dx, dy) in (("w", (0, 1)), ("n", (1, 0))):
        lw = live[k]
        for (x, y), key in lw.items():
            if below[k].get((x, y)) in carry or not bearing(key):
                continue
            run, ok = 1, True
            for sgn in (1, -1):
                cx, cy = x, y
                while True:
                    px, py = (cx + dx, cy + dy) if sgn > 0 else (cx, cy)
                    if corner(k, px, py):
                        break
                    cx += dx * sgn
                    cy += dy * sgn
                    nk = lw.get((cx, cy))
                    if nk is None or not bearing(nk):
                        ok = False
                        break
                    if (cx, cy) in base[k]:
                        break
                    run += 1
                if not ok:
                    break
            if ok and run <= V.LINTEL:
                out.add(key)
    return out


# ------------------------------------------------------------------ evaluate2 с X, F, k, c

def intact_carry(blk, flags, kw):
    cache = blk.__dict__.setdefault("_carry6", {})
    ck = (flags, tuple(sorted(kw.items())))
    if ck not in cache:
        saved = getattr(blk, "carry", None)
        evaluate2k(blk, frozenset(), flags, **kw)
        cache[ck] = frozenset(blk.carry)
        if saved is not None:
            blk.carry = saved
    return cache[ck]


def evaluate2k(blk, removed=frozenset(), flags="", C=2, L=12, mass_rule=True, order=2, carry_rule="any",
               run_c=2, roof_reach=1, **kw):
    """collapse_v5.evaluate2z с правилами X, F, k, c. Без Z - исходный evaluate2; без X F k c - evaluate2z."""
    if "Z" not in flags:
        return ORIG_E2(blk, removed, flags, C=C, L=L, mass_rule=mass_rule, order=order, carry_rule=carry_rule,
                       run_c=run_c, roof_reach=roof_reach, **kw)
    if not any(f in flags for f in NEW_RULES + "e"):      # e - свой путь без новых правил (самопроверка)
        return H.evaluate2z(blk, removed, flags, C=C, L=L, mass_rule=mass_rule, order=order,
                            carry_rule=carry_rule, run_c=run_c, roof_reach=roof_reach, **kw)
    carry0 = None
    if removed and ("X" in flags or "F" in flags):
        carry0 = intact_carry(blk, flags, dict(C=C, L=L, mass_rule=mass_rule, order=order, carry_rule=carry_rule,
                                               run_c=run_c, roof_reach=roof_reach))
    if not removed:
        carry0 = None                     # целый блок: тип навеса считается по нему же, X не действует
    X = "X" in flags and carry0 is not None
    A = "A" in flags
    cls = {key: V.eff_cls(key, p, flags) for key, p in blk.parts.items()}
    role = {key: p.get("role", "") for key, p in blk.parts.items()}
    bearing = lambda key: cls[key] in V.BEARING      # noqa: E731
    special = (lambda key: role[key] in V.SPECIAL) if A else (lambda key: False)   # noqa: E731
    sup, carry, info = set(), set(), {}
    fallen_x = set()                                 # кладка, упавшая по X
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
        okf, dist, best_l, strong = slab_floors6(blk, z, live, below, carry, floors, direct, ranch, direct_b,
                                                 C, L, flags, carry0)
        # X: кладка без основания - стояла в целом блоке на своём несущем, теперь его нет
        nobase = set()
        if X:
            for k in ("w", "n", "o"):
                for xy, key in live[k].items():
                    if not bearing(key) or special(key):
                        continue
                    under = below[k].get(xy)
                    if under is not None and under in carry0 and under not in carry:
                        nobase.add(key)
            x_fall_o = {xy for xy, key in live["o"].items() if key in nobase and xy not in msup and
                        xy not in strong}
            tier = {xy for xy in okf - strong if xy in x_fall_o or below["o"].get(xy) in fallen_x}
            okf -= tier
        for xy in floors:
            info[live["f"][xy]] = (xy in direct, dist.get(xy), best_l.get(xy))
            if xy in okf:
                sup.add(live["f"][xy])
        if "I" in flags:
            lint = lintels6(live, below, carry, bearing, strong) if "k" in flags else \
                V.lintels(live, below, carry, bearing)
        else:
            lint = set()
        for k, sides in (("w", lambda x, y: ((x, y), (x - 1, y))),
                         ("n", lambda x, y: ((x, y), (x, y - 1)))):
            for (x, y), key in live[k].items():
                under = below[k].get((x, y))
                if key in nobase:
                    held_w = any(s in strong for s in sides(x, y)) or key in lint
                else:
                    held_w = any(s in okf for s in sides(x, y)) or under in carry or key in lint
                if held_w:
                    sup.add(key)
                    if bearing(key) and (carry_rule == "any" or under in carry or key in lint or
                                         any(s in direct for s in sides(x, y))):
                        carry.add(key)
                elif key in nobase:
                    fallen_x.add(key)
        furn = {xy for xy, key in live["o"].items() if cls[key] == "furniture" and not special(key)}
        fsup = set()
        for (x, y), key in live["o"].items():
            if special(key):
                continue
            under = below["o"].get((x, y))
            walls = [live["w"].get((x, y)), live["w"].get((x + 1, y)),
                     live["n"].get((x, y)), live["n"].get((x, y + 1))]
            if key in nobase:
                held_o = (x, y) in msup or (x, y) in strong
            else:
                held_o = (x, y) in okf or (x, y) in msup or \
                    under in carry or (under in sup and cls[under] == "furniture") or \
                    any(w in carry for w in walls if w)
            if held_o:
                sup.add(key)
                if bearing(key) and (carry_rule == "any" or under in carry or
                                     (x, y) in direct or (x, y) in msup):
                    carry.add(key)
                if (x, y) in furn:
                    fsup.add((x, y))
            elif key in nobase:
                fallen_x.add(key)
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


def evaluate6(blk, removed=frozenset(), flags=MODEL, tie="all"):
    """M0i. Без X, F, k, c - collapse_v5.evaluate5 (M0h)."""
    removed = frozenset(removed)
    old_e2, old_ts, old_th = V.evaluate2, T.tree_structure, T.tree_hold
    V.evaluate2 = evaluate2k
    if "V" in flags:
        T.tree_structure = H.tree_structure5
    T.tree_hold = lambda b, r, c, ro, ca: G.tree_hold4(b, r, c, ro, ca, tie)
    try:
        return T.evaluate3(blk, removed, flags.replace("V", ""))
    finally:
        V.evaluate2, T.tree_structure, T.tree_hold = old_e2, old_ts, old_th


# ------------------------------------------------------------------ судья

class Base6(G.Base4):
    """Судья M0h (Base5) с evaluate6, плюс непросмотренные опоры: исход зависит от того, несущие ли
    непросмотренные COLUMN/TRUSS (прогон без U) - UNSUPPORTED."""

    def __init__(self, blk, disp, vessel=False, ver=None, foot=None, model=MODEL):
        self.blk, self.disp, self.vessel, self.ver, self.foot, self.model = blk, disp, vessel, ver, foot, model
        self.sup0, info = evaluate6(blk, frozenset(), model)
        self.light = P.light_beam(blk, self.sup0, info)
        self.by_cell = collections.defaultdict(list)
        for key in blk.parts:
            for c in T.part_cells(key):
                self.by_cell[c].append(key)
        self.alt0 = {e: evaluate6(blk, frozenset(), alt_flags(model, e))[0] for e in CANDIDATE_RULES}
        self.any0 = evaluate6(blk, frozenset(), model, tie="any")[0]
        self.unrev = any(p.get("role") in ("COLUMN", "TRUSS") and not p.get("rev") for p in blk.parts.values())
        self.nou0 = evaluate6(blk, frozenset(), model.replace("U", ""))[0] if self.unrev else None
        if foot is not None:
            self.set_foot(foot)

    def set_foot(self, foot):
        self.foot = foot
        self.ext = frozenset(k for k in self.blk.parts if (k[1], k[2], k[3]) not in foot)
        self.iso0 = evaluate6(self.blk, self.ext, self.model)[0]
        return self

    def judge(self, removed, extra=()):
        old4, oldc = G.evaluate4, G.CANDIDATE_RULES
        model = self.model

        def ev(blk, rm, flags=model, tie="all"):
            for e in CANDIDATE_RULES:
                if flags == model.replace(e, ""):
                    flags = alt_flags(model, e)
            return evaluate6(blk, rm, flags, tie)
        G.evaluate4, G.CANDIDATE_RULES = ev, CANDIDATE_RULES
        try:
            res = G.Base4.judge(self, removed, extra)
        finally:
            G.evaluate4, G.CANDIDATE_RULES = old4, oldc
        if self.unrev:
            removed = frozenset(removed)
            s_nou = evaluate6(self.blk, removed, model.replace("U", ""))[0]
            if self.fallen_of(self.nou0, s_nou, removed) != res["fallen"]:
                res["why"]["исход зависит от непросмотренной опоры (COLUMN/TRUSS)"] = 1
                res["status"] = "UNSUPPORTED"
        return res


# ------------------------------------------------------------------ самопроверка

def cmd_selfcheck():
    """1) свой путь evaluate6 (флаг e) с флагами M0h = collapse_v5.evaluate5 на всех целых блоках; 2) M0i против M0h на целых
    блоках по типу части."""
    roles = V.load_roles()
    os.makedirs(OUT, exist_ok=True)
    bad, nblk = 0, 0
    diff = collections.Counter()
    rows = []
    t0 = time.time()
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None:
            continue
        V.apply_roles(blk, roles)
        nblk += 1
        a = H.evaluate5(blk, frozenset(), M0H)[0]
        b = evaluate6(blk, frozenset(), M0H + "e")[0]
        if a != b:
            bad += 1
            print("РАСХОЖДЕНИЕ M0h", tname, bname, len(a ^ b))
        i = evaluate6(blk, frozenset(), MODEL)[0]
        lost = sorted(k for k in a - i if k[3] > 0)
        got = sorted(k for k in i - a if k[3] > 0)
        for k in lost:
            diff[("M0i роняет", k[0], blk.parts[k].get("role", ""))] += 1
        for k in got:
            diff[("M0i держит", k[0], blk.parts[k].get("role", ""))] += 1
        if lost or got:
            rows.append([tname, bname, len(lost), len(got), T.compress(lost)[:400], T.compress(got)[:400]])
    cc.write_tsv(OUT + "/selfcheck_intact.tsv", ["terrain", "block", "M0i_drops", "M0i_holds", "drops", "holds"],
                 rows)
    res = {"blocks": nblk, "M0h_equal": bad == 0, "M0h_mismatch_blocks": bad, "blocks_differ": len(rows),
           "by_kind": {" ".join(k): v for k, v in sorted(diff.items())}, "sec": round(time.time() - t0)}
    with open(OUT + "/selfcheck.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 1 if bad else 0


# ------------------------------------------------------------------ контролируемые конструкции

TRUTH = OUT + "/synth_truth.tsv"
LOCK = OUT + "/rules.lock.txt"
LOCKED = ["tools/collapse_v6.py", "tools/collapse_v5.py", "tools/collapse_census.py", "tools/collapse_v2.py",
          "tools/collapse_v3.py", "tools/collapse_v4.py", "tools/collapse_pilot.py", TRUTH,
          "census/collapse/stage0c/roles.tsv", "census/collapse/stage0d/tree_offsets.tsv"]
SX, SY, SZ = 18, 14, 4


def rec(kind):
    base = {"layers": [True] + [False] * 11, "nl": 1, "ufo_door": 0, "stop_los": 0, "no_floor": 0,
            "big_wall": 0, "door": 0, "tu_walk": 4, "armor": 30, "die": 0, "alt": 0, "t_level": 0, "type": 0}
    if kind in ("wall", "column"):
        base.update(layers=[True] * 12, nl=12, stop_los=1, armor=50 if kind == "wall" else 60)
    return base


def room_walls(x0, x1, y0, y1):
    """Стены по периметру клеток x0..x1, y0..y1: w по западным краям столбцов x0 и x1+1, n по северным краям
    строк y0 и y1+1."""
    return [("w", x0, y) for y in range(y0, y1 + 1)] + [("w", x1 + 1, y) for y in range(y0, y1 + 1)] + \
        [("n", x, y0) for x in range(x0, x1 + 1)] + [("n", x, y1 + 1) for x in range(x0, x1 + 1)]


TRUSS_RING = [(3, 3), (5, 3), (7, 3), (9, 3), (9, 5), (9, 7), (9, 9), (7, 9), (5, 9), (3, 9), (3, 7), (3, 5)]


def synth_block(build):
    """Конструкции четырёх проверок. Земля - пол z0 везде. Ключи частей - (k, x, y, z) как в блоке игры."""
    blk = cc.Block("SYNTH", "terrain", build, SX, SY, SZ)

    def put(k, x, y, z, kind, role, rev=True):
        blk.add(k, x, y, z, "SYNTH", 0, rec(kind))
        blk.parts[(k, x, y, z)]["role"] = role
        blk.parts[(k, x, y, z)]["rev"] = rev

    for x in range(SX):
        for y in range(SY):
            put("f", x, y, 0, "floor", "FLOOR")

    def slab(x0, x1, y0, y1, z):
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                put("f", x, y, z, "floor", "FLOOR")

    def walls(lst, z):
        for k, x, y in lst:
            put(k, x, y, z, "wall", "WALL")

    if build in ("s1", "s2"):
        # комната 8x8 на стенах z0, плита z1
        walls(room_walls(3, 10, 3, 10), 0)
        if build == "s1":
            slab(3, 10, 3, 10, 1)
            # перегородка на плите z1: стена w по x=7, y 4..9, под ней стены нет
            walls([("w", 7, y) for y in range(4, 10)], 1)
        else:
            # плита комнаты с балконом в клетку x=11 (стена w:11 - под его западным краем); каменная башня 2x2
            # в клетках x 12-13 вплотную к балкону: массив z0..z2, пол башни z1 продолжает плиту комнаты.
            # Стены комнаты под башней нет - башня стоит только на своём основании
            slab(3, 11, 3, 10, 1)
            for x in (12, 13):
                for y in (5, 6):
                    for z in (0, 1, 2):
                        put("o", x, y, z, "column", "MASS")
                    put("f", x, y, 1, "floor", "FLOOR")
    elif build in ("s3", "s3r", "s3w"):
        # покрытие 7x7 на фермах через клетку по периметру (s3); s3r - фермы и стены периметра, фермы
        # просмотрены; s3w - то же, фермы НЕ просмотрены (конструкция не определена)
        for x, y in TRUSS_RING:
            put("o", x, y, 0, "column", "TRUSS", rev=build != "s3w")
        if build in ("s3r", "s3w"):
            walls(room_walls(3, 9, 3, 9), 0)
        slab(3, 9, 3, 9, 1)
    elif build in ("s4", "s4c"):
        # стена w по x=8, y 2..11 в два этажа; s4 - проём z0 в y 6-7, s4c - проём z0 в y 2-3 у угла с
        # n-стеной по y=2, x 4..7 (тоже два этажа)
        gap = (6, 7) if build == "s4" else (2, 3)
        walls([("w", 8, y) for y in range(2, 12) if y not in gap], 0)
        walls([("w", 8, y) for y in range(2, 12)], 1)
        if build == "s4c":
            walls([("n", x, 2) for x in range(4, 8)], 0)
            walls([("n", x, 2) for x in range(4, 8)], 1)
    else:
        raise SystemExit("неизвестная конструкция " + build)
    return blk


SYNTH_MODELS = [
    ("M0i", lambda blk, rm: evaluate6(blk, rm, MODEL)[0]),
    ("M0h", lambda blk, rm: H.evaluate5(blk, rm, M0H)[0]),
    ("M0f", lambda blk, rm: T.evaluate3(blk, rm, H.M0F)[0]),
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


def check_lock():
    lock = read_lock()
    bad = [p for p in LOCKED if lock.get(p) != sha(p)]
    if bad:
        raise SystemExit("замок нарушен: " + ", ".join(bad))


def cmd_lock():
    if os.path.exists(LOCK):
        raise SystemExit("замок уже есть: " + LOCK)
    lines = ["версия модели M0i обрушения, записано %s - до прогона контролируемых конструкций, сценариев "
             "разработки 0h и нового слепого набора" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "флаги %s (collapse_v6.evaluate6: M0h плюс X кладка без основания, F навес по целому блоку, k "
             "перемычка с углом, c консоль от клетки на балке до %d)" % (MODEL, C_BEAM),
             "судья Base6: Base5 плюс UNSUPPORTED, если исход зависит от непросмотренной COLUMN/TRUSS",
             "параметры: C=2 L=12 order=2 L_ROOF=16 C_CANOPY=0 L_TARP=6 LINTEL=%d C_BEAM=%d" % (V.LINTEL, C_BEAM),
             "правда контролируемых конструкций написана до первого прогона: %s" % TRUTH]
    lines += ["%s sha256 %s" % (p, sha(p)) for p in LOCKED]
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def above_ground(blk):
    return {k for k in blk.parts if k[3] > 0}


def cmd_synth():
    check_lock()
    import collapse_summary as S
    disp = S.disputed_records()
    rows_t = P.read_tsv(TRUTH)
    rows, tot = [], collections.defaultdict(collections.Counter)
    judge_rows = []
    for t in rows_t:
        blk0 = synth_block(t["build"])
        rm = frozenset(cc.select(blk0, t["remove"]))
        must = cc.select(blk0, t["must_fall"]) - rm if t["must_fall"] else set()
        unsure = cc.select(blk0, t["unsure"]) - rm if t["unsure"] else set()
        stand = above_ground(blk0) - rm - must - unsure
        group = "рушится" if must else "стоит"
        for name, fn in SYNTH_MODELS:
            blk = synth_block(t["build"])
            if fn is None:
                sup = above_ground(blk) - rm
            else:
                sup = fn(blk, rm)
            fell = above_ground(blk) - rm - set(sup)
            false = sorted(stand & fell)
            missed = sorted(must - fell)
            ok = not false and not missed
            c = tot[(name, group)]
            c["сценариев"] += 1
            c["верно"] += ok
            c["ложных обвалов"] += len(false)
            c["пропущенных обвалов"] += len(missed)
            c["частей должно стоять"] += len(stand)
            c["частей должно упасть"] += len(must)
            c["неясных упало"] += len(unsure & fell)
            c["неясных всего"] += len(unsure)
            rows.append([t["id"], t["check"], group, name, "да" if ok else "нет", len(false), len(missed),
                         len(unsure & fell), len(unsure), T.compress(false), T.compress(missed)])
        for name, cls_ in (("M0i", Base6), ("M0h", H.Base5)):
            blk = synth_block(t["build"])
            st = cls_(blk, disp).judge(rm)
            judge_rows.append([t["id"], name, st["status"], t["judge_expect"],
                               "да" if t["judge_expect"] in ("", st["status"]) else "нет",
                               json.dumps(st["why"], ensure_ascii=False)])
    cc.write_tsv(OUT + "/synth.tsv", ["id", "check", "group", "model", "ok", "false_falls", "missed_falls",
                                      "unsure_fell", "unsure", "false_parts", "missed_parts"], rows)
    cc.write_tsv(OUT + "/synth_judge.tsv", ["id", "judge", "status", "expect", "ok", "why"], judge_rows)
    res = {"models": {m: MODEL if m == "M0i" else M0H if m == "M0h" else H.M0F if m == "M0f" else "-"
                      for m, _ in SYNTH_MODELS},
           "by_model_group": {"%s / %s" % k: dict(v) for k, v in sorted(tot.items())},
           "judge": [dict(zip(["id", "judge", "status", "expect", "ok"], r[:5])) for r in judge_rows]}
    with open(OUT + "/synth.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res["by_model_group"], ensure_ascii=False, indent=1))
    for r in rows:
        if r[4] == "нет":
            print("  ", *r)
    for r in judge_rows:
        print("   судья", *r)


# ------------------------------------------------------------------ разработка: 33 сценария 0h

def dev_models():
    out = [("M0i", lambda blk, rm: evaluate6(blk, rm, MODEL)[0]),
           ("M0h", lambda blk, rm: H.evaluate5(blk, rm, M0H)[0]),
           ("M0f", lambda blk, rm: T.evaluate3(blk, rm, H.M0F)[0])]
    for e in NEW_RULES:
        out.append(("M0i без " + e, lambda blk, rm, e=e: evaluate6(blk, rm, MODEL.replace(e, ""))[0]))
    return out


def cmd_dev():
    """Сценарии 0h - материал разработки (по ним выбиралась M0i), не приёмка. Модель без судьи и судья
    отдельно; итоги по частям, по сценариям и по зданиям (блокам)."""
    check_lock()
    import collapse_summary as S
    import collapse_review5 as R
    roles = V.load_roles()
    task, blocks = R.load_task_blocks(roles)
    disp = S.disputed_records()
    models = dev_models() + [("ничего не ронять", None)]
    rows = []
    per = {}                                       # (модель, id) -> (ok, false, missed)
    meta = {}
    for e in P.read_tsv(R.EXPECT):
        t = task[e["id"]]
        bkey = (t["terrain"].upper(), t["block"].upper())
        blk = blocks[bkey]
        rm = frozenset(cc.select(blk, t["remove"]))
        mf = cc.select(blk, e["must_fall"]) - rm
        ms = cc.select(blk, e["must_stand"]) - rm
        group = "рушится" if mf else "стоит"
        ji = Base6(blk, disp).judge(rm)
        jh = H.Base5(blk, disp).judge(rm)
        meta[e["id"]] = (group, bkey, ji["status"], jh["status"], ji["why"])
        for name, fn in models:
            if fn is None:
                s0 = evaluate6(blk, frozenset(), MODEL)[0]
                sup = set(s0) - rm
            else:
                s0 = fn(blk, frozenset())
                sup = fn(blk, rm)
            missed = sorted(k for k in mf if k in sup and k in s0)
            false = sorted(k for k in ms if k not in sup and k in s0)
            per[(name, e["id"])] = (not missed and not false, len(false), len(missed))
            rows.append([e["id"], group, "%s/%s" % bkey, ji["status"], jh["status"], name,
                         "да" if not missed and not false else "нет", len(false), len(missed), T.compress(false),
                         T.compress(missed)])
    cc.write_tsv(OUT + "/dev_0h.tsv", ["id", "group", "block", "judge_M0i", "judge_M0h", "model", "ok",
                                       "false_falls", "missed_falls", "false_parts", "missed_parts"], rows)
    res = {}
    for scope, keep in (("модель, все сценарии", lambda m: True),
                        ("судья M0i OK", lambda m: m[2] == "OK"),
                        ("судья M0h OK", lambda m: m[3] == "OK")):
        for name, _ in models:
            for group in ("рушится", "стоит"):
                ids = [i for i, m in meta.items() if m[0] == group and keep(m)]
                if not ids:
                    continue
                bl = collections.defaultdict(list)
                for i in ids:
                    bl[meta[i][1]].append(per[(name, i)][0])
                res["%s / %s / %s" % (scope, name, group)] = {
                    "сценариев": len(ids), "верно": sum(per[(name, i)][0] for i in ids),
                    "ложных частей": sum(per[(name, i)][1] for i in ids),
                    "пропущенных частей": sum(per[(name, i)][2] for i in ids),
                    "зданий": len(bl), "зданий верно": sum(all(v) for v in bl.values())}
    res["судья"] = {i: {"M0i": m[2], "M0h": m[3], "почему M0i": m[4]} for i, m in sorted(meta.items())}
    with open(OUT + "/dev_0h.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for k, v in res.items():
        if k != "судья":
            print(k, v)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"selfcheck": cmd_selfcheck, "lock": cmd_lock, "synth": cmd_synth, "dev": cmd_dev}.get(cmd)
    if fn is None:
        print(__doc__)
        sys.exit(0)
    sys.exit(fn() or 0)
