#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ASSEMBLY_EVIDENCE_V2_PREP - два новых независимых кандидатных детектора составного поверх V6_PREP (специалист 02.10,
передал Vitali в чате). CPU, чтение.

  ASSEMBLY_REPEATED_COMPONENT_V1 (assembly_repeated_v1, детектор ASMR) - кадр несколько раз в одном повторяющемся
      следе сборки;
  TWO_COMPONENT_ASSEMBLY_V1 (two_component_v1, детектор ASM2) - две детали с одним устойчивым сдвигом, повтором на
      разных картах и очень высокой взаимной зависимостью.
Оба - только CANDIDATE -> REVIEW, STRONG не бывает. Детектора для одиночного места нет: SINGLE_PLACEMENT остаётся
на ревью. ASSEMBLY_COMPONENT_GROUP_V1 (AG V1), ASM V1, AR2, MCD, таксономия, ревью, маршрут B и весь замороженный код
V2-V8 и артефакты V5/V6_PREP не меняются (читаются, хэши сверяются).

Порядок (специалист 02.10): сначала проверка на старых эталонах разработки (holdout V4, V5_COMPONENT_VALIDATION_V1,
AR boundary validation; не на 80 кадрах V5): existence precision >= 0.95 и не меньше 20 закрытых случаев, иначе
INSUFFICIENT_SAMPLE - детектор остаётся диагностикой и в пересчёт не входит. Потом параметры и итог проверки
фиксируются в spec.json, и только потом один пересчёт V6-80 (report пишется один раз).

    py -3.13 tools/hdart/assembly_evidence_v2_prep.py validate   эталоны разработки -> dev_validation.json
    py -3.13 tools/hdart/assembly_evidence_v2_prep.py spec       параметры, итог проверки, хэши -> spec.json
    py -3.13 tools/hdart/assembly_evidence_v2_prep.py discover   доводы на 80 кадрах -> found_evidence.json (замок)
    py -3.13 tools/hdart/assembly_evidence_v2_prep.py report     один пересчёт -> report.json, report.md
    py -3.13 tools/hdart/assembly_evidence_v2_prep.py check      целость spec, кода и входов
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
import assembly_group_v1 as ag                    # noqa: E402
import assembly_repeated_v1 as arc                # noqa: E402
import identity_routing as ir                     # noqa: E402
import post_review_safety as prs                  # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_holdout_v4 as hv                  # noqa: E402
import relation_holdout_v5 as h5                  # noqa: E402
import relation_v6_prep as v6                     # noqa: E402
import two_component_v1 as tc                     # noqa: E402
import v5_ar2_recount as rc                       # noqa: E402

# Порядок детекторов в замороженном V5AR2Claims.finalize читается из rc.DETECTOR_ORDER при вызове. Ключи только
# добавляются (ASMG=9 уже добавлен relation_v6_prep при импорте); значения прежних ключей те же. Файлы не правятся.
rc.DETECTOR_ORDER = dict(rc.DETECTOR_ORDER, **{ag.DETECTOR: 9, arc.DETECTOR: 10, tc.DETECTOR: 11})

ENC = ir.ENC
PROFILE = "ASSEMBLY_EVIDENCE_V2_PREP"
OUT = os.path.join(ir.PROBES, "assembly-evidence-v2-prep")
V5 = h5.OUT
V6 = v6.OUT
SELF = "tools/hdart/assembly_evidence_v2_prep.py"
CODE = ["tools/hdart/assembly_repeated_v1.py", "tools/test_assembly_repeated_v1.py",
        "tools/hdart/two_component_v1.py", "tools/test_two_component_v1.py", SELF]
GATES = v6.GATES
DEV_TRUTH = (("holdout V4", h5.DEV_SOURCES["v4_truth"]),
             ("V5 component validation", h5.DEV_SOURCES["component_validation_truth"]),
             ("AR boundary validation", h5.DEV_SOURCES["ar_boundary_truth"]))
