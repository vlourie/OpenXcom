#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TWO_COMPONENT_ASSEMBLY_V1 - составной из двух кадров без третьего общего (специалист 02.10,
ASSEMBLY_EVIDENCE_V2_PREP). CPU, чтение. Добавка: assembly_discovery_v1 (ASM V1) и assembly_group_v1 (AG V1) не
правятся, их доводы остаются как есть; здесь только новый источник улик.

Чем отличается от соседства («стул возле стола»): довод даёт не то, что b часто рядом с a, а то, что пара живёт
только вместе и всегда в одном положении - с ОБЕИХ сторон:

  1. устойчивый сдвиг: в окне TC_R по x/y и TC_DZ по этажу b стоит относительно a на одном сдвиге o (сдвигов, где b
     встречается хотя бы в TC_OFF мест a, ровно один) и a относительно b - на одном обратном -o;
  2. очень высокая взаимная зависимость: b на сдвиге o в >= TC_DEP мест a И a на сдвиге -o в >= TC_DEP мест b
     (стул всегда у стола, а стол часто без стула - довода нет);
  3. повтор: совместных мест не меньше TC_CO с каждой стороны, и они на >= TC_BLOCKS разных картах (одна карта,
     где дважды нарисовано то же, - не сборка; одно место - не довод вовсе: SINGLE_PLACEMENT остаётся на ревью);
  4. совместимость слоёв: пол + предмет (слои 0 и 3) не берутся - совместное положение в клетке ещё не один объект,
     а закрытых случаев на эталонах разработки 2 (INSUFFICIENT_SAMPLE); такие пары только в диагностике (fo_diag);
  5. один набор PCK у a и b.
Довод TC (COMPOSITE_PART, детектор ASM2) всегда CANDIDATE: на ревью, автоматического действия нет, STRONG не бывает.

Параметры выбраны по закрытым эталонам РАЗРАБОТКИ (holdout V4, V5_COMPONENT_VALIDATION_V1, AR boundary validation)
до пересчёта на 80 кадрах V6 и записаны в spec.json ASSEMBLY_EVIDENCE_V2_PREP.
"""
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import assembly_discovery_v1 as asm               # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402

DETECTOR = "ASM2"
TYPE = asm.TYPE                 # COMPOSITE_PART
RULE = "TC"
LEVEL = "CANDIDATE"
TC_R = 3                        # окно 7x7, как AG V1
TC_DZ = 2
TC_DEP = 0.9                    # взаимная зависимость с каждой стороны
TC_OFF = 0.25                   # сдвиг считается, если партнёр на нём хотя бы в четверти мест
TC_CO = 2                       # совместных мест с каждой стороны
TC_BLOCKS = 2                   # разных карт среди совместных мест
TC_CAP = 400                    # мест кадра больше - равномерная выборка
FLOOR, OBJECT = 0, 3
PARAMS = {"TC_R": TC_R, "TC_DZ": TC_DZ, "TC_DEP": TC_DEP, "TC_OFF": TC_OFF, "TC_CO": TC_CO,
          "TC_BLOCKS": TC_BLOCKS, "TC_CAP": TC_CAP, "level": LEVEL, "same_set": True,
          "slots": "любые, кроме пола и предмета (слои 0 и 3) - те только в диагностике fo_diag",
          "offset": "один сдвиг с каждой стороны (доля >= TC_OFF), обратные друг другу"}


def sample(pl, cap=TC_CAP):
    if len(pl) <= cap:
        return pl
    step = len(pl) / cap
    return [pl[int(i * step)] for i in range(cap)]


def floor_object(sa, sb):
    return {sa, sb} == {FLOOR, OBJECT}


class Windows:
    """Окна вокруг мест кадра по слоям (с кэшем): {(сдвиг, слой, кадр): (мест, {карты})}."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.cache = {}

    def slots(self, k):
        return sorted({la for _t, _b, _g, _x, la in self.ctx.places.of(k.upper())})

    def get(self, k, slot):
        K = k.upper()
        kk = (K, slot)
        if kk in self.cache:
            return self.cache[kk]
        pl = sample([(b, g, xyz) for _t, b, g, xyz, la in self.ctx.places.of(K) if la == slot])
        c, bl = Counter(), defaultdict(set)
        for b, g, (x, y, z) in pl:
            seen = set()
            for dx in range(-TC_R, TC_R + 1):
                for dy in range(-TC_R, TC_R + 1):
                    for dz in range(-TC_DZ, TC_DZ + 1):
                        for la, f in g.get((x + dx, y + dy, z + dz), []):
                            node = ((dx, dy, dz), la, f)
                            if node in seen or (node[0] == (0, 0, 0) and la == slot and f == K):
                                continue
                            seen.add(node)
                            c[node] += 1
                            bl[node].add(b)
        r = {"m": len(pl), "nodes": {n: (c[n], bl[n]) for n in c}}
        self.cache[kk] = r
        return r


