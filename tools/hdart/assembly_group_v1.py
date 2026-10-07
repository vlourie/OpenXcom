#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ASSEMBLY_COMPONENT_GROUP_V1 - составной как ГРУППА кадров одной многоклеточной сборки (специалист 02.10,
RELATION_DISCOVERY_V6_PREP). CPU, чтение. Добавка к ASSEMBLY_DISCOVERY_V1: assembly_discovery_v1 не правится, его
доводы остаются как есть; здесь только новый источник улик.

Почему ASM V1 пропускал: он требует пары по отдельности - b в ядре a на ровно одном сдвиге И a в ядре b на обратном
(взаимность), ядро - узлы в >= 0.75 мест. Многоклеточный предмет так не собирается, когда кусок b общий для нескольких
сборок (ствол под разными кронами, борт под разными надстройками): в ядре b кадра a нет, взаимность рвётся, хотя все
места a - одна и та же сборка (holdout V5: CATACDECOR_DOOM:16 ~ :15, FORESTRED:55, FOREST_WASTE:57, ISLANDURBAN3:13).

Здесь сначала собирается сборка, потом из неё выводятся пары:

  экземпляр места - связная часть своего слота по ходам ASM (assembly_discovery_v1.MOVES) в окне GRP_R по x/y и
                    GRP_DZ по этажу, плюс пол (слот 0) под каждой клеткой части - общий след сборки; кадр в слое
                    пола - это предмет, стоящий на нём (его часть с полом под ней), пола без предмета нет;
  ядро сборки     - узлы (сдвиг, слот, кадр), которые есть не меньше чем в max(GRP_REPEAT, GRP_CORE n) местах кадра
                    (n - места кадра в слоте; больше GRP_CAP - равномерная выборка GRP_CAP мест);
  группа сборки   - кадр и кадры его ядра.

Довод AG (COMPOSITE_PART, детектор ASMG, всегда CANDIDATE - на ревью, автоматического действия нет) на паре a ~ b:
  1. повтор: у обоих кадров в своих слотах не меньше GRP_REPEAT мест;
  2. геометрия: b в ядре a ровно на одном сдвиге ИЛИ a в ядре b ровно на одном сдвиге (несколько сдвигов - узор,
     не сборка; одна сторона допустима - это и есть общий кусок нескольких сборок);
  3. та же сборка: ядра a и b делят не меньше GRP_SHARED третьих кадров (кроме a и b) - пара стоит не просто рядом,
     вокруг неё одна и та же группа; это новая улика вместо взаимности, порог взаимности ASM V1 не трогается;
  4. один набор PCK у a и b (кадры одной сборки рисуются в одном наборе; межнаборные - вне V1).
Без условия 3 одностороннее соседство (стул всегда у стола) довода не даёт - как в ASM V1.

Параметры выбраны по закрытым эталонам РАЗРАБОТКИ (holdout V4, V5_COMPONENT_VALIDATION_V1, AR boundary
validation): среди правил с 0 парами NONE на них больше всего настоящих составных (124, других связей 7). Записаны
в spec.json V6_PREP до диагностического пересчёта на 80 кадрах holdout V5.
"""
import os
import sys
from collections import Counter, defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import assembly_discovery_v1 as asm               # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402

DETECTOR = "ASMG"
TYPE = asm.TYPE                 # COMPOSITE_PART
RULE = "AG"
LEVEL = "CANDIDATE"
GRP_R = 3                       # окно 7x7 клеток: самолёт и крупная машина видны из любой своей клетки
GRP_DZ = 2                      # два этажа вверх и вниз: дерево и мачта на несколько этажей
GRP_REPEAT = 2                  # сборка повторяется - не меньше двух мест (как ASM_REPEAT)
GRP_CORE = 0.5                  # узел ядра - не меньше чем в половине мест кадра
GRP_SHARED = 1                  # общих третьих кадров в ядрах a и b
GRP_CAP = 400                   # мест кадра больше - равномерная выборка
SAME_SET = True
PARAMS = {"GRP_R": GRP_R, "GRP_DZ": GRP_DZ, "GRP_REPEAT": GRP_REPEAT, "GRP_CORE": GRP_CORE,
          "GRP_SHARED": GRP_SHARED, "GRP_CAP": GRP_CAP, "SAME_SET": SAME_SET, "level": LEVEL,
          "moves": "assembly_discovery_v1.MOVES (свой слот) плюс пол под клеткой части",
          "geometry": "партнёр в ядре на ровно одном сдвиге хотя бы с одной стороны",
          "same_assembly": "ядра делят >= GRP_SHARED третьих кадров"}


def at(grid, pos, slot):
    for la, k in grid.get(pos, []):
        if la == slot:
            return k
    return None


def in_window(o):
    return abs(o[0]) <= GRP_R and abs(o[1]) <= GRP_R and abs(o[2]) <= GRP_DZ


def grow(grid, xyz, slot, seen):
    """Связная часть слота slot от (0, 0, 0); seen {(сдвиг, слот): кадр} пополняется."""
    q = deque([((0, 0, 0), slot)])
    while q:
        o, s = q.popleft()
        for d, s2 in asm.MOVES[s]:
            o2 = asm.add(o, d)
            if not in_window(o2) or (o2, s2) in seen:
                continue
            k = at(grid, asm.add(xyz, o2), s2)
            if k is not None:
                seen[(o2, s2)] = k
                q.append((o2, s2))


def instance(grid, xyz, slot, K):
    """Экземпляр сборки в одном месте: {(сдвиг, слот): кадр}."""
    seen = {((0, 0, 0), slot): K}
    if slot == 0:
        k3 = at(grid, xyz, 3)
        if k3 is None:
            return seen                                    # пол без предмета - сборки нет
        seen[((0, 0, 0), 3)] = k3
        grow(grid, xyz, 3, seen)
    else:
        grow(grid, xyz, slot, seen)
    for (o, s) in list(seen):
        if s != 0:
            f = at(grid, asm.add(xyz, o), 0)
            if f is not None:
                seen.setdefault((o, 0), f)
    return seen


def sample(pl, cap=GRP_CAP):
    if len(pl) <= cap:
        return pl
    step = len(pl) / cap
    return [pl[int(i * step)] for i in range(cap)]


class Groups:
    """Ядра сборок кадров по слотам (с кэшем)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.cache = {}

    def slots(self, k):
        return sorted({la for _t, _b, _g, _x, la in self.ctx.places.of(k.upper())})

    def core(self, k, slot):
        """-> {"n", "m", "members": {(сдвиг, слот, кадр): (мест, блоков)}, "frames": {кадр}}."""
        K = k.upper()
        kk = (K, slot)
        if kk in self.cache:
            return self.cache[kk]
        allp = [(b, g, xyz) for _t, b, g, xyz, la in self.ctx.places.of(K) if la == slot]
        pl = sample(allp)
        rec, blk = Counter(), defaultdict(set)
        for b, g, xyz in pl:
            for (o, s), kb in instance(g, xyz, slot, K).items():
                if kb == K:
                    continue
                rec[(o, s, kb)] += 1
                blk[(o, s, kb)].add(b)
        m = len(pl)
        need = max(GRP_REPEAT, GRP_CORE * m) if m >= GRP_REPEAT else float("inf")
        mem = {x: (c, len(blk[x])) for x, c in rec.items() if c >= need}
        r = {"n": len(allp), "m": m, "members": mem, "frames": {kb for (_o, _s, kb) in mem},
             "seen": set(kb for (_o, _s, kb) in rec)}
        self.cache[kk] = r
        return r