DEV_MIN_N = 20
DEV_MIN_PREC = 0.95
DETECTORS = {"ASSEMBLY_REPEATED_COMPONENT_V1": arc, "TWO_COMPONENT_ASSEMBLY_V1": tc}
FROZEN = dict(v6.FROZEN, v6_spec=os.path.join(V6, "spec.json"), v6_found_group=os.path.join(V6, "found_group.json"),
              v6_found_group_lock=os.path.join(V6, "found_group.lock.json"), v6_report=os.path.join(V6, "report.json"))
PARAM_CHOICE = {
    "ASSEMBLY_REPEATED_COMPONENT_V1":
        "разведка блокнота сессии ae2_explore.py / ae2_rc.py / ae2_rc2.py 02.10 только по эталонам разработки: все "
        "ложные NONE (U_BASE_B:22~:67, MOORINGS:9~:0, DOOM_BASE:50~:60, C_INT_THIRD:47~:7, SEAORGANIC1XPZ:62~:11, "
        "ATLANTSEASHORT:33~:14, WHITEBASES01:55~:56) - пол, повторённый под сборкой; без пола NONE 0. Якорь "
        "единственный в своём следе - защита от узора (забор A B A B), след на >= 2 картах - повторяющаяся сборка",
    "TWO_COMPONENT_ASSEMBLY_V1":
        "разведка ae2_explore.py / ae2_rules.py / ae2_none.py 02.10 только по эталонам разработки: все NONE с "
        "зависимостью 1.0 - одно место (SINGLE_PLACEMENT) или другой набор (KITSUNE:15 ~ C_INT_HALF_XCOM:48, одна "
        "карта); порог 0.9, совместных мест >= 2 на >= 2 картах и один сдвиг с каждой стороны - NONE 0. Пол + "
        "предмет: закрытых случаев 2 - INSUFFICIENT_SAMPLE, в доводы не входит"}


def p(out, *name):
    return os.path.join(out, *name)


def file_sha(path):
    return v2.file_sha(path)


def ctx_places():
    return v3.Ctx(index=v2.load_index(v2.OUT))


# ---------------------------------------------------------------- validate (эталоны разработки)

def dev_pairs():
    """Закрытые пары эталонов разработки, по одной на пару (первый источник)."""
    seen, out = set(), []
    for name, path in DEV_TRUTH:
        for r in ir.load_json(path)["pairs"]:
            if r["existence"] == "OPEN":
                continue
            k = h5.pk(r["a"], r["b"])
            if k in seen:
                continue
            seen.add(k)
            lab = ("COMPOSITE" if r["existence"] == "RELATED" and "COMPOSITE" in r["closed"] else
                   ("NONE" if r["existence"] == "NONE" else "OTHER_RELATED"))
            out.append((name, r["a"].upper(), r["b"].upper(), lab, r["closed"]))
    return out


def fires_tc(W, a, b, diag=False):
    return any(tc.judge(W, a, sa, b, sb, diag=diag) for sa in W.slots(a) for sb in W.slots(b))


def fires_rc(Fp, a, b):
    return bool(arc.discover(Fp, a, only=b))


def fires_ag(G, a, b):
    return any(ag.judge(G, a, sa, b, sb) for sa in G.slots(a) for sb in G.slots(b))


def summarize(rows):
    c = Counter(r["truth"] for r in rows)
    n = len(rows)
    ex = (c["COMPOSITE"] + c["OTHER_RELATED"])
    return {"fired_closed": n, "COMPOSITE": c["COMPOSITE"], "OTHER_RELATED": c["OTHER_RELATED"], "NONE": c["NONE"],
            "existence_precision": v2.rate(ex, n), "composite_type_precision": v2.rate(c["COMPOSITE"], n),
            "also_ag": sum(1 for r in rows if r["ag"]),
            "none_pairs": ["%s ~ %s" % (r["a"], r["b"]) for r in rows if r["truth"] == "NONE"],
            "other_pairs": ["%s ~ %s [%s]" % (r["a"], r["b"], "/".join(r["closed"])) for r in rows
                            if r["truth"] == "OTHER_RELATED"]}


