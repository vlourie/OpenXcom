#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RELATION_DISCOVERY_V4_PREP - PLACEMENT_STRUCTURE_V3 и RECOLOR_DERIVED_DISCOVERY_V4 (специалист 02.10). CPU, чтение.

Пересуд таксономии (probes/relation-taxonomy-adjudication) и второй судья (probes/relation-truth-v2) дали истину v2
с CLOSED / OPEN. Заморозки нет: составной и derived/recolor ниже 0.70. Здесь два фронта, пороги действующих
детекторов V2/V3 не меняются, STRONG глобально не ослабляется; V3 и его выходы только читаются:

  1. PLACEMENT_STRUCTURE_V3 (вместо доводов PLACE V3 на тех же парах):
     - доля встречи считается по слою места, а не по всем местам кадра (у NUKE_CITY:3 в слое 2 сосед 8 из 8, в слое
       3 его нет - V3 делил 8 на 12);
     - взаимная доля, общий след и уровни - как V3 (P3 / P3x / P3c), только знаменатель по слою (P3L*);
     - одностороннее постоянное примыкание (доля a >= CO_CAND при CO_PLACES местах, обратно < CO_CAND) -
       ATTACHMENT_CANDIDATE: улика и ревью, никогда не составной (A1 - кадр примыкает, A1r - к кадру примыкают);
     - взаимность по связкам (P5r): связка - места кадра в одном блоке, этаже и слое, соседние по x/y (8 соседей);
       для пар с долей встречи по клеткам >= RUN_PAIR с обеих сторон доля связок с партнёром >= CO_CAND с обеих
       сторон, связок не меньше RUN_MIN у каждого. STRONG - только при двух уликах вне карты из трёх (как P3x),
       иначе CANDIDATE. Признак придуман на двух честных взаимных парах (U_BITSGOLD:0 / U_EXT02GOLD:6 и
       NUKE_CITY:3 / :4): на 60 он не независим, оценку даст новый holdout.
  2. RECOLOR_DERIVED_DISCOVERY_V4 - отдельный детектор R4, все доводы симметричны и TYPE_OPEN (подтип на ревью):
     - R4b почти тот же силуэт: IoU в [R4_NEAR, GEO) прямо или в отражении, функция цвета >= FUNC, цветов основы
       >= MIN_COLORS, границ >= BORDER_KEEP;
     - R4d материал и местная правка: силуэт >= GEO, функция в [R4D_FUNC, FUNC), границ >= R4D_BORDER, цветов >=
       MIN_COLORS, силуэт не общий (кадров с IoU >= GEO не больше R4D_GENERIC);
     - R4c соответствие наборов: тот же номер кадра в другом наборе, у наборов >= R4C_COMMON общих номеров,
       доля с силуэтом >= GEO не меньше R4C_GEO, у пары силуэт >= R4C_PAIR и границ >= BORDER_KEEP;
     - R4 поднимается до существования STRONG (не типа) только когда пара наборов - строгая перекраска: доля общих
       номеров с силуэтом >= GEO и функцией >= FUNC не меньше R4_SET_STRICT.
     Отрицательный контроль - тот же тест с цветами B, перемешанными внутри силуэта.
  3. Политика MIRRORED_RECOLOR: срабатывание V3 (MR1) - RELATED_STRONG, подтип MIRRORED_RECOLOR_CANDIDATE (TYPE_OPEN):
     кадр не рисуется сам, вывод не запускается. Вариант «typed» - TYPE_STRONG, как разрешает слепая проверка
     (probes/mirror-recolor-blind-v1); считается рядом, решает специалист. NEAR_RECOLOR - диагностика, как V3.
     Анимация и перекраска сосуществуют (RELATION_TAXONOMY).

Метрики - по истине v2 (relation_truth_v2.truth_v2): OPEN вне знаменателей; довод верен, если его группа закрыта,
неверен, если её нет ни среди закрытых, ни среди открытых. VERIFIED ставит только человек.

    py -3.13 tools/hdart/relation_discovery_v4.py discover   доводы V4 для 60 кадров holdout V8 -> relations_v4.json
    py -3.13 tools/hdart/relation_discovery_v4.py controls   те же детекторы на парах контроля -> controls_v4.json
    py -3.13 tools/hdart/relation_discovery_v4.py report     условия, точность правил, сравнение с V3 -> report.md
