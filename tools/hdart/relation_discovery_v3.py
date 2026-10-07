#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RELATION_DISCOVERY_V3_PREP - существование связи отдельно от её типа (специалист 02.10). Только CPU и чтение.

V2_PREP (probes/relation-discovery-v2-prep) закрыл шесть опасных одиночных заказов, но на контроле STRONG «связь
есть» 0.99, а точный тип 0.90; составной 0.45, модуль 0/8; одна пара держала одно ребро, и настоящий составной
THULBASES03:84 <-> :82 терялся за ребром die. Здесь три вещи и граф, остальное - из V2 без изменений:

  0. Граф доводов. Довод - (группа связи, пара кадров), хранится один раз; детекторы, которые его подтверждают, -
     опора довода. У пары может быть несколько доводов разных групп (составной и разрушенный вид).
  1. Существование и тип раздельно. Существование: RELATED_STRONG (опора не ниже STRONG от недиагностического
     детектора) или RELATED_CANDIDATE. Тип: TYPE_STRONG - только когда существование STRONG, детектор не
     диагностический и у пары нет спорящей гипотезы другой группы вывода (derived / state / animation; точная копия
     пикселей и расстановка не спорят) и спора направления; иначе TYPE_OPEN. RELATED_STRONG + TYPE_OPEN - кадр не
     рисуется сам по себе, подтип уходит на ревью. Маршрут B (routing_model_v8.pipeline_of) получает только роли
     доводов с TYPE_STRONG.
  2. MIRRORED_RECOLOR_V1 - диагностический детектор кандидатов: отражённый силуэт (IoU >= GEO), отражённая
     топология (границы цветовых областей >= BORDER_KEEP), функция цвета (>= FUNC при основе от MIN_COLORS цветов),
     совместимость MCD (тип клетки и воксели, отражённые по диагонали) - улика, не ворота. Тот же тест без
     отражения при силуэте 0.98-0.998 (не побайтно равном) - NEAR_RECOLOR. Оба - не выше RELATED_CANDIDATE и
     TYPE_OPEN до слепой проверки. Отрицательный контроль - пары NONE прежних эталонов и тот же тест с цветами B,
     перемешанными внутри силуэта.
  3. PLACEMENT_STRUCTURE_V2 - составной по узору расстановки: взаимная доля встречи на постоянном сдвиге (как V2),
     и ещё общий след - все взаимные куски вместе в доле мест (JOINT). Одна карта не решает: STRONG по одной
     расстановке - только при PS_MANY местах и больше в CO_BLOCKS блоках; при 2..PS_MANY-1 местах нужны две улики из
     трёх вне карты: порядок номеров (тот же набор, номера не дальше ORDER_REACH), строительные свойства MCD (тип
     клетки, броня, горючесть, топливо, звук шагов) и дополняющая геометрия (воксели обоих кусков касаются на общей
     грани, доля касания >= CONTACT). Модуль - стыкуется по оси с семьёй кадров того же строительного класса MCD
     (своя копия или разные соседи), геометрия на грани сходится; только CANDIDATE.

Пороги заданы до прогона и под ошибки не подстраиваются. Правило спора типа выбрано, когда ошибки контроля V2 уже
были видны (специалист назвал их примером), поэтому точность типа на контроле - не независимая оценка: её даст
новый слепой holdout. VERIFIED ставит только человек.

    py -3.13 tools/hdart/relation_discovery_v3.py index      маски всех кадров (по индексу V2) -> index/masks.npz
    py -3.13 tools/hdart/relation_discovery_v3.py discover   доводы 60 кадров holdout V8 -> relations_v3.json
    py -3.13 tools/hdart/relation_discovery_v3.py controls   те же детекторы на парах эталонов V4_R1, V5, V7
    py -3.13 tools/hdart/relation_discovery_v3.py report     безопасность, существование, тип, полнота -> report.md