def status_of(s):
    if s["fired_closed"] < DEV_MIN_N:
        return "INSUFFICIENT_SAMPLE"
    return "PASS" if (s["existence_precision"] or 0) >= DEV_MIN_PREC else "FAIL"


def do_validate(out=OUT):
    if os.path.exists(p(out, "spec.json")):
        raise SystemExit("spec уже записан - проверка на эталонах разработки закрыта: %s" % p(out, "spec.json"))
    t0 = time.time()
    ctx = ctx_places()
    W, Fp, G = tc.Windows(ctx), arc.Footprints(ctx), ag.Groups(ctx)
    pairs = dev_pairs()
    fired = {"ASSEMBLY_REPEATED_COMPONENT_V1": [], "TWO_COMPONENT_ASSEMBLY_V1": [], "TC_FLOOR_OBJECT_DIAG": []}
    n_by = Counter(lab for _s, _a, _b, lab, _c in pairs)
    for src, a, b, lab, closed in pairs:
        row = {"src": src, "a": a, "b": b, "truth": lab, "closed": closed}
        hit = {"ASSEMBLY_REPEATED_COMPONENT_V1": fires_rc(Fp, a, b) or fires_rc(Fp, b, a),
               "TWO_COMPONENT_ASSEMBLY_V1": fires_tc(W, a, b),
               "TC_FLOOR_OBJECT_DIAG": fires_tc(W, a, b, diag=True)}
        if any(hit.values()):
            row["ag"] = fires_ag(G, a, b)
            for k, h in hit.items():
                if h:
                    fired[k].append(row)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE,
           "sources": [[n, pth.replace(os.sep, "/"), file_sha(pth)] for n, pth in DEV_TRUTH],
           "closed_pairs": dict(n_by), "min_n": DEV_MIN_N, "min_existence_precision": DEV_MIN_PREC,
           "params": {"ASSEMBLY_REPEATED_COMPONENT_V1": arc.PARAMS, "TWO_COMPONENT_ASSEMBLY_V1": tc.PARAMS},
           "code_sha256": {c: file_sha(c) for c in CODE}, "detectors": {}}
    for k, rows in fired.items():
        s = summarize(rows)
        s["status"] = status_of(s)
        if k == "TC_FLOOR_OBJECT_DIAG":
            s["status"] = "DIAGNOSTIC_ONLY (" + s["status"] + ")"
        s["pairs"] = rows
        res["detectors"][k] = s
    res["seconds"] = round(time.time() - t0)
    ir.dump_json(p(out, "dev_validation.json"), res)
    for k, s in res["detectors"].items():
        print("%s: %s; закрытых срабатываний %d (составной %d, другая связь %d, NONE %d), existence %s, "
              "тип составного %s, совпало с AG %d" % (
                  k, s["status"], s["fired_closed"], s["COMPOSITE"], s["OTHER_RELATED"], s["NONE"],
                  hv.f3(s["existence_precision"]), hv.f3(s["composite_type_precision"]), s["also_ag"]))
    print("dev_validation.json, %d с" % res["seconds"])


# ---------------------------------------------------------------- spec

def load_validation(out=OUT):
    d = ir.load_json(p(out, "dev_validation.json"))
    bad = [c for c, s in d["code_sha256"].items() if file_sha(c) != s]
    if bad:
        raise SystemExit("код изменён после проверки на эталонах разработки: %s" % bad)
    return d


