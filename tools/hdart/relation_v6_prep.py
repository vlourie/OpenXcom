#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RELATION_DISCOVERY_V6_PREP - диагностика ASSEMBLY_COMPONENT_GROUP_V1 на тех же 80 кадрах holdout V5
(специалист 02.10, передал Vitali в чате). CPU, чтение. НЕ независимая оценка: кадры и эталон V5 уже видены.

Единственное новое изменение - доводы AG детектора ASMG (assembly_group_v1) поверх замороженных доводов V5
(found_v5.json: AR2 и ASM V1, плюс V3, V4, V8). Не трогаются: AR2, MCD, пороги перекраски, таксономия, жизненный
цикл ревью, маршрут B, ASM V1, весь замороженный код и артефакты V5 (читаются, хэши сверяются). Замороженные ворота
V5 не переписываются: вердикт V5 остаётся FAIL.

Ворота V6_PREP (специалист 02.10): PRE_REVIEW_DANGEROUS = 0, POST_REVIEW_DANGEROUS = 0,
relation_existence_precision >= 0.95, derived/recolor >= 0.70, state >= 0.70, composite_frame_recall >= 0.90,
composite_pair_recall >= 0.70, automatic_action_precision >= 0.95, existing ASM candidate precision >= 0.95,
existing ASM STRONG precision >= 0.95. Составной считается и по замороженному правилу (довод любого уровня), и только
STRONG (R-181).

    py -3.13 tools/hdart/relation_v6_prep.py spec       параметры, ворота, хэши кода и входов -> spec.json (до пересчёта)
    py -3.13 tools/hdart/relation_v6_prep.py discover   доводы AG на 80 кадрах -> found_group.json (замок)
    py -3.13 tools/hdart/relation_v6_prep.py report     -> report.json, report.md
    py -3.13 tools/hdart/relation_v6_prep.py check      целость spec, кода и замороженных входов
VERIFIED ставит только человек.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import assembly_discovery_v1 as asm               # noqa: E402
import assembly_group_v1 as ag                    # noqa: E402
import identity_routing as ir                     # noqa: E402
import post_review_safety as prs                  # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_holdout_v4 as hv                  # noqa: E402
import relation_holdout_v5 as h5                  # noqa: E402
import v5_ar2_recount as rc                       # noqa: E402

# Порядок детекторов в замороженном V5AR2Claims.finalize читается из глобального rc.DETECTOR_ORDER при вызове.
# Новый ключ только добавляется (после AR2 = 8); значения прежних ключей те же - поведение для замороженных доводов
# не меняется (контроль в report: без доводов AG ворота равны замороженному отчёту V5). Файл v5_ar2_recount не правится.
rc.DETECTOR_ORDER = dict(rc.DETECTOR_ORDER, **{ag.DETECTOR: 9})

ENC = ir.ENC
PROFILE = "RELATION_DISCOVERY_V6_PREP"
OUT = os.path.join(ir.PROBES, "relation-v6-prep")
V5 = h5.OUT
SELF = "tools/hdart/relation_v6_prep.py"
CODE = ["tools/hdart/assembly_group_v1.py", "tools/test_assembly_group_v1.py", SELF]
EDGE_STRONG = h5.EDGE_STRONG
GATES = (("PRE_REVIEW_DANGEROUS", "count", 0), ("POST_REVIEW_DANGEROUS", "count", 0),
         ("relation_existence_precision", "rate", 0.95), ("derived_recolor_discovery", "rate", 0.70),
         ("state_discovery", "rate", 0.70), ("composite_frame_recall", "rate", 0.90),
         ("composite_pair_recall", "rate", 0.70), ("automatic_action_precision", "rate", 0.95),
         ("ASSEMBLY_candidate_existence_precision", "rate", 0.95),
         ("ASSEMBLY_STRONG_composite_precision", "rate", 0.95))
GATE_DEFS = {
    "composite_frame_recall": "кадры holdout, у которых есть пара с истиной COMPOSITE: доля, где хоть одна такая пара "
                              "закрыта утверждением группы composite (relation_holdout_v4.diagnostics item_recall)",
    "composite_pair_recall": "пары пула с истиной COMPOSITE: доля с утверждением группы composite любого уровня "
                             "(true_composite_recall замороженного V5); рядом - только STRONG (R-181)",
    "ASSEMBLY_*": "только существующий ASM V1 (детектор ASM), как в отчёте V5; доводы AG считаются отдельно",
    "остальные": "как в relation_holdout_v5.do_report"}
