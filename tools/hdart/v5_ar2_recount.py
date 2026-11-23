#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V5_AR2_RECOUNT_V1 - один диагностический пересчёт тех же 80 кадров holdout V4 с ALIGNED_RECOLOR_V2 вместо AR1
(специалист 02.10, передал Vitali в чате). CPU, чтение. Не независимая оценка.

Что меняется против V5_PREP: доводы AR1 из found5.json убраны, вместо них доводы AR2 (aligned_recolor_v2: AR1 с
границами >= 0.70, существование STRONG, подтип открыт). Доводы V8, V3, V4 и ASM - те же замороженные. В маршруте
довод AR2 - TYPE_OPEN («AR2: подтип на ревью»), автоматического действия перекраски нет.

Условия заморозки V5 те же, новых ворот нет (v5_freeze_readiness.readiness): PRE 0 и POST 0, существование >= 0.95,
производный >= 0.70, состояние >= 0.70, composite discovery recall >= 0.70, авто >= 0.95, ASSEMBLY candidate
existence >= 0.95 и ASSEMBLY STRONG composite >= 0.95; composite_strong_recall - диагностика.

KITSUNE:15 считается исправленным, только если (1) после ревью (кандидаты на парах closed NONE удалены) он не опасен
и (2) он не опасен, когда на нём оставлены только доводы на парах, связь которых закрыта RELATED независимым
эталоном (holdout V4, V5_COMPONENT_VALIDATION_V1, ALIGNED_RECOLOR_BOUNDARY_VALIDATION_V1). Порог 0.70 после
пересчёта не двигается.

    py -3.13 tools/hdart/v5_ar2_recount.py freeze     спецификация и хэши кода -> FREEZE.json (до пересчёта)
    py -3.13 tools/hdart/v5_ar2_recount.py discover   доводы AR2 на 80 кадрах -> found_ar2.json (замок)
    py -3.13 tools/hdart/v5_ar2_recount.py report     -> report.json, report.md
