#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ASSEMBLY_REPEATED_COMPONENT_V1 - один кадр несколько раз внутри одной многоклеточной сборки (специалист 02.10,
ASSEMBLY_EVIDENCE_V2_PREP, класс REPEATED_COMPONENT_IN_ASSEMBLY). CPU, чтение. Добавка: assembly_discovery_v1
(ASM V1) и assembly_group_v1 (AG V1) не правятся.

Почему AG V1 пропускает такой кусок: в ядре сборки он стоит на нескольких сдвигах сразу, а AG берёт партнёра только
на одном сдвиге (несколько сдвигов у AG - узор). Здесь улика другая: не «a рядом с b много раз», а СЛЕД сборки, в
котором a повторяется, - и след сам повторяется на разных картах.

  след места    - связная часть слоя якоря F по ходам ASM (assembly_discovery_v1.MOVES) в окне RC_R по x/y и RC_DZ
                  по этажу, и все слои в клетках этой части: узлы (сдвиг, слой, кадр);
  ядро следа    - узлы, которые есть не меньше чем в max(2, RC_CORE m) мест F (m мест в слое, больше RC_CAP -
                  равномерная выборка);
  якорь F       - кадр не в слое пола; мест не меньше RC_REPEAT на >= RC_BLOCKS разных картах; ЕДИНСТВЕННЫЙ в своём
                  ядре (F не стоит в ядре ни на одном другом узле - иначе это поле одинаковых, узор, забор A B A B);
  повторяющийся - кадр a того же набора, не в слое пола, в ядре F на >= RC_REP разных сдвигах (пол, повторённый под
  кусок a         сборкой, - поверхность, на которой она стоит, а не её часть: на эталонах разработки это все пять
                  ложных NONE).
Довод RC (COMPOSITE_PART, детектор ASMR, всегда CANDIDATE - на ревью) на парах a ~ F и a ~ b, где b - кадр ядра F
того же набора не в слое пола, стоящий в ядре ровно на одном узле (единственная деталь той же сборки).

Параметры выбраны по закрытым эталонам РАЗРАБОТКИ (holdout V4, V5_COMPONENT_VALIDATION_V1, AR boundary validation)
до пересчёта на 80 кадрах V6 и записаны в spec.json ASSEMBLY_EVIDENCE_V2_PREP.
"""
import os
import sys
from collections import Counter, defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import assembly_discovery_v1 as asm               # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402

DETECTOR = "ASMR"
TYPE = asm.TYPE                 # COMPOSITE_PART
RULE = "RC"
LEVEL = "CANDIDATE"
RC_R = 3
RC_DZ = 2
RC_CORE = 0.5                   # узел ядра - не меньше чем в половине мест якоря
RC_REPEAT = 2                   # мест якоря
RC_BLOCKS = 2                   # разных карт среди мест якоря - след повторяется
RC_REP = 2                      # разных сдвигов повторяющегося куска в ядре
RC_CAP = 400
FLOOR = 0
PARAMS = {"RC_R": RC_R, "RC_DZ": RC_DZ, "RC_CORE": RC_CORE, "RC_REPEAT": RC_REPEAT, "RC_BLOCKS": RC_BLOCKS,
          "RC_REP": RC_REP, "RC_CAP": RC_CAP, "level": LEVEL, "same_set": True,
          "anchor": "не пол, единственный в своём ядре, места на >= RC_BLOCKS картах",
          "repeated": "не пол, в ядре якоря на >= RC_REP сдвигах",
          "partners": "якорь и кадры ядра не в слое пола ровно на одном узле"}


def sample(pl, cap=RC_CAP):
    if len(pl) <= cap:
        return pl
    step = len(pl) / cap
    return [pl[int(i * step)] for i in range(cap)]


def at(grid, pos, slot):
    for la, k in grid.get(pos, []):
        if la == slot:
            return k
    return None


def in_window(o):
    return abs(o[0]) <= RC_R and abs(o[1]) <= RC_R and abs(o[2]) <= RC_DZ


def footprint(grid, xyz, slot):
    """След места: {(сдвиг, слой, кадр)} - связная часть слоя slot и все слои в её клетках."""
    seen = {((0, 0, 0), slot)}
    q = deque([(0, 0, 0)])
    qs = deque([slot])
    while q:
        o, s = q.popleft(), qs.popleft()
        for d, s2 in asm.MOVES[s]:
            o2 = asm.add(o, d)
            if not in_window(o2) or (o2, s2) in seen:
                continue
            if at(grid, asm.add(xyz, o2), s2) is not None:
                seen.add((o2, s2))
                q.append(o2)
                qs.append(s2)
    nodes = set()
    for o in {o for (o, _s) in seen}:
        for la, k in grid.get(asm.add(xyz, o), []):
            nodes.add((o, la, k))
    return nodes


class Footprints:
    """Ядра следов кадров по слоям (с кэшем)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.cache = {}

    def slots(self, k):
        return sorted({la for _t, _b, _g, _x, la in self.ctx.places.of(k.upper())})

    def core(self, k, slot):
        """-> {"n", "m", "blocks", "members": {(сдвиг, слой, кадр): мест}, "seen": {кадр}}."""
        K = k.upper()
        kk = (K, slot)
        if kk in self.cache:
            return self.cache[kk]
        allp = [(b, g, xyz) for _t, b, g, xyz, la in self.ctx.places.of(K) if la == slot]
        pl = sample(allp)
        rec = Counter()
        seen = set()
        for _b, g, xyz in pl:
            for n in footprint(g, xyz, slot):
                rec[n] += 1
                seen.add(n[2])
        m = len(pl)
        need = max(RC_REPEAT, RC_CORE * m) if m >= RC_REPEAT else float("inf")
        r = {"n": len(allp), "m": m, "blocks": len({b for b, _g, _x in allp}),
             "members": {x: c for x, c in rec.items() if c >= need}, "seen": seen}
        self.cache[kk] = r
        return r