"""
import argparse
import os
import sys
import time
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir             # noqa: E402
import relation_discovery_v2 as v2        # noqa: E402

ENC = ir.ENC
OUT = os.path.join(ir.PROBES, "relation-discovery-v3-prep")
H8, CONTROLS = v2.H8, v2.CONTROLS

# пороги V2 - без изменений
GEO, FUNC, MIN_COLORS, BORDER_KEEP = v2.GEO, v2.FUNC, v2.MIN_COLORS, v2.BORDER_KEEP
CO_STRONG, CO_CAND, CO_BLOCKS = v2.CO_STRONG, v2.CO_CAND, v2.CO_BLOCKS
MOD_SHARE, MOD_PLACES = v2.MOD_SHARE, v2.MOD_PLACES
# новые - заданы до прогона (специалист 02.10: 2-4 расстановки - мало, нужны улики PCK/MCD/порядка)
PS_MANY = 5                      # с этого числа мест у обоих кусков (и CO_BLOCKS блоков) карта решает сама
JOINT = CO_CAND                  # общий след: все взаимные куски вместе в такой доле мест
ORDER_REACH = 6                  # порядок номеров многоклеточной вещи: тот же набор, номера не дальше
CONTACT = 0.5                    # дополняющая геометрия: доля касания вокселей на общей грани
MCD_STRUCT = ("armor", "flammable", "fuel", "footstep")      # плюс тип клетки - строительные свойства
THRESHOLDS = dict(v2.THRESHOLDS, PS_MANY=PS_MANY, JOINT=JOINT, ORDER_REACH=ORDER_REACH, CONTACT=CONTACT,
                  MCD_STRUCT="tile_type," + ",".join(MCD_STRUCT))

GROUP = dict(v2.GROUP, MIRRORED_RECOLOR="derived", NEAR_RECOLOR="derived")
SYMMETRIC = v2.SYMMETRIC + ("MIRRORED_RECOLOR", "NEAR_RECOLOR")
EXACT_TYPES = ("EXACT_COPY_PEER", "EXACT_MIRROR_PEER")
DERIVATION = ("derived", "state", "animation")          # гипотезы вывода спорят между собой; расстановка - нет
DIAGNOSTIC = ("MIRROR",)                                  # не выше RELATED_CANDIDATE и TYPE_OPEN
DETECTOR_ORDER = dict(v2.DETECTOR_ORDER, MIRROR=5)
BINDING, GROUPS, REF_GROUPS, OPEN_REL = v2.BINDING, v2.GROUPS, v2.REF_GROUPS, v2.OPEN_REL
STRONG, CAND = "RELATED_STRONG", "RELATED_CANDIDATE"
T_STRONG, T_OPEN = "TYPE_STRONG", "TYPE_OPEN"
p, split, key, rate, edge = v2.p, v2.split, v2.key, v2.rate, v2.edge


# ---------------------------------------------------------------- 0. граф доводов

class Claims:
    """Довод - (группа, неупорядоченная пара), один раз; опора - утверждения детекторов (тип, направление,
    уровень). Роли без цели и улики V8 - по кадру, как в V2. finalize() считает существование и тип."""

    def __init__(self):
        self.claims = {}
        self.by_asset = defaultdict(set)
        self.self_roles = defaultdict(list)
        self.evidence = defaultdict(list)

    def add(self, e):
        s, t = e["source"].upper(), e["target"].upper()
        if not t or s == t:
            return None
        k = (GROUP[e["type"]], frozenset((s, t)))
        c = self.claims.get(k)
        if c is None:
            c = self.claims[k] = {"pair": sorted((s, t)), "group": k[0], "support": []}
            self.by_asset[s].add(k)
            self.by_asset[t].add(k)
        if not any((x["type"], x["source"], x["target"], x["detector"]) ==
                   (e["type"], s, t, e["detector"]) for x in c["support"]):
            c["support"].append(dict(e, source=s, target=t))
        return c

    def of(self, a):
        return [self.claims[k] for k in self.by_asset.get(a.upper(), ())]

    def pair(self, a, b):
        return [c for c in self.of(a) if b.upper() in c["pair"]]

    def between(self, a, b):
        """Для v2.danger_v2: есть ли хоть один довод на паре."""
        cs = self.pair(a, b)
        return cs[0] if cs else None

    def finalize(self):
        for c in self.claims.values():
            sup = sorted(c["support"], key=lambda e: (e["level"] not in BINDING, e["detector"] in DIAGNOSTIC,
                                                      DETECTOR_ORDER[e["detector"]], e["type"]))
            c["support"] = sup
            prim = sup[0]
            c["type"], c["source"], c["target"] = prim["type"], prim["source"], prim["target"]
            c["existence"] = STRONG if any(e["level"] in BINDING and e["detector"] not in DIAGNOSTIC
                                           for e in sup) else CAND
            c["exact"] = any(e["type"] in EXACT_TYPES for e in sup)
        pairs = defaultdict(list)
        for c in self.claims.values():
            pairs[frozenset(c["pair"])].append(c)
        for cs in pairs.values():
            spoken = sorted({c["group"] for c in cs if c["group"] in DERIVATION and not c["exact"]})
            for c in cs:
                why = []
                if c["existence"] != STRONG:
                    why.append("существование - кандидат")
                if all(e["detector"] in DIAGNOSTIC for e in c["support"]):
                    why.append("только диагностический детектор")
                if c["group"] in spoken and len(spoken) > 1:
                    why.append("спор типа: %s" % "/".join(spoken))
                dirs = {(e["source"], e["target"]) for e in c["support"]
                        if e["level"] in BINDING and e["type"] not in SYMMETRIC}
                if len(dirs) > 1:
                    why.append("спор направления")
                c["type_level"] = T_OPEN if why else T_STRONG
                c["type_open_why"] = why
        return self


def claims_from_v8(rows):
    """Доводы V8 из строк замороженного отчёта (рёбра, обратные чтения), роли без цели и улики - как v2.v8_graph."""
    C = Claims()
    for r in rows:
        a = r["asset_id"].upper()
        for e in r["edges"]:
            if e["relation_type"] == "CANONICAL":
                continue
            if not e["target"]:
                C.self_roles[a].append({"type": e["relation_type"], "level": e["confidence"], "detector": "V8",
                                        "rule": e["rule"], "evidence": e["evidence"]})
                continue
            C.add(edge(e["relation_type"], a, e["target"], e["confidence"], "V8", e["rule"], e["evidence"]))
        for x in r.get("relations_in", []):
            C.add(edge(x["inverse_of"], x["target"], a, x["confidence"], "V8", x["rule"], x["evidence"]))
        for x in r.get("open_evidence", []):
            C.evidence[a].append(dict(x, detector="V8"))
    return C


def add_found(C, found):
    for e in found["edges"]:
        C.add(e)
    for a, roles in found["self_roles"].items():
        C.self_roles[a.upper()] += roles
    return C


def bound(C, a):
    """Кадр не рисуется сам по себе: роль без цели; довод STRONG, где тип открыт, связь симметрична или кадр -
    выводимая сторона."""
    A = a.upper()
    if any(x["level"] in BINDING for x in C.self_roles.get(A, [])):
        return True
    return any(c["existence"] == STRONG and (c["type_level"] == T_OPEN or c["type"] in SYMMETRIC or c["source"] == A)
               for c in C.of(a))


def has_evidence(C, a):
    A = a.upper()
    return bool(C.evidence.get(A)) or any(x["level"] not in BINDING for x in C.self_roles.get(A, [])) or \
        any(c["existence"] != STRONG for c in C.of(a))


def groups_of(C, a, mode):
    """auto - существование STRONG и TYPE_STRONG; strong - существование STRONG, группа гипотезы; discovery - любые
    доводы и роли."""
    A = a.upper()
    lv = BINDING + (("CANDIDATE",) if mode == "discovery" else ())
    gs = {GROUP[x["type"]] for x in C.self_roles.get(A, []) if x["level"] in lv and x["type"] in GROUP}
    for c in C.of(a):
        if mode == "discovery" or (c["existence"] == STRONG and (mode == "strong" or c["type_level"] == T_STRONG)):
            gs.add(c["group"])
    return sorted(gs) or ["canonical"]


def pipe_roles(C, a):
    """Роли для замороженной оси B: свои и доводы с TYPE_STRONG (симметричные или кадр - выводимая сторона)."""
    A = a.upper()
    roles = {x["type"] for x in C.self_roles.get(A, []) if x["level"] in BINDING}
    roles |= {v2.PIPE_ROLE.get(c["type"], c["type"]) for c in C.of(a)
              if c["existence"] == STRONG and c["type_level"] == T_STRONG and (c["type"] in SYMMETRIC or c["source"] == A)}
    return sorted(roles) or ["CANONICAL"]


# ---------------------------------------------------------------- контекст: маски всех кадров

class Masks:
    """Маски непустых кадров индекса V2 одной матрицей: IoU кадра со всеми сразу."""

    def __init__(self, keys, packed, shape):
        self.keys = list(keys)
        self.pos = {k: i for i, k in enumerate(self.keys)}
        self.shape = tuple(shape)
        n = shape[0] * shape[1]
        self.M = np.unpackbits(packed, axis=1)[:, :n].astype(np.float32)
        self.area = self.M.sum(1)

    def iou(self, q):
        qv = q.ravel().astype(np.float32)
        inter = self.M @ qv
        return inter / np.maximum(self.area + qv.sum() - inter, 1)


def build_masks(world, ix):
    keys, rows, shape = [], [], None
    for i, k in enumerate(sorted(ix.frames)):
        s, f = split(k)
        im = world.sprite(s.lower(), f, None)
        if im is None:
            continue
        m = np.asarray(im.convert("RGBA"))[..., 3] > 0
        if shape is None:
            shape = m.shape
        if m.shape != shape:
            continue
        keys.append(k)
        rows.append(np.packbits(m.ravel()))
        if i % 5000 == 0:
            print("маски: %d из %d" % (i, len(ix.frames)), flush=True)
    return keys, np.stack(rows), shape


def load_masks(out=OUT):
    path = p(out, "index", "masks.npz")
    if not os.path.exists(path):
        raise SystemExit("нет %s - сначала: relation_discovery_v3.py index" % path)
    z = np.load(path, allow_pickle=False)
    return Masks([str(k) for k in z["keys"]], z["packed"], z["shape"])


class Ctx(v2.Ctx):
    def __init__(self, world=None, index=None, masks=None):
        super().__init__(world, index)
        self.masks = masks

    def info(self, k):
        return self.st.info(*split(k))

    def mcd_mirror_compatible(self, a, b):
        """Тот же тип клетки, воксели B - воксели A, отражённые по диагонали клетки (горизонтальное отражение
        изометрического кадра меняет местами оси x и y), или те же (симметричный объём)."""
        ia, ib = self.info(a), self.info(b)
        if not (ia.get("rec") and ib.get("rec")) or ia["tile_type"] != ib["tile_type"]:
            return False
        va, vb = ia["vox"], ib["vox"]
        return bool((vb == va.transpose(0, 2, 1)).all() or (vb == va).all())


# ---------------------------------------------------------------- 2. MIRRORED_RECOLOR_V1 (диагностика)

def recolor_test(ctx, a, b, flip, B=None):
    """Тест перекраски пары с отражением B или без: (оценки, None) или (None, почему нет)."""
    A = ctx.rgba(a)
    if B is None:
        B = ctx.rgba(b)
    if A is None or B is None:
        return None, "нет кадра"
    BB = np.ascontiguousarray(B[:, ::-1]) if flip else B
    f_ab, f_ba, iou, na, nb, biou = v2.funcs(A, BB)
    if iou < GEO:
        return None, "силуэт %.3f" % iou
    if max(f_ab, f_ba) < FUNC:
        return None, "функция %.3f/%.3f" % (f_ab, f_ba)
    nbase = max(na, nb) if min(f_ab, f_ba) >= FUNC else (na if f_ab >= FUNC else nb)
    if nbase < MIN_COLORS:
        return None, "цветов основы %d" % nbase
    if biou < BORDER_KEEP:
        return None, "границ %.2f" % biou
    mcd = ctx.mcd_mirror_compatible(a, b) if flip else ctx.mcd_compatible(a, b)
    return {"silhouette": round(iou, 4), "topology": round(biou, 3), "f_ab": round(f_ab, 3), "f_ba": round(f_ba, 3),
            "base_colors": nbase, "mcd": mcd,
            "direction": "peer" if min(f_ab, f_ba) >= FUNC else ("b_from_a" if f_ab >= FUNC else "a_from_b")}, None


def mirror_edge(a, b, flip, sc):
    typ, rule = ("MIRRORED_RECOLOR", "MR1") if flip else ("NEAR_RECOLOR", "NR1")
    e = edge(typ, a, b, "CANDIDATE", "MIRROR", rule,
             "%s: силуэт %.3f, границ %.2f, функция %.3f/%.3f, цветов основы %d, MCD %s" % (
                 "отражение" if flip else "силуэт почти тот же", sc["silhouette"], sc["topology"], sc["f_ab"],
                 sc["f_ba"], sc["base_colors"], "совместим" if sc["mcd"] else "нет"))
    e["scores"] = sc
    return e


def permuted(ctx, b, seed):
    """Отрицательный контроль: те же цвета B, перемешанные внутри силуэта - структура пропала, палитра та же."""
    B = ctx.rgba(b).copy()
    m = B[..., 3] > 0
    px = B[m]
    B[m] = px[np.random.default_rng(seed).permutation(len(px))]
    return B


def mirror_near_edges(ctx, a):
    """Кандидаты по всему индексу: отражённый силуэт и почти тот же силуэт (не побайтно равный - его ведёт V2)."""
    A = ctx.rgba(a)
    if A is None or ctx.masks is None:
        return []
    m = A[..., 3] > 0
    if m.shape != ctx.masks.shape:
        return []
    direct, mirr = ctx.masks.iou(m), ctx.masks.iou(m[:, ::-1])
    skip = {a.upper()} | ctx.ix.exact(a) | ctx.ix.mirror(a) | ctx.ix.same_mask(a)
    out = []
    for flip, arr in ((False, direct), (True, mirr)):
        for i in np.nonzero(arr >= GEO)[0]:
            b = ctx.masks.keys[i]
            if b in skip or (flip and direct[i] >= GEO):
                continue
            sc, _why = recolor_test(ctx, a, b, flip)
            if sc:
                out.append(mirror_edge(a, b, flip, sc))
    return out


def mirror_near_pair(ctx, a, b):
    """Тот же тест на одной паре (контроль): отражение, если прямой силуэт не совпал."""
    a, b = a.upper(), b.upper()
    if b in ctx.ix.exact(a) or b in ctx.ix.mirror(a) or b in ctx.ix.same_mask(a):
        return []
    A, B = ctx.rgba(a), ctx.rgba(b)
    if A is None or B is None or A.shape != B.shape:
        return []
    ma, mb = A[..., 3] > 0, B[..., 3] > 0
    d = (ma & mb).sum() / max((ma | mb).sum(), 1)
    flip = d < GEO
    sc, _why = recolor_test(ctx, a, b, flip)
    return [mirror_edge(a, b, flip, sc)] if sc else []


# ---------------------------------------------------------------- 3. PLACEMENT_STRUCTURE_V2

def contact(va, vb, o):
    """Доля касания вокселей A и B на общей грани при сдвиге B = A + o (только по одной оси); None - грани нет."""
    if sum(abs(v) for v in o) != 1:
        return None
    dx, dy, dz = o
    if dx:
        fa, fb = va[:, :, 15 if dx > 0 else 0], vb[:, :, 0 if dx > 0 else 15]
    elif dy:
        fa, fb = va[:, 15 if dy > 0 else 0, :], vb[:, 0 if dy > 0 else 15, :]
    else:
        fa, fb = va[11 if dz > 0 else 0], vb[0 if dz > 0 else 11]
    if not fa.any() or not fb.any():
        return 0.0
    return float((fa & fb).sum() / min(fa.sum(), fb.sum()))


def struct_class(info):
    if not info.get("rec"):
        return None
    return (int(info["tile_type"]),) + tuple(int(info["phys"][k]) for k in MCD_STRUCT)


def off_map(ctx, a, b, o):
    """Улики вне карты для пары кусков на сдвиге o: порядок номеров, строительные свойства MCD, геометрия."""
    (sa, fa), (sb, fb) = split(a), split(b)
    ia, ib = ctx.info(a), ctx.info(b)
    ca, cb = struct_class(ia), struct_class(ib)
    c = contact(ia["vox"], ib["vox"], o) if ia.get("rec") and ib.get("rec") else None
    return {"order": sa == sb and 0 < abs(fa - fb) <= ORDER_REACH,
            "mcd": ca is not None and ca == cb,
            "geometry": c is not None and c >= CONTACT}, c


def signatures(ctx, a):
    """Места кадра вне пола: [(блок, {(сдвиг, слой a, слой b, b)})] - соседи на 27 сдвигах, пол не считается."""
    A = a.upper()
    out = []
    for _t, b, grid, (x, y, z), la in ctx.places.of(a):
        if la == 0:
            continue
        s = set()
        for o in v2.OFFSETS:
            for lb, kb in grid.get((x + o[0], y + o[1], z + o[2]), []):
                if lb == 0 or kb == A or (o == (0, 0, 0) and lb == la):
                    continue
                s.add((o, la, lb, kb))
        out.append((b, s))
    return out


def placement_structure(ctx, a, only=None):
    """COMPOSITE_PART по узору: взаимные куски на постоянном сдвиге, общий след, повтор; улики вне карты при
    малом числе мест. Без взаимности (стул у стола) довода нет вовсе."""
    sig = signatures(ctx, a)
    n = len(sig)
    if n < 2:
        return []
    cnt = Counter(e for _b, s in sig for e in s)
    mutual = {}
    for e, k in cnt.items():
        if k / n < CO_CAND:
            continue
        o, la, lb, kb = e
        s_ba, nb = v2.reverse_share(ctx, a, kb, o, la, lb)
        if s_ba >= CO_CAND and nb >= 2:
            mutual[e] = (k, s_ba, nb)
    if not mutual:
        return []
    with_all = [b for b, s in sig if all(e in s for e in mutual)]
    joint, blocks = len(with_all) / n, len(set(with_all))
    out, done = [], set()
    for e, (k, s_ba, nb) in sorted(mutual.items(), key=lambda kv: (-min(kv[1][0] / n, kv[1][1]), kv[0][3])):
        o, la, lb, kb = e
        if kb in done or (only is not None and kb != only.upper()):
            continue
        done.add(kb)
        ev, c = off_map(ctx, a, kb, o)
        share, places = min(k / n, s_ba), min(n, nb)
        n_ev = sum(ev.values())
        if share >= CO_STRONG and joint >= CO_STRONG and places >= PS_MANY and blocks >= CO_BLOCKS:
            level, rule = "STRONG", "P3"
        elif joint >= JOINT and n_ev >= 2:
            level, rule = "STRONG", "P3x"
        else:
            level, rule = "CANDIDATE", "P3c"
        e2 = edge("COMPOSITE_PART", a, kb, level, "PLACE", rule,
                  "сдвиг %s, слои %d/%d: a %d из %d мест, b %.2f из %d; след из %d кусков вместе %.2f, блоков %d; "
                  "вне карты: порядок %s, MCD %s, геометрия %s" % (
                      list(o), la, lb, k, n, s_ba, nb, len(mutual) + 1, joint, blocks,
                      "да" if ev["order"] else "нет", "да" if ev["mcd"] else "нет",
                      "нет грани" if c is None else "%.2f" % c))
        e2["scores"] = {"share": round(share, 3), "joint": round(joint, 3), "places": places, "blocks": blocks,
                        "footprint": len(mutual) + 1, "off_map": ev}
        out.append(e2)
    return out


def module_structure(ctx, a):
    """STRUCTURAL_MODULAR (CANDIDATE): в доле мест >= MOD_SHARE по оси вплотную кадр того же строительного класса MCD
    (своя копия или другой), воксели на грани касаются; ни один сосед не держит узор (иначе это составной)."""
    ia = ctx.info(a)
    cls = struct_class(ia)
    if cls is None:
        return None
    A = a.upper()
    pa = [pl for pl in ctx.places.of(a) if pl[4] != 0]
    if len(pa) < MOD_PLACES:
        return None
    hit, partners, axis = 0, Counter(), Counter()
    for _t, _b, grid, (x, y, z), la in pa:
        here = set()
        for o in v2.AXES:
            for l2, k2 in grid.get((x + o[0], y + o[1], z), []):
                if l2 != la:
                    continue
                i2 = ctx.info(k2)
                if struct_class(i2) != cls:
                    continue
                c = contact(ia["vox"], i2["vox"], o)
                if c is not None and c >= CONTACT:
                    here.add(k2)
                    axis["x" if o[0] else "y"] += 1
        hit += bool(here)
        partners.update(here)
    share = hit / len(pa)
    if share < MOD_SHARE:
        return None
    others = {k: v for k, v in partners.items() if k != A and k not in (ctx.ix.exact(a) if ctx.ix else set())}
    own = len(partners) - len(others)
    if others and max(others.values()) / len(pa) >= CO_CAND and not own and len(others) == 1:
        return None                                   # один постоянный сосед - узор составного, не модуль
    return {"type": "STRUCTURAL_MODULAR", "level": "CANDIDATE", "detector": "PLACE", "rule": "P4c",
            "evidence": "стыкуется по оси в %d из %d мест (%.2f): своя копия %s, другие %d (%s), оси %s" % (
                hit, len(pa), share, "да" if own else "нет", len(others),
                ", ".join(sorted(others)[:4]), dict(axis))}


# ---------------------------------------------------------------- discover: 60 кадров holdout V8

def discover(ctx, keys):
    edges, self_roles = [], {}
    for a in keys:
        es = v2.exact_edges(ctx.ix, a) + v2.mcd_edges(ctx, a) + v2.recolor_edges(ctx, a) + \
            placement_structure(ctx, a) + mirror_near_edges(ctx, a)
        m = module_structure(ctx, a)
        if m:
            self_roles[a.upper()] = [m]
        edges += es
        print(a, dict(Counter("%s %s" % (e["type"], e["level"]) for e in es)), "модуль" if m else "", flush=True)
    return {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "thresholds": THRESHOLDS, "keys": list(keys),
            "edges": edges, "self_roles": self_roles,
            "note": "утверждения детекторов, не маршрут; VERIFIED ставит только человек"}


# ---------------------------------------------------------------- контроль

def detect_pair(ctx, a, b):
    a, b = a.upper(), b.upper()
    out = []
    if b in ctx.ix.exact(a):
        out.append(edge("EXACT_COPY_PEER", a, b, "STRONG", "EXACT", "X1", "пиксели совпадают"))
    elif b in ctx.ix.mirror(a):
        out.append(edge("EXACT_MIRROR_PEER", a, b, "STRONG", "EXACT", "X2", "пиксели совпадают после отражения"))
    elif b in ctx.ix.same_mask(a):
        e = v2.recolor_pair(ctx, a, b)
        if e:
            out.append(e)
    else:
        out += mirror_near_pair(ctx, a, b)
    if split(a)[0] == split(b)[0]:
        out += [e for e in v2.mcd_edges(ctx, a) if {e["source"], e["target"]} == {a, b}]
    out += placement_structure(ctx, a, only=b)
    return out


def claim_outcome(c, rel):
    if rel in ("", "OPEN"):
        return "open"
    if rel == "NONE":
        return "wrong"
    return "ok" if c["group"] in REF_GROUPS.get(rel, set()) else "wrong"


def short(c):
    return {"group": c["group"], "type": c["type"], "source": c["source"], "target": c["target"],
            "existence": c["existence"], "type_level": c["type_level"], "type_open_why": c["type_open_why"],
            "support": [{"type": e["type"], "level": e["level"], "detector": e["detector"], "rule": e["rule"],
                         "evidence": e["evidence"], **({"scores": e["scores"]} if "scores" in e else {})}
                        for e in c["support"]]}


def controls(ctx):
    rows, seen = [], set()
    for name in CONTROLS:
        for x in ir.read_tsv(p(ir.PROBES, name, "reference_pairs.tsv")):
            a, b = x["asset_id"].upper(), x["relative"].upper()
            k = frozenset((a, b))
            if k in seen or a == b:
                continue
            seen.add(k)
            C = Claims()
            for e in detect_pair(ctx, a, b):
                C.add(e)
            C.finalize()
            rel = x["ref_pair_relation"]
            perm = []
            for c in C.claims.values():
                for e in c["support"]:
                    if e["detector"] == "MIRROR":
                        flip = e["type"] == "MIRRORED_RECOLOR"
                        sc, _w = recolor_test(ctx, a, b, flip, B=permuted(ctx, b, 7))
                        perm.append(bool(sc))
            rows.append({"holdout": name, "asset_id": a, "relative": b, "ref": rel, "perm_fired": perm,
                         "claims": [dict(short(c), outcome=claim_outcome(c, rel)) for c in C.claims.values()]})
        print(name, "пар", len(rows), flush=True)
    return {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "thresholds": THRESHOLDS, "pairs": rows}


def judged(rel):
    return rel not in ("", "OPEN")


def existence_stats(pairs_claims):
    """[(ref, [claim])] -> точность существования (пара со STRONG, судима), точность типа (TYPE_STRONG, судимы)."""
    ex = [(rel, cs) for rel, cs in pairs_claims if judged(rel) and any(c["existence"] == STRONG for c in cs)]
    ty = [(rel, c) for rel, cs in pairs_claims if judged(rel) for c in cs if c["type_level"] == T_STRONG]
    return {"existence_precision": rate(sum(rel != "NONE" for rel, _ in ex), len(ex)), "existence_judged": len(ex),
            "existence_wrong": len([1 for rel, _ in ex if rel == "NONE"]),
            "typed_precision": rate(sum(claim_outcome(c, rel) == "ok" for rel, c in ty), len(ty)), "typed_judged": len(ty),
            "typed_by_group": {g: {"ok": sum(claim_outcome(c, rel) == "ok" for rel, c in ty if c["group"] == g),
                                   "n": sum(c["group"] == g for _rel, c in ty)} for g in sorted({c["group"] for _r, c in ty})}}


def recall_stats(pairs_claims):
    """По смыслу эталона: найдено существование STRONG (любой группы), обнаружено (нужная группа, любой уровень),
    решено автоматически (нужная группа, STRONG и TYPE_STRONG)."""
    out = {}
    for rel in REF_GROUPS:
        pos = [cs for r, cs in pairs_claims if r == rel]
        out[rel] = {"n": len(pos),
                    "existence": sum(any(c["existence"] == STRONG for c in cs) for cs in pos),
                    "discovery": sum(any(c["group"] in REF_GROUPS[rel] for c in cs) for cs in pos),
                    "strong": sum(any(c["group"] in REF_GROUPS[rel] and c["existence"] == STRONG for c in cs) for cs in pos),
                    "auto": sum(any(c["group"] in REF_GROUPS[rel] and c["existence"] == STRONG and
                                    c["type_level"] == T_STRONG for c in cs) for cs in pos)}
    return out


def mirror_stats(pairs_claims_perm):
    """Диагностика MIRRORED_RECOLOR / NEAR_RECOLOR: по смыслу эталона, сколько раз сработал; перемешанный контроль."""
    by = defaultdict(Counter)
    perm = Counter()
    for rel, cs, pf in pairs_claims_perm:
        for c in cs:
            for e in c["support"]:
                if e["detector"] == "MIRROR":
                    tier = "%s MCD %s" % (e["type"], "да" if e.get("scores", {}).get("mcd") else "нет")
                    by[tier][rel or "OPEN"] += 1
        for f in pf:
            perm["fired" if f else "silent"] += 1
    return {"by_tier": {k: dict(v) for k, v in by.items()}, "permuted": dict(perm)}


def control_stats(ctl):
    pc = [(r["ref"], r["claims"]) for r in ctl["pairs"]]
    neg = [cs for rel, cs in pc if rel == "NONE"]
    wrong_ex = ["%s %s (%s): %s" % (r["asset_id"], r["relative"], r["holdout"],
                                     ", ".join("%s %s" % (c["type"], c["existence"]) for c in r["claims"]
                                               if c["existence"] == STRONG))
                for r in ctl["pairs"] if r["ref"] == "NONE" and any(c["existence"] == STRONG for c in r["claims"])]
    wrong_ty = ["%s %s (%s): %s %s, эталон %s" % (r["asset_id"], r["relative"], r["holdout"], c["type"], c["rule"]
                                                   if "rule" in c else c["support"][0]["rule"], r["ref"])
                for r in ctl["pairs"] if judged(r["ref"]) for c in r["claims"]
                if c["type_level"] == T_STRONG and c["outcome"] == "wrong"]
    opened = Counter(w.split(":")[0] for r in ctl["pairs"] for c in r["claims"] if c["existence"] == STRONG
                     for w in c["type_open_why"])
    return dict(existence_stats(pc), recall=recall_stats(pc), none_pairs=len(neg),
                none_with_strong=sum(any(c["existence"] == STRONG for c in cs) for cs in neg),
                none_with_any=sum(bool(cs) for cs in neg), existence_wrong_list=wrong_ex, typed_wrong_list=wrong_ty,
                type_opened=dict(opened),
                mirror=mirror_stats([(r["ref"], r["claims"], r["perm_fired"]) for r in ctl["pairs"]]))


# ---------------------------------------------------------------- отчёт на 60

def score_rows(rows, C, pairs, fsets, v8):
    out = []
    for r in rows:
        a = r["asset_id"]
        pipe, _why = v8.pipeline_of(r["semantic_eff"], r["surface"], pipe_roles(C, a))
        creative = pipe == "OBJECT_PIPELINE" and not bound(C, a) and not has_evidence(C, a)
        out.append({"asset_id": a, "pipeline": pipe, "creative": creative, "bound": bound(C, a),
                    "ref_pipeline": r["ref_pipeline"], "ref_role_groups": r["ref_role_groups"],
                    "ref_role_status": r["ref_role_status"],
                    "g_auto": groups_of(C, a, "auto"), "g_strong": groups_of(C, a, "strong"),
                    "g_discovery": groups_of(C, a, "discovery"),
                    "danger": v2.danger_v2(r, creative, C, pairs.get(a, []), fsets[a.upper()])})
    return out


def pairs_of_60(C, keys, pairs):
    """Пары эталона 60 кадров: [(смысл, [довод])], каждая неупорядоченная пара один раз."""
    out, seen = [], set()
    for a in keys:
        for x in pairs.get(a, []):
            k = frozenset((a.upper(), x["relative"].upper()))
            if k in seen:
                continue
            seen.add(k)
            out.append((x["ref_pair_relation"], C.pair(a, x["relative"]), a.upper(), x["relative"].upper()))
    return out


def do_report(out=OUT, h8=H8):
    import map_mockup as mm
    import routing_model_v8 as v8
    rep, _ref, pairs, h, sha = v2.h8_inputs(h8)
    found = ir.load_json(p(out, "relations_v3.json"))
    ctl = ir.load_json(p(out, "controls.json")) if os.path.exists(p(out, "controls.json")) else None
    ix = v2.load_index(v2.OUT)
    keys = [x["asset_id"] for x in h["items"]]
    for rr_ in (rep["rows"], rep["rows_logic"]):
        assert [r["asset_id"] for r in rr_] == keys, "строки отчёта V8 не в порядке holdout"
    mcd = v8.Mcd(mm.World())
    fsets = {a.upper(): v8.facts(mcd, a) for a in keys}
    C8 = claims_from_v8(rep["rows"]).finalize()
    C = add_found(claims_from_v8(rep["rows"]), found).finalize()
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "RELATION_DISCOVERY_V3_PREP",
           "thresholds": THRESHOLDS, "h8_sha256": sha, "relations_v3_created": found["created"], "axes": {}}
    for axis, rows in (("logic", rep["rows_logic"]), ("end_to_end", rep["rows"])):
        s8, s3 = score_rows(rows, C8, pairs, fsets, v8), score_rows(rows, C, pairs, fsets, v8)
        res["axes"][axis] = {
            "frozen_dangerous": [r["asset_id"] for r in rows if v8.dangerous_creative_standalone(r)],
            "v3_v8claims": {r["asset_id"]: r["danger"] for r in s8 if r["danger"]},
            "v3": {r["asset_id"]: r["danger"] for r in s3 if r["danger"]},
            "creative": {"frozen": sum(r["creative"] for r in rows), "v8claims": sum(r["creative"] for r in s8),
                         "v3": sum(r["creative"] for r in s3), "v3_list": [r["asset_id"] for r in s3 if r["creative"]]},
            "logic_v3": v2.logic(s3),
            "groups": {m: v2.group_metrics(s3, "g_" + m) for m in ("auto", "strong", "discovery")},
            "rows": s3}
    pc = pairs_of_60(C, keys, pairs)
    pc2 = [(rel, cs) for rel, cs, _a, _b in pc]
    multi = ["%s %s: %s" % (a, b, " + ".join("%s %s/%s" % (c["type"], c["existence"][8:], c["type_level"][5:])
                                             for c in cs)) for rel, cs, a, b in pc if len(cs) > 1]
    K = {k.upper() for k in keys}
    all60 = [c for c in C.claims.values() if set(c["pair"]) & K]
    pmap = {frozenset((a, b)): rel for rel, _cs, a, b in pc}
    v8only = {k for k, c in C8.claims.items()}
    unj = Counter((c["group"], c["existence"], c["type_level"]) for c in all60 if frozenset(c["pair"]) not in pmap)
    ex_wrong = ["%s %s: %s" % (a, b, ", ".join("%s %s" % (c["type"], "V8" if (c["group"], frozenset(c["pair"])) in v8only
                                                         else c["support"][0]["detector"]) for c in cs if c["existence"] == STRONG))
                for rel, cs, a, b in pc if rel == "NONE" and any(c["existence"] == STRONG for c in cs)]
    ty_wrong = ["%s %s: %s %s (%s), эталон %s" % (a, b, c["type"], c["support"][0]["rule"], c["support"][0]["detector"], rel)
                for rel, cs, a, b in pc if judged(rel) for c in cs if c["type_level"] == T_STRONG and claim_outcome(c, rel) == "wrong"]
    exact = []
    for a in keys:
        for x in pairs.get(a, []):
            b = x["relative"].upper()
            if b in ix.exact(a) or b in ix.mirror(a):
                exact.append({"pair": [a, b], "ref": x["ref_pair_relation"],
                              "found": any(c["exact"] for c in C.pair(a, b))})
    mir = [(rel, cs, []) for rel, cs in pc2]
    res.update({"existence": existence_stats(pc2), "recall": recall_stats(pc2), "existence_wrong": ex_wrong,
                "typed_wrong": ty_wrong, "multi_claim_pairs": multi, "exact": exact,
                "unjudged_claims": {"%s %s %s" % k: v for k, v in sorted(unj.items())},
                "mirror_60": mirror_stats(mir),
                "mirror_60_list": ["%s %s %s %s" % (e["type"], e["source"], e["target"], e["evidence"])
                                   for e in found["edges"] if e["detector"] == "MIRROR"],
                "type_opened_60": dict(Counter(w.split(":")[0] for c in all60 if c["existence"] == STRONG
                                               for w in c["type_open_why"])),
                "modules": {a: r[0]["evidence"] for a, r in found["self_roles"].items()},
                "composite_edges": ["%s %s %s %s: %s" % (e["source"], e["target"], e["level"], e["rule"], e["evidence"])
                                    for e in found["edges"] if e["type"] == "COMPOSITE_PART"],
                "claims_60": [short(c) for c in all60],
                "controls": control_stats(ctl) if ctl else None})
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    print("отчёт: %s" % p(out, "report.md"))


def fg(gm):
    k = round(gm["recall"] * gm["reference"]) if gm["recall"] is not None else 0
    return "%s (%d/%d)" % (gm["recall"], k, gm["reference"])


def write_md(out, res):
    L = ["# RELATION_DISCOVERY_V3_PREP — существование и тип связи, 60 кадров holdout V8", "",
         "Диагностика на известных 60 (специалист 02.10): маршрут B, EXACT_COPY, правила MCD-state и граф анимации "
         "не менялись, V8 остаётся FAIL. Пороги заданы до прогона: %s." % ", ".join("%s %s" % kv for kv in res["thresholds"].items()),
         "Входы V8 только читаются: %s." % ", ".join("%s %s" % (k, v[:12]) for k, v in res["h8_sha256"].items()), ""]
    for axis, name in (("logic", "ось A эталона (как B_SAFETY)"), ("end_to_end", "ось A специалиста (как E2E_SAFETY)")):
        x = res["axes"][axis]
        L += ["## Безопасность — %s" % name, "",
              "| правило | опасных | кадры |", "|---|---|---|",
              "| V8 замороженное | %d | %s |" % (len(x["frozen_dangerous"]), " ".join(x["frozen_dangerous"])),
              "| V3, доводы V8 | %d | %s |" % (len(x["v3_v8claims"]), " ".join(x["v3_v8claims"])),
              "| V3, доводы V8 + V3 | %d | %s |" % (len(x["v3"]), " ".join(x["v3"])), "",
              "Одиночных творческих заказов: замороженный %d, доводы V8 %d, V8 + V3 %d (%s)." % (
                  x["creative"]["frozen"], x["creative"]["v8claims"], x["creative"]["v3"], ", ".join(x["creative"]["v3_list"]) or "нет"),
              "Логика B (роли только с TYPE_STRONG): %s (%s/%s, охват %s)." % (
                  x["logic_v3"]["accuracy"], x["logic_v3"]["ok"], x["logic_v3"]["decided"], x["logic_v3"]["coverage"]), ""]
        if x["v3"]:
            L += ["- %s: %s" % (a, "; ".join(w)) for a, w in x["v3"].items()] + [""]
    e = res["existence"]
    L += ["## Существование и тип на 60", "",
          "| мера | значение | судимых |", "|---|---|---|",
          "| точность существования (пара со STRONG, эталон не NONE) | %s | %d (неверно %d) |" % (
              e["existence_precision"], e["existence_judged"], e["existence_wrong"]),
          "| точность типа (доводы TYPE_STRONG) | %s | %d |" % (e["typed_precision"], e["typed_judged"]), ""]
    L += ["Тип по группам: " + ", ".join("%s %d/%d" % (g, v["ok"], v["n"]) for g, v in e["typed_by_group"].items()), "",
          "Тип открыт (довод STRONG): " + (", ".join("%s %d" % kv for kv in res["type_opened_60"].items()) or "нет"), ""]
    if res["existence_wrong"]:
        L += ["Существование неверно (эталон NONE):", ""] + ["- " + w for w in res["existence_wrong"]] + [""]
    if res["typed_wrong"]:
        L += ["Тип неверен:", ""] + ["- " + w for w in res["typed_wrong"]] + [""]
    if res["multi_claim_pairs"]:
        L += ["Пары с несколькими доводами (эталон знает один смысл на пару):", ""] + ["- " + w for w in res["multi_claim_pairs"]] + [""]
    L += ["## Полнота по парам эталона на 60", "",
          "Существование — довод STRONG любой группы; обнаружение — довод нужной группы любого уровня (кандидат уводит "
          "кадр в ревью); STRONG — нужная группа, существование STRONG; авто — ещё и TYPE_STRONG.", "",
          "| смысл | пар | существование | обнаружение | STRONG | авто |", "|---|---|---|---|---|---|"]
    for rel, v in res["recall"].items():
        L.append("| %s | %d | %s | %s | %s | %s |" % (rel, v["n"], *(rate(v[k], v["n"]) for k in ("existence", "discovery", "strong", "auto"))))
    ex = res["exact"]
    L += ["", "Точные копии: пар %d, связано доводом с опорой EXACT %d (%s)." % (
        len(ex), sum(x["found"] for x in ex), rate(sum(x["found"] for x in ex), len(ex))), ""]
    gm = res["axes"]["logic"]["groups"]
    L += ["## Полнота по группам (кадр, ось A эталона)", "",
          "| группа | авто | STRONG (гипотеза) | обнаружение | точность обнаружения |", "|---|---|---|---|---|"]
    for gr in GROUPS:
        L.append("| %s | %s | %s | %s | %s (%d) |" % (gr, fg(gm["auto"][gr]), fg(gm["strong"][gr]), fg(gm["discovery"][gr]),
                                                    gm["discovery"][gr]["precision"], gm["discovery"][gr]["predicted"]))
    L += ["", "Доводы на парах, которых эталон не видел: " + ", ".join("%s %d" % kv for kv in res["unjudged_claims"].items()), "",
          "## Составной (PLACEMENT_STRUCTURE_V2)", ""] + ["- " + w for w in res["composite_edges"]] + [
          "", "## Модуль (кандидаты)", ""] + ["- %s: %s" % kv for kv in res["modules"].items()] + [
          "", "## MIRRORED_RECOLOR_V1 / NEAR_RECOLOR на 60 (только кандидаты)", ""] + \
         ["- " + w for w in res["mirror_60_list"]] + [""]
    m = res["mirror_60"]["by_tier"]
    L += ["По смыслу эталона: " + "; ".join("%s: %s" % (k, v) for k, v in m.items()), ""]
    c = res["controls"]
    if c:
        L += ["## Контроль: пары эталонов V4_R1, V5, V7", "",
              "| мера | значение | судимых |", "|---|---|---|",
              "| точность существования | %s | %d (неверно %d) |" % (c["existence_precision"], c["existence_judged"], c["existence_wrong"]),
              "| точность типа TYPE_STRONG | %s | %d |" % (c["typed_precision"], c["typed_judged"]), "",
              "Тип по группам: " + ", ".join("%s %d/%d" % (g, v["ok"], v["n"]) for g, v in c["typed_by_group"].items()),
              "Тип открыт (довод STRONG): " + ", ".join("%s %d" % kv for kv in c["type_opened"].items()),
              "Пар NONE %d, со STRONG %d, с любым доводом %d." % (c["none_pairs"], c["none_with_strong"], c["none_with_any"]), "",
              "| смысл | пар | существование | обнаружение | STRONG | авто |", "|---|---|---|---|---|---|"]
        for rel, v in c["recall"].items():
            L.append("| %s | %d | %s | %s | %s | %s |" % (rel, v["n"], *(rate(v[k], v["n"]) for k in ("existence", "discovery", "strong", "auto"))))
        L += ["", "MIRRORED_RECOLOR / NEAR_RECOLOR на контроле: " + "; ".join(
            "%s: %s" % (k, v) for k, v in c["mirror"]["by_tier"].items()) + ". Перемешанный контроль: %s." % c["mirror"]["permuted"], ""]
        if c["existence_wrong_list"]:
            L += ["Существование неверно:", ""] + ["- " + w for w in c["existence_wrong_list"]] + [""]
        if c["typed_wrong_list"]:
            L += ["Тип неверен:", ""] + ["- " + w for w in c["typed_wrong_list"]] + [""]
    with open(p(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L))


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["index", "discover", "controls", "report"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.cmd == "index":
        import map_mockup as mm
        os.makedirs(p(a.out, "index"), exist_ok=True)
        keys, packed, shape = build_masks(mm.World(), v2.load_index(v2.OUT))
        np.savez_compressed(p(a.out, "index", "masks.npz"), keys=np.array(keys), packed=packed, shape=np.array(shape))
        print("маски: %d кадров %s" % (len(keys), shape))
    elif a.cmd == "discover":
        h = ir.load_json(p(H8, "holdout.json"))
        ctx = Ctx(index=v2.load_index(v2.OUT), masks=load_masks(a.out))
        ir.dump_json(p(a.out, "relations_v3.json"), discover(ctx, [x["asset_id"] for x in h["items"]]))
    elif a.cmd == "controls":
        ctx = Ctx(index=v2.load_index(v2.OUT), masks=load_masks(a.out))
        ir.dump_json(p(a.out, "controls.json"), controls(ctx))
    else:
        do_report(a.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