def spec_body(val):
    enabled = sorted(k for k in DETECTORS if val["detectors"][k]["status"] == "PASS")
    return {"profile": PROFILE,
            "params": {k: m.PARAMS for k, m in DETECTORS.items()},
            "detector_names": {k: m.DETECTOR for k, m in DETECTORS.items()},
            "rules": {k: m.RULE for k, m in DETECTORS.items()}, "level": "CANDIDATE",
            "enabled": enabled,
            "dev_status": {k: val["detectors"][k]["status"] for k in val["detectors"]},
            "gates": [list(g) for g in GATES], "dev_rule": {"min_n": DEV_MIN_N, "min_existence_precision": DEV_MIN_PREC},
            "param_choice": PARAM_CHOICE,
            "base": "доводы V5 (found_v5.json) + доводы AG V1 (relation-v6-prep/found_group.json); контроль - ворота "
                    "без новых детекторов равны отчёту V6_PREP",
            "single_placement": "детектора нет; SINGLE_PLACEMENT - REVIEW / unresolved",
            "not_touched": ["ASSEMBLY_COMPONENT_GROUP_V1", "ASM V1", "AR2", "MCD", "пороги перекраски", "таксономия",
                            "жизненный цикл ревью", "маршрут B", "замороженный код V2-V8 и артефакты V5/V6_PREP"],
            "detector_order": "rc.DETECTOR_ORDER дополняется ASMG=9, ASMR=10, ASM2=11 во время пересчёта",
            "note": "пересчёт на тех же 80 кадрах V5 - один раз, не независимая оценка; вердикт V5 FAIL не меняется"}


def do_spec(out=OUT):
    path = p(out, "spec.json")
    if os.path.exists(path):
        raise SystemExit("spec уже записан: %s" % path)
    missing = [c for c in CODE + list(FROZEN.values()) if not os.path.exists(c)]
    if missing:
        raise SystemExit("нет файлов: %s" % missing)
    val = load_validation(out)
    d5 = h5.load_freeze(V5)
    if h5.code_changed(d5):
        raise SystemExit("замороженный код V5 изменён: %s" % h5.code_changed(d5))
    v6.load_spec(V6)
    body = spec_body(val)
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                code_sha256={c: file_sha(c) for c in CODE},
                frozen_sha256={k: file_sha(v) for k, v in FROZEN.items()},
                frozen_paths={k: v.replace(os.sep, "/") for k, v in FROZEN.items()},
                dev_validation_sha256=file_sha(p(out, "dev_validation.json")), v5_freeze_sha256=d5["sha256"])
    ir.dump_json(path, data)
    print("spec записан: %s (%s); в пересчёт входят: %s" % (path, data["sha256"][:12], body["enabled"] or "ничего"))


def load_spec(out=OUT):
    d = ir.load_json(p(out, "spec.json"))
    val = load_validation(out)
    if file_sha(p(out, "dev_validation.json")) != d["dev_validation_sha256"]:
        raise SystemExit("dev_validation.json изменён после spec")
    if ir.sha({k: d[k] for k in spec_body(val)}) != d["sha256"]:
        raise SystemExit("spec.json изменён после записи")
    bad = [c for c, s in d["code_sha256"].items() if file_sha(c) != s]
    if bad:
        raise SystemExit("код изменён после spec: %s" % bad)
    bad = [k for k, s in d["frozen_sha256"].items() if file_sha(d["frozen_paths"][k]) != s]
    if bad:
        raise SystemExit("замороженные входы изменены: %s" % bad)
    if spec_body(val) != {k: d[k] for k in spec_body(val)}:
        raise SystemExit("параметры модулей разошлись со spec.json")
    return d


# ---------------------------------------------------------------- discover