VERIFIED ставит только человек.
"""
import argparse
import copy
import json
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aligned_recolor_v1 as ar1                  # noqa: E402
import aligned_recolor_v2 as ar2                  # noqa: E402
import identity_routing as ir                     # noqa: E402
import post_review_safety as prs                  # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_discovery_v5 as rd5               # noqa: E402
import relation_holdout_v4 as hv                  # noqa: E402
import relation_taxonomy as tx                    # noqa: E402

ENC = ir.ENC
PROFILE = "V5_AR2_RECOUNT_V1"
OUT = os.path.join(ir.PROBES, "v5-ar2-recount")
HOLD = rd5.HOLD
KITSUNE = "KITSUNE:15"
CODE = ["tools/hdart/aligned_recolor_v2.py", "tools/test_aligned_recolor_v2.py", "tools/hdart/v5_ar2_recount.py",
        "tools/test_v5_ar2_recount.py", "tools/hdart/post_review_safety.py", "tools/hdart/v5_freeze_readiness.py",
        "tools/hdart/aligned_recolor_v1.py", "tools/hdart/relation_discovery_v5.py"]
STRONG, CAND, T_STRONG, T_OPEN, BINDING = v4.STRONG, v4.CAND, v4.T_STRONG, v4.T_OPEN, v4.BINDING
DETECTOR_ORDER = dict(rd5.DETECTOR_ORDER5, AR2=8)
KITSUNE_RULE = ("KITSUNE:15 исправлен, только если POST_REVIEW не опасен И не опасен, когда на кадре оставлены "
                "только доводы на парах, закрытых RELATED независимым эталоном (holdout V4, V5_COMPONENT_VALIDATION_V1, "
                "ALIGNED_RECOLOR_BOUNDARY_VALIDATION_V1). Порог 0.70 после пересчёта не двигается, исключений нет")


def p(*a):
    return os.path.join(OUT, *a)


# ---------------------------------------------------------------- доводы: V5_PREP с AR2 вместо AR1

class _Base5AR2(rd5._Base5):
    """Как rd5._Base5 (замороженный), плюс детектор AR2: порядок 8, «AR2: подтип на ревью» - TYPE_OPEN."""

    def finalize(self):
        for c in self.claims.values():
            sup = sorted(c["support"], key=lambda e: (e["level"] not in BINDING, e["detector"] in v3.DIAGNOSTIC,
                                                      DETECTOR_ORDER[e["detector"]], e["type"]))
            c["support"] = sup
            prim = sup[0]
            c["type"], c["source"], c["target"] = prim["type"], prim["source"], prim["target"]
            c["existence"] = STRONG if any(e["level"] in BINDING and e["detector"] not in v3.DIAGNOSTIC
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
                if all(e["detector"] in v3.DIAGNOSTIC for e in c["support"]):
                    why.append("только диагностический детектор")
                if c["group"] in spoken and len(spoken) > 1:
                    why.append("спор типа: %s" % "/".join(spoken))
                dirs = {(e["source"], e["target"]) for e in c["support"]
                        if e["level"] in BINDING and e["type"] not in rd5.SYMMETRIC5}
                if len(dirs) > 1:
                    why.append("спор направления")
                bind = [e for e in c["support"] if e["level"] in BINDING]
                if c["group"] == "attachment":
                    why.append("примыкание - улика")
                if bind and all(e["detector"] == "R4" for e in bind):
                    why.append("R4: подтип на ревью")
                if bind and all(e["detector"] in ("R4", "AR1") for e in bind) and \
                        any(e["detector"] == "AR1" for e in bind):
                    why.append("AR1: подтип на ревью")
                if bind and all(e["detector"] in ("R4", "AR1", "AR2") for e in bind) and \
                        any(e["detector"] == "AR2" for e in bind):
                    why.append("AR2: подтип на ревью")
                if bind and all(e["detector"] == "MR4" for e in bind) and not self.MR_TYPED:
                    why.append("MIRRORED_RECOLOR_CANDIDATE")
                c["type_level"] = T_OPEN if why else T_STRONG
                c["type_open_why"] = why
        return self


class V5AR2Claims(tx.TaxClaims, _Base5AR2):
    """Порядок как у rd5.V5Claims: TaxClaims поверх _Base5AR2."""


def claims(rows, found3, found4, edges):
    C = v3.claims_from_v8(rows)
    C.__class__ = V5AR2Claims
    for e in found3["edges"]:
        e2 = v4.convert_v3(e)
        if e2:
            C.add(e2)
    for a, roles in found3["self_roles"].items():
        C.self_roles[a.upper()] += roles
    for e in found4["edges"]:
        C.add(e)
    for e in edges:
        C.add(e)
    return C.finalize()


def edges_ar2(f5, far2):
    """found5 без AR1 плюс доводы AR2. -> (доводы, убрано AR1)."""
    keep = [e for e in f5["edges"] if e["detector"] != ar1.DETECTOR]
    return keep + far2["edges"], len(f5["edges"]) - len(keep)


# ---------------------------------------------------------------- спецификация и заморозка

def spec():
    return {"profile": PROFILE, "decision": "специалист 02.10, передал Vitali в чате (docs/DECISIONS.md 2026-10-02)",
            "aligned_recolor_v2": ar2.PARAMS, "validated_range": "границ >= 0.70",
            "not_validated": "границ < 0.70 - AR2 не срабатывает; ни 0.65, ни 0.60, ни исключений после пересчёта",
            "route": "довод AR2: существование STRONG, тип ALIGNED_RECOLOR TYPE_OPEN («AR2: подтип на ревью»), "
                     "автоматического действия перекраски нет",
            "edges": "found5.json V5_PREP без доводов AR1 плюс found_ar2.json; V8, V3, V4, ASM - замороженные",
            "freeze_conditions": "v5_freeze_readiness.readiness без изменений: PRE 0, POST 0, existence >= 0.95, "
                                 "derived >= 0.70, state >= 0.70, composite discovery recall >= 0.70, auto >= 0.95, "
                                 "ASSEMBLY candidate existence >= 0.95, ASSEMBLY STRONG composite >= 0.95; "
                                 "composite_strong_recall - диагностика",
            "closed_none_sources": ["holdout V4 truth.json", "V5_COMPONENT_VALIDATION_V1 truth.json",
                                    "ALIGNED_RECOLOR_BOUNDARY_VALIDATION_V1 truth.json"],
            "kitsune_rule": KITSUNE_RULE,
            "control": "V5_PREP (found5 как есть, классы rd5) обязан дать ворота отчёта V5_PREP; claims этого модуля "
                       "на found5 как есть - те же ворота",
            "holdout": "те же 80 кадров и эталон holdout V4; один пересчёт, не независимая оценка"}


def code_sha():
    return {c: hv.file_sha(c) for c in CODE}


def do_freeze():
    if os.path.exists(p("FREEZE.json")):
        raise SystemExit("уже заморожено: %s" % p("FREEZE.json"))
    if os.path.exists(p("found_ar2.json")):
        raise SystemExit("пересчёт уже был - заморозка после него не имеет смысла")
    missing = [c for c in CODE if not os.path.exists(c)]
    if missing:
        raise SystemExit("нет файлов: %s" % ", ".join(missing))
    body = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec": spec(), "code_sha256": code_sha(),
            "validation": ar2.check_validation(),
            "v5_prep_freeze_sha256": hv.file_sha(rd5.p("FREEZE.json")),
            "found5_sha256": hv.file_sha(rd5.p("found5.json")),
            "holdout_relations_lock_sha256": hv.file_sha(os.path.join(HOLD, "relations.lock.json")),
            "holdout_reference_lock_sha256": hv.file_sha(os.path.join(HOLD, "reference.lock.json"))}
    os.makedirs(OUT, exist_ok=True)
    ir.dump_json(p("FREEZE.json"), body)
    print("заморожено: %s, sha256 %s" % (p("FREEZE.json"), hv.file_sha(p("FREEZE.json"))[:12]))


def check_freeze():
    if not os.path.exists(p("FREEZE.json")):
        raise SystemExit("нет FREEZE.json - сначала freeze")
    fz = ir.load_json(p("FREEZE.json"))
    bad = [c for c, s in fz["code_sha256"].items() if hv.file_sha(c) != s]
    if json.dumps(fz["spec"], sort_keys=True, ensure_ascii=False) != \
            json.dumps(json.loads(json.dumps(spec(), ensure_ascii=False)), sort_keys=True, ensure_ascii=False):
        bad.append("spec")
    for k, f in (("v5_prep_freeze_sha256", rd5.p("FREEZE.json")), ("found5_sha256", rd5.p("found5.json")),
                 ("holdout_relations_lock_sha256", os.path.join(HOLD, "relations.lock.json")),
                 ("holdout_reference_lock_sha256", os.path.join(HOLD, "reference.lock.json"))):
        if hv.file_sha(f) != fz[k]:
            bad.append(os.path.basename(f))
    if bad:
        raise SystemExit("изменено после заморозки: %s" % ", ".join(bad))
    return fz


# ---------------------------------------------------------------- discover

def do_discover():
    fz = check_freeze()
    if os.path.exists(p("found_ar2.json")):
        raise SystemExit("доводы AR2 уже посчитаны: %s" % p("found_ar2.json"))
    h = hv.load_holdout(HOLD)
    keys = hv.keys_of(h)
    ctx = hv.ctx_v3()
    si = v4.SetIndex(ctx)
    edges, perm = [], []
    for a in keys:
        t0 = time.time()
        es = ar2.discover(ctx, si, a)
        for e in es:
            fired = bool(ar2.pair(ctx, si, e["source"], e["target"], B=v3.permuted(ctx, e["target"], 7)))
            perm.append({"pair": [e["source"], e["target"]], "fired": fired})
        edges += es
        print(a, len(es), "%.1f с" % (time.time() - t0), flush=True)
    ir.dump_json(p("found_ar2.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE,
                                       "freeze_sha256": hv.file_sha(p("FREEZE.json")), "keys": keys, "edges": edges,
                                       "permuted_control": perm,
                                       "note": "утверждения AR2, не маршрут; VERIFIED ставит только человек"})
    ir.dump_json(p("found_ar2.lock.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                            "found_ar2_sha256": hv.file_sha(p("found_ar2.json")),
                                            "freeze_sha256": hv.file_sha(p("FREEZE.json")),
                                            "spec_created": fz["created"]})
    print("доводов AR2 %d; перемешанный контроль %d из %d; замок %s" % (
        len(edges), sum(x["fired"] for x in perm), len(perm), hv.file_sha(p("found_ar2.json"))[:12]))


def load_found_ar2():
    lk = ir.load_json(p("found_ar2.lock.json"))
    if hv.file_sha(p("found_ar2.json")) != lk["found_ar2_sha256"]:
        raise SystemExit("found_ar2.json изменён после замка")
    return ir.load_json(p("found_ar2.json"))


# ---------------------------------------------------------------- KITSUNE и безопасность

def keep_on_asset(C, asset, keep):
    """Копия доводов, где у кадра asset оставлены только доводы на парах из keep (ключи tx.pk)."""
    A = asset.upper()
    C2 = copy.copy(C)
    C2.claims, C2.by_asset = {}, defaultdict(set)
    removed = []
    for k, c in C.claims.items():
        if A in c["pair"] and tx.pk(*c["pair"]) not in keep:
            removed.append(c["pair"])
            continue
        C2.claims[k] = c
        for x in c["pair"]:
            C2.by_asset[x].add(k)
    return C2, removed


def truth_sources(T, vrows, brows):
    """Три закрытых независимых эталона -> [(имя, [(a, b, существование)])]."""
    return [("holdout V4", [tuple(sorted(k)) + (t[0],) for k, t in T.items()]),
            ("V5 component validation", [(r["a"], r["b"], r["existence"]) for r in vrows]),
            ("AR boundary validation", [(r["a"], r["b"], r["existence"]) for r in brows])]


def closed_related(sources):
    out = {}
    for name, rows in sources:
        for a, b, ex in rows:
            if ex == "RELATED":
                out.setdefault(tx.pk(a, b), []).append(name)
    return out


def decision(res, a):
    x = {s["asset_id"].upper(): s for s in res["score"]}[a.upper()]
    return {"pipeline": x["pipeline"], "creative_standalone": x["creative"], "danger": x["danger"],
            "dangerous": bool(x["danger"]),
            "decision": "DANGEROUS (creative standalone при истинной связи)" if x["danger"] else
            ("creative standalone" if x["creative"] else "не creative: связан или на REVIEW")}


def claim_view(c, T, rel, none):
    k = tx.pk(*c["pair"])
    t = T.get(k)
    return {"pair": c["pair"], "group": c["group"], "type": c["type"], "existence": c["existence"],
            "type_level": c["type_level"], "type_open_why": c["type_open_why"], "auto": tx.auto_claim(c),
            "detectors": sorted({e["detector"] + " " + e.get("rule", "") + " " + e["level"] for e in c["support"]}),
            "truth_v4": None if t is None else {"existence": t[0], "closed": sorted(t[1]), "open": sorted(t[2])},
            "state_v4": hv.tv_state(c, t) if t else None,
            "closed_related_by": rel.get(k, []), "closed_none_by": none.get(k, [])}


def kitsune_detail(ctx, si, T, C, pre, post, cf, rel, none, far2):
    """Без толкования: истинные пары KITSUNE, очки AR1/AR2, доводы, решение до и после ревью."""
    A = ctx.rgba(KITSUNE)
    cands = {b.upper() for b in ar2.candidates(ctx, KITSUNE)}
    ar2_pairs = {tx.pk(e["source"], e["target"]) for e in far2["edges"]}
    pairs = []
    for k, t in sorted(T.items(), key=lambda kv: sorted(kv[0])):
        if KITSUNE not in k or t[0] != "RELATED":
            continue
        b = [x for x in k if x != KITSUNE][0]
        B = ctx.rgba(b)
        row = {"pair": [KITSUNE, b], "truth_v4": sorted(t[1]), "truth_open": sorted(t[2]),
               "in_ar2_candidates": b in cands, "ar2_edge": tx.pk(KITSUNE, b) in ar2_pairs}
        if A is None or B is None or A.shape != B.shape:
            row["scores"] = None
        else:
            sc = ar1.scores(A, B)
            ok2, why2 = ar2.passes(sc, si.generic(KITSUNE), si.generic(b))
            ok1, why1 = ar1.passes(sc, si.generic(KITSUNE), si.generic(b))
            row.update(scores={k2: sc[k2] for k2 in ("shift", "flip", "silhouette", "unshifted", "topology", "fmax",
                                                      "f_ab", "f_ba", "residual", "base_colors")},
                       border=sc["topology"], ar1_passes=ok1, ar1_why_not=why1, ar2_passes=ok2, ar2_why_not=why2)
        row["claims"] = [claim_view(c, T, rel, none) for c in C.pair(KITSUNE, b)]
        pairs.append(row)
    held = [claim_view(c, T, rel, none) for c in C.of(KITSUNE)]
    fixed = not post["dangerous"].get(KITSUNE) and not cf["dangerous"].get(KITSUNE) and \
        not decision(cf, KITSUNE)["creative_standalone"]
    return {"true_pairs": pairs, "held_by": held,
            "decision_pre_review": decision(pre, KITSUNE), "decision_post_review": decision(post, KITSUNE),
            "decision_confirmed_only": decision(cf, KITSUNE),
            "fixed": fixed, "rule": KITSUNE_RULE}


# ---------------------------------------------------------------- диагностика AR2

def ar2_diag(base, new, C, keys, pool, T, rel, none, perm):
    st = hv.tv_state
    d = Counter()
    rows = []
    for _a, _b, t, cs in new["pc"]:
        for c in cs:
            es = [e for e in c["support"] if e["detector"] == ar2.DETECTOR]
            if not es:
                continue
            border = max(e["scores"]["topology"] for e in es)
            band = "0.70-0.80" if border < ar1.AR_BORDER else ">=0.80"
            d["triggered"] += 1
            d["band " + band] += 1
            s = st(c, t)
            if not t or t[0] == "OPEN":
                d["open"] += 1
            elif t[0] == "NONE":
                d["false_relation"] += 1
                d["false_relation " + band] += 1
            else:
                d["true_related"] += 1
                d["true_related " + band] += 1
                d["subtype_" + {"ok": "correct", "open": "open", "wrong": "wrong"}[s]] += 1
            if tx.auto_claim(c) and s == "wrong":
                d["false_action"] += 1
            if tx.auto_claim(c) and all(e["detector"] in ("R4", "AR1", "AR2") for e in c["support"]
                                        if e["level"] in BINDING):
                d["auto_from_ar2"] += 1
            rows.append({"pair": c["pair"], "border": border, "band": band,
                         "truth": None if not t else t[0], "closed": sorted(t[1]) if t else [],
                         "state": s, "existence": c["existence"], "type_level": c["type_level"]})
    out = []
    for a in keys:
        for c in C.of(a):
            if frozenset(c["pair"]) in pool:
                continue
            es = [e for e in c["support"] if e["detector"] == ar2.DETECTOR]
            if es:
                k = tx.pk(*c["pair"])
                out.append({"pair": c["pair"], "border": max(e["scores"]["topology"] for e in es),
                            "closed_related_by": rel.get(k, []), "closed_none_by": none.get(k, [])})
    uniq = {tuple(x["pair"]): x for x in out}
    d["outside_pool"] = len(uniq)
    d["outside_pool_closed_none"] = sum(1 for x in uniq.values() if x["closed_none_by"])
    d["outside_pool_closed_related"] = sum(1 for x in uniq.values() if x["closed_related_by"])
    d["permuted_control_fired"] = sum(x["fired"] for x in perm)
    d["permuted_control_n"] = len(perm)
    cleared = sorted(a for a in base["dangerous"] if a not in new["dangerous"])
    return dict(d), rows, sorted(uniq.values(), key=lambda x: x["pair"]), cleared


# ---------------------------------------------------------------- report

def do_report():
    import relation_holdout_v4_ref as ref
    import ar_boundary_validation as bv
    import v5_freeze_readiness as vfr
    fz = check_freeze()
    rd5.check_freeze()
    if not ref.do_verify(HOLD):
        raise SystemExit("замок эталона holdout V4 не цел")
    d, h = hv.load_freeze(HOLD), hv.load_holdout(HOLD)
    ch = hv.code_changed(d)
    if ch:
        raise SystemExit("замороженный код V4 изменён: %s" % ", ".join(ch))
    if ar2.check_validation() != fz["validation"]:
        raise SystemExit("отчёт слепой проверки полосы изменился после заморозки")
    V, _by_pair, vrows = vfr.validation()
    bv.check_freeze()
    blk = ir.load_json(bv.p("reference.lock.json"))
    if v2.file_sha(bv.p("truth.json")) != blk["truth_sha256"]:
        raise SystemExit("эталон слепой проверки полосы изменён после заморозки")
    brows = ir.load_json(bv.p("truth.json"))["pairs"]
    f5 = rd5.load_found5()
    far2 = load_found_ar2()
    T, _lk = hv.load_truth(HOLD)
    ans = {r["asset_id"]: r for r in ir.read_tsv(os.path.join(HOLD, "answers_vitali.tsv"))}
    keys = hv.keys_of(h)
    found3, found4 = hv.load_found(HOLD)
    base_r = hv.routing_base(HOLD, d, h)
    rows_r = hv.routing_rows(base_r, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    items = ir.load_json(os.path.join(HOLD, "key.json"))["items"]
    pool = {tx.pk(it["a"], it["b"]) for it in items}
    args = (T, items, keys, h, base_r["fsets"])

    def ev(C):
        return rd5.evaluate(rows_r, C, *args)

    frozen = ir.load_json(rd5.p("report.json"))
    C_prep = rd5.claims(rows_r, found3, found4, f5)
    prep = ev(C_prep)
    C_prep2 = claims(rows_r, found3, found4, f5["edges"])
    prep2 = ev(C_prep2)

    def gv(r):
        return [(g["value"], g["n"]) for g in r["gates"]]
    control = {"rd5_equals_v5_prep_report": [g["value"] for g in prep["gates"]] == [g["value"] for g in frozen["gates"]],
               "this_class_on_found5_equals_rd5": gv(prep2) == gv(prep) and prep2["dangerous"] == prep["dangerous"]}

    edges, dropped_ar1 = edges_ar2(f5, far2)
    C = claims(rows_r, found3, found4, edges)
    new = ev(C)
    sources = truth_sources(T, vrows, brows)
    none_pairs = prs.closed_none(*sources)
    rel = closed_related(sources)
    pp, post = prs.pre_post(ev, C, none_pairs)
    if pp["PRE_REVIEW_DANGEROUS"] != len(new["dangerous"]):
        raise SystemExit("PRE_REVIEW_DANGEROUS не совпал с пересчётом")
    pp_prep, _post_prep = prs.pre_post(ev, C_prep, none_pairs)
    C_post, _dr, _st = prs.after_review(C, none_pairs)
    C_cf, cf_removed = keep_on_asset(C_post, KITSUNE, set(rel))
    cf = ev(C_cf)

    G = vfr.gate_map(new["gates"])
    cond, verdict = vfr.readiness(G, V, pp["POST_REVIEW_DANGEROUS"])
    cond_prep, verdict_prep = vfr.readiness(vfr.gate_map(prep["gates"]), V, pp_prep["POST_REVIEW_DANGEROUS"])
    ctx = hv.ctx_v3()
    si = v4.SetIndex(ctx)
    K = kitsune_detail(ctx, si, T, C, new, post, cf, rel, none_pairs, far2)
    K["confirmed_only_removed"] = cf_removed
    diag, ar2_rows, outside, cleared = ar2_diag(prep, new, C, keys, pool, T, rel, none_pairs,
                                                far2.get("permuted_control", []))
    comp = new["recall"]["composite"]
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE, "decision": spec()["decision"],
           "freeze_sha256": hv.file_sha(p("FREEZE.json")), "spec_created": fz["created"],
           "found_ar2_sha256": hv.file_sha(p("found_ar2.json")), "found5_sha256": hv.file_sha(rd5.p("found5.json")),
           "validation": fz["validation"], "control": control, "dropped_ar1_edges": dropped_ar1,
           "ar2_edges": len(far2["edges"]),
           "freeze_conditions": cond, "verdict": verdict,
           "freeze_conditions_v5_prep": cond_prep, "verdict_v5_prep": verdict_prep,
           "gates": new["gates"], "gates_v5_prep": prep["gates"],
           "composite_discovery_recall": {"value": comp.get("discovery_rate"), "found": comp["discovery"],
                                          "n": comp["n"], "role": "gate >= 0.70"},
           "composite_strong_recall": {"value": v2.rate(comp["strong"], comp["n"]), "found": comp["strong"],
                                       "n": comp["n"], "role": "diagnostic"},
           "assembly_validation": V,
           "post_review": pp, "post_review_v5_prep": {k: pp_prep[k] for k in (
               "PRE_REVIEW_DANGEROUS", "POST_REVIEW_DANGEROUS", "pre_dangerous", "post_dangerous")},
           "post_review_gates": vfr.summary(post),
           "kitsune": K, "ar2": diag, "ar2_rows": ar2_rows, "ar2_outside_pool": outside,
           "ar2_cleared_dangerous_vs_v5_prep": cleared,
           "dangerous": new["dangerous"], "dangerous_v5_prep": prep["dangerous"]}
    os.makedirs(OUT, exist_ok=True)
    ir.dump_json(p("report.json"), res)
    write_md(res)
    print("PRE %d, POST %d; legacy %s, assembly %s, post-review %s -> freeze readiness %s; KITSUNE fixed: %s; "
          "контроль %s" % (pp["PRE_REVIEW_DANGEROUS"], pp["POST_REVIEW_DANGEROUS"], verdict["legacy_gates"],
                           verdict["assembly_validation"], verdict["post_review_safety"], verdict["freeze_readiness"],
                           K["fixed"], control))
    return res


def f3(x):
    return "-" if x is None else ("%.3f" % x if isinstance(x, float) else str(x))


def cl_line(x):
    t = x["truth_v4"]
    return "%s, %s/%s, %s %s%s, авто %s; детекторы: %s; эталон V4: %s; закрыто RELATED: %s; закрыто NONE: %s" % (
        " ~ ".join(x["pair"]), x["group"], x["type"], x["existence"], x["type_level"],
        " (%s)" % "; ".join(x["type_open_why"]) if x["type_open_why"] else "", "да" if x["auto"] else "нет",
        ", ".join(x["detectors"]),
        "%s %s" % (t["existence"], "/".join(t["closed"]) or "-") if t else "нет",
        ", ".join(x["closed_related_by"]) or "нет", ", ".join(x["closed_none_by"]) or "нет")


def dec_line(x):
    return "%s; pipeline %s; creative standalone %s; причины опасности: %s" % (
        x["decision"], x["pipeline"], "да" if x["creative_standalone"] else "нет", "; ".join(x["danger"]) or "нет")


def write_md(res):
    v, K, P = res["verdict"], res["kitsune"], res["post_review"]
    L = ["# V5_AR2_RECOUNT_V1 — пересчёт тех же 80 кадров с ALIGNED_RECOLOR_V2", "",
         "Решение: %s. Один диагностический пересчёт, не независимая оценка. FREEZE %s (%s), found_ar2 %s. "
         "Порог границ AR2 0.70 (слепая проверка %s, отчёт %s); ниже 0.70 — не проверено." % (
             res["decision"], res["freeze_sha256"][:12], res["spec_created"], res["found_ar2_sha256"][:12],
             res["validation"]["profile"], res["validation"]["report_sha256"][:12]), "",
         "Контроль: V5_PREP пересчитан = отчёт V5_PREP — %s; классы этого модуля на found5 как есть = V5_PREP — %s." % (
             "да" if res["control"]["rd5_equals_v5_prep_report"] else "НЕТ",
             "да" if res["control"]["this_class_on_found5_equals_rd5"] else "НЕТ"),
         "Доводов AR1 убрано %d, доводов AR2 добавлено %d." % (res["dropped_ar1_edges"], res["ar2_edges"]), "",
         "```",
         "PRE_REVIEW_DANGEROUS  = %d %s" % (P["PRE_REVIEW_DANGEROUS"], ", ".join(P["pre_dangerous"])),
         "POST_REVIEW_DANGEROUS = %d %s" % (P["POST_REVIEW_DANGEROUS"], ", ".join(P["post_dangerous"])),
         "", "legacy gates        = %s" % v["legacy_gates"], "assembly validation = %s" % v["assembly_validation"],
         "post-review safety  = %s" % v["post_review_safety"], "freeze readiness    = %s" % v["freeze_readiness"],
         "", "KITSUNE:15 fixed    = %s" % ("YES" if K["fixed"] else "NO"), "```", "",
         "## Условия заморозки (без изменений)", "",
         "| условие | V5_PREP | V5 + AR2 | n | нужно | итог |", "|---|---|---|---|---|---|"]
    prev = {r["cond"]: r for r in res["freeze_conditions_v5_prep"]}
    for r in res["freeze_conditions"]:
        L.append("| %s | %s | %s | %s | %s | %s |" % (r["cond"], f3(prev[r["cond"]]["value"]), f3(r["value"]), r["n"],
                                                     r["need"], r["status"]))
    cd, cs = res["composite_discovery_recall"], res["composite_strong_recall"]
    pv = res["post_review_v5_prep"]
    L += ["", "- composite_strong_recall = %s (%d / %d) — диагностика" % (f3(cs["value"]), cs["found"], cs["n"]),
          "- composite_discovery_recall = %s (%d / %d) — ворота" % (f3(cd["value"]), cd["found"], cd["n"]),
          "- V5_PREP для сравнения: PRE %d %s, POST %d %s" % (
              pv["PRE_REVIEW_DANGEROUS"], ", ".join(pv["pre_dangerous"]), pv["POST_REVIEW_DANGEROUS"],
              ", ".join(pv["post_dangerous"])), "",
          "## Безопасность после ревью", "",
          "Удалены кандидаты на парах closed NONE (%d): %s." % (len(P["dropped_candidates"]), "; ".join(
              "%s (%s, %s; %s)" % (" ~ ".join(x["pair"]), x["group"], ", ".join(x["detectors"]), "/".join(x["truth"]))
              for x in P["dropped_candidates"]) or "нет"),
          "STRONG на парах closed NONE (не удаляются): %d%s." % (len(P["strong_on_closed_none"]), "".join(
              "; %s (%s; %s)" % (" ~ ".join(x["pair"]), x["group"], "/".join(x["truth"]))
              for x in P["strong_on_closed_none"])), ""]
    for u in P["unmasked"]:
        L.append("- %s после ревью опасен: держал только %s" % (u["asset"], "; ".join(
            " ~ ".join(x["pair"]) for x in u["masked_by"])))
    L += ["", "## KITSUNE:15 (без толкования)", "", "Правило: %s." % K["rule"], "",
          "### Истинные пары (эталон holdout V4)", "",
          "| пара | эталон | в кандидатах AR2 | границы | силуэт | fmax | остаток | сдвиг | AR1 | AR2 | почему AR2 нет |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in K["true_pairs"]:
        s = x.get("scores")
        if s is None:
            L.append("| %s | %s | %s | нет картинки | | | | | | | |" % (" ~ ".join(x["pair"]), "/".join(x["truth_v4"]),
                                                                  "да" if x["in_ar2_candidates"] else "нет"))
            continue
        L.append("| %s | %s | %s | %.3f | %.3f | %.3f | %.3f | %s | %s | %s | %s |" % (
            " ~ ".join(x["pair"]), "/".join(x["truth_v4"]), "да" if x["in_ar2_candidates"] else "нет", x["border"],
            s["silhouette"], s["fmax"], s["residual"], s["shift"], "прошёл" if x["ar1_passes"] else "нет",
            "прошёл" if x["ar2_passes"] and x["ar2_edge"] else ("очки проходят, довода нет" if x["ar2_passes"]
                                                               else "нет"),
            "; ".join(x["ar2_why_not"]) or "-"))
    L += ["", "Доводы на истинных парах:", ""]
    for x in K["true_pairs"]:
        L += ["- " + cl_line(c) for c in x["claims"]] or []
        if not x["claims"]:
            L.append("- %s: доводов нет" % " ~ ".join(x["pair"]))
    L += ["", "### Все доводы на кадре", ""] + ["- " + cl_line(c) for c in K["held_by"]]
    L += ["", "### Решение маршрута", "",
          "- до ревью: " + dec_line(K["decision_pre_review"]),
          "- после удаления кандидатов на парах closed NONE: " + dec_line(K["decision_post_review"]),
          "- только доводы на парах, закрытых RELATED независимым эталоном (убраны: %s): %s" % (
              "; ".join(" ~ ".join(x) for x in K["confirmed_only_removed"]) or "ничего",
              dec_line(K["decision_confirmed_only"])), "",
          "KITSUNE:15 исправлен: **%s**." % ("да" if K["fixed"] else "нет"), "",
          "## ALIGNED_RECOLOR_V2 на 80 кадрах", ""]
    a = res["ar2"]
    L.append("- " + ", ".join("%s %s" % kv for kv in sorted(a.items())))
    L += ["- снято опасных против V5_PREP: %s" % (", ".join(res["ar2_cleared_dangerous_vs_v5_prep"]) or "ничего"), "",
          "| пара пула | границы | полоса | эталон | закрыто | состояние подтипа | существование | тип |",
          "|---|---|---|---|---|---|---|---|"]
    for x in sorted(res["ar2_rows"], key=lambda r: r["pair"]):
        L.append("| %s | %.3f | %s | %s | %s | %s | %s | %s |" % (" ~ ".join(x["pair"]), x["border"], x["band"],
                                                              x["truth"] or "нет", "/".join(x["closed"]) or "-",
                                                              x["state"], x["existence"], x["type_level"]))
    L += ["", "Вне пула (%d):" % len(res["ar2_outside_pool"]), ""]
    for x in res["ar2_outside_pool"]:
        L.append("- %s: границы %.3f; закрыто RELATED: %s; закрыто NONE: %s" % (
            " ~ ".join(x["pair"]), x["border"], ", ".join(x["closed_related_by"]) or "нет",
            ", ".join(x["closed_none_by"]) or "нет"))
    L += ["", "VERIFIED ставит только человек."]
    with open(p("report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["freeze", "discover", "report"])
    a = ap.parse_args()
    {"freeze": do_freeze, "discover": do_discover, "report": do_report}[a.cmd]()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