def offsets(w, slot, k):
    """Сдвиги кадра k в слое slot в окне w с долей >= TC_OFF."""
    m = w["m"]
    return [o for (o, s, f), (c, _b) in w["nodes"].items() if f == k and s == slot and m and c / m >= TC_OFF]


def features(W, a, sa, b, sb):
    """Признаки пары в слоях sa/sb или None (b ни разу не в окне a)."""
    A, B = a.upper(), b.upper()
    wa, wb = W.get(A, sa), W.get(B, sb)
    if not wa["m"] or not wb["m"]:
        return None
    oab = [o for (o, s, f) in wa["nodes"] if f == B and s == sb]
    if not oab:
        return None
    best = None
    for o in oab:
        ca, bla = wa["nodes"][(o, sb, B)]
        cb, blb = wb["nodes"].get((asm.neg(o), sa, A), (0, set()))
        pa, pb = ca / wa["m"], cb / wb["m"]
        cand = {"offset": list(o), "dep_a": round(pa, 3), "dep_b": round(pb, 3), "dep": round(min(pa, pb), 3),
                "co_a": ca, "co_b": cb, "blocks": len(bla & blb) if cb else 0, "m": [wa["m"], wb["m"]]}
        if best is None or (cand["dep"], cand["co_a"]) > (best["dep"], best["co_a"]):
            best = cand
    best["n_off_a"] = len(offsets(wa, sb, B))
    best["n_off_b"] = len(offsets(wb, sa, A))
    best["slots"] = [sa, sb]
    return best


def passes(f):
    return (f["dep"] >= TC_DEP and min(f["co_a"], f["co_b"]) >= TC_CO and f["blocks"] >= TC_BLOCKS
            and f["n_off_a"] == 1 and f["n_off_b"] == 1)


def judge(W, a, sa, b, sb, diag=False):
    """Довод TC на паре (a в слое sa, b в слое sb) или None. diag=True - пол + предмет для диагностики (без
    условия одного сдвига: пол лежит вокруг предмета на многих сдвигах)."""
    A, B = a.upper(), b.upper()
    if v2.split(A)[0] != v2.split(B)[0] or A == B:
        return None
    fo = floor_object(sa, sb)
    if fo != diag:
        return None
    f = features(W, A, sa, B, sb)
    if f is None:
        return None
    if diag:
        ok = f["dep"] >= TC_DEP and min(f["co_a"], f["co_b"]) >= TC_CO and f["blocks"] >= TC_BLOCKS
    else:
        ok = passes(f)
    if not ok:
        return None
    e = v2.edge(TYPE, A, B, LEVEL, DETECTOR, RULE + ("-FO-DIAG" if diag else ""),
                "две детали: сдвиг %s, слои %d/%d; b на нём в %d из %d мест a (%.2f), a на обратном в %d из %d мест b "
                "(%.2f); карт %d; других сдвигов нет" % (
                    f["offset"], sa, sb, f["co_a"], f["m"][0], f["dep_a"], f["co_b"], f["m"][1], f["dep_b"],
                    f["blocks"]))
    e["scores"] = f
    return e


def discover(W, a, only=None, diag=False):
    """Доводы TC кадра a: кандидаты - кадры его набора, хоть раз стоявшие в окне a."""
    A = a.upper()
    out, done = [], set()
    for sa in W.slots(A):
        wa = W.get(A, sa)
        cands = sorted({f for (_o, _s, f) in wa["nodes"]})
        for B in cands:
            if B == A or B in done or (only is not None and B != only.upper()):
                continue
            if v2.split(A)[0] != v2.split(B)[0]:
                continue
            best = None
            for sb in W.slots(B):
                e = judge(W, A, sa, B, sb, diag=diag)
                if e and (best is None or e["scores"]["dep"] > best["scores"]["dep"]):
                    best = e
            if best:
                out.append(best)
                done.add(B)
    return out
