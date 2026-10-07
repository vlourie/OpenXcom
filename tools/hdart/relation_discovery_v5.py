#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RELATION_DISCOVERY_V5_PREP - ALIGNED_RECOLOR_V1 и ASSEMBLY_DISCOVERY_V1 поверх замороженного V4 (специалист 02.10,
передал Vitali в чате). CPU, чтение. Диагностика на тех же 80 кадрах holdout V4 - не независимая оценка.

Всё остальное - как в замороженном V4: доводы V8, V3 (convert_v3), V4, таксономия, TYPE_OPEN, MCD, политика
зеркала, маршрут B, ворота и их подсчёт (relation_holdout_v4: routing_rows, danger, creative_of, gate_rows,
diagnostics). Новые доводы только добавляются: AR1 (группа derived, TYPE_OPEN) и ASM (COMPOSITE_PART).
Замороженные модули, эталон и отчёт holdout V4 не меняются.

Порядок, записанный до пересчёта:
    py -3.13 tools/hdart/relation_discovery_v5.py dev       проверка на старой истине v2 (не на 80) -> dev.md
    py -3.13 tools/hdart/relation_discovery_v5.py freeze    параметры и хэши кода -> FREEZE.json; после - не меняются
    py -3.13 tools/hdart/relation_discovery_v5.py discover  новые доводы на 80 кадрах V4 -> found5.json (замок)
    py -3.13 tools/hdart/relation_discovery_v5.py report    ворота и диагностика -> report.json, report.md
VERIFIED ставит только человек.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aligned_recolor_v1 as ar                   # noqa: E402
import assembly_discovery_v1 as asm               # noqa: E402
import identity_routing as ir                     # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_holdout_v4 as hv                  # noqa: E402
import relation_taxonomy as tx                    # noqa: E402

ENC = ir.ENC
OUT = os.path.join(ir.PROBES, "relation-discovery-v5-prep")
HOLD = hv.OUT
PROFILE = "RELATION_DISCOVERY_V5_PREP"
CODE = ["tools/hdart/aligned_recolor_v1.py", "tools/hdart/assembly_discovery_v1.py",
        "tools/hdart/relation_discovery_v5.py", "tools/test_aligned_recolor_v1.py",
        "tools/test_assembly_discovery_v1.py", "tools/test_relation_discovery_v5.py"]
STRONG, CAND, T_STRONG, T_OPEN, BINDING = v4.STRONG, v4.CAND, v4.T_STRONG, v4.T_OPEN, v4.BINDING
GROUP5 = dict(v4.GROUP, **{ar.TYPE: "derived"})
SYMMETRIC5 = v4.SYMMETRIC + (ar.TYPE,)
DETECTOR_ORDER5 = dict(v4.DETECTOR_ORDER, ASM=7, AR1=8)
TARGETS = {"dangerous_creative_standalone": 0, "relation_existence_precision": 0.95,
           "derived_recolor_discovery": 0.70, "state_discovery": 0.70, "true_composite_recall": 0.70,
           "automatic_action_precision": 0.95, "handoff_unassigned": 0}
TILE = {0: "FLOOR", 1: "WALL", 2: "WALL", 3: "OBJECT"}
DEFS = {
    "gates": "те же, что у замороженного relation_holdout_v4 (gate_rows, v4.metrics, v4.recall, danger), цели "
             "специалиста: dangerous 0, existence >= 0.95, derived >= 0.70, state >= 0.70, composite >= 0.70, "
             "auto >= 0.95; handoff 0 - как в V4. Слой приёмки N_MIN 10 (relation_holdout_v4_ref.acceptance)",
    "control": "V5 без новых доводов (found5 пуст) обязан дать те же ворота и метрики, что замороженный отчёт V4",
    "ar1": "доводы с опорой AR1 на парах пула: triggered; true_related - истина RELATED; false_relation - истина "
           "NONE; open - истина OPEN или вне эталона; subtype_correct - claim_state ok; subtype_open - RELATED, "
           "claim_state open; subtype_wrong - RELATED, claim_state wrong; helped - ok и вся опора довода - AR1; "
           "false_action - auto_claim и wrong; helped_dangerous - кадр опасен в V4 и не опасен в V5, и на его "
           "опасной паре есть довод AR1; вне пула - отдельно",
    "asm": "доводы с опорой ASM на парах пула, по модели (OBJECT / WALL / FLOOR из edge.scores.model): triggered, "
           "ok / wrong / open по claim_state, precision = ok / (ok + wrong), helped - ok и у довода нет опоры другого "
           "детектора, hurt - wrong; recall модели - доля закрытых COMPOSITE пар категории с доводом ASM",
    "category": "категория закрытой пары COMPOSITE - тип клетки MCD обоих кадров (0 пол - FLOOR, 1/2 стена - WALL, "
                "3 предмет - OBJECT), если он одинаков у обоих; разный или без записи MCD - OTHER",
    "old_misses": "закрытые COMPOSITE пары без довода группы composite в V4 (37): recovered_by_assembly - в V5 есть "
                  "довод composite с опорой ASM; still_missed - довода composite нет; wrongly_recovered - "
                  "довода composite нет, но V5 добавил на пару довод другой группы",
}


