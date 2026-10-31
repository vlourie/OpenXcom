#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ROUTING_RULES_V5_PREP - правила маршрута V5 и диагностический пересчёт на тех же 40 (специалист 01.10). CPU.

Holdout ROUTING_RULES_V4_R1 - FAIL, итог стоит и не пересчитывается (routing-holdout-v4r1/diag2.md). Специалист
разложил промахи на три дыры; V5 закрывает их, V4/V4_R1 и замороженные файлы holdout не трогаются:

1. MCD_STATE_RELATIONS (mcd_state.py): разрушенный вид, второе состояние и кадр анимации - из записей MCD.
   Состояние выводится из канонической основы, одиночным заказом не идёт (NUKE2:2 = die NUKE2:3).
2. FIXED_NEIGHBOUR - только улика: в точность родства не входит, родства, куска и производного не даёт; одиночный
   заказ при нём уходит в REVIEW (кроме поверхности - у стены соседи по определению).
3. Онтология: STRUCTURAL_SURFACE (стена, обшивка, пол, архитектурная панель) отдельно от OBJECT_PART (кусок
   вещи, машины, мебели, существа), TERRAIN_RELIEF и NOT_OBJECT (служебное и прочее вне конвейера предметов).
   Человек на карточках V4 давал четыре вида; поверхность V5 выводится из его ответа и физики MCD:
       улика поверхности STRONG     запись стены (Tile_Type 1/2), стена в клетке предмета (Big_Wall 2/3 или 4-9
                                    со Stop_LOS), дверь, запись пола с плоским покровом (obj_struct floor_like)
       улика поверхности CANDIDATE  Big_Wall 1 со Stop_LOS - блок на всю клетку, закрывает обзор
   OBJECT_PART / NOT_OBJECT + любая улика -> STRUCTURAL_SURFACE; OBJECT + улика -> REVIEW «вещь или поверхность?»
   (одиночный заказ требует, чтобы улик поверхности не было). Калибровка на очереди без этих 40 (лист в
   recount.md): запись стены - ~90% поверхностей по словам опознания, Big_Wall 1 + Stop_LOS - ~80%.

Правила V5 по порядку (первое сработавшее решает):
    R1   A = TERRAIN_RELIEF                                         EXCLUDE
    R2   A = NOT_OBJECT без улики поверхности                       EXCLUDE
    R0v  родство подтверждено человеком                             по родству
    R3m  кадр - состояние по MCD (die / alt), STRONG                STATE_VARIANT  (из основы)
    R3a  кадр анимации по MCD, STRONG                               ANIMATION_FAMILY (общий облик и опознание,
                                                                    не разрушенный вид; специалист 01.10)
    R3   state_variants.json / class_decisions state_variant        STATE_VARIANT
    R4   перекраска / зеркало семейства                             DERIVED
         с FAMILY_RELATION_V2 (fr2, family_relation_v2.py) перекраска - только прямым ребром:
    R4d    прямое строгое ребро, кадр - производная сторона         DERIVED
    R4     зеркало семейства (как было)                             DERIVED
    R4l    recolor семейства без прямого подтверждения              REVIEW (LEGACY_RELATION, не ложь)
    R5   составной заказ / part_fragment                            COMPOSITE_PART
    R6   modular_objects / structural_modular                       STRUCTURAL_MODULAR
    R7   открытый вопрос о родстве (у поверхности part_fragment_suspect - не вопрос: стена касается края)
                                                                    REVIEW
    R7r  кандидат перекраски не подтверждён                         REVIEW
    R7m  состояние по MCD, CANDIDATE (общий обломок, взаимный alt)  REVIEW
    S    STRUCTURAL_SURFACE                                         EXCLUDE (конвейер поверхностей)
    R7n  FIXED_NEIGHBOUR - улика                                    REVIEW
    R7s  A = OBJECT при улике поверхности                           REVIEW
    R8a  A = OBJECT_PART                                            REVIEW
    R8   A = OBJECT                                                 STANDALONE_RENDER (последний запасной)
    R9   иначе                                                      REVIEW

Пересчёт на 40 - диагностика, не PASS: правила написаны после того, как ответы и эталон этих 40 были видны.
Папка holdout только читается; хэши её файлов до и после пишутся в отчёт. Цели специалиста для заморозки V5:
опасных 0, точность родства >= 0.95, точность маршрута >= 0.90, охват >= 0.70.

    py -3.13 tools/hdart/routing_rules_v5.py recount     пересчёт на 40 -> routing-rules-v5-prep/recount.md / .json
    py -3.13 tools/hdart/routing_rules_v5.py recount-fr2 то же с FAMILY_RELATION_V2 -> recount_fr2.md / .json