"""
import argparse
import os
import sys
import time
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir                     # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_taxonomy as tx                    # noqa: E402

ENC = ir.ENC
OUT = os.path.join(ir.PROBES, "relation-discovery-v4-prep")
p, split, key, rate, edge = v2.p, v2.split, v2.key, v2.rate, v2.edge
STRONG, CAND, T_STRONG, T_OPEN = v3.STRONG, v3.CAND, v3.T_STRONG, v3.T_OPEN
BINDING = v2.BINDING
GEO, FUNC, MIN_COLORS, BORDER_KEEP = v2.GEO, v2.FUNC, v2.MIN_COLORS, v2.BORDER_KEEP
CO_STRONG, CO_CAND, CO_PLACES, CO_BLOCKS = v2.CO_STRONG, v2.CO_CAND, v2.CO_PLACES, v2.CO_BLOCKS
PS_MANY, JOINT = v3.PS_MANY, v3.JOINT

# пороги новых признаков - заданы до пересчёта на 60 и контроле
RUN_PAIR = 0.50                  # P5r: доля встречи по клеткам с обеих сторон, с которой смотрим связки
RUN_MIN = 2                      # P5r: связок у каждого куска не меньше
R4_NEAR = 0.92                   # R4b: нижняя граница почти того же силуэта
R4D_FUNC, R4D_BORDER, R4D_GENERIC = 0.80, 0.80, 30
R4C_COMMON, R4C_GEO, R4C_PAIR = 8, 0.80, 0.90
R4_SET_STRICT = 0.50
THRESHOLDS = dict(v3.THRESHOLDS, RUN_PAIR=RUN_PAIR, RUN_MIN=RUN_MIN, R4_NEAR=R4_NEAR, R4D_FUNC=R4D_FUNC,
                  R4D_BORDER=R4D_BORDER, R4D_GENERIC=R4D_GENERIC, R4C_COMMON=R4C_COMMON, R4C_GEO=R4C_GEO,
                  R4C_PAIR=R4C_PAIR, R4_SET_STRICT=R4_SET_STRICT)

R4_TYPES = ("NEAR_SILHOUETTE_RECOLOR", "LOCAL_EDIT_VARIANT", "SET_CORRESPONDENCE")
GROUP = dict(v3.GROUP, ATTACHMENT_CANDIDATE="attachment", **{t: "derived" for t in R4_TYPES})
SYMMETRIC = v3.SYMMETRIC + R4_TYPES
DIAGNOSTIC = v3.DIAGNOSTIC                                 # NEAR_RECOLOR (детектор MIRROR) - как V3
DETECTOR_ORDER = dict(v3.DETECTOR_ORDER, PLACE4=4, MR4=5, R4=6)
PIPE_ROLE = dict(v2.PIPE_ROLE, MIRRORED_RECOLOR="RECOLOR_PEER")     # пара - не целое (pipeline_of)
GATES = {"dangerous": 0, "existence_precision": 0.95, "derived_discovery": 0.70, "state_discovery": 0.70,
         "composite_discovery": 0.70, "auto_action_precision": 0.95}


# ---------------------------------------------------------------- политика доводов

class _Base4(v3.Claims):
    """v3.Claims со своими группами и порядком детекторов; R4 и ATTACHMENT - всегда TYPE_OPEN; MR4 - TYPE_OPEN,
    если политика не typed."""
    MR_TYPED = False

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

    def finalize(self):
        for c in self.claims.values():
            sup = sorted(c["support"], key=lambda e: (e["level"] not in BINDING, e["detector"] in DIAGNOSTIC,
                                                      DETECTOR_ORDER[e["detector"]], e["type"]))
            c["support"] = sup
            prim = sup[0]
            c["type"], c["source"], c["target"] = prim["type"], prim["source"], prim["target"]
            c["existence"] = STRONG if any(e["level"] in BINDING and e["detector"] not in DIAGNOSTIC
                                           for e in sup) else CAND
            c["exact"] = any(e["type"] in v3.EXACT_TYPES for e in sup)
        pairs = defaultdict(list)
        for c in self.claims.values():
            pairs[frozenset(c["pair"])].append(c)
        for cs in pairs.values():
            spoken = sorted({c["group"] for c in cs if c["group"] in v3.DERIVATION and not c["exact"]})
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
                bind = [e for e in c["support"] if e["level"] in BINDING]
                if c["group"] == "attachment":
                    why.append("примыкание - улика")
                if bind and all(e["detector"] == "R4" for e in bind):
                    why.append("R4: подтип на ревью")
                if bind and all(e["detector"] == "MR4" for e in bind) and not self.MR_TYPED:
                    why.append("MIRRORED_RECOLOR_CANDIDATE")
                c["type_level"] = T_OPEN if why else T_STRONG
                c["type_open_why"] = why
        return self


class V4Claims(tx.TaxClaims, _Base4):
    """Порядок: TaxClaims (анимация и перекраска сосуществуют) поверх _Base4."""


class V4ClaimsTyped(V4Claims):
    MR_TYPED = True


def pipe_roles(C, a):
    A = a.upper()
    roles = {x["type"] for x in C.self_roles.get(A, []) if x["level"] in BINDING}
    roles |= {PIPE_ROLE.get(c["type"], c["type"]) for c in C.of(a)
              if tx.auto_claim(c) and (c["type"] in SYMMETRIC or c["source"] == A)}
    return sorted(roles) or ["CANONICAL"]


def bound(C, a):
    A = a.upper()
    if any(x["level"] in BINDING for x in C.self_roles.get(A, [])):
        return True
    return any(c["existence"] == STRONG and (c["type_level"] == T_OPEN or c["type"] in SYMMETRIC or c["source"] == A)
               for c in C.of(a))


def convert_v3(e):
    """Довод V3 в V4: PLACE (составной V3) снимается - его заменяет PLACE4; MR1 - RELATED_STRONG (детектор MR4)."""
    if e["detector"] == "PLACE" and e["type"] == "COMPOSITE_PART":
        return None
    if e["detector"] == "MIRROR" and e["type"] == "MIRRORED_RECOLOR":
        return dict(e, level="STRONG", detector="MR4", rule="MR1s")
    return e


# ---------------------------------------------------------------- 1. PLACEMENT_STRUCTURE_V3

def sig4(ctx, a):
    """Места кадра вне пола: [(террейн, блок, (x, y, z), слой, {(сдвиг, слой a, слой b, b)})]."""
    A = a.upper()
    out = []
    for t, blk, grid, (x, y, z), la in ctx.places.of(a):
        if la == 0:
            continue
        s = set()
        for o in v2.OFFSETS:
            for lb, kb in grid.get((x + o[0], y + o[1], z + o[2]), []):
                if lb == 0 or kb == A or (o == (0, 0, 0) and lb == la):
                    continue
                s.add((o, la, lb, kb))
        out.append((t, blk, (x, y, z), la, s))
    return out


class PlaceCache:
    def __init__(self, ctx):
        self.ctx = ctx
        self.pl = {}

    def layer(self, k, layer):
        kk = (k.upper(), layer)
        if kk not in self.pl:
            self.pl[kk] = [(t, b, g, xyz) for t, b, g, xyz, la in self.ctx.places.of(k) if la == layer]
        return self.pl[kk]

    def reverse(self, a, b, o, la, lb):
        """Доля мест b (слой lb) с a на обратном сдвиге (слой la) и число мест b."""
        pb = self.layer(b, lb)
        if not pb:
            return 0.0, 0
        A = a.upper()
        hit = sum(any(l2 == la and k2 == A for l2, k2 in g.get((x - o[0], y - o[1], z - o[2]), []))
                  for _t, _b, g, (x, y, z) in pb)
        return hit / len(pb), len(pb)


def runs(places):
    """Связки: компоненты мест в одном (террейн, блок, этаж), соседние по x/y (8 соседей). places: [(t, b, g, xyz)]."""
    parent = list(range(len(places)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    groups = defaultdict(dict)
    for i, (t, b, _g, (x, y, z)) in enumerate(places):
        groups[(t, b, z)][(x, y)] = i
    for pos in groups.values():
        for (x, y), i in pos.items():
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    j = pos.get((x + dx, y + dy))
                    if j is not None and j != i:
                        ri, rj = find(i), find(j)
                        if ri != rj:
                            parent[ri] = rj
    comp = defaultdict(list)
    for i in range(len(places)):
        comp[find(i)].append(i)
    return list(comp.values())


def run_share(pc, a, b, o, la, lb):
    """Доля связок a (слой la), где хоть в одном месте b стоит на сдвиге o в слое lb; число связок."""
    pa = pc.layer(a, la)
    rs = runs(pa)
    if not rs:
        return 0.0, 0
    B = b.upper()
    hit = 0
    for r in rs:
        for i in r:
            _t, _b, g, (x, y, z) = pa[i]
            if any(l2 == lb and k2 == B for l2, k2 in g.get((x + o[0], y + o[1], z + o[2]), [])):
                hit += 1
                break
    return hit / len(rs), len(rs)


def neg(o):
    return tuple(-v for v in o)


def placement_v3(ctx, a, only=None, pc=None):
    """Доводы расстановки кадра a: COMPOSITE_PART (P3L / P3Lx / P3Lc / P5r / P5rc) и ATTACHMENT_CANDIDATE (A1, A1r).
    only - одна пара (контроль): примыкание к кадру (A1r) тогда не ищется - его найдёт вызов с другой стороны."""
    pc = pc or PlaceCache(ctx)
    S = sig4(ctx, a)
    if len(S) < 2:
        return []
    A = a.upper()
    n_la = Counter(x[3] for x in S)
    cnt = Counter(e for x in S for e in x[4])
    rec = {}
    for e, k in cnt.items():
        o, la, lb, kb = e
        if (only is not None and kb != only.upper()) or k < 2:
            continue
        fwd = k / n_la[la]
        s_ba, nb = pc.reverse(A, kb, o, la, lb)
        if only is None and fwd < RUN_PAIR and (s_ba < CO_CAND or nb < CO_PLACES):
            continue                                  # ни взаимности, ни примыкания к кадру
        rec[e] = (k, n_la[la], fwd, s_ba, nb)
    mutual = {e for e, (k, n, fwd, s_ba, nb) in rec.items() if fwd >= CO_CAND and s_ba >= CO_CAND and min(n, nb) >= 2}
    joint, blocks = {}, {}
    for la in {e[1] for e in mutual}:
        mu = [e for e in mutual if e[1] == la]
        with_all = [blk for _t, blk, _xyz, l, s in S if l == la and all(e in s for e in mu)]
        joint[la], blocks[la] = len(with_all) / n_la[la], len(set(with_all))
    best = {}
    for e, r in rec.items():
        kb = e[3]
        sc = (e in mutual, min(r[2], r[3]), r[0])
        if kb not in best or sc > best[kb][0]:
            best[kb] = (sc, e, r)
    out = []
    for kb in sorted(best):
        _sc, e, (k, n, fwd, s_ba, nb) = best[kb]
        o, la, lb, _ = e
        base = "сдвиг %s, слои %d/%d: a %d из %d мест слоя (%.2f), b %.2f из %d" % (list(o), la, lb, k, n, fwd, s_ba, nb)
        if e in mutual:
            ev, c = v3.off_map(ctx, A, kb, o)
            n_ev, share, places = sum(ev.values()), min(fwd, s_ba), min(n, nb)
            jt, bl = joint[la], blocks[la]
            if share >= CO_STRONG and jt >= CO_STRONG and places >= PS_MANY and bl >= CO_BLOCKS:
                level, rule = "STRONG", "P3L"
            elif jt >= JOINT and n_ev >= 2:
                level, rule = "STRONG", "P3Lx"
            else:
                level, rule = "CANDIDATE", "P3Lc"
            e2 = edge("COMPOSITE_PART", A, kb, level, "PLACE4", rule, "%s; след %.2f, блоков %d; вне карты %s" % (
                base, jt, bl, ev_text(ev, c)))
            e2["scores"] = {"share": round(share, 3), "joint": round(jt, 3), "places": places, "blocks": bl,
                            "off_map": ev}
            out.append(e2)
            continue
        if fwd >= RUN_PAIR and s_ba >= RUN_PAIR:
            ra, na_r = run_share(pc, A, kb, o, la, lb)
            rb, nb_r = run_share(pc, kb, A, neg(o), lb, la)
            if min(ra, rb) >= CO_CAND and min(na_r, nb_r) >= RUN_MIN:
                ev, c = v3.off_map(ctx, A, kb, o)
                n_ev = sum(ev.values())
                level, rule = ("STRONG", "P5r") if n_ev >= 2 else ("CANDIDATE", "P5rc")
                e2 = edge("COMPOSITE_PART", A, kb, level, "PLACE4", rule,
                          "%s; связки: a %.2f из %d, b %.2f из %d; вне карты %s" % (
                              base, ra, na_r, rb, nb_r, ev_text(ev, c)))
                e2["scores"] = {"cell": [round(fwd, 3), round(s_ba, 3)], "runs": [round(ra, 3), na_r, round(rb, 3), nb_r],
                                "off_map": ev}
                out.append(e2)
                continue
        if fwd >= CO_CAND and n >= CO_PLACES and s_ba < CO_CAND:
            e2 = edge("ATTACHMENT_CANDIDATE", A, kb, "CANDIDATE", "PLACE4", "A1", "кадр примыкает: " + base)
        elif only is None and s_ba >= CO_CAND and nb >= CO_PLACES and fwd < CO_CAND:
            e2 = edge("ATTACHMENT_CANDIDATE", kb, A, "CANDIDATE", "PLACE4", "A1r", "к кадру примыкает: " + base)
        else:
            continue
        e2["scores"] = {"fwd": round(fwd, 3), "rev": round(s_ba, 3), "places": [n, nb]}
        out.append(e2)
    return out


def ev_text(ev, c):
    return "порядок %s, MCD %s, геометрия %s" % ("да" if ev["order"] else "нет", "да" if ev["mcd"] else "нет",
                                                 "нет грани" if c is None else "%.2f" % c)


# ---------------------------------------------------------------- 2. RECOLOR_DERIVED_DISCOVERY_V4

class SetIndex:
    """Номера кадров каждого набора в матрице масок; IoU двух кадров по маскам; статистика пары наборов."""

    def __init__(self, ctx):
        self.ctx, self.m = ctx, ctx.masks
        self.sets = defaultdict(dict)
        for i, k in enumerate(self.m.keys):
            s, f = split(k)
            self.sets[s][f] = i
        self.stats = {}
        self.gen = {}

    def iou_idx(self, i, j):
        inter = float(self.m.M[i] @ self.m.M[j])
        return inter / max(self.m.area[i] + self.m.area[j] - inter, 1.0)

    def generic(self, k):
        if k not in self.gen:
            i = self.m.pos.get(k.upper())
            self.gen[k] = int((self.m.iou(self.m.M[i].reshape(self.m.shape)) >= GEO).sum()) if i is not None else 0
        return self.gen[k]

    def pair_stats(self, s, t):
        kk = tuple(sorted((s, t)))
        if kk in self.stats:
            return self.stats[kk]
        fs, ft = self.sets.get(s, {}), self.sets.get(t, {})
        common = sorted(set(fs) & set(ft))
        geo = [n for n in common if self.iou_idx(fs[n], ft[n]) >= GEO]
        strict = 0
        if common and len(geo) / len(common) >= R4_SET_STRICT:
            for n in geo:
                A, B = self.ctx.rgba(key(s, n)), self.ctx.rgba(key(t, n))
                if A is None or B is None:
                    continue
                f_ab, f_ba, _iou, _na, _nb, _b = v2.funcs(A, B)
                if max(f_ab, f_ba) >= FUNC:
                    strict += 1
        r = {"common": len(common), "geo": rate(len(geo), len(common)), "strict": rate(strict, len(common))}
        self.stats[kk] = r
        return r


def r4_scores(A, B, flip):
    BB = np.ascontiguousarray(B[:, ::-1]) if flip else B
    f_ab, f_ba, iou, na, nb, biou = v2.funcs(A, BB)
    fmax = max(f_ab, f_ba)
    nbase = max(na, nb) if min(f_ab, f_ba) >= FUNC else (na if f_ab >= f_ba else nb)
    return {"silhouette": round(iou, 4), "topology": round(biou, 3), "f_ab": round(f_ab, 3), "f_ba": round(f_ba, 3),
            "fmax": fmax, "base_colors": nbase, "flip": flip}


def r4_pair(ctx, si, a, b, B=None, set_level=True):
    """Доводы R4 на паре (a, b): R4b / R4d по лучшему из прямого и отражённого силуэта, R4c по наборам. B - подмена
    кадра b (перемешанный контроль)."""
    a, b = a.upper(), b.upper()
    if a == b or b in ctx.ix.exact(a) or b in ctx.ix.mirror(a):
        return []
    A = ctx.rgba(a)
    B0 = ctx.rgba(b)
    if A is None or B0 is None or A.shape != B0.shape:
        return []
    B = B0 if B is None else B
    ma, mb = A[..., 3] > 0, B0[..., 3] > 0
    u = (ma | mb).sum()
    d = float((ma & mb).sum() / u) if u else 0.0
    mf = mb[:, ::-1]
    uf = (ma | mf).sum()
    f = float((ma & mf).sum() / uf) if uf else 0.0
    (sa, fa), (sb, fb) = split(a), split(b)
    st = si.pair_stats(sa, sb) if sa != sb else None
    strict = bool(st and st["common"] >= R4C_COMMON and (st["strict"] or 0) >= R4_SET_STRICT)
    level = "STRONG" if strict else "CANDIDATE"
    sset = "" if st is None else "; наборы: общих %d, силуэт %.2f, строгая перекраска %.2f" % (
        st["common"], st["geo"] or 0, st["strict"] or 0)
    out = []
    flip = f > d
    iou_m = f if flip else d
    if iou_m >= R4_NEAR:
        sc = r4_scores(A, B, flip)
        okb = R4_NEAR <= sc["silhouette"] < GEO and sc["fmax"] >= FUNC and sc["base_colors"] >= MIN_COLORS and \
            sc["topology"] >= BORDER_KEEP
        okd = sc["silhouette"] >= GEO and R4D_FUNC <= sc["fmax"] < FUNC and sc["base_colors"] >= MIN_COLORS and \
            sc["topology"] >= R4D_BORDER and si.generic(a) <= R4D_GENERIC
        for ok, typ, rule in ((okb, "NEAR_SILHOUETTE_RECOLOR", "R4b"), (okd, "LOCAL_EDIT_VARIANT", "R4d")):
            if ok:
                e = edge(typ, a, b, level, "R4", rule + ("s" if strict else ""),
                         "%s: силуэт %.3f, границ %.2f, функция %.3f/%.3f, цветов основы %d%s" % (
                             "отражение" if flip else "прямо", sc["silhouette"], sc["topology"], sc["f_ab"], sc["f_ba"],
                             sc["base_colors"], sset))
                e["scores"] = dict(sc, fmax=round(sc["fmax"], 3), set=st)
                out.append(e)
    if set_level and st and fa == fb and d >= R4C_PAIR and st["common"] >= R4C_COMMON and (st["geo"] or 0) >= R4C_GEO:
        sc = r4_scores(A, B, False)
        if sc["topology"] >= BORDER_KEEP:
            e = edge("SET_CORRESPONDENCE", a, b, level, "R4", "R4c" + ("s" if strict else ""),
                     "тот же номер, силуэт %.3f, границ %.2f, функция %.3f/%.3f%s" % (
                         sc["silhouette"], sc["topology"], sc["f_ab"], sc["f_ba"], sset))
            e["scores"] = dict(sc, fmax=round(sc["fmax"], 3), set=st)
            out.append(e)
    return out


def r4_discover(ctx, si, a):
    """Кандидаты по всему индексу: прямой или отражённый силуэт >= min(R4_NEAR, R4C_PAIR)."""
    A = ctx.rgba(a)
    if A is None:
        return []
    m = A[..., 3] > 0
    if m.shape != ctx.masks.shape:
        return []
    lo = min(R4_NEAR, R4C_PAIR)
    direct, mirr = ctx.masks.iou(m), ctx.masks.iou(m[:, ::-1])
    out = []
    for i in np.nonzero((direct >= lo) | (mirr >= R4_NEAR))[0]:
        out += r4_pair(ctx, si, a, ctx.masks.keys[i])
    return out


# ---------------------------------------------------------------- discover / controls

def discover(ctx, keys):
    pc, si = PlaceCache(ctx), SetIndex(ctx)
    edges = []
    for a in keys:
        t0 = time.time()
        es = placement_v3(ctx, a, pc=pc) + r4_discover(ctx, si, a)
        edges += es
        print(a, dict(Counter("%s %s" % (e["rule"], e["level"]) for e in es)), "%.1f с" % (time.time() - t0), flush=True)
    return {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "thresholds": THRESHOLDS, "keys": list(keys),
            "edges": edges, "note": "утверждения детекторов V4, не маршрут; VERIFIED ставит только человек"}


def controls(ctx):
    pc, si = PlaceCache(ctx), SetIndex(ctx)
    v3c = ir.load_json(p(v3.OUT, "controls.json"))
    rows = []
    for i, r in enumerate(v3c["pairs"]):
        a, b = r["asset_id"], r["relative"]
        es = placement_v3(ctx, a, only=b, pc=pc) + placement_v3(ctx, b, only=a, pc=pc) + r4_pair(ctx, si, a, b)
        perm = []
        for e in es:
            if e["detector"] == "R4":
                pe = r4_pair(ctx, si, a, b, B=v3.permuted(ctx, b, 7))
                perm.append([e["rule"], any(x["rule"] == e["rule"] for x in pe)])
        rows.append({"holdout": r["holdout"], "asset_id": a.upper(), "relative": b.upper(), "edges": es, "perm": perm})
        if i % 100 == 0:
            print("контроль: %d из %d" % (i, len(v3c["pairs"])), flush=True)
    return {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "thresholds": THRESHOLDS, "pairs": rows}


# ---------------------------------------------------------------- отчёт

def claims_60(rep, found3, found4, cls):
    C = v3.claims_from_v8(rep["rows"])
    C.__class__ = cls
    for e in found3["edges"]:
        e2 = convert_v3(e)
        if e2:
            C.add(e2)
    for a, roles in found3["self_roles"].items():
        C.self_roles[a.upper()] += roles
    for e in found4["edges"]:
        C.add(e)
    return C.finalize()


def claims_controls(ctl3, ctl4, cls):
    """пара -> Claims: доводы V3 (без PLACE, MR1 как MR4) и доводы V4 на паре."""
    new = {tx.pk(r["asset_id"], r["relative"]): r for r in ctl4["pairs"]} if ctl4 else {}
    out = {}
    for r in ctl3["pairs"]:
        k = tx.pk(r["asset_id"], r["relative"])
        C = cls()
        for c in r["claims"]:
            for e in c["support"]:
                e2 = convert_v3(edge(e["type"], c["source"], c["target"], e["level"], e["detector"], e["rule"],
                                     e["evidence"]))
                if e2:
                    C.add(e2)
        for e in new.get(k, {}).get("edges", []):
            C.add(e)
        out[k] = C.finalize()
    return out


def claim_state(c, t):
    import relation_truth_v2 as tv
    return tv.claim_state(c, t)


def metrics(pc):
    """pc: [(истина v2 или None, [довод])]. Существование, тип (факт), автоматическое действие."""
    ex = [(t, cs) for t, cs in pc if t and t[0] != "OPEN" and any(c["existence"] == STRONG for c in cs)]
    ty = [(t, c) for t, cs in pc if t for c in cs if c["existence"] == STRONG and c["type_level"] == T_STRONG]
    au = [(t, c) for t, cs in pc if t for c in cs if tx.auto_claim(c)]

    def prec(xs):
        st = Counter(claim_state(c, t) for t, c in xs)
        return rate(st["ok"], st["ok"] + st["wrong"]), st["ok"] + st["wrong"], st["open"]

    def by(xs):
        g = defaultdict(Counter)
        for t, c in xs:
            g[c["group"]][claim_state(c, t)] += 1
        return {k: dict(v) for k, v in sorted(g.items())}
    tp, tn, to = prec(ty)
    ap, an, ao = prec(au)
    return {"existence_precision": rate(sum(t[0] == "RELATED" for t, _ in ex), len(ex)), "existence_judged": len(ex),
            "existence_wrong": sum(t[0] == "NONE" for t, _ in ex),
            "typed_fact_precision": tp, "typed_fact_judged": tn, "typed_fact_open": to,
            "auto_action_precision": ap, "auto_action_judged": an, "auto_action_open": ao, "auto_by_group": by(au)}


def recall(pc):
    """Полнота по закрытым ярлыкам истины v2: обнаружение (любой довод нужной группы), STRONG, авто."""
    out = {}
    for name, labs, g in (("derived", set(tx.DERIVED_LABELS), "derived"), ("state", {"STATE_VARIANT"}, "state"),
                          ("animation", {"ANIMATION_FAMILY"}, "animation"), ("composite", {"COMPOSITE"}, "composite"),
                          ("attachment", {"ATTACHMENT_CANDIDATE"}, "attachment"),
                          ("counterpart", {"STRUCTURAL_COUNTERPART"}, None)):
        pos = [cs for t, cs in pc if t and t[0] == "RELATED" and t[1] & labs and
               not (name == "derived" and "EXACT_COPY" in t[1])]
        x = {"n": len(pos), "existence": sum(any(c["existence"] == STRONG for c in cs) for cs in pos)}
        if g:
            x.update({"discovery": sum(any(c["group"] == g for c in cs) for cs in pos),
                      "strong": sum(any(c["group"] == g and c["existence"] == STRONG for c in cs) for cs in pos),
                      "auto": sum(any(c["group"] == g and tx.auto_claim(c) for c in cs) for cs in pos)})
            x["discovery_rate"] = rate(x["discovery"], x["n"])
        out[name] = x
    return out


def rule_table(pcs):
    """Точность каждого правила V4 и MR: по существованию (пара RELATED / NONE) и по группе довода."""
    tab = defaultdict(Counter)
    for t, cs in pcs:
        if not t:
            continue
        for c in cs:
            for e in c["support"]:
                if e["detector"] not in ("PLACE4", "R4", "MR4"):
                    continue
                r = tab["%s %s" % (e["rule"], e["level"])]
                r["n"] += 1
                r["ex_" + {"RELATED": "ok", "NONE": "wrong", "OPEN": "open"}[t[0]]] += 1
                r["type_" + claim_state(c, t)] += 1
    return {k: dict(v) for k, v in sorted(tab.items())}


def score_rows(rows, C, pairs, fsets, v8):
    out = []
    for r in rows:
        a = r["asset_id"]
        pipe, _why = v8.pipeline_of(r["semantic_eff"], r["surface"], pipe_roles(C, a))
        creative = pipe == "OBJECT_PIPELINE" and not bound(C, a) and not v3.has_evidence(C, a)
        out.append({"asset_id": a, "pipeline": pipe, "creative": creative,
                    "danger": v2.danger_v2(r, creative, C, pairs.get(a, []), fsets[a.upper()])})
    return out


def gates(blk):
    d = blk["dangerous"]
    e = [blk["m60"]["existence_precision"], blk["mctl"]["existence_precision"]]
    au = [blk["m60"]["auto_action_precision"], blk["mctl"]["auto_action_precision"]]
    r = blk["r60"]
    vals = [("dangerous", d, d == GATES["dangerous"]),
            ("existence_precision", min(x for x in e if x is not None), None),
            ("derived_discovery", r["derived"].get("discovery_rate"), None),
            ("state_discovery", r["state"].get("discovery_rate"), None),
            ("composite_discovery", r["composite"].get("discovery_rate"), None),
            ("auto_action_precision", min(x for x in au if x is not None), None)]
    out = []
    for n, v, ok in vals:
        if ok is None:
            ok = v is not None and v >= GATES[n]
        out.append({"gate": n, "value": v, "need": GATES[n], "pass": bool(ok)})
    return out


def do_report(out=OUT):
    import map_mockup as mm
    import routing_model_v8 as v8
    import relation_truth_v2 as tv
    rep, pairs, h, sha, found3, ctl3, keys = tx.v3_inputs()
    found4 = ir.load_json(p(out, "relations_v4.json"))
    ctl4 = ir.load_json(p(out, "controls_v4.json"))
    T, _rows, _bad, _j2 = tv.truth_v2()
    rp = tx.ref_pairs_60(keys, pairs)
    mcd = v8.Mcd(mm.World())
    fsets = {a.upper(): v8.facts(mcd, a) for a in keys}
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "RELATION_DISCOVERY_V4_PREP",
           "thresholds": THRESHOLDS, "h8_sha256": sha, "relations_v4_created": found4["created"],
           "controls_v4_created": ctl4["created"], "truth": dict(Counter(v[0] for v in T.values())), "variants": {}}

    def t_of(k):
        v = T.get(k)
        return v[:3] if v else None

    variants = (("v3_tax", "V3 + TaxClaims (база)", None, None),
                ("v4_mr_open", "V4, MR - TYPE_OPEN (действующее решение)", V4Claims, False),
                ("v4_mr_typed", "V4, MR - TYPE_STRONG (разрешено слепой проверкой)", V4ClaimsTyped, True))
    for name, title, cls, _typed in variants:
        if cls is None:
            C = tx.claims_60(rep, found3, tx.TaxClaims)
            CC = {k: Cx for k, (_r, Cx) in tx.control_claims(ctl3, tx.TaxClaims).items()}
            roles, bnd = tx.pipe_roles, v3.bound
        else:
            C = claims_60(rep, found3, found4, cls)
            CC = claims_controls(ctl3, ctl4, cls)
            roles, bnd = pipe_roles, bound
        pc60 = [(t_of(tx.pk(a, b)), C.pair(a, b)) for a, b, _rel in rp]
        pcc = [(t_of(k), list(Cx.claims.values())) for k, Cx in CC.items()]
        axes = {}
        for axis, rows in (("logic", rep["rows_logic"]), ("end_to_end", rep["rows"])):
            s = []
            for r in rows:
                a = r["asset_id"]
                pipe, _w = v8.pipeline_of(r["semantic_eff"], r["surface"], roles(C, a))
                creative = pipe == "OBJECT_PIPELINE" and not bnd(C, a) and not v3.has_evidence(C, a)
                s.append({"asset_id": a, "creative": creative,
                          "danger": v2.danger_v2(r, creative, C, pairs.get(a, []), fsets[a.upper()])})
            axes[axis] = {"dangerous": {x["asset_id"]: x["danger"] for x in s if x["danger"]},
                          "creative": [x["asset_id"] for x in s if x["creative"]]}
        blk = {"title": title, "axes": axes, "dangerous": max(len(x["dangerous"]) for x in axes.values()),
               "m60": metrics(pc60), "mctl": metrics(pcc), "r60": recall(pc60), "rctl": recall(pcc),
               "rules": rule_table(pc60 + pcc)}
        blk["gates"] = gates(blk)
        blk["wrong"] = wrong_list(rp, C, CC, t_of)
        blk["missed"] = missed_list(rp, C, t_of)
        res["variants"][name] = blk
    perm = Counter()
    for r in ctl4["pairs"]:
        for rule, fired in r["perm"]:
            perm["%s %s" % (rule, "сработал" if fired else "молчит")] += 1
    res["permuted_controls"] = dict(perm)
    res["composite_edges_60"] = ["%s %s %s %s: %s" % (e["source"], e["target"], e["level"], e["rule"], e["evidence"])
                                 for e in found4["edges"] if e["detector"] == "PLACE4"]
    res["r4_edges_60"] = Counter("%s %s" % (e["rule"], e["level"]) for e in found4["edges"] if e["detector"] == "R4")
    mb = p(tv.MOUT, "report.json")
    res["mirror_blind"] = ir.load_json(mb) if os.path.exists(mb) else None
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    print("отчёт: %s" % p(out, "report.md"))


def wrong_list(rp, C, CC, t_of):
    """Неверные доводы: STRONG на паре NONE и TYPE_STRONG с группой вне истины."""
    out = []
    items = [(a, b, C.pair(a, b)) for a, b, _r in rp] + [(sorted(k)[0], sorted(k)[1], list(Cx.claims.values()))
                                                        for k, Cx in CC.items()]
    for a, b, cs in items:
        t = t_of(tx.pk(a, b))
        if not t:
            continue
        for c in cs:
            st = claim_state(c, t)
            if c["existence"] == STRONG and (t[0] == "NONE" or (c["type_level"] == T_STRONG and st == "wrong")):
                out.append("%s %s: %s %s/%s (%s), истина %s %s" % (
                    a, b, c["type"], c["existence"][8:], c["type_level"][5:],
                    "+".join(sorted({"%s:%s" % (e["detector"], e["rule"]) for e in c["support"]})), t[0],
                    "/".join(sorted(t[1])) or "-"))
    return out


def missed_list(rp, C, t_of):
    out = []
    for a, b, _r in rp:
        t = t_of(tx.pk(a, b))
        if not t or t[0] != "RELATED":
            continue
        for lab, g in (("COMPOSITE", "composite"), ("STATE_VARIANT", "state")) + tuple((l, "derived") for l in tx.DERIVED_LABELS):
            if lab in t[1] and not any(c["group"] == g for c in C.pair(a, b)):
                out.append("%s %s: %s, доводы %s" % (a, b, lab, ", ".join("%s %s" % (c["group"], c["existence"][8:])
                                                                          for c in C.pair(a, b)) or "-"))
    return sorted(set(out))


def f3(x):
    return "-" if x is None else ("%.3f" % x if isinstance(x, float) else str(x))


def write_md(out, res):
    L = ["# RELATION_DISCOVERY_V4_PREP — структура расстановки V3 и фронт перекраски V4", "",
         "Диагностический пересчёт на тех же 60 и контроле по истине v2 (второй судья). Пороги V2/V3 не менялись; новые "
         "пороги: %s." % ", ".join("%s %s" % (k, res["thresholds"][k]) for k in (
             "RUN_PAIR", "RUN_MIN", "R4_NEAR", "R4D_FUNC", "R4D_BORDER", "R4D_GENERIC", "R4C_COMMON", "R4C_GEO",
             "R4C_PAIR", "R4_SET_STRICT")),
         "Истина v2 по парам: %s. OPEN вне знаменателей." % res["truth"], ""]
    V = res["variants"]
    L += ["## Условия заморозки", "", "| условие | нужно | %s |" % " | ".join(v["title"] for v in V.values()),
          "|---|---|" + "---|" * len(V)]
    names = [g["gate"] for g in next(iter(V.values()))["gates"]]
    for i, n in enumerate(names):
        L.append("| %s | %s | %s |" % (n, GATES[n], " | ".join("%s%s" % (f3(v["gates"][i]["value"]),
                                                                          "" if v["gates"][i]["pass"] else " **нет**")
                                                              for v in V.values())))
    L += ["", "## Существование, тип, автоматическое действие", "",
          "| вариант | набор | existence | typed fact | auto action | авто открыто |", "|---|---|---|---|---|---|"]
    for v in V.values():
        for s, m in (("60", v["m60"]), ("контроль", v["mctl"])):
            L.append("| %s | %s | %s (%d, неверных %d) | %s (%d) | %s (%d) | %d |" % (
                v["title"], s, f3(m["existence_precision"]), m["existence_judged"], m["existence_wrong"],
                f3(m["typed_fact_precision"]), m["typed_fact_judged"], f3(m["auto_action_precision"]),
                m["auto_action_judged"], m["auto_action_open"]))
    L += ["", "## Полнота по закрытым ярлыкам истины v2", "",
          "| вариант | набор | смысл | пар | существование | обнаружение | STRONG | авто |", "|---|---|---|---|---|---|---|---|"]
    for v in V.values():
        for s, r in (("60", v["r60"]), ("контроль", v["rctl"])):
            for name, x in r.items():
                if x["n"]:
                    L.append("| %s | %s | %s | %d | %d | %s | %s | %s |" % (
                        v["title"], s, name, x["n"], x["existence"], x.get("discovery", "-"), x.get("strong", "-"),
                        x.get("auto", "-")))
    L += ["", "## Безопасность", ""]
    for v in V.values():
        for ax, x in v["axes"].items():
            L.append("- %s, %s: опасных %d %s; одиночных творческих %d" % (
                v["title"], ax, len(x["dangerous"]), sorted(x["dangerous"]), len(x["creative"])))
    L += ["", "## Правила V4 и MR (60 и контроль вместе)", "",
          "| правило | доводов | пара RELATED | пара NONE | пара OPEN | группа верна | группа неверна | группа открыта |",
          "|---|---|---|---|---|---|---|---|"]
    for k, x in V["v4_mr_open"]["rules"].items():
        L.append("| %s | %d | %d | %d | %d | %d | %d | %d |" % (k, x.get("n", 0), x.get("ex_ok", 0), x.get("ex_wrong", 0),
                                                              x.get("ex_open", 0), x.get("type_ok", 0),
                                                              x.get("type_wrong", 0), x.get("type_open", 0)))
    L += ["", "Перемешанный контроль R4 (цвета B внутри силуэта): %s." % (res["permuted_controls"] or "срабатываний R4 на контроле нет"),
          "", "Доводы R4 на 60: %s." % (dict(res["r4_edges_60"]) or "нет"), "", "## Составной на 60 (PLACE4)", ""]
    L += ["- " + x for x in res["composite_edges_60"]] or ["- нет"]
    for name in ("v4_mr_open", "v4_mr_typed"):
        L += ["", "## Неверные доводы — %s" % V[name]["title"], ""]
        L += ["- " + x for x in V[name]["wrong"]] or ["- нет"]
    L += ["", "## Пропуски на 60 (закрытый ярлык, довода группы нет) — %s" % V["v4_mr_open"]["title"], ""]
    L += ["- " + x for x in V["v4_mr_open"]["missed"]] or ["- нет"]
    mb = res.get("mirror_blind")
    if mb:
        L += ["", "## Слепая проверка MIRRORED_RECOLOR (probes/mirror-recolor-blind-v1)", "",
              "Сводка из её report.json: %s." % {k: mb[k] for k in mb if k in ("existence_precision", "subtype_precision",
                                                                                  "type_strong_allowed", "fires", "negatives")}]
    with open(p(out, "report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["discover", "controls", "report"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.cmd == "discover":
        h = ir.load_json(p(v2.H8, "holdout.json"))
        ctx = v3.Ctx(index=v2.load_index(v2.OUT), masks=v3.load_masks(v3.OUT))
        ir.dump_json(p(a.out, "relations_v4.json"), discover(ctx, [x["asset_id"] for x in h["items"]]))
    elif a.cmd == "controls":
        ctx = v3.Ctx(index=v2.load_index(v2.OUT), masks=v3.load_masks(v3.OUT))
        ir.dump_json(p(a.out, "controls_v4.json"), controls(ctx))
    else:
        do_report(a.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