DIAG_DEFS = {
    "groups_formed": "связные части графа доводов AG (assembly_group_v1.groups)",
    "frames_covered": "кадров в группах всего / из них кадров holdout",
    "true_composite_pairs_added": "пары пула с истиной COMPOSITE, где без AG утверждения composite не было, а с AG есть",
    "false_composite_pairs_added": "пары пула с доводом AG и истиной NONE",
    "wrong_type": "пары пула с доводом AG, истина RELATED и закрытые подтипы без COMPOSITE",
    "open": "пары пула с доводом AG, где истина OPEN или подтип не закрыт; вне пула - отдельно",
    "helped_dangerous": "кадры опасные без AG и не опасные с AG; для каждого - пары AG на нём с истиной",
    "hurt": "кадры, ставшие опасными с AG (до и после ревью); утверждения с AG в состоянии wrong"}
SENSITIVITY = (("GRP_CORE=0.75 (порог ядра как у ASM V1)", {"GRP_CORE": 0.75}),
               ("без условия той же сборки (GRP_SHARED=0)", {"GRP_SHARED": 0}),
               ("без условия одного набора", {"SAME_SET": False}))
DEV_TRUTH = (("holdout V4", h5.DEV_SOURCES["v4_truth"]),
             ("V5 component validation", h5.DEV_SOURCES["component_validation_truth"]),
             ("AR boundary validation", h5.DEV_SOURCES["ar_boundary_truth"]),
             ("holdout V5 (сам диагностический пул)", os.path.join(V5, "truth.json")))
PARAM_CHOICE = (
    "по закрытым эталонам разработки (holdout V4, V5_COMPONENT_VALIDATION_V1, AR boundary validation), разведка "
    "блокнота сессии v6_explore4.py / v6_rules4.py 02.10: среди правил с 0 парами NONE на них больше всего "
    "настоящих составных - ядро 0.5, общий третий кадр >= 1, один набор (COMP 124, NONE 0, другие связи 7); "
    "ядро 0.75 - COMP 106; без общего третьего кадра - NONE 1-9. Разбивка по V5 видена до выбора (пул V5 - тот же "
    "диагностический), поэтому V6_PREP - не независимая оценка")
FROZEN = {"v5_freeze": os.path.join(V5, "FREEZE.json"), "v5_holdout": os.path.join(V5, "holdout.json"),
          "v5_relations_lock": os.path.join(V5, "relations.lock.json"),
          "v5_reference_lock": os.path.join(V5, "reference.lock.json"), "v5_truth": os.path.join(V5, "truth.json"),
          "v5_answers": os.path.join(V5, "answers_vitali.tsv"), "v5_report": os.path.join(V5, "report.json"),
          "v5_key": os.path.join(V5, "key.json")}


def p(out, *name):
    return os.path.join(out, *name)


def file_sha(path):
    return v2.file_sha(path)


# ---------------------------------------------------------------- spec

def spec_body():
    return {"profile": PROFILE, "params": ag.PARAMS, "detector": ag.DETECTOR, "rule": ag.RULE, "level": ag.LEVEL,
            "gates": [list(g) for g in GATES], "gate_defs": GATE_DEFS, "diag_defs": DIAG_DEFS,
            "sensitivity": [[n, o] for n, o in SENSITIVITY], "param_choice": PARAM_CHOICE,
            "not_touched": ["AR2", "MCD", "пороги перекраски", "таксономия", "жизненный цикл ревью", "маршрут B",
                            "ASM V1", "замороженный код V2-V8 и артефакты V5"],
            "detector_order": "rc.DETECTOR_ORDER дополняется ключом ASMG=9 во время пересчёта; файл не правится",
            "note": "диагностика на тех же 80 кадрах V5, не независимая оценка; вердикт V5 FAIL не меняется"}