# ---------------------------------------------------------------- доводы V5

class _Base5(v3.Claims):
    """Как v4._Base4, с группами, симметрией и порядком детекторов V5; AR1 - всегда TYPE_OPEN."""
    MR_TYPED = False

    def add(self, e):
        s, t = e["source"].upper(), e["target"].upper()
        if not t or s == t:
            return None
        k = (GROUP5[e["type"]], frozenset((s, t)))
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
            sup = sorted(c["support"], key=lambda e: (e["level"] not in BINDING, e["detector"] in v3.DIAGNOSTIC,
                                                      DETECTOR_ORDER5[e["detector"]], e["type"]))
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
                        if e["level"] in BINDING and e["type"] not in SYMMETRIC5}
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
                if bind and all(e["detector"] == "MR4" for e in bind) and not self.MR_TYPED:
                    why.append("MIRRORED_RECOLOR_CANDIDATE")
                c["type_level"] = T_OPEN if why else T_STRONG
                c["type_open_why"] = why
        return self


class V5Claims(tx.TaxClaims, _Base5):
    """Порядок: TaxClaims (анимация и перекраска сосуществуют) поверх _Base5."""


def claims(rows, found3, found4, found5):
    C = v3.claims_from_v8(rows)
    C.__class__ = V5Claims
    for e in found3["edges"]:
        e2 = v4.convert_v3(e)
        if e2:
            C.add(e2)
    for a, roles in found3["self_roles"].items():
        C.self_roles[a.upper()] += roles
    for e in found4["edges"]:
        C.add(e)
    for e in (found5 or {}).get("edges", []):
        C.add(e)
    return C.finalize()


# ---------------------------------------------------------------- спецификация и заморозка

def spec():
    return {"profile": PROFILE, "decision": "специалист 02.10, передал Vitali в чате (docs/DECISIONS.md 2026-10-02)",
            "aligned_recolor_v1": ar.PARAMS, "assembly_discovery_v1": asm.PARAMS, "targets": TARGETS,
            "defs": DEFS, "n_min": 10, "holdout": "те же 80 кадров и замороженный эталон holdout V4 (truth.json, "
            "answers_vitali.tsv); пересчёт - диагностика, не независимая оценка",
            "unchanged": "V2-V8, relation_taxonomy, relation_truth_v2, routing_holdout_v5/v7/v8, relation_holdout_v4 "
                         "и его эталон, relation_discovery_v2/v3/v4 и их выходы relations.lock.json; пороги V4 "
                         "не снижены; исключений по наборам нет"}


def p(*a):
    return os.path.join(OUT, *a)


def code_sha():
    return {c: hv.file_sha(c) for c in CODE}


def do_freeze():
    if os.path.exists(p("FREEZE.json")):
        raise SystemExit("уже заморожено: %s" % p("FREEZE.json"))
    if os.path.exists(p("found5.json")):
        raise SystemExit("пересчёт уже был - заморозка после него не имеет смысла")
    missing = [c for c in CODE if not os.path.exists(c)]
    if missing:
        raise SystemExit("нет файлов: %s" % ", ".join(missing))
    body = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec": spec(), "code_sha256": code_sha(),
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
    for k, f in (("holdout_relations_lock_sha256", "relations.lock.json"),
                 ("holdout_reference_lock_sha256", "reference.lock.json")):
        if hv.file_sha(os.path.join(HOLD, f)) != fz[k]:
            bad.append(f)
    if bad:
        raise SystemExit("изменено после заморозки: %s" % ", ".join(bad))
    return fz