def do_discover(out=OUT):
    lock = p(out, "found_evidence.lock.json")
    if os.path.exists(lock):
        raise SystemExit("доводы уже посчитаны и заморожены: %s" % lock)
    d = load_spec(out)
    keys = h5.keys_of(h5.load_holdout(V5))
    t0 = time.time()
    ctx = ctx_places()
    W, Fp = tc.Windows(ctx), arc.Footprints(ctx)
    edges = {"ASSEMBLY_REPEATED_COMPONENT_V1": [], "TWO_COMPONENT_ASSEMBLY_V1": [], "TC_FLOOR_OBJECT_DIAG": []}
    for k in keys:
        edges["ASSEMBLY_REPEATED_COMPONENT_V1"] += arc.discover(Fp, k)
        edges["TWO_COMPONENT_ASSEMBLY_V1"] += tc.discover(W, k)
        edges["TC_FLOOR_OBJECT_DIAG"] += tc.discover(W, k, diag=True)
    path = p(out, "found_evidence.json")
    ir.dump_json(path, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": d["sha256"], "keys": keys,
                        "enabled": d["enabled"], "edges": edges,
                        "note": "доводы CANDIDATE; в утверждения идут только enabled; TC_FLOOR_OBJECT_DIAG - "
                                "только диагностика; VERIFIED ставит человек"})
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": d["sha256"],
                        "path": path.replace(os.sep, "/"), "sha256": file_sha(path)})
    print("доводы: %s, %.0f с" % ({k: len(v) for k, v in edges.items()}, time.time() - t0))


def load_found(out=OUT):
    lk = ir.load_json(p(out, "found_evidence.lock.json"))
    if file_sha(lk["path"]) != lk["sha256"]:
        raise SystemExit("found_evidence.json изменён после заморозки")
    return ir.load_json(lk["path"])


# ---------------------------------------------------------------- report

def frames_covered(dg, ku):
    """Кадры holdout с истинным составным: {кадр: найдена ли хоть одна его пара}."""
    by = {}
    for s in dg["closed_by"]:
        a, rest = s.split(" ~ ", 1)
        b = rest.split(" [")[0]
        hit = not s.endswith("не найдено")
        for x in (a, b):
            if x in ku:
                by[x] = by.get(x, False) or hit
    return by


def det_diag(det, base, new, pp_base, pp_new, edges, pool, ku):
    """Срабатывания одного детектора det на пуле: закрытые RELATED / NONE / OPEN, помог, вред."""
    st = hv.tv_state

    def sup(cs):
        return [e for c in cs for e in c["support"] if e["detector"] == det]

    bpc = {tuple(sorted((a, b))): cs for a, b, _t, cs in base["ev"]["pc"]}
    comp_added, comp_had, other_rel, none_, opened = [], [], [], [], []
    for a, b, t, cs in new["ev"]["pc"]:
        if not sup(cs):
            continue
        key = "%s ~ %s" % (a, b)
        had = any(c["group"] == "composite" for c in bpc.get(tuple(sorted((a, b))), []))
        if not t or t[0] == "OPEN":
            opened.append(key)
        elif t[0] == "NONE":
            none_.append(key)
        elif "COMPOSITE" in t[1]:
            (comp_had if had else comp_added).append(key)
        elif t[1]:
            other_rel.append("%s [%s]" % (key, "/".join(sorted(t[1]))))
        else:
            opened.append(key + " [RELATED, подтип открыт]")
    fb, fn = frames_covered(base["dg"], ku), frames_covered(new["dg"], ku)
    helped_frames = sorted(k for k in fn if fn[k] and not fb.get(k))
    pairs = {h5.pk(e["source"], e["target"]) for e in edges}
    wrong = [("%s ~ %s" % (a, b)) for a, b, t, cs in new["ev"]["pc"] for c in cs
             if any(e["detector"] == det for e in c["support"]) and st(c, t) == "wrong"]
    return {"edges": len(edges), "pairs": len(pairs), "pool_pairs": len(pairs & pool),
            "outside_pool_pairs": len(pairs - pool),
            "closed_related_composite": len(comp_added) + len(comp_had),
            "closed_related_composite_new": comp_added, "closed_related_composite_already": len(comp_had),
            "closed_related_other_type": other_rel, "closed_none": none_, "open": opened,
            "helped_frame_recall": helped_frames,
            "helped_dangerous": sorted(set(base["ev"]["dangerous"]) - set(new["ev"]["dangerous"])),
            "hurt": {"dangerous_pre_new": sorted(set(new["ev"]["dangerous"]) - set(base["ev"]["dangerous"])),
                     "dangerous_post_new": sorted(set(pp_new["post_dangerous"]) - set(pp_base["post_dangerous"])),
                     "unmasked_after_review": [u["asset"] for u in pp_new["unmasked"]],
                     "wrong_claims": wrong}}