def do_spec(out=OUT):
    path = p(out, "spec.json")
    if os.path.exists(path):
        raise SystemExit("spec уже записан: %s" % path)
    missing = [c for c in CODE + list(FROZEN.values()) if not os.path.exists(c)]
    if missing:
        raise SystemExit("нет файлов: %s" % missing)
    d5 = h5.load_freeze(V5)
    ch = h5.code_changed(d5)
    if ch:
        raise SystemExit("замороженный код V5 изменён: %s" % ch)
    body = spec_body()
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                code_sha256={c: file_sha(c) for c in CODE},
                frozen_sha256={k: file_sha(v) for k, v in FROZEN.items()},
                frozen_paths={k: v.replace(os.sep, "/") for k, v in FROZEN.items()},
                v5_freeze_sha256=d5["sha256"])
    ir.dump_json(path, data)
    print("spec записан: %s (%s)" % (path, data["sha256"][:12]))


def load_spec(out=OUT):
    d = ir.load_json(p(out, "spec.json"))
    if ir.sha({k: d[k] for k in spec_body()}) != d["sha256"]:
        raise SystemExit("spec.json изменён после записи")
    bad = [c for c, s in d["code_sha256"].items() if file_sha(c) != s]
    if bad:
        raise SystemExit("код изменён после spec: %s" % bad)
    bad = [k for k, s in d["frozen_sha256"].items() if file_sha(d["frozen_paths"][k]) != s]
    if bad:
        raise SystemExit("замороженные входы V5 изменены: %s" % bad)
    if spec_body() != {k: d[k] for k in spec_body()}:
        raise SystemExit("параметры модуля разошлись со spec.json")
    return d


# ---------------------------------------------------------------- discover

def ctx_places():
    return v3.Ctx(index=v2.load_index(v2.OUT))


def run_ag(ctx, keys, over=None):
    """Доводы AG по ключам; over {параметр: значение} - временно (чувствительность), потом возвращаются."""
    old = {k: getattr(ag, k) for k in (over or {})}
    try:
        for k, v in (over or {}).items():
            setattr(ag, k, v)
        G = ag.Groups(ctx)
        edges = []
        for a in keys:
            edges += ag.discover(G, a)
        return edges
    finally:
        for k, v in old.items():
            setattr(ag, k, v)


def do_discover(out=OUT):
    lock = p(out, "found_group.lock.json")
    if os.path.exists(lock):
        raise SystemExit("доводы AG уже посчитаны и заморожены: %s" % lock)
    d = load_spec(out)
    keys = h5.keys_of(h5.load_holdout(V5))
    t0 = time.time()
    ctx = ctx_places()
    edges = run_ag(ctx, keys)
    sens = {}
    for name, over in SENSITIVITY:
        sens[name] = run_ag(ctx, keys, over)
    path = p(out, "found_group.json")
    ir.dump_json(path, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": d["sha256"], "keys": keys,
                        "edges": edges, "sensitivity": sens, "groups": ag.groups(edges),
                        "note": "доводы AG (ASMG, CANDIDATE); не маршрут; VERIFIED ставит человек"})
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": d["sha256"],
                        "path": path.replace(os.sep, "/"), "sha256": file_sha(path)})
    print("доводы AG: %d на %d кадрах, групп %d, %.0f с" % (len(edges), len(keys), len(ag.groups(edges)),
                                                           time.time() - t0))


def load_group(out=OUT):
    lk = ir.load_json(p(out, "found_group.lock.json"))
    if file_sha(lk["path"]) != lk["sha256"]:
        raise SystemExit("found_group.json изменён после заморозки")
    return ir.load_json(lk["path"])


# ---------------------------------------------------------------- report

def comp_pairs(pc):
    return [(a, b, cs) for a, b, t, cs in pc if t and t[0] == "RELATED" and "COMPOSITE" in t[1]]


def strong_recall(pc, items):
    """Составной только по STRONG (R-181): пары и кадры."""
    comp = comp_pairs(pc)
    hit = [any(c["group"] == "composite" and c["existence"] == rc.STRONG for c in cs) for _a, _b, cs in comp]
    by = {}
    for (a, b, _cs), h in zip(comp, hit):
        for x in (a, b):
            if x in items:
                by[x] = by.get(x, False) or h
    return {"pair": v2.rate(sum(hit), len(comp)), "pairs": len(comp), "pair_hit": sum(hit),
            "frame": v2.rate(sum(by.values()), len(by)), "frames": len(by), "frame_hit": sum(by.values())}


def ag_support(cs):
    return [e for c in cs for e in c["support"] if e["detector"] == ag.DETECTOR]


