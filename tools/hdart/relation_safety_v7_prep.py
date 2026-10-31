#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RELATION_SAFETY_MODEL_V7_PREP - переразложение уже найденных доводов на вопрос производства «можно ли этот кадр
рисовать независимо?» (специалист 02.10, передал Vitali в чате). CPU, чтение. Новых детекторов нет.

V6_PREP и ASSEMBLY_EVIDENCE_V2_PREP остаются FAIL навсегда: их артефакты и код не меняются, только читаются.

Что меняется - только модель ворот и смысл одного детектора:
  REPEATED_COMPONENT (assembly_repeated_v1, ASMR) больше не довод COMPOSITE. Его доводы при сборке утверждений
      переписываются в REPEATED_ASSEMBLY_RELATION: существование CANDIDATE, подтип TYPE_OPEN, своя группа
      assembly_open - голоса в composite_*_recall у него нет. Файл детектора и его найденные доводы не меняются.
  TWO_COMPONENT (two_component_v1, ASM2) - как в V2_PREP, без изменений.
  Ворота делятся на hard safety / typed capabilities / review quality / diagnostic. Точный COMPOSITE - диагностика.
  Новое: related_frame_safety_recall (определение в METRIC, фиксируется в spec.json до расчёта).

Порядок: spec (определения, ворота, правило вердикта, хэши) -> discover (существующие детекторы AG, TC, RC на
80 кадрах holdout V4; на 80 кадрах V5 доводы уже заморожены в V6_PREP и V2_PREP) -> report (один раз): история -
те же ворота на прежних замороженных системах - и модель V7 на двух старых контрольных наборах.

    py -3.13 tools/hdart/relation_safety_v7_prep.py spec
    py -3.13 tools/hdart/relation_safety_v7_prep.py discover
    py -3.13 tools/hdart/relation_safety_v7_prep.py report
    py -3.13 tools/hdart/relation_safety_v7_prep.py check