"""
import argparse
import hashlib
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402
import mcd_state as ms                 # noqa: E402
import routing_holdout as rh           # noqa: E402
import routing_holdout_diag as rd      # noqa: E402
import routing_holdout_diag2 as d2     # noqa: E402
import routing_rules as rr             # noqa: E402

ROOT = ir.ROOT
OUT = ms.OUT
HOLDOUT = rh.OUT
SEMANTIC_V5 = ["OBJECT", "OBJECT_PART", "STRUCTURAL_SURFACE", "TERRAIN_RELIEF", "NOT_OBJECT", "UNSURE"]
TARGETS = {"dangerous_false_standalone_max": 0, "relation_precision_min": 0.95, "relation_precision_min_n": 5,
           "routing_accuracy_min": 0.90, "routing_coverage_min": 0.70}
CODE = ("tools/hdart/routing_rules_v5.py", "tools/hdart/mcd_state.py", "tools/hdart/obj_struct.py",
        "tools/hdart/routing_rules.py", "tools/hdart/routing_holdout.py")
# вид утверждения V5 -> группа и точный вид эталона (как rh.CLAIM_GROUP / CLAIM_EXACT, плюс MCD; без FIXED_NEIGHBOUR)
CLAIM_GROUP = {"RECOLOR_OF": "derived", "RECOLOR_WITH_LOCAL_EDIT": "derived", "STATE_VARIANT_OF": "derived",
               "ANIMATION_FRAME_OF": "derived"}
CLAIM_EXACT = {"RECOLOR_OF": ("RECOLOR_OF",), "RECOLOR_WITH_LOCAL_EDIT": ("DERIVED_FROM",),
               "STATE_VARIANT_OF": ("STATE_VARIANT_OF",), "ANIMATION_FRAME_OF": ()}   # анимация - не разрушенный вид
EVIDENCE_ONLY = ("FIXED_NEIGHBOUR",)
FR2_DIRECT = ("VERIFIED_DIRECT", "DIRECT_NEW")


# ---------------------------------------------------------------- улики

def surface_evidence(st, key):
    """(уровень, почему) по записи MCD кадра: STRONG | CANDIDATE | '' (нет улики)."""
    s, f = key.split(":")
    try:
        rec = st.record(s, int(f))
    except (Exception, SystemExit):         # noqa: BLE001 - набор не читается: улики нет
        rec = None
    if rec is None:
        return "", "записи MCD нет"
    tt, bw, los, door = rec[53], rec[33], rec[31], rec[35] or rec[30]
    if tt in (1, 2):
        return "STRONG", "запись стены (Tile_Type %d)" % tt
    if bw in (2, 3) or (4 <= bw <= 9 and los):
        return "STRONG", "стена в клетке предмета (Big_Wall %d%s)" % (bw, ", Stop_LOS" if los else "")
    if door:
        return "STRONG", "дверь"
    if tt == 0:
        import obj_struct as os_
        cl, why = os_.asset_class(st.info(s, int(f)))
        if cl == "floor_like":
            return "STRONG", why
    if bw == 1 and los:
        return "CANDIDATE", "блок на всю клетку, закрывает обзор (Big_Wall 1, Stop_LOS)"
    return "", ""


def semantic_v5(sk, surf):
    """Вид V5 из ответа человека (онтология V4) и улики поверхности; второе - заметка."""
    if surf and sk in ("OBJECT_PART", "NOT_OBJECT"):
        return "STRUCTURAL_SURFACE", "%s + улика поверхности" % sk
    return sk, ""


# ---------------------------------------------------------------- маршрут

def route_v5(a, sk, meta, mcd, surf, unit_map=None, use_mcd=True, use_surface=True, neighbour_review=True,
             fr2=None):
    """(маршрут, правило, улика, вид V5). meta - routing_rules.metadata с relations; mcd - mcd_state.index;
    surf - (уровень, почему) улики поверхности; fr2 - family_relation_v2.load() или None (прежний R4)."""
    unit_map = unit_map or rr.RELATION_UNIT_HOLDOUT
    gen, fam_rel, fam_review, state, modular, cls, rels = meta
    lvl, swhy = surf if use_surface else ("", "")
    kind, _note = semantic_v5(sk, lvl)
    g = gen.get(a, {})
    blockers = (g.get("blockers") or "").split()
    rel = g.get("relation", "")
    if sk == "TERRAIN_RELIEF":
        return "EXCLUDE", "R1", "A " + sk, kind
    if sk == "NOT_OBJECT" and kind == "NOT_OBJECT":
        return "EXCLUDE", "R2", "A " + sk, kind
    rs = (rels or {}).get(a, [])
    cand = [r for r in rr.relation_open(rs, unit_map) if r["kind"] not in EVIDENCE_ONLY]
    ver = [r for r in cand if r.get("verified") and r["kind"] in unit_map]
    if ver:
        return unit_map[ver[0]["kind"]], "R0v", "%s %s (подтверждено)" % (ver[0]["kind"], ver[0]["relative"]), kind
    ml = [x for x in (mcd.get(a.upper(), []) if use_mcd else []) if x["side"] == "derived"]
    strong = [x for x in ml if x["level"] == "STRONG" and x["via"] != "anim"]
    if strong:
        x = strong[0]
        return "STATE_VARIANT", "R3m", "MCD %s %s, основа %s" % (x["via"], x["base"], x["root"]), kind
    anim = [x for x in ml if x["level"] == "STRONG" and x["via"] == "anim"]
    if anim:        # петля анимации - общий облик и опознание, не разрушенный вид (специалист 01.10)
        x = anim[0]
        return "ANIMATION_FAMILY", "R3a", "MCD anim %s, основа %s" % (x["base"], x["root"]), kind
    if a in state or cls.get(a) == "state_variant":
        return "STATE_VARIANT", "R3", "state_variants / class_decisions", kind
    fr = fam_rel.get(a, "canonical")
    if fr2 is None:
        if rel in ("recolor", "mirror") or fr not in ("canonical", "alternate_view"):
            return "DERIVED", "R4", "relation %s" % (rel or fr), kind
    else:           # FAMILY_RELATION_V2: перекраска - только прямое строгое ребро, без цепочки семейства
        direct = [e for e in fr2.get(a.upper(), []) if e["status"] in FR2_DIRECT and e["side"] == "derived"]
        if direct:
            e = direct[0]
            return "DERIVED", "R4d", "FR2 %s %s %s, основа %s" % (e["relation"], e["status"], e["confidence"],
                                                                    e["relative"]), kind
        if rel == "mirror" or fr == "mirror":
            return "DERIVED", "R4", "relation mirror", kind
        if rel == "recolor" or fr == "recolor":
            leg = [e["relative"] for e in fr2.get(a.upper(), []) if e["status"] == "LEGACY_RELATION"]
            return "REVIEW", "R4l", "LEGACY_RELATION recolor %s: строгий тест не прошёл" % (
                ", ".join(leg) or "-"), kind
        if fr not in ("canonical", "alternate_view", "recolor", "mirror"):
            return "DERIVED", "R4", "relation %s" % fr, kind
    if g.get("kind") == "составной" or cls.get(a) == "part_fragment":
        return "COMPOSITE_PART", "R5", "kind %s, class %s" % (g.get("kind", "-"), cls.get(a, "-")), kind
    if a in modular or cls.get(a) == "structural_modular":
        return "STRUCTURAL_MODULAR", "R6", "modular_objects / class_decisions", kind
    skip = ("part_fragment_suspect",) if kind == "STRUCTURAL_SURFACE" else ()
    opened = [b for b in blockers if b.split(":")[0] in rr.OPEN_BLOCKERS and b.split(":")[0] not in skip]
    if a in fam_review:
        opened.append("review семейства")
    if rel == "alternate_view" or fam_rel.get(a) == "alternate_view":
        opened.append("alternate_view")
    if opened:
        return "REVIEW", "R7", " ".join(opened), kind
    if cand:
        return "REVIEW", "R7r", "; ".join("%s %s %s" % (r["kind"], r["level"], r["relative"]) for r in cand), kind
    if ml:
        return "REVIEW", "R7m", "; ".join("MCD %s %s %s" % (x["via"], x["base"], x["why"]) for x in ml), kind
    if kind == "STRUCTURAL_SURFACE":
        return "EXCLUDE", "S", "поверхность: %s" % swhy, kind
    nb = [r for r in rs if r["kind"] in EVIDENCE_ONLY]
    if nb and neighbour_review:
        return "REVIEW", "R7n", "улика: " + "; ".join("%s %s" % (r["kind"], r["relative"]) for r in nb), kind
    if sk == "OBJECT" and lvl:
        return "REVIEW", "R7s", "вещь или поверхность? %s" % swhy, kind
    if sk == "OBJECT_PART":
        return "REVIEW", "R8a", "OBJECT_PART, подтверждённой одиночности нет", kind
    if sk == "OBJECT":
        return "STANDALONE_RENDER", "R8", "нет более сильного родства", kind
    return "REVIEW", "R9", "A " + (sk or "-"), kind


# ---------------------------------------------------------------- родство

def claim_rows(rels, mcd, refp, keys, fr2=None):
    """Утверждения V5 против эталона пар: перекраска детектора (без FIXED_NEIGHBOUR), состояния MCD STRONG и, если
    дан fr2, прямые рёбра FAMILY_RELATION_V2 (та же пара детектора не повторяется).
    Тот же подсчёт, что routing_holdout.relation_metrics, со своими видами."""
    ref = {(r["asset_id"].upper(), r["relative"].upper()): r for r in refp}
    raw, seen = [], set()
    for k in keys:
        for c in rels.get(k, []):
            if c["kind"] not in EVIDENCE_ONLY:
                raw.append((k, c["relative"], c["kind"], c["level"], c["side"], "detector"))
                seen.add((k.upper(), c["relative"].upper(), c["kind"]))
        for x in mcd.get(k.upper(), []):
            if x["level"] == "STRONG":
                raw.append((k, x["relative"], x["kind"], "STRONG", x["side"], "mcd_" + x["via"]))
        for e in (fr2 or {}).get(k.upper(), []):
            if e["status"] in FR2_DIRECT and (k.upper(), e["relative"].upper(), e["relation"]) not in seen:
                seen.add((k.upper(), e["relative"].upper(), e["relation"]))
                raw.append((k, e["relative"], e["relation"], e["confidence"], e["side"], "fr2_" + e["status"]))
    out = []
    for k, rel_to, kind, level, side, src in raw:
        r = ref.get((k.upper(), rel_to.upper()))
        rel = (r or {}).get("ref_pair_relation") or "OPEN"
        st = "open" if rel == "OPEN" else ("ok" if rh.GROUP.get(rel) == CLAIM_GROUP[kind] else "wrong")
        dr = (r or {}).get("direction") or "open"
        dir_ok = None
        if st == "ok" and side in ("derived", "base") and dr in d2.KNOWN_DIR:
            dir_ok = (side == "derived") == (dr == "asset_derived")
        out.append({"asset_id": k, "relative": rel_to, "kind": kind, "level": level, "side": side, "source": src,
                    "ref": rel, "direction": dr, "status": st, "exact": rel in CLAIM_EXACT[kind],
                    "direction_ok": dir_ok, "judged": r is not None})
    return out


def neighbour_evidence(frozen_claims):
    return [{"asset_id": c["asset_id"], "relative": c["relative"], "ref": c["ref"],
             "v4r1_status": c["status"]} for c in frozen_claims if c["kind"] in EVIDENCE_ONLY]


# ---------------------------------------------------------------- пересчёт

def dir_sha(path):
    res = {}
    for base, _dirs, files in os.walk(path):
        for n in files:
            fp = os.path.join(base, n)
            with open(fp, "rb") as f:
                res[os.path.relpath(fp, path).replace(os.sep, "/")] = hashlib.sha256(f.read()).hexdigest()
    return res


def targets(tot, prec):
    t = TARGETS
    p = prec["relation_precision"] if prec["closed"] >= t["relation_precision_min_n"] else None

    def ge(v, lim):
        return None if v is None else v >= lim
    return {"DANGEROUS_FALSE_STANDALONE = 0": tot["dangerous_false_standalone"] <= t["dangerous_false_standalone_max"],
            "relation_precision_gate >= %.2f (закрытых >= %d)" % (t["relation_precision_min"],
                                                                 t["relation_precision_min_n"]):
                ge(p, t["relation_precision_min"]),
            "routing_accuracy >= %.2f" % t["routing_accuracy_min"]: ge(tot["routing_accuracy"], t["routing_accuracy_min"]),
            "routing_coverage >= %.2f" % t["routing_coverage_min"]: ge(tot["routing_coverage"], t["routing_coverage_min"])}


def dominance_counts(rows, rows_nodom, mcd, keys):
    """MCD_DOMINANCE_RULE (PROVISIONAL): где сработало, где маршрут сменился, помогло или навредило по эталону."""
    trig = sorted(k for k in keys if any(x.get("dominance") and x["side"] == "derived"
                                         for x in mcd.get(k.upper(), [])))
    old = {r["asset_id"]: r for r in rows_nodom}
    changed, helped, hurt = [], [], []
    for r in rows:
        o = old[r["asset_id"]]
        if o["rule_unit"] == r["rule_unit"]:
            continue
        changed.append([r["asset_id"], o["rule_unit"], r["rule_unit"], r["ref_route"]])
        if r["ref_route"] == "open":
            continue
        if r["rule_unit"] == r["ref_route"] and o["rule_unit"] != r["ref_route"]:
            helped.append(r["asset_id"])
        elif o["rule_unit"] == r["ref_route"] and r["rule_unit"] != r["ref_route"]:
            hurt.append(r["asset_id"])
    return {"triggered": trig, "route_changed": changed, "helped": helped, "hurt": hurt}


def fr2_diag(rows, build, fr2, keys):
    """FAMILY_RELATION_V2 против V5_PREP на тех же 40: что закрыли прямые рёбра, без подстройки."""
    base = {r["asset_id"]: r for r in build(fr2=None)}
    fam = []
    for r in rows:
        b = base[r["asset_id"]]
        if b["rule"] == "R7" and ("review семейства" in b["why"] or "family_review" in b["why"]):
            st = ("REVIEW" if r["rule_unit"] == "REVIEW" else "open_ref" if r["ref_route"] == "open" else
                  "closed_ok" if r["rule_unit"] == r["ref_route"] else "closed_wrong")
            fam.append({"asset_id": r["asset_id"], "v5prep": "%s %s" % (b["rule"], b["why"]),
                        "fr2": "%s %s" % (r["rule_unit"], r["rule"]), "why": r["why"], "ref_route": r["ref_route"],
                        "result": st})
    no_new = {k: [e for e in v if e["status"] != "DIRECT_NEW"] for k, v in fr2.items()}
    return {"v5prep_total": rh.routing_metrics(list(base.values())),
            "sensitivity": {"без DIRECT_NEW (только VERIFIED_DIRECT)": rh.routing_metrics(build(fr2=no_new))},
            "family_review": fam, "family_review_result": dict(Counter(x["result"] for x in fam)),
            "changed": [[r["asset_id"], base[r["asset_id"]]["rule_unit"], base[r["asset_id"]]["rule"],
                         r["rule_unit"], r["rule"], r["ref_route"], r["why"]] for r in rows
                        if r["rule"] != base[r["asset_id"]]["rule"]],
            "edges": {k: ["%s %s %s %s" % (e["status"], e["confidence"] or "-", e["side"], e["relative"])
                          for e in fr2.get(k.upper(), [])] for k in keys if fr2.get(k.upper())}}


def recount(out=OUT, hold=HOLDOUT, fr2=None, tag=""):
    import map_mockup as mm
    import obj_struct as os_
    before = dir_sha(hold)
    d, h = rh.load_freeze(hold), rh.load_holdout(hold)
    a1, a2 = rd.load_amend(hold), d2.load_amend2(hold)
    ref, refp, _lk = rh.load_reference(hold)
    rels = rh.load_relations(hold)
    supp = d2.load_supp(hold)
    frozen = ir.load_json(os.path.join(hold, "report.json"))
    ans = {r["asset_id"]: r for r in ir.read_tsv(os.path.join(hold, "answers_vitali.tsv"))}
    keys = [x["asset_id"] for x in h["items"]]
    layer = {x["asset_id"]: x for x in h["items"]}
    inp = dict(d["inputs"])
    inp["relations"] = rh.load_json_path(hold)
    meta = rr.metadata(inp)
    umap = d["routing"]["relation_unit"]
    world = mm.World()
    st = os_.Struct(world)
    sets = {k.split(":")[0] for k in keys} | {c["relative"].split(":")[0] for k in keys for c in rels.get(k, [])}
    mcd = ms.index(ms.build(sets, world))
    mcd_nodom = ms.index(ms.build(sets, world, dominant=False))
    surf = {a: surface_evidence(st, a) for a in keys}
    old = {r["asset_id"]: r for r in frozen["rows"]}

    def build(mcd_idx=None, **kw):
        kw.setdefault("fr2", fr2)
        rows = []
        for a in keys:
            sk = ans.get(a, {}).get("semantic_kind", "")
            u, rule, why, kind = route_v5(a, sk, meta, mcd if mcd_idx is None else mcd_idx, surf[a], umap, **kw)
            r = ref.get(a, {})
            rows.append({"asset_id": a, "layer": layer[a]["layer"], "sub": layer[a]["sub"], "semantic_kind": sk,
                         "semantic_v5": kind, "surface": surf[a][0], "surface_why": surf[a][1],
                         "ref_semantic_kind": r.get("ref_semantic_kind") or "open",
                         "ref_semantic_v5": semantic_v5(r.get("ref_semantic_kind") or "open", surf[a][0])[0],
                         "rule_unit": u, "rule": rule, "why": why, "ref_route": r.get("ref_route") or "open",
                         "v4r1_unit": old[a]["rule_unit"], "v4r1_rule": old[a]["rule"]})
        return rows

    rows = build()
    tot = rh.routing_metrics(rows)
    claims = claim_rows(rels, mcd, refp, keys, fr2)
    rel = d2.slices(claims, a1["strict_blind_exclude_pairs"], set(h["excluded_sets"]))
    sup_rels = {k: [c for c in v if c["kind"] not in EVIDENCE_ONLY] for k, v in rels.items()}
    sup = d2.supp_slices(sup_rels, supp, keys, a2["supplement_pairs"]) if supp is not None else None
    sens = {"без улик поверхности": rh.routing_metrics(build(use_surface=False)),
            "без MCD_STATE": rh.routing_metrics(build(use_mcd=False)),
            "FIXED_NEIGHBOUR не даёт и REVIEW": rh.routing_metrics(build(neighbour_review=False)),
            "MCD без правила частоты (найдено на FORESTRED:4)": rh.routing_metrics(build(mcd_idx=mcd_nodom))}
    rel_nodom = d2.slices(claim_rows(rels, mcd_nodom, refp, keys, fr2), a1["strict_blind_exclude_pairs"],
                          set(h["excluded_sets"]))["relation_precision_gate"]
    review_closed = [[r["asset_id"], r["rule"], r["ref_route"], r["why"]] for r in rows
                     if r["rule_unit"] == "REVIEW" and r["ref_route"] != "open"]
    # независимость поверхности от NOT_OBJECT: тот же маршрут при OBJECT_PART и NOT_OBJECT; у OBJECT - не одиночный
    indep = []
    for a in keys:
        if not surf[a][0] and a != "CRYPTEK1:16":
            continue
        us = {sk: route_v5(a, sk, meta, mcd, surf[a], umap, fr2=fr2)[:2] for sk in ("OBJECT", "OBJECT_PART", "NOT_OBJECT")}
        indep.append({"asset_id": a, "surface": surf[a][0], "why": surf[a][1],
                      "by_answer": {k: "%s %s" % v for k, v in us.items()},
                      "part_eq_not_object": us["OBJECT_PART"][0] == us["NOT_OBJECT"][0],
                      "object_not_standalone": us["OBJECT"][0] != "STANDALONE_RENDER"})
    nb = neighbour_evidence(frozen["relation_claims"])
    nuke = next(r for r in rows if r["asset_id"] == "NUKE2:2")
    nuke_claim = [c for c in claims if c["asset_id"] == "NUKE2:2" and c["source"].startswith("mcd_")]
    sem = lambda fa, fb: [r for r in rows if r[fa] != "UNSURE" and r[fb] != "open"]   # noqa: E731
    s4, s5 = sem("semantic_kind", "ref_semantic_kind"), sem("semantic_v5", "ref_semantic_v5")
    checks = {
        "NUKE2:2 закрыт через MCD": nuke["rule"] == "R3m" and nuke["rule_unit"] == "STATE_VARIANT" and
                                    any(c["status"] == "ok" for c in nuke_claim),
        "FIXED_NEIGHBOUR нет в точности родства": not any(c["kind"] in EVIDENCE_ONLY for c in claims),
        "FIXED_NEIGHBOUR сам не дал маршрута, кроме REVIEW": all(
            r["rule_unit"] == "REVIEW" for r in rows if r["rule"] == "R7n"),
        "поверхности: OBJECT_PART и NOT_OBJECT дают один маршрут": all(x["part_eq_not_object"] for x in indep),
        "CRYPTEK1:16 и поверхности не одиночный и при OBJECT": all(x["object_not_standalone"] for x in indep)}
    after = dir_sha(hold)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "diagnostic_only": True,
           "not_blind": "правила V5 написаны после ответов и эталона этих 40 - PASS не заявляется",
           "holdout": hold.replace(os.sep, "/"), "holdout_freeze_sha256": d["sha256"],
           "holdout_untouched": before == after, "holdout_files": len(before),
           "code_sha256": {c: rh.file_sha(c) for c in CODE},
           "targets": targets(tot, rel["relation_precision_gate"]), "checks": checks, "total": tot,
           "v4r1_total": frozen["total"], "outcomes": rd.breakdown(rows),
           "v4r1_outcomes": rd.breakdown([dict(r, rule_unit=r["v4r1_unit"]) for r in rows]),
           "relations": rel, "supplement": sup, "claims": claims, "neighbour_evidence": nb,
           "independence": indep, "sensitivity": sens, "relation_gate_without_dominance": rel_nodom,
           "review_ref_closed": review_closed,
           "semantic_agreement_v4": rh.rate(sum(r["semantic_kind"] == r["ref_semantic_kind"] for r in s4), len(s4)),
           "semantic_agreement_v5": rh.rate(sum(r["semantic_v5"] == r["ref_semantic_v5"] for r in s5), len(s5)),
           "semantic_n": len(s5), "rules_fired": dict(Counter(r["rule"] for r in rows)),
           "layers": {n: rd.breakdown([r for r in rows if r["layer"] == n]) for n, _q, _s in rh.LAYERS},
           "rows": rows}
    res["tag"] = tag
    res["mcd_dominance_rule"] = ms.MCD_DOMINANCE_RULE
    res["dominance"] = dominance_counts(rows, build(mcd_idx=mcd_nodom), mcd, keys)
    if fr2 is not None:
        res["fr2"] = fr2_diag(rows, build, fr2, keys)
    os.makedirs(out, exist_ok=True)
    ir.dump_json(os.path.join(out, "recount%s.json" % tag), res)
    write_md(out, res)
    if not res["holdout_untouched"]:
        raise SystemExit("папка holdout изменилась во время пересчёта - так быть не должно")
    return res


def write_md(out, res):
    word = {True: "достигнута", False: "**нет**", None: "не решено"}
    t, t4 = res["total"], res["v4r1_total"]
    g = res["relations"]["relation_precision_gate"]
    L = ["# ROUTING_RULES_V5_PREP%s - диагностический пересчёт на тех же 40" % (
             " + FAMILY_RELATION_V2" if res.get("fr2") else ""), "",
         "Не слепо и не PASS: правила V5 написаны после ответов Vitali и эталона этих 40. Итог holdout V4_R1 (FAIL) "
         "стоит, папка holdout только читалась (файлов %d, не изменились: %s)." % (
             res["holdout_files"], "да" if res["holdout_untouched"] else "**НЕТ**"), "",
         "## Цели для заморозки V5", "", "| показатель | V4_R1 | V5_PREP | цель | |", "|---|---|---|---|---|",
         "| DANGEROUS_FALSE_STANDALONE | %d | %d | 0 | %s |" % (
             t4["dangerous_false_standalone"], t["dangerous_false_standalone"],
             word[res["targets"]["DANGEROUS_FALSE_STANDALONE = 0"]]),
         "| точность родства (gate: strict_blind, ACTIONABLE) | 0.826 (19 из 23) | %s (%d из %d) | >= 0.95 | %s |" % (
             g["relation_precision"], g["ok"], g["closed"], word[list(res["targets"].values())[1]]),
         "| точность маршрута | %s (%d из %d) | %s (%d из %d) | >= 0.90 | %s |" % (
             t4["routing_accuracy"], t4["correct"], t4["decided"], t["routing_accuracy"], t["correct"], t["decided"],
             word[list(res["targets"].values())[2]]),
         "| охват | %s (%d из %d) | %s (%d из %d) | >= 0.70 | %s |" % (
             t4["routing_coverage"], t4["decided"], t4["ref_closed"], t["routing_coverage"], t["decided"],
             t["ref_closed"], word[list(res["targets"].values())[3]]),
         "| сверхосторожно (эталон одиночный) | %s | %s | - | |" % (t4["overconservative_rate"],
                                                                    t["overconservative_rate"]),
         "", "## Проверки специалиста", ""]
    L += ["- %s: %s" % (k, "да" if v else "**нет**") for k, v in res["checks"].items()]
    L += ["", "## Исходы", "", "| исход | V4_R1 | V5_PREP |", "|---|---|---|"]
    L += ["| %s | %d | %d |" % (k, res["v4r1_outcomes"][k], v) for k, v in res["outcomes"].items()]
    L += ["", "Правила V5: %s." % ", ".join("%s %d" % kv for kv in sorted(res["rules_fired"].items())), "",
          "Ось A: согласие Vitali с эталоном в онтологии V4 %s, в онтологии V5 (поверхность из улики MCD с обеих "
          "сторон) %s, сравнимых %d." % (res["semantic_agreement_v4"], res["semantic_agreement_v5"],
                                         res["semantic_n"]), "",
          "## Точность родства по срезам (ACTIONABLE_RELATION_TRUTH)", "",
          "| срез | верно | ошибка | закрыто | точность |", "|---|---|---|---|---|"]
    for k in ("relation_precision_gate", "relation_precision_all", "strong_relation_precision_primary",
              "candidate_relation_precision_primary"):
        x = res["relations"][k]
        L.append("| %s | %d | %d | %d | %s |" % (k, x["ok"], x["closed"] - x["ok"], x["closed"],
                                                 x["relation_precision"]))
    if res["supplement"]:
        x = res["supplement"]["strong_relation_precision_supplemental"]
        L.append("| strong_relation_precision_supplemental | %d | %d | %d | %s |" % (
            x["ok"], x["closed"] - x["ok"], x["closed"], x["relation_precision"]))
    L += ["", "unresolved по правилу: %s." % ("; ".join(" ~ ".join(u[:2]) for u in
                                                         res["relations"]["unresolved_by_rule"]) or "нет"), "",
          "| утверждение | вид | источник | уровень | эталон | статус |", "|---|---|---|---|---|---|"]
    for c in res["claims"]:
        L.append("| %s ~ %s | %s | %s | %s | %s %s | %s |" % (c["asset_id"], c["relative"], c["kind"], c["source"],
                                                              c["level"], c["ref"], c["direction"], c["status"]))
    L += ["", "## FIXED_NEIGHBOUR - теперь улика, не родство", "",
          "| кадр | сосед | эталон | статус в V4_R1 |", "|---|---|---|---|"]
    L += ["| %s | %s | %s | %s |" % (x["asset_id"], x["relative"], x["ref"], x["v4r1_status"])
          for x in res["neighbour_evidence"]]
    L += ["", "## Поверхность не зависит от NOT_OBJECT", "",
          "| кадр | улика | OBJECT | OBJECT_PART | NOT_OBJECT |", "|---|---|---|---|---|"]
    L += ["| %s | %s %s | %s | %s | %s |" % (x["asset_id"], x["surface"] or "-", x["why"], x["by_answer"]["OBJECT"],
                                             x["by_answer"]["OBJECT_PART"], x["by_answer"]["NOT_OBJECT"])
          for x in res["independence"]]
    L += ["", "## Чувствительность (не итог)", "", "| вариант | точность | решено | охват | опасных |",
          "|---|---|---|---|---|"]
    for k, s in res["sensitivity"].items():
        L.append("| %s | %s | %d из %d | %s | %d |" % (k, s["routing_accuracy"], s["decided"], s["ref_closed"],
                                                       s["routing_coverage"], s["dangerous_false_standalone"]))
    x = res["relation_gate_without_dominance"]
    L += ["", "Точность родства (gate) без правила частоты MCD: %s (%d из %d) - правило найдено на этих 40, "
          "на новом слепом наборе проверяется заново." % (x["relation_precision"], x["ok"], x["closed"]), "",
          "## REVIEW при закрытом эталоне (охват)", "", "| кадр | правило | эталон | почему REVIEW |", "|---|---|---|---|"]
    L += ["| %s | %s | %s | %s |" % tuple(r) for r in res["review_ref_closed"]]
    dm = res["dominance"]
    L += ["", "## MCD_DOMINANCE_RULE (PROVISIONAL, origin FORESTRED:4 diagnostic, requires_blind_validation)", "",
          "Сработало: %s. Маршрут сменился: %s. Помогло: %s. Навредило: %s." % (
              ", ".join(dm["triggered"]) or "нет", "; ".join("%s %s -> %s (эталон %s)" % tuple(c)
                                                            for c in dm["route_changed"]) or "нет",
              ", ".join(dm["helped"]) or "нет", ", ".join(dm["hurt"]) or "нет")]
    if res.get("fr2"):
        f = res["fr2"]
        b = f["v5prep_total"]
        L += ["", "## FAMILY_RELATION_V2 против V5_PREP (диагностика, без подстройки)", "",
              "V5_PREP: точность %s (%d из %d), охват %s (%d из %d), опасных %d." % (
                  b["routing_accuracy"], b["correct"], b["decided"], b["routing_coverage"], b["decided"],
                  b["ref_closed"], b["dangerous_false_standalone"]), "",
              "REVIEW из-за семейства в V5_PREP: %d; итог с FR2: %s." % (
                  len(f["family_review"]), ", ".join("%s %d" % kv for kv in sorted(f["family_review_result"].items()))),
              "", "| кадр | V5_PREP | FR2 | эталон | итог | почему |", "|---|---|---|---|---|---|"]
        L += ["| %s | %s | %s | %s | %s | %s |" % (x["asset_id"], x["v5prep"], x["fr2"], x["ref_route"], x["result"],
                                                  x["why"]) for x in f["family_review"]]
        L += ["", "Сменили маршрут:", "", "| кадр | V5_PREP | FR2 | эталон | почему |", "|---|---|---|---|---|"]
        L += ["| %s | %s %s | %s %s | %s | %s |" % tuple(c) for c in f["changed"]]
        L += ["", "| вариант | точность | решено | охват | опасных |", "|---|---|---|---|---|"]
        for k, s in f["sensitivity"].items():
            L.append("| %s | %s | %d из %d | %s | %d |" % (k, s["routing_accuracy"], s["decided"], s["ref_closed"],
                                                           s["routing_coverage"], s["dangerous_false_standalone"]))
        L += ["", "Рёбра FR2 у кадров holdout:", ""]
        L += ["- %s: %s" % (k, "; ".join(v)) for k, v in sorted(f["edges"].items())]
    L += ["", "## По предметам", "",
          "| предмет | A Vitali | вид V5 | улика | V4_R1 | V5 | правило | эталон | исход | почему |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        L.append("| %s | %s | %s | %s | %s %s | %s | %s | %s | %s | %s |" % (
            r["asset_id"], r["semantic_kind"], r["semantic_v5"], r["surface"] or "-", r["v4r1_rule"], r["v4r1_unit"],
            r["rule_unit"], r["rule"], r["ref_route"], rd.outcome(r), r["why"]))
    with open(os.path.join(out, "recount%s.md" % res.get("tag", "")), "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:40]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["recount", "recount-fr2"])
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.cmd == "recount-fr2":
        import family_relation_v2 as fr2
        recount(fr2=fr2.load(), tag="_fr2")
    else:
        recount()


if __name__ == "__main__":
    main()