def group_diag(base, new, pp_base, pp_new, ag_edges, keys, pool, T):
    st = hv.tv_state
    bpc = {tuple(sorted((a, b))): cs for a, b, _t, cs in base["pc"]}
    d = Counter()
    added, false_none, wrong_type, opened = [], [], [], []
    for a, b, t, cs in new["pc"]:
        if not ag_support(cs):
            continue
        d["pool_pairs_with_ag"] += 1
        key = "%s ~ %s" % (a, b)
        had = any(c["group"] == "composite" for c in bpc.get(tuple(sorted((a, b))), []))
        if not t or t[0] == "OPEN":
            opened.append(key)
        elif t[0] == "NONE":
            false_none.append(key)
        elif "COMPOSITE" in t[1]:
            d["true_composite_with_ag"] += 1
            if not had:
                added.append(key)
        elif t[1]:
            wrong_type.append("%s [%s]" % (key, "/".join(sorted(t[1]))))
        else:
            opened.append(key + " [RELATED, подтип открыт]")
    pairs_ag = {tx_pk(e["source"], e["target"]) for e in ag_edges}
    outside = sorted(pk for pk in pairs_ag if pk not in pool)
    groups = ag.groups(ag_edges)
    covered = {k for g in groups for k in g}
    ku = {k.upper() for k in keys}
    helped = sorted(set(base["dangerous"]) - set(new["dangerous"]))
    helped_d = []
    for f in helped:
        prs_ = [("%s ~ %s" % (a, b), "/".join(sorted(t[1])) if t and t[0] == "RELATED" else (t[0] if t else "OPEN"))
                for a, b, t, cs in new["pc"] if f in (a, b) and ag_support(cs)]
        helped_d.append({"frame": f, "ag_pairs_with_truth": prs_})
    wrong_claims = [("%s ~ %s" % (a, b)) for a, b, t, cs in new["pc"] for c in cs
                    if any(e["detector"] == ag.DETECTOR for e in c["support"]) and st(c, t) == "wrong"]
    return {"edges": len(ag_edges), "groups_formed": len(groups),
            "frames_covered": len(covered), "holdout_frames_covered": len(covered & ku),
            "group_sizes": dict(Counter(len(g) for g in groups)),
            "pool_pairs_with_ag": d["pool_pairs_with_ag"], "true_composite_with_ag": d["true_composite_with_ag"],
            "true_composite_pairs_added": len(added), "true_added": added,
            "false_composite_pairs_added": len(false_none), "false_none": false_none,
            "wrong_type": wrong_type, "open": opened, "outside_pool_pairs": len(outside),
            "helped_dangerous": helped_d,
            "hurt": {"dangerous_pre_new": sorted(set(new["dangerous"]) - set(base["dangerous"])),
                     "dangerous_post_new": sorted(set(pp_new["post_dangerous"]) - set(pp_base["post_dangerous"])),
                     "unmasked_after_review": [u["asset"] for u in pp_new["unmasked"]],
                     "wrong_claims_with_ag": wrong_claims}}


def tx_pk(a, b):
    return h5.pk(a, b)


def calibration(ctx, over=None):
    """AG по парам закрытых эталонов (оба слота каждого кадра): сколько срабатывает на COMP / NONE / OTHER."""
    old = {k: getattr(ag, k) for k in (over or {})}
    try:
        for k, v in (over or {}).items():
            setattr(ag, k, v)
        G = ag.Groups(ctx)
        res = {}
        for name, path in DEV_TRUTH:
            c = Counter()
            for r in ir.load_json(path)["pairs"]:
                if r["existence"] == "OPEN":
                    continue
                lab = ("COMPOSITE" if r["existence"] == "RELATED" and "COMPOSITE" in r["closed"] else
                       ("NONE" if r["existence"] == "NONE" else "OTHER_RELATED"))
                c[lab + "_n"] += 1
                hit = any(ag.judge(G, r["a"], sa, r["b"], sb) for sa in G.slots(r["a"]) for sb in G.slots(r["b"]))
                c[lab + "_fired"] += hit
            res[name] = dict(c)
        return res
    finally:
        for k, v in old.items():
            setattr(ag, k, v)