# ---------------------------------------------------------------- dev: старая истина v2 (не 80 кадров)

def dev_truth():
    d = ir.load_json(os.path.join(HOLD, "inputs", "truth_v2.json"))
    return d["pairs"]


def pair_edges(ctx, si, A, a, b):
    es = ar.pair(ctx, si, a, b) + asm.discover(A, a, only=b) + asm.discover(A, b, only=a)
    return es


def do_dev():
    if os.path.exists(p("found5.json")):
        raise SystemExit("пересчёт на 80 уже был - dev после него не меняет параметры")
    ctx = hv.ctx_v3()
    si, A = v4.SetIndex(ctx), asm.Assembly(ctx)
    rows, t0 = [], time.time()
    pairs = dev_truth()
    for i, r in enumerate(pairs):
        es = pair_edges(ctx, si, A, r["a"], r["b"])
        perm = []
        for e in es:
            if e["detector"] == ar.DETECTOR:
                perm.append(bool(ar.pair(ctx, si, r["a"], r["b"], B=v3.permuted(ctx, r["b"], 7))))
        rows.append({"a": r["a"], "b": r["b"], "existence": r["existence"], "closed": r["closed"],
                     "edges": [{k: e[k] for k in ("detector", "rule", "level", "evidence")} for e in es],
                     "perm_fired": perm})
        if i % 100 == 0:
            print("dev: %d из %d, %.0f с" % (i, len(pairs), time.time() - t0), flush=True)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "pairs": rows, "summary": dev_summary(rows)}
    os.makedirs(OUT, exist_ok=True)
    ir.dump_json(p("dev.json"), res)
    write_dev_md(res)
    print(json.dumps(res["summary"], ensure_ascii=False, indent=1))


def dev_class(r):
    if r["existence"] == "NONE":
        return "NONE"
    if r["existence"] != "RELATED":
        return "OPEN"
    if "COMPOSITE" in r["closed"]:
        return "COMPOSITE"
    if set(r["closed"]) & set(tx.DERIVED_LABELS):
        return "DERIVED"
    return "RELATED_OTHER"


def dev_summary(rows):
    s = defaultdict(Counter)
    for r in rows:
        cl = dev_class(r)
        s[cl]["n"] += 1
        for det in (ar.DETECTOR, asm.DETECTOR):
            es = [e for e in r["edges"] if e["detector"] == det]
            if es:
                s[cl][det] += 1
                if any(e["level"] == STRONG for e in es):
                    s[cl][det + " STRONG"] += 1
        if any(r["perm_fired"]):
            s[cl]["AR1 перемешанный контроль сработал"] += 1
    return {k: dict(v) for k, v in sorted(s.items())}