def anchor_ok(F, sf, core):
    if sf == FLOOR or core["n"] < RC_REPEAT or core["blocks"] < RC_BLOCKS:
        return False
    return not any(k == F and not (o == (0, 0, 0) and s == sf) for (o, s, k) in core["members"])


def assembly(Fp, F, sf):
    """Повторяющиеся куски и единственные детали следа якоря F в слое sf -> (rep {a: [узлы]}, uniq {b: узел}) или None."""
    F = F.upper()
    core = Fp.core(F, sf)
    if not anchor_ok(F, sf, core):
        return None
    fs = v2.split(F)[0]
    by = defaultdict(list)
    for (o, s, k) in core["members"]:
        if s == FLOOR or k == F or v2.split(k)[0] != fs:
            continue
        by[k].append((o, s))
    rep = {k: sorted(v) for k, v in by.items() if len({o for o, _s in v}) >= RC_REP}
    uniq = {k: v[0] for k, v in by.items() if len(v) == 1}
    if not rep:
        return None
    return rep, uniq, core


def claims(Fp, F, sf):
    """Доводы RC сборки с якорем F: a ~ F и a ~ b для каждого повторяющегося a."""
    r = assembly(Fp, F, sf)
    if r is None:
        return []
    rep, uniq, core = r
    out = []
    for a, nodes in sorted(rep.items()):
        partners = [(F, ((0, 0, 0), sf))] + sorted((b, n) for b, n in uniq.items() if b != a)
        for b, (o, s) in partners:
            e = v2.edge(TYPE, a, b, LEVEL, DETECTOR, RULE,
                        "повторяющийся кусок сборки: %s в следе якоря %s (слой %d, %d мест на %d картах) на %d сдвигах "
                        "%s; %s - %s" % (a, F, sf, core["n"], core["blocks"], len({x for x, _y in nodes}),
                                         [list(x) for x, _y in nodes][:4], b,
                                         "якорь" if b == F else "единственная деталь на сдвиге %s, слой %d" % (list(o), s)))
            e["scores"] = {"anchor": F, "anchor_slot": sf, "anchor_places": core["n"], "anchor_blocks": core["blocks"],
                           "m": core["m"], "repeated": a, "repeated_nodes": [[list(x), y] for x, y in nodes],
                           "partner_role": "anchor" if b == F else "unique_member",
                           "partner_node": [list(o), s], "core_size": len(core["members"])}
            out.append(e)
    return out


def anchors_near(Fp, k):
    """Кандидаты в якоря для кадра k: он сам и кадры его набора не в слое пола, хоть раз стоявшие в его следах."""
    K = k.upper()
    ks = v2.split(K)[0]
    out = {(K, s) for s in Fp.slots(K) if s != FLOOR}
    for s in Fp.slots(K):
        for F in Fp.core(K, s)["seen"]:
            if F != K and v2.split(F)[0] == ks:
                out |= {(F, sf) for sf in Fp.slots(F) if sf != FLOOR}
    return sorted(out)


def discover(Fp, k, only=None):
    """Доводы RC, где кадр k - повторяющийся кусок, якорь или единственная деталь; only - одна пара (контроль)."""
    K = k.upper()
    out, done = [], set()
    for F, sf in anchors_near(Fp, K):
        for e in claims(Fp, F, sf):
            if K not in (e["source"], e["target"]):
                continue
            other = e["target"] if e["source"] == K else e["source"]
            if only is not None and other != only.upper():
                continue
            if other in done:
                continue
            done.add(other)
            out.append(e)
    return out