def do_report(out=OUT):
    if os.path.exists(p(out, "report.json")):
        raise SystemExit("пересчёт V6-80 уже сделан (один раз): %s" % p(out, "report.json"))
    sp = load_spec(out)
    fe = load_found(out)
    fg = v6.load_group(V6)
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
    c3 = ctx_places()
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
        return {"ev": ev, "pp": pp, "gates": gates, "verdict": verdict, "dg": dg,
                "strong_only": v6.strong_recall(ev["pc"], ku), "handoff": G["handoff_unassigned"]["value"]}

    t0 = time.time()
    base_edges = found5["edges"] + fg["edges"]
    base = run(base_edges)
    rep6 = ir.load_json(p(V6, "report.json"))
    g6 = {g["gate"]: g["value"] for g in rep6["gates"]}
    gb = {g["gate"]: g["value"] for g in base["gates"]}
    same = {g: gb[g] == g6[g] for g in g6}
    if not all(same.values()):
        raise SystemExit("контроль не прошёл: без новых детекторов ворота не равны отчёту V6_PREP: %s" % same)
    enabled = sp["enabled"]
    det_name = {k: DETECTORS[k].DETECTOR for k in DETECTORS}
    new_edges = [e for k in enabled for e in fe["edges"][k]]
    new = run(base_edges + new_edges)
    per = {}
    for k in DETECTORS:
        es = fe["edges"][k]
        solo = run(base_edges + es)
        dd = det_diag(det_name[k], base, solo, base["pp"], solo["pp"], es, pool, ku)
        gg = {x["gate"]: x["value"] for x in solo["gates"]}
        dd.update({"enabled": k in enabled, "dev_status": sp["dev_status"][k],
                   "solo_gates": {g: gg[g] for g in ("composite_frame_recall", "composite_pair_recall",
                                                     "PRE_REVIEW_DANGEROUS", "POST_REVIEW_DANGEROUS")}})
        per[k] = dd
    # пол + предмет: только диагностика, в утверждения не входит
    fo = fe["edges"]["TC_FLOOR_OBJECT_DIAG"]
    fo_pairs = sorted({h5.pk(e["source"], e["target"]) for e in fo})
    tl = {h5.pk(a, b): t for a, b, t, _cs in new["ev"]["pc"]}

    def tstr(t):
        if not t:
            return "вне пула"
        return t[0] if t[0] != "RELATED" else "RELATED/" + "/".join(sorted(t[1]))
    fo_diag = ["%s ~ %s [%s]" % (a, b, tstr(tl.get((a, b)))) for a, b in fo_pairs]
    fc_new = frames_covered(new["dg"], ku)
    uncovered = []
    for k in sorted(x for x, hit in fc_new.items() if not hit):
        pl = c3.places.of(k)
        uncovered.append({"frame": k, "places": len(pl), "blocks": len({b for _t, b, _g, _x, _l in pl}),
                          "class": "SINGLE_PLACEMENT -> REVIEW / unresolved" if len(pl) <= 1 else "не найдено"})
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE, "spec_sha256": sp["sha256"],
           "v5_freeze_sha256": d["sha256"], "n_frames": len(keys), "enabled": enabled,
           "dev_status": sp["dev_status"], "verdict": new["verdict"], "gates": new["gates"],
           "gates_v6_base": base["gates"], "control_base_equals_v6_prep": same,
           "composite": {"v6_base": {"frame": base["dg"]["item_recall"], "pair": base["dg"]["pair_recall"],
                                     "strong_only": base["strong_only"]},
                         "new": {"frame": new["dg"]["item_recall"], "pair": new["dg"]["pair_recall"],
                                 "strong_only": new["strong_only"], "closed_by": new["dg"]["closed_by"]},
                         "uncovered_frames": uncovered},
           "dangerous": {"pre_base": base["pp"]["pre_dangerous"], "post_base": base["pp"]["post_dangerous"],
                         "pre_new": new["pp"]["pre_dangerous"], "post_new": new["pp"]["post_dangerous"]},
           "post_review_new": {"removed_closed_none": len(new["pp"]["dropped_candidates"]),
                               "removed_new": [x for x in new["pp"]["dropped_candidates"]
                                               if any(s.split()[0] in (arc.DETECTOR, tc.DETECTOR)
                                                      for s in x["detectors"])],
                               "unmasked": new["pp"]["unmasked"],
                               "invariant_holds": not new["pp"]["unmasked"] and new["pp"]["POST_REVIEW_DANGEROUS"] == 0},
           "detectors": per, "floor_object_diag": fo_diag, "handoff_unassigned": new["handoff"],
           "seconds": round(time.time() - t0)}
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    print("ASSEMBLY_EVIDENCE_V2_PREP: %s; в пересчёте %s; PRE %s, POST %s; составной кадры %s, пары %s; отчёт %s" % (
        res["verdict"], enabled or "ничего", res["dangerous"]["pre_new"], res["dangerous"]["post_new"],
        hv.f3(new["dg"]["item_recall"]), hv.f3(new["dg"]["pair_recall"]), p(out, "report.md")))
    return res