def write_dev_md(res):
    L = ["# V5_PREP — проверка на старой истине v2 (до заморозки, не на 80 кадрах)", "",
         "Пары истины v2 (inputs/truth_v2.json holdout V4: первый пакет, 60 V8, контроль). На каждой паре AR1 и ASM в "
         "режиме одной пары. Параметры от этого прогона не подбирались: они записаны в коде до него.", "",
         "| класс пары | пар | AR1 | AR1 STRONG | ASM | ASM STRONG | перемешанный контроль AR1 |",
         "|---|---|---|---|---|---|---|"]
    for k, v in res["summary"].items():
        L.append("| %s | %d | %d | %d | %d | %d | %d |" % (k, v.get("n", 0), v.get("AR1", 0), v.get("AR1 STRONG", 0),
                                                         v.get("ASM", 0), v.get("ASM STRONG", 0),
                                                         v.get("AR1 перемешанный контроль сработал", 0)))
    L += ["", "## Срабатывания", ""]
    for r in res["pairs"]:
        for e in r["edges"]:
            L.append("- %s ~ %s [%s %s]: %s %s — %s" % (r["a"], r["b"], r["existence"], "|".join(r["closed"]),
                                                       e["rule"], e["level"], e["evidence"]))
    L += ["", "VERIFIED ставит только человек."]
    with open(p("dev.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")


# ---------------------------------------------------------------- discover на 80 кадрах

def do_discover():
    fz = check_freeze()
    if os.path.exists(p("found5.json")):
        raise SystemExit("новые доводы уже посчитаны: %s" % p("found5.json"))
    h = hv.load_holdout(HOLD)
    keys = hv.keys_of(h)
    ctx = hv.ctx_v3()
    si, A = v4.SetIndex(ctx), asm.Assembly(ctx)
    edges, perm = [], []
    for a in keys:
        t0 = time.time()
        es = ar.discover(ctx, si, a) + asm.discover(A, a)
        for e in es:
            if e["detector"] == ar.DETECTOR:
                fired = bool(ar.pair(ctx, si, e["source"], e["target"],
                                     B=v3.permuted(ctx, e["target"], 7)))
                perm.append({"pair": [e["source"], e["target"]], "fired": fired})
        edges += es
        print(a, dict(Counter("%s %s" % (e["rule"], e["level"]) for e in es)), "%.1f с" % (time.time() - t0),
              flush=True)
    ir.dump_json(p("found5.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE,
                                    "freeze_sha256": hv.file_sha(p("FREEZE.json")), "keys": keys, "edges": edges,
                                    "ar1_permuted_control": perm,
                                    "note": "утверждения детекторов V5_PREP, не маршрут; VERIFIED ставит только человек"})
    ir.dump_json(p("found5.lock.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                         "found5_sha256": hv.file_sha(p("found5.json")),
                                         "freeze_sha256": hv.file_sha(p("FREEZE.json")),
                                         "spec_created": fz["created"]})
    print("доводов %d (%s); замок %s" % (len(edges), dict(Counter(e["rule"] for e in edges)),
                                         hv.file_sha(p("found5.json"))[:12]))


def load_found5():
    lk = ir.load_json(p("found5.lock.json"))
    if hv.file_sha(p("found5.json")) != lk["found5_sha256"]:
        raise SystemExit("found5.json изменён после замка")
    return ir.load_json(p("found5.json"))


# ---------------------------------------------------------------- report

def evaluate(rows, C, T, items, keys, h, fsets):
    """Как замороженный relation_holdout_v4.do_report: пары пула, ворота, опасные."""
    import routing_model_v8 as v8
    pk = tx.pk
    pool = {pk(it["a"], it["b"]) for it in items}
    pc = [(it["a"], it["b"], T.get(pk(it["a"], it["b"])), C.pair(it["a"], it["b"])) for it in items]
    outside = sorted({"%s ~ %s" % tuple(c["pair"]) for a in keys for c in C.of(a) if frozenset(c["pair"]) not in pool})
    m = v4.metrics([(t, cs) for _a, _b, t, cs in pc])
    r = v4.recall([(t, cs) for _a, _b, t, cs in pc])
    tp = defaultdict(list)
    for a, b, t, _cs in pc:
        if t:
            tp[a].append((b, t))
            tp[b].append((a, t))
    score, layer = [], {x["asset_id"]: x for x in h["items"]}
    for row in rows:
        a = row["asset_id"]
        pipe, creative = hv.creative_of(row, C)
        why, opn = hv.danger(a, creative, C, tp.get(a.upper(), []), fsets[a.upper()])
        score.append({"asset_id": a, "layer": layer[a]["layer"], "semantic_kind": row["semantic_kind"],
                      "pipeline": pipe, "creative": creative, "danger": why, "danger_open": opn,
                      "handoff_unassigned": row["pipeline_target"] not in v8.PIPELINES})
    dangerous = [x for x in score if x["danger"]]
    vals = {"dangerous_creative_standalone": (len(dangerous), len(score)),
            "relation_existence_precision": (m["existence_precision"], m["existence_judged"]),
            "derived_recolor_discovery": (r["derived"].get("discovery_rate"), r["derived"]["n"]),
            "state_discovery": (r["state"].get("discovery_rate"), r["state"]["n"]),
            "true_composite_recall": (r["composite"].get("discovery_rate"), r["composite"]["n"]),
            "automatic_action_precision": (m["auto_action_precision"], m["auto_action_judged"]),
            "handoff_unassigned": (sum(x["handoff_unassigned"] for x in score), len(score))}
    gates, verdict = hv.gate_rows(vals)
    return {"pc": pc, "outside": outside, "metrics": m, "recall": r, "score": score, "gates": gates,
            "verdict": verdict, "dangerous": {x["asset_id"]: x["danger"] for x in dangerous}}


def category(ctx, a, b):
    ia, ib = ctx.info(a), ctx.info(b)
    if not (ia.get("rec") and ib.get("rec")):
        return "OTHER"
    ta, tb = TILE.get(ia["tile_type"]), TILE.get(ib["tile_type"])
    return ta if ta == tb and ta else "OTHER"


def has_det(c, det):
    return any(e["detector"] == det for e in c["support"])


def ar1_diag(base, new, outside):
    st = hv.tv_state
    d = Counter()
    for _a, _b, t, cs in new["pc"]:
        for c in cs:
            if not has_det(c, ar.DETECTOR):
                continue
            d["triggered"] += 1
            if not t or t[0] == "OPEN":
                d["open"] += 1
            elif t[0] == "NONE":
                d["false_relation"] += 1
            else:
                d["true_related"] += 1
                s = st(c, t)
                d["subtype_" + {"ok": "correct", "open": "open", "wrong": "wrong"}[s]] += 1
            s = st(c, t)
            if s == "ok" and all(e["detector"] == ar.DETECTOR for e in c["support"]):
                d["helped"] += 1
            if tx.auto_claim(c) and s == "wrong":
                d["false_action"] += 1
    cleared = []
    for a, why in base["dangerous"].items():
        if a in new["dangerous"]:
            continue
        rel = {w.split(" ")[1].rstrip(":") for w in why if len(w.split(" ")) > 1}
        by = [c for _x, _y, _t, cs in new["pc"] for c in cs if a.upper() in c["pair"] and
              set(c["pair"]) & rel and has_det(c, ar.DETECTOR)]
        if by:
            cleared.append(a)
    d["helped_dangerous"] = len(cleared)
    d["outside_pool"] = sum(1 for x in outside if x[1] == ar.DETECTOR)
    return dict(d), cleared


def asm_diag(ctx, base, new, outside):
    st = hv.tv_state
    per = defaultdict(Counter)
    for _a, _b, t, cs in new["pc"]:
        for c in cs:
            es = [e for e in c["support"] if e["detector"] == asm.DETECTOR]
            if not es:
                continue
            model = es[0].get("scores", {}).get("model", "?")
            r = per[model]
            r["triggered"] += 1
            s = st(c, t)
            r[s] += 1
            if s == "ok" and all(e["detector"] == asm.DETECTOR for e in c["support"]):
                r["helped"] += 1
            if s == "wrong":
                r["hurt"] += 1
    res = {}
    for model, r in sorted(per.items()):
        res[model] = dict(r, precision=v2.rate(r["ok"], r["ok"] + r["wrong"]))
    comp = [(a, b, cs) for (a, b, t, cs) in new["pc"] if t and t[0] == "RELATED" and "COMPOSITE" in t[1]]
    cat = defaultdict(Counter)
    for a, b, cs in comp:
        k = category(ctx, a, b)
        cat[k]["total"] += 1
        if any(c["group"] == "composite" for c in cs):
            cat[k]["found"] += 1
        if any(c["group"] == "composite" and has_det(c, asm.DETECTOR) for c in cs):
            cat[k]["found_asm"] += 1
    recall = {k: dict(v, recall=v2.rate(v["found"], v["total"]), asm_recall=v2.rate(v["found_asm"], v["total"]))
              for k, v in sorted(cat.items())}
    prev = {tx.pk(a, b): cs for a, b, t, cs in base["pc"]}
    old = Counter()
    lines = []
    for a, b, cs in comp:
        if any(c["group"] == "composite" for c in prev[tx.pk(a, b)]):
            continue
        new_c = [c for c in cs if c["group"] == "composite"]
        if any(has_det(c, asm.DETECTOR) for c in new_c):
            k = "recovered_by_assembly"
        elif new_c:
            k = "recovered_other"
        elif any(has_det(c, asm.DETECTOR) or has_det(c, ar.DETECTOR) for c in cs):
            k = "wrongly_recovered"
        else:
            k = "still_missed"
        old[k] += 1
        lines.append("%s ~ %s [%s]: %s%s" % (a, b, category(ctx, a, b), k, "".join(
            "; %s %s" % (e["rule"], e["level"]) for c in new_c for e in c["support"] if e["detector"] == "ASM")))
    return {"by_model": res, "recall_by_category": recall, "old_misses": dict(old), "old_miss_lines": lines,
            "outside_pool": sum(1 for x in outside if x[1] == asm.DETECTOR)}


def outside_dets(C, keys, pool):
    out = []
    for a in keys:
        for c in C.of(a):
            if frozenset(c["pair"]) in pool:
                continue
            for e in c["support"]:
                if e["detector"] in (ar.DETECTOR, asm.DETECTOR):
                    out.append(("%s ~ %s" % tuple(c["pair"]), e["detector"], e["rule"], e["level"]))
    return sorted(set(out))


def do_report():
    import relation_holdout_v4_ref as ref
    fz = check_freeze()
    if not ref.do_verify(HOLD):
        raise SystemExit("замок эталона holdout V4 не цел")
    d, h = hv.load_freeze(HOLD), hv.load_holdout(HOLD)
    ch = hv.code_changed(d)
    if ch:
        raise SystemExit("замороженный код V4 изменён: %s" % ", ".join(ch))
    f5 = load_found5()
    T, _lk = hv.load_truth(HOLD)
    ans = {r["asset_id"]: r for r in ir.read_tsv(os.path.join(HOLD, "answers_vitali.tsv"))}
    keys = hv.keys_of(h)
    found3, found4 = hv.load_found(HOLD)
    base_r = hv.routing_base(HOLD, d, h)
    rows = hv.routing_rows(base_r, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    items = ir.load_json(os.path.join(HOLD, "key.json"))["items"]
    pool = {tx.pk(it["a"], it["b"]) for it in items}
    frozen = ir.load_json(os.path.join(HOLD, "report.json"))
    C0 = claims(rows, found3, found4, None)
    base = evaluate(rows, C0, T, items, keys, h, base_r["fsets"])
    C5 = claims(rows, found3, found4, f5)
    new = evaluate(rows, C5, T, items, keys, h, base_r["fsets"])
    control = [g["value"] for g in base["gates"]] == [g["value"] for g in frozen["gates"]] and \
        [g["n"] for g in base["gates"]] == [g["n"] for g in frozen["gates"]]
    gates, verdict = ref.acceptance(new["gates"])
    outside = outside_dets(C5, keys, pool)
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))
    tname = {0: "floor", 1: "wall", 2: "wall", 3: "object"}

    def tinfo(k):
        i = ctx.info(k)
        return tname.get(i.get("tile_type"), "none") if i.get("rec") else "none"
    ar_d, cleared = ar1_diag(base, new, outside)
    perm = f5.get("ar1_permuted_control", [])
    ar_d["permuted_control_fired"] = sum(x["fired"] for x in perm)
    ar_d["permuted_control_n"] = len(perm)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE,
           "freeze_sha256": hv.file_sha(p("FREEZE.json")), "found5_sha256": hv.file_sha(p("found5.json")),
           "spec_created": fz["created"], "control_v5_without_new_equals_frozen_v4": control,
           "verdict_diagnostic": verdict, "gates": gates, "gates_v4": base["gates"], "metrics": new["metrics"],
           "recall": new["recall"], "dangerous": new["dangerous"], "dangerous_v4": base["dangerous"],
           "ar1": ar_d, "ar1_cleared_dangerous": cleared, "asm": asm_diag(ctx, base, new, outside),
           "outside_pool_new": [list(x) for x in outside],
           "outside_pool_all": len(new["outside"]), "outside_pool_v4": len(base["outside"]),
           "diagnostics": hv.diagnostics(new["pc"], {k.upper() for k in keys}, tinfo),
           "new_edges": dict(Counter("%s %s" % (e["rule"], e["level"]) for e in f5["edges"]))}
    ir.dump_json(p("report.json"), res)
    write_md(res)
    print("диагностика V5_PREP: %s (контроль V5 без новых = V4: %s); %s" % (verdict, control, p("report.md")))
    return res