VERIFIED ставит только человек.
"""
import argparse
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import assembly_evidence_v2_prep as ae2           # noqa: E402  (ставит ASMG/ASMR/ASM2 в rc.DETECTOR_ORDER)
import assembly_repeated_v1 as arc                # noqa: E402
import identity_routing as ir                     # noqa: E402
import post_review_safety as prs                  # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_discovery_v5 as rd5               # noqa: E402
import relation_holdout_v4 as hv                  # noqa: E402
import relation_holdout_v5 as h5                  # noqa: E402
import relation_v6_prep as v6                     # noqa: E402
import two_component_v1 as tc                     # noqa: E402
import v5_ar2_recount as rc                       # noqa: E402

ENC = ir.ENC
PROFILE = "RELATION_SAFETY_MODEL_V7_PREP"
OUT = os.path.join(ir.PROBES, "relation-safety-v7-prep")
SELF = "tools/hdart/relation_safety_v7_prep.py"
CODE = [SELF, "tools/test_relation_safety_v7_prep.py"]
V4H, V5H, V6D, AE2D = hv.OUT, h5.OUT, v6.OUT, ae2.OUT

# REPEATED_ASSEMBLY_RELATION: новый тип и группа добавляются ключами в словари замороженных модулей при работе
# (как rc.DETECTOR_ORDER в V6_PREP / V2_PREP); прежние ключи не трогаются, файлы не правятся.
RAR_TYPE = "REPEATED_ASSEMBLY_RELATION"
RAR_GROUP = "assembly_open"
RAR_DETECTOR = "RAR"
rd5.GROUP5[RAR_TYPE] = RAR_GROUP
rc.DETECTOR_ORDER = dict(rc.DETECTOR_ORDER, **{RAR_DETECTOR: 12})
ASM_FAMILY = ("ASM", "ASMG", "ASM2", "ASMR", RAR_DETECTOR)

JOINT = hv.JOINT_LABELS
METRIC = {
    "related_frame_safety_recall": {
        "frames": "кадры holdout (ключи), у которых в пуле есть хоть одна пара с истиной RELATED, где производственно "
                  "значимый ярлык (JOINT_LABELS опасности relation_holdout_v4.danger: EXACT_COPY, RECOLOR_PEER, "
                  "MIRRORED_VARIANT_PEER, DERIVED, STATE_VARIANT, ANIMATION_FAMILY, COMPOSITE, MODULAR_SECTION) "
                  "есть среди закрытых или открытых ярлыков истины",
        "hit": "у кадра есть пара пула с истиной RELATED (любые ярлыки), на которой у системы есть хоть одно "
               "утверждение любого уровня и любой группы: это настоящая связь, и она снимает кадр с независимого "
               "рисования - BLOCK (STRONG, связывает кадр: relation_discovery_v4.bound по одному утверждению), "
               "REVIEW (CANDIDATE -> ревью) или CANONICAL (STRONG направленный, кадр - основа, родственник "
               "выводится из него)",
        "not_hit": "утверждения только на парах NONE / OPEN или вне пула; роли без цели",
        "value": "доля кадров с hit; рядом в отчёте разбивка по действию и три варианта-диагностики (не ворота): "
                 "только BLOCK+REVIEW, только значимые пары, знаменатель только по закрытым значимым ярлыкам"}}
GATES = (("PRE_REVIEW_DANGEROUS", "count", 0, "hard"), ("POST_REVIEW_DANGEROUS", "count", 0, "hard"),
         ("relation_existence_precision", "rate", 0.95, "hard"),
         ("related_frame_safety_recall", "rate", 0.90, "hard"),
         ("automatic_action_precision", "rate", 0.95, "hard"),
         ("derived_recolor_discovery", "rate", 0.70, "typed"), ("state_discovery", "rate", 0.70, "typed"),
         ("ASSEMBLY_candidate_existence_precision", "rate", 0.95, "review"),
         ("ASSEMBLY_STRONG_composite_precision", "rate", 0.95, "review"))
GATE_DEFS = {
    "PRE/POST_REVIEW_DANGEROUS": "как V5/V6_PREP: relation_holdout_v4.danger до и после post_review_safety",
    "relation_existence_precision / automatic / derived / state": "как relation_holdout_v5 (rd5.evaluate)",
    "related_frame_safety_recall": "METRIC",
    "ASSEMBLY_*": "как V5/V6_PREP: только ASM V1 (детектор ASM), h5.asm_pairs; все детекторы сборки - диагностика",
    "N_MIN": "доля с n < %d - INSUFFICIENT_SAMPLE (h5.acceptance)" % h5.N_MIN}
DIAGNOSTIC = ("composite_pair_recall", "composite_frame_subtype_recall", "composite_strong_recall", "module_recall",
              "handoff_unassigned", "assembly_family_existence", "rar_pairs")
VERDICT_RULE = (
    "Модель V7 считается на двух старых контрольных наборах: holdout V5 (80 кадров; доводы found5 + AG V6_PREP + TC и "
    "RC V2_PREP) и holdout V4 (80 кадров; доводы пересчёта V5 found5 без AR1 + AR2 и AG, TC, RC, найденные здесь "
    "существующими детекторами). PASS - все ворота hard и typed PASS на обоих наборах, ворота review PASS на holdout "
    "V5 и на holdout V4 не FAIL (INSUFFICIENT_SAMPLE / NO_DATA там допустимы: holdout V4 не набирал пары сборки). "
    "Любой FAIL - FAIL. Иначе INCONCLUSIVE. Порог 0.90 и определение метрики записаны до расчёта; история (те же "
    "ворота на прежних замороженных системах) - калибровка, в вердикт не входит.")
SYSTEMS = {"V5": ("V5 frozen", "V6_PREP", "V2_PREP (RC как COMPOSITE)", "V7 model"),
           "V4": ("V4 frozen", "V5 recount (AR2)", "V7 model")}
FROZEN = dict(ae2.FROZEN, ae2_spec=os.path.join(AE2D, "spec.json"),
              ae2_found=os.path.join(AE2D, "found_evidence.json"),
              ae2_found_lock=os.path.join(AE2D, "found_evidence.lock.json"),
              ae2_report=os.path.join(AE2D, "report.json"),
              v4_report=os.path.join(V4H, "report.json"), v5_report=os.path.join(V5H, "report.json"),
              v5_recount_report=rc.p("report.json"), v5_recount_found_ar2=rc.p("found_ar2.json"),
              v5_prep_found5=rd5.p("found5.json"))
FROZEN_CODE = ["tools/hdart/assembly_repeated_v1.py", "tools/hdart/two_component_v1.py",
               "tools/hdart/assembly_group_v1.py", "tools/hdart/assembly_evidence_v2_prep.py",
               "tools/hdart/relation_v6_prep.py", "tools/hdart/relation_holdout_v5.py",
               "tools/hdart/relation_holdout_v4.py", "tools/hdart/v5_ar2_recount.py",
               "tools/hdart/post_review_safety.py", "tools/hdart/relation_discovery_v5.py"]


def p(out, *name):
    return os.path.join(out, *name)


def file_sha(path):
    return v2.file_sha(path)


# ---------------------------------------------------------------- модель

def reclass_rc(e):
    """Довод RC (ASMR, COMPOSITE_PART, CANDIDATE) -> REPEATED_ASSEMBLY_RELATION: существование CANDIDATE, подтип
    открыт, группа assembly_open (голоса в составном нет). Исходный словарь не меняется."""
    if e["detector"] != arc.DETECTOR or e["level"] != "CANDIDATE":
        raise SystemExit("не довод RC уровня CANDIDATE: %s" % e)
    sc = dict(e.get("scores") or {}, source_detector=arc.DETECTOR, source_type=e["type"],
              v7_class="REPEATED_ASSEMBLY_RELATION", subtype="TYPE_OPEN")
    return dict(e, type=RAR_TYPE, detector=RAR_DETECTOR, scores=sc)


def action_of(c, a):
    """Что утверждение c делает с кадром a: BLOCK / REVIEW / CANONICAL."""
    if c["existence"] != rc.STRONG:
        return "REVIEW"
    if c["type_level"] == v4.T_OPEN or c["type"] in v4.SYMMETRIC or c["source"] == a:
        return "BLOCK"
    return "CANONICAL"


def relevant(t, closed_only=False):
    if not t or t[0] != "RELATED":
        return False
    labs = set(t[1]) if closed_only else set(t[1]) | set(t[2])
    return bool(labs & set(JOINT))


def related_frame_safety(pc, keys):
    """pc = [(a, b, истина или None, [утверждение])], keys - кадры holdout. -> значение, n, разбивка, промахи."""
    ku = {k.upper() for k in keys}
    by = defaultdict(list)
    for a, b, t, cs in pc:
        A, B = a.upper(), b.upper()
        for x, y in ((A, B), (B, A)):
            if x in ku:
                by[x].append((y, t, cs))
    rows = {}
    for f in sorted(by):
        prs_ = by[f]
        if not any(relevant(t) for _y, t, _cs in prs_):
            continue
        acts, rel_acts = Counter(), Counter()
        for y, t, cs in prs_:
            if not (t and t[0] == "RELATED" and cs):
                continue
            best = sorted({action_of(c, f) for c in cs}, key=("BLOCK", "REVIEW", "CANONICAL").index)[0]
            acts[best] += 1
            if relevant(t):
                rel_acts[best] += 1
        rows[f] = {"hit": bool(acts), "actions": dict(acts), "hit_relevant": bool(rel_acts),
                   "hit_block_review": bool(acts["BLOCK"] or acts["REVIEW"]),
                   "closed_relevant": any(relevant(t, True) for _y, t, _cs in prs_),
                   "pairs": [{"other": y, "truth": tstr(t), "claims": claim_list(cs, f)} for y, t, cs in prs_
                             if t and t[0] == "RELATED"]}
    n = len(rows)
    hit = sum(r["hit"] for r in rows.values())
    cl = [r for r in rows.values() if r["closed_relevant"]]
    best = Counter()
    for r in rows.values():
        if r["hit"]:
            best[sorted(r["actions"], key=("BLOCK", "REVIEW", "CANONICAL").index)[0]] += 1
    return {"value": v2.rate(hit, n), "n": n, "hit": hit,
            "by_best_action": dict(best),
            "variant_block_review_only": v2.rate(sum(r["hit_block_review"] for r in rows.values()), n),
            "variant_relevant_pair_only": v2.rate(sum(r["hit_relevant"] for r in rows.values()), n),
            "variant_closed_relevant_frames": {"value": v2.rate(sum(r["hit"] for r in cl), len(cl)), "n": len(cl)},
            "missed": {f: r["pairs"] for f, r in rows.items() if not r["hit"]}}


def tstr(t):
    if not t:
        return "вне пула"
    if t[0] != "RELATED":
        return t[0]
    return "RELATED closed=%s open=%s" % ("/".join(sorted(t[1])) or "-", "/".join(sorted(t[2])) or "-")


def claim_list(cs, f):
    return ["%s %s/%s %s [%s]" % (c["group"], c["existence"].replace("RELATED_", ""),
                                  c["type_level"].replace("TYPE_", ""), action_of(c, f),
                                  ",".join(sorted({e["detector"] for e in c["support"]}))) for c in cs]


def module_recall(pc):
    pos = [cs for _a, _b, t, cs in pc if t and t[0] == "RELATED" and "MODULAR_SECTION" in t[1]]
    return {"n": len(pos), "modular_group": v2.rate(sum(any(c["group"] == "modular" for c in cs) for cs in pos),
                                                   len(pos)),
            "any_claim": v2.rate(sum(bool(cs) for cs in pos), len(pos))}


def family_existence(pc):
    """По детектору сборки: пары пула с его доводом -> закрытые RELATED / NONE / OPEN."""
    out = {}
    for det in ASM_FAMILY:
        st = Counter()
        for _a, _b, t, cs in pc:
            if not any(e["detector"] == det for c in cs for e in c["support"]):
                continue
            st["RELATED" if t and t[0] == "RELATED" else "NONE" if t and t[0] == "NONE" else "OPEN"] += 1
        if st:
            out[det] = dict(st, existence_precision=v2.rate(st["RELATED"], st["RELATED"] + st["NONE"]))
    return out


def rar_pairs(pc):
    out = []
    for a, b, t, cs in pc:
        if any(e["detector"] == RAR_DETECTOR for c in cs for e in c["support"]):
            only = all(all(e["detector"] == RAR_DETECTOR for e in c["support"]) for c in cs)
            out.append("%s ~ %s [%s]%s" % (a, b, tstr(t), " только RAR" if only else ""))
    return out


def evaluate_v7(rows, C, args, trow, keys, none_pairs, tinfo):
    """Ворота V7 и диагностика для одной системы на одном наборе."""
    ev = rd5.evaluate(rows, C, *args)
    pp, _post = prs.pre_post(lambda c: rd5.evaluate(rows, c, *args), C, none_pairs)
    if pp["PRE_REVIEW_DANGEROUS"] != len(ev["dangerous"]):
        raise SystemExit("PRE_REVIEW_DANGEROUS не совпал с пересчётом")
    G = {g["gate"]: g for g in ev["gates"]}
    cand, strong = h5.asm_pairs(ev["pc"], trow)
    vc, nc, _a, _b = h5.rate_closed(cand, "exist", "yes")
    vs, ns, _c, _d = h5.rate_closed(strong, "composite", "yes")
    rf = related_frame_safety(ev["pc"], keys)
    ku = {k.upper() for k in keys}
    dg = hv.diagnostics(ev["pc"], ku, tinfo)["composite"]
    vals = {"PRE_REVIEW_DANGEROUS": (pp["PRE_REVIEW_DANGEROUS"], len(keys)),
            "POST_REVIEW_DANGEROUS": (pp["POST_REVIEW_DANGEROUS"], len(keys)),
            "relation_existence_precision": (G["relation_existence_precision"]["value"],
                                             G["relation_existence_precision"]["n"]),
            "related_frame_safety_recall": (rf["value"], rf["n"]),
            "automatic_action_precision": (G["automatic_action_precision"]["value"],
                                           G["automatic_action_precision"]["n"]),
            "derived_recolor_discovery": (G["derived_recolor_discovery"]["value"], G["derived_recolor_discovery"]["n"]),
            "state_discovery": (G["state_discovery"]["value"], G["state_discovery"]["n"]),
            "ASSEMBLY_candidate_existence_precision": (vc, nc),
            "ASSEMBLY_STRONG_composite_precision": (vs, ns)}
    gates, verdict = h5.acceptance(vals, tuple(g[:3] for g in GATES))
    grp = {g[0]: g[3] for g in GATES}
    for g in gates:
        g["group"] = grp[g["gate"]]
    diag = {"composite_pair_recall": {"value": G["true_composite_recall"]["value"],
                                      "n": G["true_composite_recall"]["n"]},
            "composite_frame_subtype_recall": {"value": dg["item_recall"], "n": dg["items"]},
            "composite_strong_recall": v6.strong_recall(ev["pc"], ku),
            "module_recall": module_recall(ev["pc"]),
            "handoff_unassigned": G["handoff_unassigned"]["value"],
            "assembly_family_existence": family_existence(ev["pc"]),
            "rar_pairs": rar_pairs(ev["pc"])}
    return {"ev": ev, "pp": pp, "gates": gates, "verdict": verdict, "frame_safety": rf, "diagnostic": diag,
            "legacy": {g["gate"]: (g["value"], g["n"]) for g in ev["gates"]}}


# ---------------------------------------------------------------- spec

def frozen_shas():
    miss = [v for v in FROZEN.values() if not os.path.exists(v)] + [c for c in FROZEN_CODE if not os.path.exists(c)]
    if miss:
        raise SystemExit("нет файлов: %s" % ", ".join(miss))
    out = {k: file_sha(v) for k, v in sorted(FROZEN.items())}
    out.update({c: file_sha(c) for c in FROZEN_CODE})
    return out


def spec_body():
    return {"profile": PROFILE, "decision": "специалист 02.10, передал Vitali в чате: без новых детекторов, "
                                            "переразложить существующие результаты на hard safety / typed / review / "
                                            "diagnostic; V6_PREP и ASSEMBLY_EVIDENCE_V2_PREP остаются FAIL",
            "metric": METRIC, "gates": [{"gate": g, "kind": k, "need": n, "group": grp} for g, k, n, grp in GATES],
            "gate_defs": GATE_DEFS, "diagnostic": list(DIAGNOSTIC), "verdict_rule": VERDICT_RULE,
            "systems": SYSTEMS,
            "reclassification": {"REPEATED_COMPONENT (ASMR, RC)": "REPEATED_ASSEMBLY_RELATION: existence CANDIDATE, "
                                                                  "subtype TYPE_OPEN, группа %s, детектор %s; голоса "
                                                                  "в composite_*_recall нет" % (RAR_GROUP,
                                                                                                RAR_DETECTOR),
                                 "TWO_COMPONENT (ASM2, TC)": "без изменений (COMPOSITE_PART, CANDIDATE)",
                                 "TC_FLOOR_OBJECT_DIAG": "в утверждения не входит, как в V2_PREP"},
            "holdout_v4_discovery": "AG (relation_v6_prep.run_ag, параметры замороженного assembly_group_v1), TC и RC "
                                    "(two_component_v1.discover, assembly_repeated_v1.discover) на 80 кадрах holdout "
                                    "V4; параметры TC и RC выбирались по эталонам разработки, куда входят пары "
                                    "holdout V4 - для них этот набор не слепой",
            "n_min": h5.N_MIN, "frozen_inputs": frozen_shas(),
            "code": {c: file_sha(c) for c in CODE if os.path.exists(c)}}


def do_spec(out=OUT):
    path = p(out, "spec.json")
    if os.path.exists(path):
        raise SystemExit("spec уже записан: %s" % path)
    if os.path.exists(p(out, "report.json")) or os.path.exists(p(out, "found_v4.lock.json")):
        raise SystemExit("расчёт уже был - spec после расчёта не пишется")
    body = spec_body()
    body["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    os.makedirs(out, exist_ok=True)
    ir.dump_json(path, body)
    print("spec: %s (%s)" % (path, file_sha(path)[:12]))


def load_spec(out=OUT):
    path = p(out, "spec.json")
    if not os.path.exists(path):
        raise SystemExit("нет spec.json - сначала spec")
    sp = ir.load_json(path)
    now = frozen_shas()
    ch = [k for k, v in sp["frozen_inputs"].items() if now.get(k) != v]
    if ch:
        raise SystemExit("замороженные входы изменились после spec: %s" % ", ".join(ch))
    ch = [c for c, v in sp["code"].items() if file_sha(c) != v]
    if ch:
        raise SystemExit("код изменился после spec: %s" % ", ".join(ch))
    sp["sha256"] = file_sha(path)
    return sp


# ---------------------------------------------------------------- discover (holdout V4)

def do_discover(out=OUT):
    lock = p(out, "found_v4.lock.json")
    if os.path.exists(lock):
        raise SystemExit("доводы holdout V4 уже посчитаны и заморожены: %s" % lock)
    sp = load_spec(out)
    keys = hv.keys_of(hv.load_holdout(V4H))
    t0 = time.time()
    ctx = ae2.ctx_places()
    edges = {"AG": v6.run_ag(ctx, keys), "TC": [], "RC": []}
    W, Fp = tc.Windows(ctx), arc.Footprints(ctx)
    for i, k in enumerate(keys):
        edges["TC"] += tc.discover(W, k)
        edges["RC"] += arc.discover(Fp, k)
        if (i + 1) % 20 == 0:
            print("  %d/%d кадров, %.0f с" % (i + 1, len(keys), time.time() - t0), flush=True)
    path = p(out, "found_v4.json")
    ir.dump_json(path, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": sp["sha256"], "keys": keys,
                        "edges": edges, "note": "существующие детекторы на 80 кадрах holdout V4; доводы CANDIDATE; "
                                                "RC переписывается в REPEATED_ASSEMBLY_RELATION при сборке "
                                                "утверждений; VERIFIED ставит человек"})
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": sp["sha256"],
                        "path": path.replace(os.sep, "/"), "sha256": file_sha(path)})
    print("доводы holdout V4: %s, %.0f с" % ({k: len(v) for k, v in edges.items()}, time.time() - t0))


def load_found_v4(out=OUT):
    lk = ir.load_json(p(out, "found_v4.lock.json"))
    if file_sha(lk["path"]) != lk["sha256"]:
        raise SystemExit("found_v4.json изменён после заморозки")
    return ir.load_json(lk["path"])


# ---------------------------------------------------------------- report

CONTROL_MAP = {"dangerous_creative_standalone": ("PRE_REVIEW_DANGEROUS", "dangerous_creative_standalone"),
               "relation_existence_precision": ("relation_existence_precision",),
               "derived_recolor_discovery": ("derived_recolor_discovery",), "state_discovery": ("state_discovery",),
               "true_composite_recall": ("true_composite_recall", "composite_discovery_recall",
                                         "composite_pair_recall"),
               "automatic_action_precision": ("automatic_action_precision",)}


def control(res, frozen_report, post=None):
    """Повтор замороженного отчёта: значения и n легаси-ворот; POST, если он в отчёте есть."""
    fg = {g["gate"]: (g["value"], g.get("n")) for g in frozen_report["gates"]}
    out = {}
    for mine, names in CONTROL_MAP.items():
        for nm in names:
            if nm in fg:
                out[mine] = res["legacy"][mine] == fg[nm]
                break
    if post is not None:
        out["POST_REVIEW_DANGEROUS"] = res["pp"]["POST_REVIEW_DANGEROUS"] == post
    return out


def tinfo_of(ctx):
    tname = {0: "floor", 1: "wall", 2: "wall", 3: "object"}

    def tinfo(k):
        i = ctx.info(k)
        return tname.get(i.get("tile_type"), "none") if i.get("rec") else "none"
    return tinfo


def run_v5(tinfo):
    d, h = h5.load_freeze(V5H), h5.load_holdout(V5H)
    if h5.code_changed(d):
        raise SystemExit("замороженный код V5 изменён: %s" % h5.code_changed(d))
    T, trow, _lk = h5.load_truth(V5H)
    ans = {r["asset_id"]: r for r in ir.read_tsv(p(V5H, "answers_vitali.tsv"))}
    keys = h5.keys_of(h)
    found3, found4, found5 = h5.load_found(V5H)
    base_r = hv.routing_base(V5H, d, h)
    rows = hv.routing_rows(base_r, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    items = ir.load_json(p(V5H, "key.json"))["items"]
    args = (T, items, keys, h, base_r["fsets"])
    none_pairs = prs.closed_none(*h5.closed_none_sources(V5H))
    fg = v6.load_group(V6D)["edges"]
    fe = ae2.load_found(AE2D)["edges"]
    rc_e, tc_e = fe["ASSEMBLY_REPEATED_COMPONENT_V1"], fe["TWO_COMPONENT_ASSEMBLY_V1"]
    sys_edges = {"V5 frozen": found5["edges"], "V6_PREP": found5["edges"] + fg,
                 "V2_PREP (RC как COMPOSITE)": found5["edges"] + fg + rc_e + tc_e,
                 "V7 model": found5["edges"] + fg + tc_e + [reclass_rc(e) for e in rc_e]}
    out = {}
    for name in SYSTEMS["V5"]:
        C = h5.system_claims(rows, found3, found4, sys_edges[name])
        out[name] = evaluate_v7(rows, C, args, trow, keys, none_pairs, tinfo)
    rep = {n: ir.load_json(FROZEN[k]) for n, k in (("V5 frozen", "v5_report"), ("V6_PREP", "v6_report"),
                                                    ("V2_PREP (RC как COMPOSITE)", "ae2_report"))}
    posts = {"V5 frozen": rep["V5 frozen"]["post_review"]["POST_REVIEW_DANGEROUS"],
             "V6_PREP": len(rep["V6_PREP"]["dangerous"]["post_with_ag"]),
             "V2_PREP (RC как COMPOSITE)": len(rep["V2_PREP (RC как COMPOSITE)"]["dangerous"]["post_new"])}
    ctl = {n: control(out[n], rep[n], posts[n]) for n in rep}
    ctl["V6_PREP"]["composite_frame_recall"] = (
        out["V6_PREP"]["diagnostic"]["composite_frame_subtype_recall"]["value"] ==
        {g["gate"]: g["value"] for g in rep["V6_PREP"]["gates"]}["composite_frame_recall"])
    return out, ctl, {"keys": len(keys), "rc_edges": len(rc_e), "tc_edges": len(tc_e), "ag_edges": len(fg)}


def run_v4(tinfo, fv4):
    import ar_boundary_validation as bv
    import v5_freeze_readiness as vfr
    rc.check_freeze()
    rd5.check_freeze()
    d, h = hv.load_freeze(V4H), hv.load_holdout(V4H)
    if hv.code_changed(d):
        raise SystemExit("замороженный код V4 изменён: %s" % hv.code_changed(d))
    T, _lk = hv.load_truth(V4H)
    trow = {h5.pk(r["a"], r["b"]): r for r in ir.load_json(p(V4H, "truth.json"))["pairs"]}
    ans = {r["asset_id"]: r for r in ir.read_tsv(p(V4H, "answers_vitali.tsv"))}
    keys = hv.keys_of(h)
    if sorted(keys) != sorted(fv4["keys"]):
        raise SystemExit("ключи found_v4 не совпадают с holdout V4")
    found3, found4 = hv.load_found(V4H)
    base_r = hv.routing_base(V4H, d, h)
    rows = hv.routing_rows(base_r, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    items = ir.load_json(p(V4H, "key.json"))["items"]
    args = (T, items, keys, h, base_r["fsets"])
    _V, _by_pair, vrows = vfr.validation()
    bv.check_freeze()
    brows = ir.load_json(bv.p("truth.json"))["pairs"]
    none_pairs = prs.closed_none(*rc.truth_sources(T, vrows, brows))
    edges_r, _dropped = rc.edges_ar2(rd5.load_found5(), rc.load_found_ar2())
    E = fv4["edges"]
    out = {"V4 frozen": evaluate_v7(rows, hv.system_claims(rows, found3, found4), args, trow, keys, none_pairs,
                                    tinfo),
           "V5 recount (AR2)": evaluate_v7(rows, rc.claims(rows, found3, found4, edges_r), args, trow, keys,
                                           none_pairs, tinfo),
           "V7 model": evaluate_v7(rows, rc.claims(rows, found3, found4, edges_r + E["AG"] + E["TC"] +
                                                   [reclass_rc(e) for e in E["RC"]]),
                                   args, trow, keys, none_pairs, tinfo)}
    r4, rr = ir.load_json(FROZEN["v4_report"]), ir.load_json(FROZEN["v5_recount_report"])
    ctl = {"V4 frozen": control(out["V4 frozen"], r4),
           "V5 recount (AR2)": control(out["V5 recount (AR2)"], rr, rr["post_review"]["POST_REVIEW_DANGEROUS"])}
    return out, ctl, {"keys": len(keys), "ag_edges": len(E["AG"]), "tc_edges": len(E["TC"]),
                      "rc_edges": len(E["RC"])}


def overall(v5, v4_):
    """VERDICT_RULE по таблицам ворот модели V7 на двух наборах."""
    sts = []
    for g in v5["gates"]:
        sts.append(g["status"])
    for g in v4_["gates"]:
        if g["group"] == "review" and g["status"] in ("INSUFFICIENT_SAMPLE", "NO_DATA"):
            continue
        sts.append(g["status"])
    if "FAIL" in sts:
        return "FAIL"
    return "PASS" if all(s == "PASS" for s in sts) else "INCONCLUSIVE"


def slim(r):
    return {"verdict": r["verdict"], "gates": r["gates"], "frame_safety": r["frame_safety"],
            "diagnostic": r["diagnostic"], "dangerous_pre": r["pp"]["pre_dangerous"],
            "dangerous_post": r["pp"]["post_dangerous"], "unmasked": r["pp"]["unmasked"]}


def do_report(out=OUT):
    if os.path.exists(p(out, "report.json")):
        raise SystemExit("пересчёт уже сделан (один раз): %s" % p(out, "report.json"))
    sp = load_spec(out)
    fv4 = load_found_v4(out)
    if fv4["spec_sha256"] != sp["sha256"]:
        raise SystemExit("found_v4 посчитан не по этому spec")
    t0 = time.time()
    tinfo = tinfo_of(ae2.ctx_places())
    r5, c5, n5 = run_v5(tinfo)
    r4, c4, n4 = run_v4(tinfo, fv4)
    bad = ["%s / %s: %s" % (ds, s, [k for k, v in c.items() if not v]) for ds, cc in (("V5", c5), ("V4", c4))
           for s, c in cc.items() if not all(c.values())]
    if bad:
        raise SystemExit("контроль не прошёл - системы не повторяют замороженные отчёты: %s" % "; ".join(bad))
    verdict = overall(r5["V7 model"], r4["V7 model"])
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE, "spec_sha256": sp["sha256"],
           "verdict": verdict, "verdict_rule": VERDICT_RULE,
           "v7": {"holdout V5": slim(r5["V7 model"]), "holdout V4": slim(r4["V7 model"])},
           "history": {"holdout V5": {n: slim(r5[n]) for n in SYSTEMS["V5"] if n != "V7 model"},
                       "holdout V4": {n: slim(r4[n]) for n in SYSTEMS["V4"] if n != "V7 model"}},
           "control": {"holdout V5": c5, "holdout V4": c4}, "inputs": {"holdout V5": n5, "holdout V4": n4},
           "frozen_verdicts_unchanged": {"V6_PREP": ir.load_json(FROZEN["v6_report"])["verdict"],
                                         "ASSEMBLY_EVIDENCE_V2_PREP": ir.load_json(FROZEN["ae2_report"])["verdict"]},
           "seconds": round(time.time() - t0)}
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    g = {x["gate"]: x for x in r5["V7 model"]["gates"]}
    g4 = {x["gate"]: x for x in r4["V7 model"]["gates"]}
    print("%s: %s; related_frame_safety_recall V5 %s (n %s), V4 %s (n %s); отчёт %s" % (
        PROFILE, verdict, hv.f3(g["related_frame_safety_recall"]["value"]), g["related_frame_safety_recall"]["n"],
        hv.f3(g4["related_frame_safety_recall"]["value"]), g4["related_frame_safety_recall"]["n"],
        p(out, "report.md")))
    return res


def write_md(out, res):
    f3 = hv.f3
    L = ["# RELATION_SAFETY_MODEL_V7_PREP", "",
         "Вердикт: **%s**. Новых детекторов нет; REPEATED_COMPONENT переписан в REPEATED_ASSEMBLY_RELATION "
         "(CANDIDATE, TYPE_OPEN, без голоса в составном). V6_PREP и ASSEMBLY_EVIDENCE_V2_PREP остаются %s / %s." % (
             res["verdict"], res["frozen_verdicts_unchanged"]["V6_PREP"],
             res["frozen_verdicts_unchanged"]["ASSEMBLY_EVIDENCE_V2_PREP"]), "",
         "Правило вердикта: " + res["verdict_rule"], "",
         "## Модель V7: ворота", "",
         "| группа | ворота | holdout V5 | n | итог | holdout V4 | n | итог | нужно |",
         "|---|---|---|---|---|---|---|---|---|"]
    a, b = res["v7"]["holdout V5"]["gates"], res["v7"]["holdout V4"]["gates"]
    for x, y in zip(a, b):
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            x["group"], x["gate"], f3(x["value"]), x["n"], x["status"], f3(y["value"]), y["n"], y["status"],
            x["need"]))
    L += ["", "## История: те же ворота на прежних замороженных системах (калибровка, не вердикт)", "",
          "| набор | система | PRE | POST | existence | frame safety | n | automatic | derived | state | ASM cand | "
          "ASM strong | вердикт |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for ds in ("holdout V4", "holdout V5"):
        sysd = dict(res["history"][ds], **{"V7 model": res["v7"][ds]})
        for nm, r in sysd.items():
            g = {x["gate"]: x for x in r["gates"]}
            L.append("| %s | %s | %s |" % (ds, nm, " | ".join(
                [f3(g[k]["value"]) for k in ("PRE_REVIEW_DANGEROUS", "POST_REVIEW_DANGEROUS",
                                             "relation_existence_precision", "related_frame_safety_recall")] +
                [str(g["related_frame_safety_recall"]["n"])] +
                [f3(g[k]["value"]) for k in ("automatic_action_precision", "derived_recolor_discovery",
                                             "state_discovery", "ASSEMBLY_candidate_existence_precision",
                                             "ASSEMBLY_STRONG_composite_precision")] + [r["verdict"]])))
    for ds in ("holdout V5", "holdout V4"):
        r = res["v7"][ds]
        fs, dg = r["frame_safety"], r["diagnostic"]
        L += ["", "## %s, модель V7: подробности" % ds, "",
              "- related_frame_safety_recall %s (%d из %d); лучшее действие по кадрам %s" % (
                  f3(fs["value"]), fs["hit"], fs["n"], fs["by_best_action"]),
              "- варианты (диагностика): только BLOCK+REVIEW %s; только значимые пары %s; кадры с закрытым значимым "
              "ярлыком %s (n %d)" % (f3(fs["variant_block_review_only"]), f3(fs["variant_relevant_pair_only"]),
                                    f3(fs["variant_closed_relevant_frames"]["value"]),
                                    fs["variant_closed_relevant_frames"]["n"]),
              "- composite pair recall %s (n %s), composite frame subtype recall %s (n %s), composite STRONG %s" % (
                  f3(dg["composite_pair_recall"]["value"]), dg["composite_pair_recall"]["n"],
                  f3(dg["composite_frame_subtype_recall"]["value"]), dg["composite_frame_subtype_recall"]["n"],
                  {k: (f3(v) if isinstance(v, float) else v) for k, v in dg["composite_strong_recall"].items()}),
              "- module recall: %s" % dg["module_recall"],
              "- handoff_unassigned: %s" % dg["handoff_unassigned"],
              "- детекторы сборки, существование на парах пула: %s" % dg["assembly_family_existence"],
              "- опасные до/после ревью: %s / %s" % (r["dangerous_pre"] or "нет", r["dangerous_post"] or "нет")]
        L += ["- пары с REPEATED_ASSEMBLY_RELATION:"] + ["  - " + x for x in dg["rar_pairs"]] if dg["rar_pairs"] else \
            ["- пар с REPEATED_ASSEMBLY_RELATION в пуле нет"]
        L += ["- промахи frame safety:"] if fs["missed"] else ["- промахов frame safety нет"]
        for f, prs_ in fs["missed"].items():
            L.append("  - %s: %s" % (f, "; ".join("%s %s %s" % (x["other"], x["truth"], x["claims"] or "")
                                                  for x in prs_)))
    L += ["", "## Контроль", "", "Системы без изменений повторяют замороженные отчёты: %s" % res["control"], "",
          "VERIFIED ставит только человек."]
    with open(p(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")


def do_check(out=OUT):
    sp = load_spec(out)
    if os.path.exists(p(out, "found_v4.lock.json")):
        load_found_v4(out)
    print("spec %s цел; замороженные входы и код не менялись" % sp["sha256"][:12])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("spec", "discover", "report", "check"))
    a = ap.parse_args()
    {"spec": do_spec, "discover": do_discover, "report": do_report, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