def write_md(out, res):
    f3 = hv.f3
    val = ir.load_json(p(out, "dev_validation.json"))
    gb = {g["gate"]: g for g in res["gates_v6_base"]}
    L = ["# ASSEMBLY_EVIDENCE_V2_PREP — два новых кандидатных детектора составного поверх V6_PREP", "",
         "Пересчёт на тех же %d кадрах holdout V5 — один раз, **не независимая оценка**. Вердикт V5 (FAIL) не "
         "меняется." % res["n_frames"], "",
         "Итог ворот: **%s**. В пересчёт вошли: %s. spec %s." % (
             res["verdict"], ", ".join(res["enabled"]) or "ничего", res["spec_sha256"][:12]), "",
         "Контроль: без новых детекторов ворота равны отчёту V6_PREP — %s." % (
             "да" if all(res["control_base_equals_v6_prep"].values()) else "**нет**"), "",
         "## Проверка на эталонах разработки (до пересчёта)", "",
         "Пары: %s. Нужно: закрытых срабатываний >= %d и existence precision >= %.2f." % (
             val["closed_pairs"], val["min_n"], val["min_existence_precision"]), "",
         "| детектор | итог | срабатываний | составной | другая связь | NONE | existence | тип составного | "
         "совпало с AG |", "|---|---|---|---|---|---|---|---|---|"]
    for k, s in val["detectors"].items():
        L.append("| %s | %s | %d | %d | %d | %d | %s | %s | %d |" % (
            k, s["status"], s["fired_closed"], s["COMPOSITE"], s["OTHER_RELATED"], s["NONE"],
            f3(s["existence_precision"]), f3(s["composite_type_precision"]), s["also_ag"]))
    L += ["", "## Ворота", "", "| ворота | V6_PREP | сейчас | n | нужно | итог |", "|---|---|---|---|---|---|"]
    for g in res["gates"]:
        L.append("| %s | %s | %s | %s | %s | %s |" % (g["gate"], f3(gb[g["gate"]]["value"]), f3(g["value"]), g["n"],
                                                      g["need"], g["status"]))
    c = res["composite"]
    L += ["", "## Составной", "",
          "- любой уровень (замороженное правило): кадры %s → %s, пары %s → %s" % (
              f3(c["v6_base"]["frame"]), f3(c["new"]["frame"]), f3(c["v6_base"]["pair"]), f3(c["new"]["pair"])),
          "- только STRONG (R-181): кадры %s → %s, пары %s → %s (новые доводы - всегда CANDIDATE)" % (
              f3(c["v6_base"]["strong_only"]["frame"]), f3(c["new"]["strong_only"]["frame"]),
              f3(c["v6_base"]["strong_only"]["pair"]), f3(c["new"]["strong_only"]["pair"])),
          "- кадры без найденной пары: %s" % ("; ".join("%s (мест %d, карт %d: %s)" % (
              u["frame"], u["places"], u["blocks"], u["class"]) for u in c["uncovered_frames"]) or "нет")]
    dz = res["dangerous"]
    pr = res["post_review_new"]
    L += ["", "## Опасные", "",
          "- до ревью: %s → %s" % (dz["pre_base"] or "нет", dz["pre_new"] or "нет"),
          "- после ревью: %s → %s" % (dz["post_base"] or "нет", dz["post_new"] or "нет"),
          "- ревью: удалено кандидатов на closed NONE %d, из них новых детекторов %d; стали опасными %s; инвариант %s"
          % (pr["removed_closed_none"], len(pr["removed_new"]), [u["asset"] for u in pr["unmasked"]] or "нет",
             "держится" if pr["invariant_holds"] else "**нет**")]
    for k, g in res["detectors"].items():
        L += ["", "## %s (%s, проверка разработки %s)" % (k, "в пересчёте" if g["enabled"] else "только диагностика",
                                                           g["dev_status"]), "",
              "- сработал: доводов %d, пар %d (в пуле %d, вне пула %d)" % (
                  g["edges"], g["pairs"], g["pool_pairs"], g["outside_pool_pairs"]),
              "- закрыто RELATED: составной %d (новых %d, уже были %d), другой подтип %d" % (
                  g["closed_related_composite"], len(g["closed_related_composite_new"]),
                  g["closed_related_composite_already"], len(g["closed_related_other_type"])),
              "- закрыто NONE: %d %s" % (len(g["closed_none"]), "; ".join(g["closed_none"])),
              "- OPEN: %d %s" % (len(g["open"]), "; ".join(g["open"])),
              "- помог составному по кадрам: %s" % (", ".join(g["helped_frame_recall"]) or "нет"),
              "- помог опасным: %s" % (", ".join(g["helped_dangerous"]) or "нет"),
              "- вред: %s" % json.dumps(g["hurt"], ensure_ascii=False),
              "- новые составные: %s" % ("; ".join(g["closed_related_composite_new"]) or "нет"),
              "- другой подтип: %s" % ("; ".join(g["closed_related_other_type"]) or "нет"),
              "- ворота только с этим детектором: %s" % json.dumps(g["solo_gates"], ensure_ascii=False)]
    L += ["", "## Пол + предмет (только диагностика, в утверждения не входит)", "",
          "; ".join(res["floor_object_diag"]) or "нет", "",
          "handoff_unassigned: %s. VERIFIED ставит только человек." % res["handoff_unassigned"]]
    with open(p(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")


def do_check(out=OUT):
    d = load_spec(out)
    print("spec цел: %s; код, проверка разработки и замороженные входы те же" % d["sha256"][:12])
    if os.path.exists(p(out, "found_evidence.lock.json")):
        load_found(out)
        print("доводы целы")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["validate", "spec", "discover", "report", "check"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    {"validate": do_validate, "spec": do_spec, "discover": do_discover, "report": do_report,
     "check": do_check}[a.cmd](a.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