def offsets(core, k):
    return [(o, s) for (o, s, kb) in core["members"] if kb == k]


def judge(G, a, sa, b, sb):
    """Довод AG на паре (a в слоте sa, b в слоте sb) или None."""
    A, B = a.upper(), b.upper()
    if SAME_SET and v2.split(A)[0] != v2.split(B)[0]:
        return None
    ca, cb = G.core(A, sa), G.core(B, sb)
    if ca["n"] < GRP_REPEAT or cb["n"] < GRP_REPEAT:
        return None
    oa, ob = offsets(ca, B), offsets(cb, A)
    if not (len(oa) == 1 or len(ob) == 1):
        return None
    shared = sorted((ca["frames"] & cb["frames"]) - {A, B})
    if len(shared) < GRP_SHARED:
        return None
    side = "обе" if len(oa) == 1 and len(ob) == 1 else ("a" if len(oa) == 1 else "b")
    o, s = (oa[0] if len(oa) == 1 else (asm.neg(ob[0][0]), sb))
    ma = ca["members"].get((oa[0][0], oa[0][1], B)) if len(oa) == 1 else None
    mb = cb["members"].get((ob[0][0], ob[0][1], A)) if len(ob) == 1 else None
    e = v2.edge(TYPE, A, B, LEVEL, DETECTOR, RULE,
                "группа сборки: сдвиг %s, слоты %d/%d; в ядре %s на одном сдвиге (a %s из %d мест, b %s из %d); "
                "общих третьих кадров %d (%s)" % (
                    list(o), sa, sb, {"обе": "друг друга", "a": "a кадр b", "b": "b кадр a"}[side],
                    ma[0] if ma else "-", ca["m"], mb[0] if mb else "-", cb["m"], len(shared),
                    ", ".join(shared[:4]) + (" ..." if len(shared) > 4 else "")))
    e["scores"] = {"offset": list(o), "slots": [sa, sb], "side": side, "n": [ca["n"], cb["n"]],
                   "m": [ca["m"], cb["m"]], "in_core_a": ma[0] if ma else 0, "in_core_b": mb[0] if mb else 0,
                   "blocks": max(ma[1] if ma else 0, mb[1] if mb else 0), "shared": shared,
                   "core_a": len(ca["frames"]), "core_b": len(cb["frames"])}
    return e


def discover(G, a, only=None):
    """Доводы AG кадра a: кандидаты - кадры, хоть раз стоявшие в его экземплярах; only - одна пара (контроль)."""
    A = a.upper()
    out, done = [], set()
    for sa in G.slots(A):
        ca = G.core(A, sa)
        for B in sorted(ca["seen"]):
            if B == A or B in done or (only is not None and B != only.upper()):
                continue
            if SAME_SET and v2.split(A)[0] != v2.split(B)[0]:
                continue
            best = None
            for sb in G.slots(B):
                e = judge(G, A, sa, B, sb)
                if e and (best is None or len(e["scores"]["shared"]) > len(best["scores"]["shared"])):
                    best = e
            if best:
                out.append(best)
                done.add(B)
    return out


def groups(edges):
    """Группы - связные части графа доводов AG. -> [sorted кадров]."""
    adj = defaultdict(set)
    for e in edges:
        if e["detector"] == DETECTOR:
            adj[e["source"]].add(e["target"])
            adj[e["target"]].add(e["source"])
    seen, out = set(), []
    for k in sorted(adj):
        if k in seen:
            continue
        comp, q = set(), deque([k])
        while q:
            x = q.popleft()
            if x in comp:
                continue
            comp.add(x)
            q.extend(adj[x] - comp)
        seen |= comp
        out.append(sorted(comp))
    return out