def do_report(out=OUT):
    import routing_model_v8 as v8
    sp = load_spec(out)
    fg = load_group(out)
    d, h = h5.load_freeze(V5), h5.load_holdout(V5)
    if h5.code_changed(d):
        raise SystemExit("замороженный код V5 изменён: %s" % h5.code_changed(d))
    T, trow, _lk = h5.load_truth(V5)
    ans = {r["asset_id"]: r for r in ir.read_tsv(p(V5, "answers_vitali.tsv"))}
    keys = h5.keys_of(h)
    found3, found4, found5 = h5.load_found(V5)
    base_r = hv.routing_base(V5, d, h)
    rows = hv.routing_rows(base_r, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    items = ir.load_json(p(V5, "key.json"))["items"]
    pool = {h5.pk(it["a"], it["b"]) for it in items}
    args = (T, items, keys, h, base_r["fsets"])
    none_pairs = prs.closed_none(*h5.closed_none_sources(V5))
    c3 = v3.Ctx(index=v2.load_index(v2.OUT))
    tname = {0: "floor", 1: "wall", 2: "wall", 3: "object"}
    ku = {k.upper() for k in keys}

    def tinfo(k):
        i = c3.info(k)
        return tname.get(i.get("tile_type"), "none") if i.get("rec") else "none"

    def run(edges):
        C = h5.system_claims(rows, found3, found4, edges)
        ev = h5.evaluate(rows, C, *args)
        pp, post = prs.pre_post(lambda c: h5.evaluate(rows, c, *args), C, none_pairs)
        G = {g["gate"]: g for g in ev["gates"]}
        cand, strong = h5.asm_pairs(ev["pc"], trow)
        vc, nc, _a, _b = h5.rate_closed(cand, "exist", "yes")
        vs, ns, _c, _d = h5.rate_closed(strong, "composite", "yes")
        dg = hv.diagnostics(ev["pc"], ku, tinfo)["composite"]
        vals = {"PRE_REVIEW_DANGEROUS": (pp["PRE_REVIEW_DANGEROUS"], len(keys)),
                "POST_REVIEW_DANGEROUS": (pp["POST_REVIEW_DANGEROUS"], len(keys)),
                "relation_existence_precision": (G["relation_existence_precision"]["value"],
                                                 G["relation_existence_precision"]["n"]),
                "derived_recolor_discovery": (G["derived_recolor_discovery"]["value"],
                                              G["derived_recolor_discovery"]["n"]),
                "state_discovery": (G["state_discovery"]["value"], G["state_discovery"]["n"]),
                "composite_frame_recall": (dg["item_recall"], dg["items"]),
                "composite_pair_recall": (G["true_composite_recall"]["value"], G["true_composite_recall"]["n"]),
                "automatic_action_precision": (G["automatic_action_precision"]["value"],
                                               G["automatic_action_precision"]["n"]),
                "ASSEMBLY_candidate_existence_precision": (vc, nc),
                "ASSEMBLY_STRONG_composite_precision": (vs, ns)}
        gates, verdict = h5.acceptance(vals, GATES)
        return {"C": C, "ev": ev, "pp": pp, "post": post, "gates": gates, "verdict": verdict, "dg": dg,
                "strong_only": strong_recall(ev["pc"], ku), "handoff": G["handoff_unassigned"]["value"],
                "pair_recall_diag": dg["pair_recall"]}

    t0 = time.time()
    e5 = found5["edges"]
    base = run(e5)
    # контроль: без доводов AG ворота равны замороженному отчёту V5
    rep5 = ir.load_json(p(V5, "report.json"))
    g5 = {g["gate"]: g["value"] for g in rep5["gates"]}
    gb = {g["gate"]: g["value"] for g in base["gates"]}
    same = {"PRE_REVIEW_DANGEROUS": gb["PRE_REVIEW_DANGEROUS"] == g5["PRE_REVIEW_DANGEROUS"],
            "POST_REVIEW_DANGEROUS": gb["POST_REVIEW_DANGEROUS"] == g5["POST_REVIEW_DANGEROUS"],
            "composite_pair_recall": gb["composite_pair_recall"] == g5["composite_discovery_recall"]}
    for g in ("relation_existence_precision", "derived_recolor_discovery", "state_discovery",
              "automatic_action_precision", "ASSEMBLY_candidate_existence_precision",
              "ASSEMBLY_STRONG_composite_precision"):
        same[g] = gb[g] == g5[g]
    if not all(same.values()):
        raise SystemExit("контроль не прошёл: без AG ворота не равны замороженному V5: %s" % same)
    agE = fg["edges"]
    new = run(e5 + agE)
    gd = group_diag(base["ev"], new["ev"], base["pp"], new["pp"], agE, keys, pool, T)
    sens = []
    for name, _over in SENSITIVITY:
        es = fg["sensitivity"][name]
        r = run(e5 + es)
        g = group_diag(base["ev"], r["ev"], base["pp"], r["pp"], es, keys, pool, T)
        gg = {x["gate"]: x for x in r["gates"]}
        sens.append({"variant": name, "edges": len(es), "verdict": r["verdict"],
                     "composite_pair_recall": gg["composite_pair_recall"]["value"],
                     "composite_frame_recall": gg["composite_frame_recall"]["value"],
                     "PRE": gg["PRE_REVIEW_DANGEROUS"]["value"], "POST": gg["POST_REVIEW_DANGEROUS"]["value"],
                     "true_added": g["true_composite_pairs_added"], "false_none": g["false_composite_pairs_added"],
                     "wrong_type": len(g["wrong_type"])})
    cal = calibration(c3)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE, "spec_sha256": sp["sha256"],
           "v5_freeze_sha256": d["sha256"], "n_frames": len(keys), "params": ag.PARAMS,
           "verdict": new["verdict"], "gates": new["gates"], "gates_without_ag": base["gates"],
           "control_without_ag_equals_frozen_v5": same,
           "composite": {"without_ag": {"frame": base["dg"]["item_recall"], "pair": base["pair_recall_diag"],
                                        "strong_only": base["strong_only"]},
                         "with_ag": {"frame": new["dg"]["item_recall"], "pair": new["pair_recall_diag"],
                                     "strong_only": new["strong_only"], "closed_by": new["dg"]["closed_by"]}},
           "dangerous": {"pre_without_ag": base["pp"]["pre_dangerous"], "post_without_ag": base["pp"]["post_dangerous"],
                         "pre_with_ag": new["pp"]["pre_dangerous"], "post_with_ag": new["pp"]["post_dangerous"]},
           "post_review_with_ag": {"removed_closed_none": len(new["pp"]["dropped_candidates"]),
                                   "removed_ag": [x for x in new["pp"]["dropped_candidates"]
                                                  if any(s.startswith(ag.DETECTOR) for s in x["detectors"])],
                                   "unmasked": new["pp"]["unmasked"],
                                   "invariant_holds": not new["pp"]["unmasked"] and
                                   new["pp"]["POST_REVIEW_DANGEROUS"] == 0},
           "group_detector": gd, "sensitivity": sens, "calibration": cal,
           "handoff_unassigned": new["handoff"], "seconds": round(time.time() - t0)}
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    print("V6_PREP: %s; PRE %s, POST %s; составной кадры %s, пары %s; отчёт %s" % (
        res["verdict"], res["dangerous"]["pre_with_ag"], res["dangerous"]["post_with_ag"],
        hv.f3(new["dg"]["item_recall"]), hv.f3(new["pair_recall_diag"]), p(out, "report.md")))
    return res