def f3(x):
    return hv.f3(x)


def write_md(res):
    g4 = {g["gate"]: g for g in res["gates_v4"]}
    L = ["# RELATION_DISCOVERY_V5_PREP — диагностика на 80 кадрах holdout V4", "",
         "Итог диагностики: **%s** (слой приёмки N_MIN 10). Это не независимая оценка: кадры и эталон V4 уже "
         "видены, параметры записаны до пересчёта (FREEZE.json %s, %s)." % (
             res["verdict_diagnostic"], res["freeze_sha256"][:12], res["spec_created"]), "",
         "Контрольный опыт — V5 без новых доводов совпадает с замороженным отчётом V4: **%s**." % (
             "да" if res["control_v5_without_new_equals_frozen_v4"] else "НЕТ"), "",
         "Новые доводы на 80 кадрах: %s." % (res["new_edges"] or "нет"), "",
         "## Ворота", "", "| ворота | V4 | V5_PREP | выборка | нужно | итог |", "|---|---|---|---|---|---|"]
    for g in res["gates"]:
        L.append("| %s | %s | %s | %s | %s | %s |" % (g["gate"], f3(g4[g["gate"]]["value"]), f3(g["value"]),
                                                     g["effective_n"], g["need"], g["accepted_status"]))
    a = res["ar1"]
    L += ["", "## ALIGNED_RECOLOR_V1", "",
          "| сработал | верно связан | ложная связь | открыто | подтип верен | подтип открыт | подтип неверен | "
          "помог один | ложное действие | снял опасный | вне пула | перемешанный контроль |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|",
          "| %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d из %d |" % (
              a.get("triggered", 0), a.get("true_related", 0), a.get("false_relation", 0), a.get("open", 0),
              a.get("subtype_correct", 0), a.get("subtype_open", 0), a.get("subtype_wrong", 0), a.get("helped", 0),
              a.get("false_action", 0), a.get("helped_dangerous", 0), a.get("outside_pool", 0),
              a.get("permuted_control_fired", 0), a.get("permuted_control_n", 0)),
          "", "- опасные в V4: %s" % (res["dangerous_v4"] or "нет"),
          "- опасные в V5_PREP: %s" % (res["dangerous"] or "нет"),
          "- снято доводом AR1: %s" % (", ".join(res["ar1_cleared_dangerous"]) or "ничего")]
    s = res["asm"]
    L += ["", "## ASSEMBLY_DISCOVERY_V1", "", "| модель | сработал | верно | неверно | открыто | точность | помог один "
          "| навредил |", "|---|---|---|---|---|---|---|---|"]
    for m, v in s["by_model"].items():
        L.append("| %s | %d | %d | %d | %d | %s | %d | %d |" % (m, v.get("triggered", 0), v.get("ok", 0),
                                                               v.get("wrong", 0), v.get("open", 0),
                                                               f3(v.get("precision")), v.get("helped", 0),
                                                               v.get("hurt", 0)))
    L += ["", "Вне пула доводов ASM: %d (истины нет, точность по ним неизвестна)." % s["outside_pool"], "",
          "### Составной по закрытым парам COMPOSITE", "",
          "| категория | всего | найдено (все детекторы) | найдено ASM | полнота | полнота ASM |", "|---|---|---|---|---|---|"]
    for k, v in s["recall_by_category"].items():
        L.append("| %s | %d | %d | %d | %s | %s |" % (k, v.get("total", 0), v.get("found", 0), v.get("found_asm", 0),
                                                     f3(v.get("recall")), f3(v.get("asm_recall"))))
    L += ["", "### Прежние промахи V4", "", "- %s" % json.dumps(s["old_misses"], ensure_ascii=False)]
    L += ["  - " + x for x in s["old_miss_lines"]]
    dg = res["diagnostics"]
    L += ["", "## Диагностика замороженного вида (V5_PREP)", "",
          "- COMPOSITE: pair recall %s (%d), по клетке %s" % (f3(dg["composite"]["pair_recall"]),
                                                              dg["composite"]["pairs"], dg["composite"]["by_tile"]),
          "- DERIVED/RECOLOR (n %d): по семействам %s, не найдено ничем %d" % (
              dg["derived"]["n"], dg["derived"]["by_family"], dg["derived"]["missed_completely"]),
          "- STATE: STRONG-only %s, STRONG+CANDIDATE %s" % (f3(dg["state"]["strong_recall"]),
                                                             f3(dg["state"]["discovery_recall"])),
          "- автоматические действия по типу: %s" % json.dumps(dg["auto_by_type"], ensure_ascii=False),
          "- утверждения вне пула: V4 %d, V5_PREP %d" % (res["outside_pool_v4"], res["outside_pool_all"])]
    L += ["", "## Новые доводы вне пула", ""] + ["- %s %s %s %s" % tuple(x) for x in res["outside_pool_new"]]
    L += ["", "VERIFIED ставит только человек."]
    with open(p("report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["dev", "freeze", "discover", "report"])
    a = ap.parse_args()
    {"dev": do_dev, "freeze": do_freeze, "discover": do_discover, "report": do_report}[a.cmd]()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