def write_md(out, res):
    f3 = hv.f3
    gb = {g["gate"]: g for g in res["gates_without_ag"]}
    L = ["# RELATION_DISCOVERY_V6_PREP — ASSEMBLY_COMPONENT_GROUP_V1 на %d кадрах holdout V5" % res["n_frames"], "",
         "Диагностика на уже виденных кадрах, **не независимая оценка**. Вердикт V5 (FAIL) не меняется.", "",
         "Итог ворот V6_PREP: **%s**. spec %s, снимок V5 %s." % (res["verdict"], res["spec_sha256"][:12],
                                                               res["v5_freeze_sha256"][:12]), "",
         "Контроль: без доводов AG ворота равны замороженному отчёту V5 — %s." % (
             "да" if all(res["control_without_ag_equals_frozen_v5"].values()) else "**нет**"), "",
         "## Ворота", "", "| ворота | без AG | с AG | n | нужно | итог |", "|---|---|---|---|---|---|"]
    for g in res["gates"]:
        L.append("| %s | %s | %s | %s | %s | %s |" % (g["gate"], f3(gb[g["gate"]]["value"]), f3(g["value"]), g["n"],
                                                      g["need"], g["status"]))
    c = res["composite"]
    L += ["", "## Составной", "",
          "- любой уровень (замороженное правило): кадры %s → %s, пары %s → %s" % (
              f3(c["without_ag"]["frame"]), f3(c["with_ag"]["frame"]), f3(c["without_ag"]["pair"]),
              f3(c["with_ag"]["pair"])),
          "- только STRONG (R-181): кадры %s → %s, пары %s → %s (доводы AG - всегда CANDIDATE)" % (
              f3(c["without_ag"]["strong_only"]["frame"]), f3(c["with_ag"]["strong_only"]["frame"]),
              f3(c["without_ag"]["strong_only"]["pair"]), f3(c["with_ag"]["strong_only"]["pair"])),
          "- пропущено и с AG: %s" % ("; ".join(x for x in c["with_ag"]["closed_by"] if x.endswith("не найдено"))
                                      or "нет")]
    dz = res["dangerous"]
    L += ["", "## Опасные", "",
          "- до ревью: %s → %s" % (dz["pre_without_ag"] or "нет", dz["pre_with_ag"] or "нет"),
          "- после ревью: %s → %s" % (dz["post_without_ag"] or "нет", dz["post_with_ag"] or "нет")]
    pr = res["post_review_with_ag"]
    L += ["- ревью с AG: удалено кандидатов на closed NONE %d, из них с AG %d; стали опасными %s; инвариант %s" % (
        pr["removed_closed_none"], len(pr["removed_ag"]), [u["asset"] for u in pr["unmasked"]] or "нет",
        "держится" if pr["invariant_holds"] else "**нет**")]
    g = res["group_detector"]
    L += ["", "## Детектор группы (ASMG, AG, CANDIDATE)", "",
          "- доводов %d; групп %d (размеры %s); кадров в группах %d, из них кадров holdout %d" % (
              g["edges"], g["groups_formed"], g["group_sizes"], g["frames_covered"], g["holdout_frames_covered"]),
          "- пар пула с AG %d; истинных составных с AG %d; **добавлено истинных %d**; **ложных (NONE) %d**; "
          "другой подтип %d; открытых %d; вне пула %d" % (
              g["pool_pairs_with_ag"], g["true_composite_with_ag"], g["true_composite_pairs_added"],
              g["false_composite_pairs_added"], len(g["wrong_type"]), len(g["open"]), g["outside_pool_pairs"]),
          "- добавлено: %s" % ("; ".join(g["true_added"]) or "нет"),
          "- ложные NONE: %s" % ("; ".join(g["false_none"]) or "нет"),
          "- другой подтип: %s" % ("; ".join(g["wrong_type"]) or "нет"),
          "- открытые: %s" % ("; ".join(g["open"]) or "нет"),
          "- помог опасным: %s" % (json.dumps(g["helped_dangerous"], ensure_ascii=False) or "нет"),
          "- вред: %s" % json.dumps(g["hurt"], ensure_ascii=False)]
    L += ["", "## Чувствительность (диагностика, не ворота)", "",
          "| вариант | доводов | пары | кадры | PRE | POST | добавлено | NONE | другой подтип |",
          "|---|---|---|---|---|---|---|---|---|"]
    for s in res["sensitivity"]:
        L.append("| %s | %d | %s | %s | %s | %s | %d | %d | %d |" % (
            s["variant"], s["edges"], f3(s["composite_pair_recall"]), f3(s["composite_frame_recall"]), s["PRE"],
            s["POST"], s["true_added"], s["false_none"], s["wrong_type"]))
    L += ["", "## Калибровка по закрытым эталонам (AG на парах эталона)", "",
          "| эталон | COMPOSITE | NONE | другая связь |", "|---|---|---|---|"]
    for name, cc in res["calibration"].items():
        L.append("| %s | %d из %d | %d из %d | %d из %d |" % (
            name, cc.get("COMPOSITE_fired", 0), cc.get("COMPOSITE_n", 0), cc.get("NONE_fired", 0),
            cc.get("NONE_n", 0), cc.get("OTHER_RELATED_fired", 0), cc.get("OTHER_RELATED_n", 0)))
    L += ["", "handoff_unassigned: %s. VERIFIED ставит только человек." % res["handoff_unassigned"]]
    with open(p(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")


def do_check(out=OUT):
    d = load_spec(out)
    print("spec цел: %s; код и замороженные входы V5 те же" % d["sha256"][:12])
    if os.path.exists(p(out, "found_group.lock.json")):
        load_group(out)
        print("доводы AG целы")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["spec", "discover", "report", "check"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    {"spec": do_spec, "discover": do_discover, "report": do_report, "check": do_check}[a.cmd](a.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
