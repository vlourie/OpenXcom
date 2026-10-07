#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""RELATION_DISCOVERY_V5 - заморозка и новый слепой holdout (специалист 02.10, передал Vitali в чате). CPU.

Решение: «разрешаю freeze V5. После freeze - новый blind holdout. Ни AR2, ни ASSEMBLY, ни thresholds больше не
менять до окончательного verdict нового holdout». Система V5 - как в один пересчёт V5_AR2_RECOUNT_V1: маршрут V8,
V3 (с V2), V4, ASSEMBLY_DISCOVERY_V1 и ALIGNED_RECOLOR_V2 (границы >= 0.70; ниже - NOT VALIDATED), классы доводов
v5_ar2_recount.V5AR2Claims, безопасность после ревью post_review_safety. Замороженные модули только читаются.

FREEZE.json пишется ДО отбора: хэши кода (V2-V5, AR1/AR2, ASM, post_review_safety, пересчёт, готовность, проверки
компонентов и полосы, таксономия, истина v2, holdout V4 с эталоном, маршрут V8, этот модуль и тесты), параметры AR2 и
ASM, политика AR2, «AR2 boundary < 0.70 = NOT VALIDATED», десять ворот и N_MIN, определения диагностики, слои,
зерно, правило исключений с замером пула, правило пар, входы с хэшами, хэши источников разработки, условия готовности.

Ворота (десять; доля с закрытыми случаями меньше N_MIN = 10 - INSUFFICIENT_SAMPLE):
PRE_REVIEW_DANGEROUS = 0, POST_REVIEW_DANGEROUS = 0, relation_existence_precision >= 0.95,
derived_recolor_discovery >= 0.70, state_discovery >= 0.70, composite_discovery_recall >= 0.70,
automatic_action_precision >= 0.95, ASSEMBLY_candidate_existence_precision >= 0.95,
ASSEMBLY_STRONG_composite_precision >= 0.95, handoff_unassigned = 0.

Отбор: около 80 новых кадров; кадры holdout V4 и V5-разработки и development keys исключены из целей по ключу (их
родня - только кандидат пары, не цель). Недобор слоя НЕ переносится в другие слои - пишется до ответов.

    pools      до заморозки: размеры пулов (без детекторов)
    freeze     снимок -> FREEZE.json
    select     ленивый проход AR2 / ASM по очереди и отбор -> holdout.json
    relations  замороженные детекторы на кадрах: маршрут V8, V3, V4, AR2 (с перемешанным контролем), ASM -> замок
    cards      страница оси A для специалиста
    pairs      пул пар эталона (key.json вне пакета)
    pack       слепой пакет в нейтральной папке PACK (два судьи на пару)
    lockref    эталон из ответов судей и машинных фактов - до ответов оси A
    verify     замок эталона цел
    report     десять ворот, PRE/POST, обязательная диагностика
    check      хэши целы

    py -3.13 tools/hdart/relation_holdout_v5.py <команда>
VERIFIED ставит только человек.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aligned_recolor_v2 as ar2                  # noqa: E402
import assembly_discovery_v1 as asm               # noqa: E402
import identity_routing as ir                     # noqa: E402
import post_review_safety as prs                  # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_discovery_v5 as rd5               # noqa: E402
import relation_holdout_v4 as hv                  # noqa: E402   (импорт ставит h7.SEED = зерно V4 - ниже своё)
import relation_taxonomy as tx                    # noqa: E402
import routing_holdout as rh                      # noqa: E402
import routing_holdout_v7 as h7                   # noqa: E402
import routing_holdout_v8 as h8                   # noqa: E402
import v5_ar2_recount as rc                       # noqa: E402

ENC = ir.ENC
PROFILE = "RELATION_DISCOVERY_V5_HOLDOUT"
OUT = os.path.join(ir.PROBES, "relation-holdout-v5")
PACK = os.path.join(ir.PROBES, "pairset-1002")       # слепой пакет судей: имя папки нейтральное (DECISIONS 02.10)
SEED = "relation-holdout-v5-2026-10-02"
h7.SEED = SEED                       # ленивые пулы h7.pools берут зерно из своего модуля; код V7/V8 не меняется
N_TOTAL = 80
N_MIN = 10
EDGE_STRONG = "STRONG"   # уровень довода (v2.edge); v4.STRONG = RELATED_STRONG - уровень существования утверждения
INPUTS = dict(hv.INPUTS)
SELF = "tools/hdart/relation_holdout_v5.py"
CODE = [SELF, "tools/test_relation_holdout_v5.py",
        "tools/hdart/aligned_recolor_v2.py", "tools/test_aligned_recolor_v2.py",
        "tools/hdart/aligned_recolor_v1.py", "tools/test_aligned_recolor_v1.py",
        "tools/hdart/assembly_discovery_v1.py", "tools/test_assembly_discovery_v1.py",
        "tools/hdart/post_review_safety.py", "tools/test_post_review_safety.py",
        "tools/hdart/v5_ar2_recount.py", "tools/test_v5_ar2_recount.py",
        "tools/hdart/relation_discovery_v5.py", "tools/test_relation_discovery_v5.py",
        "tools/hdart/v5_freeze_readiness.py", "tools/hdart/v5_component_validation.py",
        "tools/test_v5_component_validation.py", "tools/hdart/ar_boundary_validation.py",
        "tools/hdart/relation_holdout_v4_ref.py", "tools/hdart/relation_holdout_v4_axis_zip.py"] + list(hv.CODE)
DEV_SOURCES = {
    "v4_holdout": os.path.join(hv.OUT, "holdout.json"),
    "v4_relations_lock": os.path.join(hv.OUT, "relations.lock.json"),
    "v4_key": os.path.join(hv.OUT, "key.json"),
    "v4_reference_lock": os.path.join(hv.OUT, "reference.lock.json"),
    "v4_truth": os.path.join(hv.OUT, "truth.json"),
    "component_validation_key": os.path.join(ir.PROBES, "v5-component-validation", "key.json"),
    "component_validation_truth": os.path.join(ir.PROBES, "v5-component-validation", "truth.json"),
    "ar_boundary_key": os.path.join(ir.PROBES, "ar-boundary-validation", "key.json"),
    "ar_boundary_truth": os.path.join(ir.PROBES, "ar-boundary-validation", "truth.json"),
    "v5_prep_found5": os.path.join(rd5.OUT, "found5.json"),
    "v5_ar2_found": os.path.join(rc.OUT, "found_ar2.json"),
    "v5_ar2_report": os.path.join(rc.OUT, "report.json"),
    "v5_readiness_report": os.path.join(ir.PROBES, "v5-freeze-readiness", "report.json")}
DEV_PAIR_KEYS = ("v4_key", "component_validation_key", "ar_boundary_key")
# закрытые независимые эталоны для POST_REVIEW (кроме своего): holdout V4, проверка компонентов, проверка полосы
NONE_SOURCES = (("holdout V4", "v4_truth"), ("V5 component validation", "component_validation_truth"),
                ("AR boundary validation", "ar_boundary_truth"))

EXCLUSION_RULE = (
    "цели holdout - новые кадры: исключены по КЛЮЧУ (кадр и asset_id) исключения V8 и V2-V4 (relation_holdout_v4."
    "exclusions: holdout V4_R1 / V5 / V7 / V8 с роднёй, истина v2, контроль, слепое зеркало, первый пакет), все 80 "
    "кадров holdout V4, их родня (relations, FR2, MCD), обе стороны пар пула V4, обе стороны пар проверки компонентов "
    "и проверки полосы AR, источники и цели доводов found5 (V5_PREP) и found_ar2 (пересчёт). Наборы PCK не "
    "исключаются. Родственники могут появиться только кандидатом пары (context / reference), не целью")
POOL_MEASUREMENT = {
    "date": "2026-10-02, до заморозки, скрипты блокнота сессии h5_pools.py / h5_pools2.py",
    "set_exclusion_as_v4": "наборы V4 с роднёй плюс ключи: строк очереди 21 в 13 наборах, квотами V4 отобралось 2 "
                           "из 80 - пул исчерпан",
    "key_only": "только ключи: строк очереди 3466 в 433 наборах, квотами V4 отбирается 80",
    "chosen": "key_only - формулировка специалиста «кадры и development keys»; исключение по ключу, а не по набору, "
              "специалист принял 02.10",
    "eligible_rows_with_key_exclusion": 3466,
    "eligible_sets_with_key_exclusion": 433,
    "would_select_with_whole_set_exclusion": "2/80"}
KNOWN_FROZEN_DEFECTS = [{
    "id": "KNOWN_FROZEN_DIAGNOSTIC_DEFECT",
    "text": "relation_discovery_v5.dev_summary misclassifies ASM STRONG due to constant mismatch. Affects diagnostic "
            "column only. Does not affect detector output, readiness gates, freeze criteria, or V5 acceptance logic. "
            "Frozen source is preserved unchanged. Correct interpretation is produced by relation_holdout_v5.py.",
    "where": "relation_discovery_v5.py dev_summary: e['level'] == STRONG, где STRONG = v4.STRONG = RELATED_STRONG, а "
             "уровень довода - 'STRONG'; столбец ASM STRONG в dev.json / dev.md V5_PREP всегда 0",
    "reach": "dev_summary зовёт только do_dev (dev.json, dev.md); ни evaluate, ни ворота, ни v5_freeze_readiness, ни "
             "relation_holdout_v5 dev.json не читают (проверено грепом 02.10)",
    "decided": "специалист 02.10, передал Vitali в чате: в frozen не исправлять, пометить в отчёте"}]

# слои: (имя, квота, ((подслой, квота), ...)); подслои с квотой 0 - только добор внутри слоя
LAYERS = (("ar2", 12, (("ar2", 12),)),
          ("asm_strong", 10, (("asm_strong", 10),)),
          ("asm_candidate", 10, (("asm_candidate", 10),)),
          ("mcd_state", 10, (("mcd_die", 4), ("mcd_alt", 2), ("mcd_anim", 2), ("mcd_dominance", 1),
                             ("mcd_candidate", 1))),
          ("standalone", 12, (("standalone", 12),)),
          ("composite", 10, (("part_suspect", 2), ("part_words", 2), ("composite", 4), ("modular_words", 2))),
          ("terrain", 2, (("relief", 1), ("floor", 1), ("object_or_relief", 0), ("surface_mcd", 0))),
          ("structural", 2, (("wall", 1), ("door", 1), ("stairs", 0), ("hull", 0), ("roof", 0), ("panel", 0),
                             ("vehicle_body", 0))),
          ("derived", 12, (("fr2_new", 3), ("fr2_verified", 2), ("legacy_recolor", 2), ("material_variant", 2),
                           ("family_mirror", 2), ("family_open", 1))))
DETECTOR_LAYERS = ("ar2", "asm_strong", "asm_candidate")
SCAN_MAX = 2500          # кадров очереди просмотреть AR2 / ASM не больше
SCAN_FOUND = 60          # слой детектора полон, когда кандидатов из разных наборов столько
SELECT_RULE = ("слои по порядку LAYERS (редкие первыми), подслои по порядку, внутри - зерно SEED; ключ один раз, "
               "набор PCK один раз на весь holdout. Недобор подслоя добирается другими подслоями ТОГО ЖЕ слоя по кругу. "
               "Недобор слоя в другие слои НЕ переносится: пишется в holdout.json до ответов, ворота с малой выборкой "
               "- INSUFFICIENT_SAMPLE. Слои детекторов: ленивый проход очереди по зерну SEED (ar2 - доводы AR2; "
               "asm_strong - довод ASM STRONG; asm_candidate - доводы ASM без STRONG) до SCAN_FOUND наборов на слой "
               "или SCAN_MAX кадров; AR2 перестаёт считаться, когда его слой полон")

AR2_POLICY = {"boundary": ar2.AR_BORDER, "existence": "STRONG",
              "subtype": "ALIGNED_RECOLOR / RECOLOR - OPEN (TYPE_OPEN, «AR2: подтип на ревью»)",
              "auto_action": "запрещено: автоматического действия перекраски нет",
              "not_validated": "AR2 boundary < 0.70 = NOT VALIDATED",
              "no_retune": "новый holdout не повод двигать порог: AR2, ASSEMBLY и пороги не меняются до "
                           "окончательного вердикта"}
ASM_POLICY = {"strong": "ASM STRONG - существование STRONG, группа composite",
              "candidate": "ASM CANDIDATE - кандидат существования, тип TYPE_OPEN",
              "params": asm.PARAMS}
POLICY = dict(hv.POLICY, claims_class="v5_ar2_recount.V5AR2Claims (TaxClaims поверх _Base5AR2): доводы V8, V3 "
                                      "(convert_v3 + self_roles), V4, ASM, AR2; AR1 нет",
              aligned_recolor_v2=AR2_POLICY, assembly=ASM_POLICY,
              post_review="post_review_safety.after_review: CANDIDATE на паре, закрытой NONE независимым эталоном, "
                          "удаляется; STRONG остаётся и пишется отдельно")
GATES = (("PRE_REVIEW_DANGEROUS", "count", 0), ("POST_REVIEW_DANGEROUS", "count", 0),
         ("relation_existence_precision", "rate", 0.95), ("derived_recolor_discovery", "rate", 0.70),
         ("state_discovery", "rate", 0.70), ("composite_discovery_recall", "rate", 0.70),
         ("automatic_action_precision", "rate", 0.95), ("ASSEMBLY_candidate_existence_precision", "rate", 0.95),
         ("ASSEMBLY_STRONG_composite_precision", "rate", 0.95), ("handoff_unassigned", "count", 0))
GATE_DEFS = {
    "PRE_REVIEW_DANGEROUS": "relation_holdout_v4.danger на всех доводах V5: творческий кадр при истинной связи",
    "POST_REVIEW_DANGEROUS": "то же после post_review_safety.after_review (closed NONE: свой эталон + holdout V4 + "
                             "проверка компонентов + проверка полосы AR)",
    "relation_existence_precision": "v4.metrics existence_precision: пары с доводом существования STRONG и закрытой "
                                    "истиной, доля RELATED",
    "derived_recolor_discovery": "v4.recall derived discovery_rate (RECOLOR_PEER / MIRRORED_VARIANT_PEER / DERIVED)",
    "state_discovery": "v4.recall state discovery_rate (STATE_VARIANT)",
    "composite_discovery_recall": "v4.recall composite discovery_rate (COMPOSITE, STRONG + CANDIDATE)",
    "automatic_action_precision": "v4.metrics auto_action_precision по relation_truth_v2.claim_state",
    "ASSEMBLY_candidate_existence_precision": "пары пула с доводом ASM и без ASM STRONG; закрытое существование, "
                                              "доля RELATED",
    "ASSEMBLY_STRONG_composite_precision": "пары пула с доводом ASM STRONG; подтип COMPOSITE по "
                                           "v5_component_validation.subtype (оба судьи - да, ни один - нет, один - "
                                           "OPEN; NONE - нет), доля «да» среди закрытых",
    "handoff_unassigned": "строки маршрута V8 с pipeline_target вне routing_model_v8.PIPELINES",
    "sample": "ворота-доли с закрытыми случаями меньше N_MIN = 10 - INSUFFICIENT_SAMPLE (и при FAIL); "
              "счётчики - PASS только при 0",
    "verdict": "FAIL - хоть одни ворота FAIL; иначе INCONCLUSIVE при INSUFFICIENT_SAMPLE или NO_DATA; иначе PASS"}
DIAG_DEFS = {
    "ar2": "triggered, closed related, closed none, open, helped dangerous (опасные без доводов AR2, не опасные с "
           "ними), false existence (довод AR2 на паре NONE), распределение границ (полосы 0.70-0.75 / 0.75-0.80 / "
           "0.80-0.90 / >=0.90), перемешанный контроль, вне пула",
    "asm_candidate": "triggered, accepted (RELATED), rejected (NONE), open, helped safety (опасные без доводов ASM "
                     "CANDIDATE, не опасные с ними), hurt (довод с claim_state wrong; кадры, ставшие опасными после "
                     "удаления ASM-кандидата ревью)",
    "asm_strong": "triggered, true composite, not composite, open (v5_component_validation.subtype)",
    "post_review": "удалено как CLOSED-NONE (по детекторам и источникам), STRONG на closed NONE, какие кадры стали "
                   "опасными после удаления - ключевой production invariant",
    "layers": "недобор слоёв (до ответов), опасные и творческие по слоям"}
AR2_BANDS = ((0.70, 0.75), (0.75, 0.80), (0.80, 0.90), (0.90, 9.0))
BODY = ("profile", "policy", "gates", "gate_defs", "n_min", "diag_defs", "seed", "n_total", "layers",
        "detector_layers", "scan", "select_rule", "exclusion_rule", "pool_measurement", "known_frozen_defects",
        "pair_rule", "pair_params",
        "ref_schema", "ref_addendum", "pack_dir", "struct_rx", "readiness", "dev_sources_sha256", "truth_v2",
        "detector_inputs_sha256", "inputs_source", "inputs", "input_sha256", "code_sha256")
file_sha = rh.file_sha
pset = rh.pset
pk = tx.pk


def p(out, *name):
    return os.path.join(out, *name)


def order(key):
    return hashlib.sha256((SEED + "|" + key).encode()).hexdigest()


def jsha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- freeze

def readiness_record():
    """Условия готовности к заморозке, как они прошли в пересчёте V5_AR2_RECOUNT_V1."""
    r = ir.load_json(DEV_SOURCES["v5_ar2_report"])
    return {"source": DEV_SOURCES["v5_ar2_report"].replace(os.sep, "/"),
            "sha256": file_sha(DEV_SOURCES["v5_ar2_report"]), "conditions": r["freeze_conditions"],
            "verdict": r["verdict"], "kitsune_fixed": r["kitsune"]["fixed"],
            "note": "восемь условий готовности (шесть ворот V5 и две точности ASSEMBLY) плюс POST_REVIEW_DANGEROUS"}


def freeze(out=OUT, inputs=None, code=None, truth=None):
    import relation_holdout_v4_ref as ref
    if os.path.exists(p(out, "FREEZE.json")):
        raise SystemExit("снимок уже заморожен: %s" % p(out, "FREEZE.json"))
    if os.path.exists(p(out, "holdout.json")):
        raise SystemExit("кадры уже отобраны - снимок после отбора не делается")
    inputs = inputs or INPUTS
    code = CODE if code is None else code
    missing = [c for c in code if not os.path.exists(c)] + [k for k, v in DEV_SOURCES.items() if not os.path.exists(v)]
    if missing:
        raise SystemExit("нет файлов: %s" % ", ".join(missing))
    if ar2.AR_BORDER != 0.70:
        raise SystemExit("AR2 boundary не 0.70")
    os.makedirs(p(out, "inputs"), exist_ok=True)
    snap = {}
    for k, src in inputs.items():
        dst = p(out, "inputs", os.path.basename(src))
        if os.path.exists(dst):
            raise SystemExit("в inputs/ два входа с именем %s" % os.path.basename(src))
        shutil.copyfile(src, dst)
        snap[k] = dst.replace(os.sep, "/")
    tpath = p(out, "inputs", "truth_v2.json")
    ir.dump_json(tpath, truth if truth is not None else hv.truth_v2_snapshot())
    body = {"profile": PROFILE, "policy": POLICY, "gates": [list(g) for g in GATES], "gate_defs": GATE_DEFS,
            "n_min": N_MIN, "diag_defs": DIAG_DEFS, "seed": SEED, "n_total": N_TOTAL,
            "layers": [[n, q, [list(s) for s in sub]] for n, q, sub in LAYERS],
            "detector_layers": list(DETECTOR_LAYERS), "scan": {"SCAN_MAX": SCAN_MAX, "SCAN_FOUND": SCAN_FOUND},
            "select_rule": SELECT_RULE, "exclusion_rule": EXCLUSION_RULE, "pool_measurement": POOL_MEASUREMENT,
            "known_frozen_defects": KNOWN_FROZEN_DEFECTS,
            "pair_rule": hv.PAIR_RULE + ". Утверждения системы - V5AR2Claims (V8, V3, V4, ASM, AR2); функции пула пар "
                                        "relation_holdout_v4 (порядок равных по его зерну)",
            "pair_params": {"EXACT_CAP": hv.EXACT_CAP, "NEIGH": hv.NEIGH, "COPLACE_TOP": hv.COPLACE_TOP,
                            "COPLACE_MIN": hv.COPLACE_MIN, "SIM_TOP": hv.SIM_TOP, "SIM_MIN": hv.SIM_MIN,
                            "CAND_TOTAL": hv.CAND_TOTAL, "CAND_MIN_INDEP": hv.CAND_MIN_INDEP,
                            "BATCH_PAIRS": hv.BATCH_PAIRS, "SEMANTIC_ALL": hv.SEMANTIC_ALL},
            "ref_schema": hv.REF_SCHEMA, "ref_addendum": dict(ref.ADDENDUM, n_min=N_MIN),
            "pack_dir": PACK.replace(os.sep, "/"),
            "struct_rx": {k: rx.pattern for k, rx in h7.STRUCT_RX.items()},
            "readiness": readiness_record(),
            "dev_sources_sha256": {k: file_sha(v) for k, v in DEV_SOURCES.items()},
            "truth_v2": {"path": tpath.replace(os.sep, "/"), "sha256": file_sha(tpath),
                         "use": "только исключение кадров разработки; в эталон holdout не идёт"},
            "detector_inputs_sha256": {k: file_sha(v) for k, v in hv.DETECTOR_INPUTS.items() if os.path.exists(v)},
            "inputs_source": {k: v.replace(os.sep, "/") for k, v in inputs.items()},
            "inputs": snap, "input_sha256": {k: file_sha(v) for k, v in snap.items()},
            "code_sha256": {c: file_sha(c) for c in code}}
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                decided="специалист 02.10, передал Vitali в чате: «разрешаю freeze V5. После freeze - новый blind "
                        "holdout. Ни AR2, ни ASSEMBLY, ни thresholds больше не менять до окончательного verdict "
                        "нового holdout»; AR2 boundary < 0.70 = NOT VALIDATED",
                rule="после заморозки ничего из этого не меняется до финального отчёта, даже если первые карточки "
                     "покажут очевидную дыру")
    ir.dump_json(p(out, "FREEZE.json"), data)
    print("V5 заморожен (sha256 %s): входов %d, файлов кода %d, источников разработки %d" % (
        data["sha256"][:12], len(snap), len(code), len(DEV_SOURCES)))
    return data


def load_freeze(out=OUT):
    d = ir.load_json(p(out, "FREEZE.json"))
    if ir.sha({k: d[k] for k in BODY}) != d["sha256"]:
        raise SystemExit("FREEZE.json изменён после заморозки: хэш не сходится")
    bad = [k for k, v in d["inputs"].items() if file_sha(v) != d["input_sha256"][k]]
    if file_sha(d["truth_v2"]["path"]) != d["truth_v2"]["sha256"]:
        bad.append("truth_v2")
    bad += [k for k, h in d["dev_sources_sha256"].items() if file_sha(DEV_SOURCES[k]) != h]
    if bad:
        raise SystemExit("снимок входов или источников разработки изменён: %s" % ", ".join(bad))
    return d


code_changed = hv.code_changed
guard = hv.guard
detectors_same = hv.detectors_same
live_same = hv.live_same


# ---------------------------------------------------------------- исключения и пулы

def dev_keys(inp, truth):
    """Ключи, которые не могут быть целью: исключения V4 по ключу плюс V4-holdout, его родня и V5-разработка."""
    import family_relation_v2 as fr2m
    import mcd_state as ms
    _ex_sets, ex_keys = hv.exclusions(inp, truth)
    fr2 = fr2m.load(inp["family_relation_v2"])
    mcd = ms.index(ir.load_json(inp["mcd_state"])["relations"])
    v4keys = {x["asset_id"].upper() for x in rh.load_holdout(hv.OUT)["items"]}
    rel = set()
    for _k, rs in rh.load_relations(hv.OUT).items():
        rel |= {r["relative"].upper() for r in rs}
    for k in v4keys:
        rel |= {e["relative"].upper() for e in fr2.get(k, [])}
        rel |= {x["relative"].upper() for x in mcd.get(k, [])}
    pairs = set()
    for name in DEV_PAIR_KEYS:
        for it in ir.load_json(DEV_SOURCES[name])["items"]:
            pairs |= {it["a"].upper(), it["b"].upper()}
    found = set()
    for name in ("v5_prep_found5", "v5_ar2_found"):
        for e in ir.load_json(DEV_SOURCES[name])["edges"]:
            found |= {e["source"].upper(), e["target"].upper()}
    ks = set(ex_keys) | v4keys | rel | pairs | found
    ks.discard("")
    return ks, {"v4_and_v8_exclusions": len(ex_keys), "v4_holdout": len(v4keys), "v4_relatives": len(rel),
                "dev_pair_sides": len(pairs), "v5_found_sides": len(found), "total": len(ks)}


def eligible(gen, ex_keys):
    return [r for r in gen if r["status"] != "SKIP" and r["key"].upper() not in ex_keys
            and r["asset_id"].upper() not in ex_keys]


def classify(e2, ea):
    """Слои детекторов кадра по доводам AR2 (e2) и ASM (ea)."""
    out = []
    if e2:
        out.append("ar2")
    if any(e["level"] == EDGE_STRONG for e in ea):
        out.append("asm_strong")
    elif ea:
        out.append("asm_candidate")
    return out


def scan(rows, discover_ar2, discover_asm, found=SCAN_FOUND, cap=SCAN_MAX, log=None):
    """Ленивый проход по очереди: rows по зерну, discover_* (ключ) -> доводы. -> (пулы слоёв детекторов, счётчики)."""
    pools = {L: [] for L in DETECTOR_LAYERS}
    sets = {L: set() for L in DETECTOR_LAYERS}
    stat = Counter()
    for r in sorted(rows, key=lambda r: order("scan|" + r["key"].upper()))[:cap]:
        if all(len(sets[L]) >= found for L in DETECTOR_LAYERS):
            break
        k = r["key"]
        stat["scanned"] += 1
        e2 = []
        if len(sets["ar2"]) < found:
            e2 = discover_ar2(k)
            stat["ar2_run"] += 1
        ea = discover_asm(k)
        for L in classify(e2, ea):
            if len(sets[L]) >= found and pset(k) not in sets[L]:
                continue
            es = e2 if L == "ar2" else ea
            note = "; ".join(sorted({"%s %s %s" % (e["rule"], e["level"], e["target"]) for e in es}))[:200]
            pools[L].append((k, r, note))
            sets[L].add(pset(k))
        if log and stat["scanned"] % 100 == 0:
            log("просмотрено %d: %s" % (stat["scanned"], {L: len(sets[L]) for L in DETECTOR_LAYERS}))
    stat.update({"found_" + L: len(sets[L]) for L in DETECTOR_LAYERS})
    return pools, dict(stat)


def select(pool, layers=LAYERS):
    """SELECT_RULE: слои по порядку, добор внутри слоя, без переноса недобора в другие слои."""
    pick, short, used_sets, used_keys = [], {}, set(), set()

    def cands(name):
        seen, res = set(), []
        for x in sorted(pool.get(name, []), key=lambda x: order(name + "|" + x[0].upper())):
            if x[0].upper() not in seen:
                seen.add(x[0].upper())
                res.append(x)
        return res

    def take(layer, name, it, extra=""):
        for k, r, note in it:
            if k.upper() in used_keys or pset(k) in used_sets:
                continue
            used_keys.add(k.upper())
            used_sets.add(pset(k))
            pick.append({"asset_id": k, "layer": layer, "sub": name, "family_asset": r["asset_id"],
                         "rank": int(r["rank"]), "kind": r["kind"], "action": r["action"],
                         "places": int(r["places"] or 0), "why_selected": note + extra})
            return True
        return False

    for layer, q, sub in layers:
        left = {name: iter(cands(name)) for name, _n in sub}
        got = Counter()
        for name, n in sub:
            while got[name] < n and take(layer, name, left[name]):
                got[name] += 1
            if got[name] < n:
                short[name] = "%d из %d (кандидатов %d)" % (got[name], n, len(cands(name)))
        while sum(got.values()) < q:
            moved = False
            for name, _n in sub:
                if sum(got.values()) >= q:
                    break
                if take(layer, name, left[name], " (добор слоя)"):
                    got[name] += 1
                    moved = True
            if not moved:
                short[layer] = "слой %d из %d - недобор, в другие слои не переносится" % (sum(got.values()), q)
                break
    pick.sort(key=lambda x: order("card|" + x["asset_id"].upper()))
    return pick, short


def do_pools(out=OUT):
    if os.path.exists(p(out, "FREEZE.json")):
        raise SystemExit("уже заморожено - пулы смотрит select")
    inp = dict(INPUTS)
    gen = ir.read_tsv(inp["generation"])
    ex, info = dev_keys(inp, hv.truth_v2_snapshot())
    rows = eligible(gen, ex)
    pool = h7.pools(inp, gen, set(), ex)
    print("исключено ключей %s; строк очереди %d в %d наборах" % (info, len(rows), len({pset(r["key"]) for r in rows})))
    for layer, q, sub in LAYERS:
        if layer in DETECTOR_LAYERS:
            print("%-13s %2d: ленивый проход AR2 / ASM при select" % (layer, q))
            continue
        print("%-13s %2d: %s" % (layer, q, ", ".join("%s %d/%d" % (s, len({x[0].upper() for x in pool.get(s, [])}), m)
                                                    for s, m in sub)))


def do_select(out=OUT):
    if os.path.exists(p(out, "holdout.json")):
        raise SystemExit("holdout уже отобран: перевыбор запрещён")
    d = load_freeze(out)
    guard(d)
    live_same(d)
    detectors_same(d)
    inp = d["inputs"]
    gen = ir.read_tsv(inp["generation"])
    truth = ir.load_json(d["truth_v2"]["path"])
    ex, info = dev_keys(inp, truth)
    t0 = time.time()
    pool = h7.pools(inp, gen, set(), ex)
    print("пулы метаданных %.0f с" % (time.time() - t0), flush=True)
    ctx = hv.ctx_v3()
    si, A = v4.SetIndex(ctx), asm.Assembly(ctx)
    det, stat = scan(eligible(gen, ex), lambda k: ar2.discover(ctx, si, k), lambda k: asm.discover(A, k),
                     log=lambda s: print(s, "%.0f с" % (time.time() - t0), flush=True))
    pool.update(det)
    items, short = select(pool)
    data = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"], "seed": SEED,
            "n": len(items), "n_target": N_TOTAL, "pool": {k: len(v) for k, v in pool.items()},
            "pool_sets": {k: len({pset(x[0]) for x in v}) for k, v in pool.items()}, "scan": stat,
            "short": short, "excluded_keys": info, "sha256": rh.digest(items), "items": items,
            "rule": "список заморожен до ответов и эталона; слой в карточку и пакет судьи не идёт; недобор слоёв "
                    "записан здесь до ответов и в другие слои не переносился"}
    ir.dump_json(p(out, "holdout.json"), data)
    print("отобрано %d из %d (sha256 %s): %s" % (len(items), N_TOTAL, data["sha256"][:12],
                                                 dict(Counter(x["layer"] for x in items))))
    print("проход детекторов:", stat)
    print("недобор:", short or "нет")
    return data


load_holdout = rh.load_holdout
keys_of = hv.keys_of


# ---------------------------------------------------------------- relations

def do_relations(out=OUT):
    lock = p(out, "relations.lock.json")
    if os.path.exists(lock):
        raise SystemExit("детекторы уже посчитаны и заморожены: %s" % lock)
    d, h = load_freeze(out), load_holdout(out)
    guard(d)
    live_same(d)
    detectors_same(d)
    import relation_probe as rp
    import routing_rules_v7 as v7
    keys = keys_of(h)
    ctx = rp.Ctx()
    rp.discover(ctx, keys, p(out, "relations"))
    path = p(out, "relations", "relations.json")
    rels = ir.load_json(path)["relations"]
    dpath = p(out, "relations", "detectors.json")
    ir.dump_json(dpath, v7.detect(ctx, d["inputs"], keys, rels))
    c3 = hv.ctx_v3()
    f3 = p(out, "relations", "relations_v3.json")
    ir.dump_json(f3, v3.discover(c3, keys))
    f4 = p(out, "relations", "relations_v4.json")
    ir.dump_json(f4, v4.discover(c3, keys))
    si, A = v4.SetIndex(c3), asm.Assembly(c3)
    edges, perm = [], []
    for a in keys:
        es = ar2.discover(c3, si, a)
        for e in es:
            fired = bool(ar2.pair(c3, si, e["source"], e["target"], B=v3.permuted(c3, e["target"], 7)))
            perm.append({"pair": [e["source"], e["target"]], "fired": fired})
        edges += es + asm.discover(A, a)
    f5 = p(out, "relations", "found_v5.json")
    ir.dump_json(f5, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "keys": keys, "edges": edges,
                      "ar2_permuted_control": perm, "note": "доводы AR2 и ASM; не маршрут; VERIFIED ставит человек"})
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"],
                        "holdout_sha256": h["sha256"], "relations_sha256": file_sha(path),
                        "path": path.replace(os.sep, "/"), "detectors_sha256": file_sha(dpath),
                        "detectors_path": dpath.replace(os.sep, "/"),
                        "v3_path": f3.replace(os.sep, "/"), "v3_sha256": file_sha(f3),
                        "v4_path": f4.replace(os.sep, "/"), "v4_sha256": file_sha(f4),
                        "v5_path": f5.replace(os.sep, "/"), "v5_sha256": file_sha(f5)})
    print("детекторы заморожены: AR2 %d, ASM %d (STRONG %d); перемешанный контроль AR2 %d из %d" % (
        sum(e["detector"] == ar2.DETECTOR for e in edges), sum(e["detector"] == asm.DETECTOR for e in edges),
        sum(e["detector"] == asm.DETECTOR and e["level"] == EDGE_STRONG for e in edges),
        sum(x["fired"] for x in perm), len(perm)))


def load_found(out=OUT):
    lk = ir.load_json(p(out, "relations.lock.json"))
    for k in ("v3", "v4", "v5"):
        if file_sha(lk[k + "_path"]) != lk[k + "_sha256"]:
            raise SystemExit("%s изменён после заморозки" % lk[k + "_path"])
    return ir.load_json(lk["v3_path"]), ir.load_json(lk["v4_path"]), ir.load_json(lk["v5_path"])


def system_claims(rows, found3, found4, edges):
    return rc.claims(rows, found3, found4, edges)


# ---------------------------------------------------------------- карточки оси A

def do_cards(out=OUT):
    import routing_model_v8 as v8
    d, h = load_freeze(out), load_holdout(out)
    guard(d)
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("ответы уже есть - карточки не перестраиваются")
    ic, cards = rh.build_cards(out, h["items"], d["inputs"])
    data = [dict(c) for c in cards]
    title = "Holdout маршрута: 40 новых предметов"
    if title not in rh.PAGE_V:
        raise SystemExit("заголовок страницы V4_R1 не найден - страница сказала бы «40»")
    page = (rh.PAGE_V.replace(title, "Holdout связей V5: %d новых кадров - только ось A" % len(cards))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__MISS__", json.dumps(ic.MISSING)).replace("__SEM__", json.dumps(v8.SEMANTIC))
            .replace("__DEFS__", json.dumps({"semantic_kind": h8.SEM_DEFS}, ensure_ascii=False))
            .replace("__KEY__", "relation-holdout-v5-" + h["sha256"][:8]))
    with open(p(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    ir.dump_json(p(out, "cards.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "holdout_sha256": h["sha256"], "img_sha256": ir.img_digest(p(out, "img")),
                                        "assets": [c["asset"] for c in cards], "cards": data})
    print("карточек %d: %s" % (len(cards), p(out, "index.html")))


# ---------------------------------------------------------------- пул пар

def dev_pairs():
    """Пары разработки, которых не должно быть в пуле: ключи пар V4, проверки компонентов, проверки полосы."""
    out = set()
    for name in DEV_PAIR_KEYS:
        out |= {pk(it["a"], it["b"]) for it in ir.load_json(DEV_SOURCES[name])["items"]}
    return out


def do_pairs(out=OUT):
    if os.path.exists(p(out, "key.json")):
        raise SystemExit("пул пар уже построен: %s" % p(out, "key.json"))
    d, h = load_freeze(out), load_holdout(out)
    guard(d)
    live_same(d)
    detectors_same(d)
    keys = keys_of(h)
    found3, found4, found5 = load_found(out)
    base = hv.routing_base(out, d, h)
    claimed, exact_claimed = defaultdict(set), defaultdict(set)
    for sk in hv.SEMANTIC_ALL:                       # утверждения при любом ответе оси A
        rows = hv.routing_rows(base, lambda a, sk=sk: sk)
        C = system_claims(rows, found3, found4, found5["edges"])
        for a in keys:
            for c in C.of(a):
                b = [x for x in c["pair"] if x != a.upper()][0]
                if all(e["type"] in v3.EXACT_TYPES for e in c["support"]):
                    exact_claimed[a.upper()].add(b)
                else:
                    claimed[a.upper()].add(b)
    ctx = hv.ctx_v3()
    items, seen, per_item = [], {}, {}
    for a in keys:
        A = a.upper()
        mrel = {x["relative"].upper() for x in base["fsets"][A]}
        byte = set(ctx.ix.exact(a)) | set(ctx.ix.mirror(a))
        sd, sm = hv.similar(ctx, a)
        indep = [("neighbour", hv.neighbours(ctx, a)), ("coplace", hv.coplace(ctx, a)), ("similar", sd),
                 ("similar_mirror", sm)]
        prs_, must = hv.item_pairs(a, claimed[A], exact_claimed[A] - claimed[A], mrel, byte, indep)
        per_item[A] = {"pairs": len(prs_), "must": must, "claimed": len(claimed[A]),
                       "exact_claimed": len(exact_claimed[A] - claimed[A])}
        for b, why in prs_:
            k = pk(A, b)
            if k in seen:
                items[seen[k]]["items"].append(A)
                items[seen[k]]["why"] = sorted(set(items[seen[k]]["why"]) | set(why))
                continue
            seen[k] = len(items)
            items.append({"a": A, "b": b, "items": [A], "why": sorted(why)})
    items.sort(key=lambda it: order("q|" + it["a"] + "|" + it["b"]))
    for i, it in enumerate(items, 1):
        it["q"] = "Q%03d" % i
    truth = ir.load_json(d["truth_v2"]["path"])
    old = {pk(x["a"], x["b"]) for x in truth["pairs"]} | dev_pairs()
    overlap = [it["q"] for it in items if pk(it["a"], it["b"]) in old]
    if overlap:
        raise SystemExit("пары пула уже были в разработке (истина v2, V4, проверки): %s" % overlap[:10])
    ir.dump_json(p(out, "key.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "holdout_sha256": h["sha256"],
                                      "rule": d["pair_rule"], "per_item": per_item, "items": items,
                                      "note": "ключ вне пакета: источник пары судье не показывается"})
    print("пар %d (обязательных %d, независимых %d); на кадр: мин %d, макс %d" % (
        len(items), sum(v["must"] for v in per_item.values()),
        sum(v["pairs"] - v["must"] for v in per_item.values()),
        min(v["pairs"] for v in per_item.values()), max(v["pairs"] for v in per_item.values())))
    print("по источникам:", dict(Counter(w for it in items for w in it["why"])))


# ---------------------------------------------------------------- слепой пакет в нейтральной папке

def write_pack(out, pack, items, batches, salt):
    """Как relation_truth_v2.write_pack с judges_per_item 2, но пакет и ответы в pack, ключ - в out."""
    import relation_truth_v2 as tv
    import routing_model_v8 as v8
    if os.path.exists(p(pack, "answers")) and os.listdir(p(pack, "answers")):
        raise SystemExit("ответы уже есть - пакет не перестраивается")
    blind = p(pack, "blind")
    os.makedirs(blind, exist_ok=True)
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))
    mcd = v8.Mcd(ctx.world)
    with open(p(blind, "JUDGE.md"), "w", encoding=ENC, newline="\n") as f:
        f.write(tv.JUDGE)
    entries = []
    t0 = time.time()
    for it in items:
        q, a, b = it["q"], it["a"], it["b"]
        L, (pa, pb, cnt, blocks) = tx.facts(ctx, mcd, a, b)
        tv.pair_image(ctx, a, b).save(p(blind, q + "_pair.png"))
        mi = tx.map_image(ctx, a, b, pa, pb, cnt, blocks)
        files = [q + "_pair.png"]
        if mi is not None:
            mi.save(p(blind, q + "_map.png"))
            files.append(q + "_map.png")
        entries.append({"q": q, "files": files, "facts": L})
        if len(entries) % 50 == 0:
            print("%d пар %.0f с" % (len(entries), time.time() - t0), flush=True)
    os.makedirs(p(pack, "answers"), exist_ok=True)
    n = len(entries)
    per = batches // 2
    parts = []
    for j in range(2):
        es = entries if j == 0 else sorted(entries, key=lambda e: tv.order(e["q"], salt + "|judge%d" % j))
        for i in range(per):
            parts.append(es[i * n // per:(i + 1) * n // per])
    for i, part in enumerate(parts):
        ans = os.path.abspath(p(pack, "answers", "judge_%d.tsv" % (i + 1))).replace(os.sep, "/")
        L = ["# Batch %d of %d: %d pairs" % (i + 1, len(parts), len(part)), "",
             "Instructions and label definitions: JUDGE.md in this folder. Write your answers to:", "",
             "    " + ans, "", "Images are in this folder.", ""]
        for e in part:
            L += ["## " + e["q"], "", "Images: " + ", ".join(e["files"]), ""] + ["- " + x for x in e["facts"]] + [""]
        with open(p(blind, "batch_%d.md" % (i + 1)), "w", encoding=ENC, newline="\n") as f:
            f.write("\n".join(L))
    pack_sha = {f: v2.file_sha(p(blind, f)) for f in sorted(os.listdir(blind))}
    lock = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "key_sha256": v2.file_sha(p(out, "key.json")),
            "pack_dir": pack.replace(os.sep, "/"), "batches": [[e["q"] for e in part] for part in parts],
            "files": len(pack_sha), "pack_sha256": ir.sha(pack_sha)}
    ir.dump_json(p(out, "pack.lock.json"), lock)
    print("пакет: %d пар, %d файлов, партий %d -> %s" % (n, len(pack_sha), len(parts), pack))
    return lock


def do_pack(out=OUT, pack=PACK):
    d = load_freeze(out)
    guard(d)
    key = ir.load_json(p(out, "key.json"))
    if os.path.exists(p(out, "pack.lock.json")):
        raise SystemExit("пакет уже собран: %s" % p(out, "pack.lock.json"))
    n = len(key["items"])
    write_pack(out, pack, [{"q": it["q"], "a": it["a"], "b": it["b"]} for it in key["items"]],
               2 * math.ceil(n / hv.BATCH_PAIRS), SEED)


def pack_of(out):
    return ir.load_json(p(out, "pack.lock.json"))["pack_dir"]


# ---------------------------------------------------------------- эталон

def build_truth(out):
    """Истина как relation_holdout_v4_ref.build: два судьи (relation_truth_v2.combine_pair) и машинные факты."""
    import relation_holdout_v4_ref as ref
    import relation_truth_v2 as tv
    import routing_model_v8 as v8
    key = ir.load_json(p(out, "key.json"))
    plock = ir.load_json(p(out, "pack.lock.json"))
    js, bad = tv.read_by_judge(plock["pack_dir"], plock)
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))
    mcd = v8.Mcd(ctx.world)
    rows, missing = [], []
    for it in key["items"]:
        q = it["q"]
        got = [x for x in js.get(q, []) if x["answered"]]
        if len(got) < 2:
            missing.append(q)
            continue
        au = tv.authority(ctx, mcd, it["a"], it["b"])
        ex, closed, opn = tv.combine_pair(got[0]["taken"], got[1]["taken"], bool(au))
        f = ref.machine_facts(ctx, mcd, it["a"], it["b"])
        if bool(f) != bool(au):
            raise SystemExit("%s: факты %s расходятся с авторитетом '%s'" % (q, f, au))
        ex2, closed2, opn2 = ref.apply_facts(ex, closed, opn, f)
        es, ss = ref.statuses(ex2, closed2, opn2)
        rows.append({"q": q, "a": it["a"], "b": it["b"], "existence": ex2, "closed": sorted(closed2),
                     "open": sorted(opn2), "authority": au, "facts": f, "judge1": sorted(got[0]["taken"]),
                     "judge2": sorted(got[1]["taken"]), "raw1": got[0]["raw"], "raw2": got[1]["raw"],
                     "judges_existence": ex, "judges_closed": sorted(closed), "judges_open": sorted(opn),
                     "existence_status": es, "subtype_status": ss,
                     "existence_basis": "machine_fact" if f else "judges"})
    return rows, bad, missing


def judge_files(out):
    plock = ir.load_json(p(out, "pack.lock.json"))
    return {"judge_%d.tsv" % (i + 1): file_sha(p(plock["pack_dir"], "answers", "judge_%d.tsv" % (i + 1)))
            for i in range(len(plock["batches"]))}


def ref_code():
    return {c: file_sha(c) for c in (SELF, "tools/hdart/relation_holdout_v4_ref.py", "tools/hdart/relation_truth_v2.py",
                                     "tools/hdart/relation_taxonomy.py", "tools/hdart/relation_holdout_v4.py")}


def do_lockref(out=OUT):
    import relation_holdout_v4_ref as ref
    lock = p(out, "reference.lock.json")
    if os.path.exists(lock):
        raise SystemExit("эталон уже заморожен: %s" % lock)
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("есть answers_vitali.tsv - эталон замораживается только до ответов оси A")
    d, h = load_freeze(out), load_holdout(out)
    guard(d)
    detectors_same(d)
    rows, bad, missing = build_truth(out)
    if bad or missing:
        raise SystemExit("ответы судей неполны или с ошибками: %s; без двух ответов: %s" % (bad[:10], missing[:10]))
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    tpath = p(out, "truth.json")
    ir.dump_json(tpath, {"created": now, "schema": d["ref_schema"], "addendum": d["ref_addendum"], "pairs": rows,
                         "existence": dict(Counter(r["existence"] for r in rows)),
                         "closed_labels": dict(Counter(l for r in rows for l in r["closed"]))})
    plock = ir.load_json(p(out, "pack.lock.json"))
    ir.dump_json(lock, {"created": now, "holdout_sha256": h["sha256"], "key_sha256": file_sha(p(out, "key.json")),
                        "pack_sha256": plock["pack_sha256"], "truth_sha256": file_sha(tpath),
                        "answers_present_at_lock": False, "freeze_sha256": d["sha256"],
                        "pair_count": len(rows), "judge_files_sha256": judge_files(out), "code_sha256": ref_code(),
                        "decisions_sha256": jsha(ref.decisions(rows)), "counts": ref.counts(rows)})
    print("эталон заморожен: %s" % json.dumps(ref.counts(rows), ensure_ascii=False))


def do_verify(out=OUT):
    import relation_holdout_v4_ref as ref
    lk = ir.load_json(p(out, "reference.lock.json"))
    bad = []
    if file_sha(p(out, "truth.json")) != lk["truth_sha256"]:
        bad.append("truth.json изменён")
    if lk["answers_present_at_lock"]:
        bad.append("ответы оси A были при заморозке")
    if lk["freeze_sha256"] != load_freeze(out)["sha256"]:
        bad.append("FREEZE.json не тот")
    if lk["key_sha256"] != file_sha(p(out, "key.json")):
        bad.append("ключи пар изменены")
    if lk["pack_sha256"] != ir.load_json(p(out, "pack.lock.json"))["pack_sha256"]:
        bad.append("пакет судей изменён")
    jf = judge_files(out)
    bad += ["ответ судьи изменён: %s" % k for k in sorted(jf) if jf[k] != lk["judge_files_sha256"].get(k)]
    ch = ref_code()
    bad += ["код изменён: %s" % k for k in sorted(ch) if ch[k] != lk["code_sha256"].get(k)]
    rows, jbad, missing = build_truth(out)
    if jbad or missing:
        bad.append("ответы судей не читаются: %s %s" % (jbad[:5], missing[:5]))
    if jsha(ref.decisions(rows)) != lk["decisions_sha256"]:
        bad.append("истина, пересобранная из ответов, расходится с замком")
    stored = ir.load_json(p(out, "truth.json"))["pairs"]
    if jsha(ref.decisions(stored)) != lk["decisions_sha256"] or ref.counts(stored) != lk["counts"]:
        bad.append("truth.json расходится с замком")
    for b in bad:
        print("FAIL " + b)
    print("замок цел: пар %d" % lk["pair_count"] if not bad else "замок НЕ цел: %d расхождений" % len(bad))
    return not bad


def load_truth(out=OUT):
    lk = ir.load_json(p(out, "reference.lock.json"))
    if file_sha(p(out, "truth.json")) != lk["truth_sha256"]:
        raise SystemExit("truth.json изменён после заморозки")
    rows = ir.load_json(p(out, "truth.json"))["pairs"]
    T = {pk(r["a"], r["b"]): (r["existence"], set(r["closed"]), set(r["open"])) for r in rows}
    return T, {pk(r["a"], r["b"]): r for r in rows}, lk


# ---------------------------------------------------------------- подсчёт

def acceptance(vals, gates=GATES, n_min=N_MIN):
    """vals {ворота: (значение, n)} -> (строки, вердикт). Доля с n < n_min - INSUFFICIENT_SAMPLE."""
    rows = []
    for g, kind, need in gates:
        v, n = vals[g]
        if kind == "count":
            st = "PASS" if v == need else "FAIL"
        elif v is None or not n:
            st = "NO_DATA"
        elif n < n_min:
            st = "INSUFFICIENT_SAMPLE"
        else:
            st = "PASS" if v >= need else "FAIL"
        rows.append({"gate": g, "kind": kind, "value": v, "n": n, "need": need, "status": st})
    sts = {r["status"] for r in rows}
    verdict = "FAIL" if "FAIL" in sts else ("INCONCLUSIVE" if sts & {"INSUFFICIENT_SAMPLE", "NO_DATA"} else "PASS")
    return rows, verdict


def asm_levels(cs):
    return {e["level"] for c in cs for e in c["support"] if e["detector"] == asm.DETECTOR}


def asm_pairs(pc, trow):
    """pc = [(a, b, истина, доводы)], trow {ключ пары: строка истины} -> (кандидаты, STRONG) с исходами."""
    import v5_component_validation as cv
    cand, strong = [], []
    for a, b, _t, cs in pc:
        lv = asm_levels(cs)
        if not lv:
            continue
        r = trow.get(pk(a, b))
        if EDGE_STRONG in lv:
            strong.append({"pair": [a, b], "composite": cv.subtype(r, {"COMPOSITE"}) if r else "OPEN",
                           "existence": r["existence"] if r else None})
        else:
            cand.append({"pair": [a, b], "exist": {"RELATED": "yes", "NONE": "no"}.get(
                r["existence"] if r else "", "OPEN"), "existence": r["existence"] if r else None})
    return cand, strong


def rate_closed(rows, field, good):
    closed = [r for r in rows if r[field] != "OPEN"]
    ok = sum(r[field] == good for r in closed)
    return v2.rate(ok, len(closed)), len(closed), ok, len(rows) - len(closed)


def ar2_band(x):
    for lo, hi in AR2_BANDS:
        if lo <= x < hi:
            return "%.2f-%.2f" % (lo, hi) if hi < 9 else ">=%.2f" % lo
    return "<%.2f" % AR2_BANDS[0][0]


def ar2_diag(pc, perm, outside):
    st = hv.tv_state
    d, bands = Counter(), Counter()
    for _a, _b, t, cs in pc:
        for c in cs:
            es = [e for e in c["support"] if e["detector"] == ar2.DETECTOR]
            if not es:
                continue
            b = ar2_band(max(e["scores"]["topology"] for e in es))
            d["triggered"] += 1
            bands[b] += 1
            if not t or t[0] == "OPEN":
                d["open"] += 1
            elif t[0] == "NONE":
                d["closed_none"] += 1
                d["false_existence"] += 1
                bands[b + " NONE"] += 1
            else:
                d["closed_related"] += 1
                bands[b + " RELATED"] += 1
            if tx.auto_claim(c):
                d["auto_action_with_ar2"] += 1      # политика: автоматического действия нет - ждём 0
            if st(c, t) == "wrong":
                d["wrong_claim"] += 1
    d["outside_pool"] = sum(1 for x in outside if x[1] == ar2.DETECTOR)
    d["permuted_control_fired"] = sum(x["fired"] for x in perm)
    d["permuted_control_n"] = len(perm)
    return dict(d, boundary=dict(sorted(bands.items())))


def asm_cand_diag(cand, pc, unmasked):
    st = hv.tv_state
    d = Counter(triggered=len(cand))
    for x in cand:
        d[{"yes": "accepted", "no": "rejected", "OPEN": "open"}[x["exist"]]] += 1
    for _a, _b, t, cs in pc:
        for c in cs:
            es = [e for e in c["support"] if e["detector"] == asm.DETECTOR and e["level"] != EDGE_STRONG]
            if es and st(c, t) == "wrong":
                d["hurt_wrong_claim"] += 1
    d["hurt_masked_frames"] = sum(1 for u in unmasked if any(any(x.startswith("ASM") for x in m["detectors"])
                                                             for m in u["masked_by"]))
    return dict(d)


def evaluate(rows, C, T, items, keys, h, fsets):
    return rd5.evaluate(rows, C, T, items, keys, h, fsets)


def closed_none_sources(out):
    """Закрытые независимые эталоны: свой плюс NONE_SOURCES. -> [(имя, [(a, b, существование)])]."""
    own = [(r["a"], r["b"], r["existence"]) for r in ir.load_json(p(out, "truth.json"))["pairs"]]
    srcs = [("holdout V5", own)]
    for name, k in NONE_SOURCES:
        srcs.append((name, [(r["a"], r["b"], r["existence"]) for r in ir.load_json(DEV_SOURCES[k])["pairs"]]))
    return srcs


def do_report(out=OUT):
    import routing_model_v8 as v8
    d, h = load_freeze(out), load_holdout(out)
    ch = code_changed(d)
    if ch:
        raise SystemExit("код изменён после заморозки: %s - отчёт по замороженной системе невозможен" % ", ".join(ch))
    live_same(d)
    detectors_same(d)
    if not do_verify(out):
        raise SystemExit("замок эталона не цел")
    T, trow, lk = load_truth(out)
    ans_p = p(out, "answers_vitali.tsv")
    if not os.path.exists(ans_p):
        raise SystemExit("нет %s" % ans_p)
    ans = {r["asset_id"]: r for r in ir.read_tsv(ans_p)}
    keys = keys_of(h)
    bad = ["%s: нет ответа" % a for a in keys if a not in ans]
    bad += ["%s: semantic_kind '%s'" % (a, ans[a].get("semantic_kind")) for a in keys
            if a in ans and ans[a].get("semantic_kind") not in v8.SEMANTIC]
    found3, found4, found5 = load_found(out)
    base = hv.routing_base(out, d, h)
    rows = hv.routing_rows(base, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    items = ir.load_json(p(out, "key.json"))["items"]
    pool = {pk(it["a"], it["b"]) for it in items}
    args = (T, items, keys, h, base["fsets"])
    edges = found5["edges"]

    def ev(es):
        C = system_claims(rows, found3, found4, es)
        return C, evaluate(rows, C, *args)
    C, new = ev(edges)
    none_pairs = prs.closed_none(*closed_none_sources(out))
    pp, post = prs.pre_post(lambda c: evaluate(rows, c, *args), C, none_pairs)
    if pp["PRE_REVIEW_DANGEROUS"] != len(new["dangerous"]):
        raise SystemExit("PRE_REVIEW_DANGEROUS не совпал")
    G = {g["gate"]: g for g in new["gates"]}
    cand, strong = asm_pairs(new["pc"], trow)
    vc, nc, _okc, _oc = rate_closed(cand, "exist", "yes")
    vs, ns, _oks, _os = rate_closed(strong, "composite", "yes")
    vals = {"PRE_REVIEW_DANGEROUS": (pp["PRE_REVIEW_DANGEROUS"], len(keys)),
            "POST_REVIEW_DANGEROUS": (pp["POST_REVIEW_DANGEROUS"], len(keys)),
            "relation_existence_precision": (G["relation_existence_precision"]["value"],
                                             G["relation_existence_precision"]["n"]),
            "derived_recolor_discovery": (G["derived_recolor_discovery"]["value"], G["derived_recolor_discovery"]["n"]),
            "state_discovery": (G["state_discovery"]["value"], G["state_discovery"]["n"]),
            "composite_discovery_recall": (G["true_composite_recall"]["value"], G["true_composite_recall"]["n"]),
            "automatic_action_precision": (G["automatic_action_precision"]["value"],
                                           G["automatic_action_precision"]["n"]),
            "ASSEMBLY_candidate_existence_precision": (vc, nc),
            "ASSEMBLY_STRONG_composite_precision": (vs, ns),
            "handoff_unassigned": (G["handoff_unassigned"]["value"], G["handoff_unassigned"]["n"])}
    gates, verdict = acceptance(vals)
    # без доводов детектора: кто был бы опасен
    _c0, no_ar2 = ev([e for e in edges if e["detector"] != ar2.DETECTOR])
    _c1, no_asmc = ev([e for e in edges if not (e["detector"] == asm.DETECTOR and e["level"] != EDGE_STRONG)])
    ar2_helped = sorted(a for a in no_ar2["dangerous"] if a not in new["dangerous"])
    asm_helped = sorted(a for a in no_asmc["dangerous"] if a not in new["dangerous"])
    outside = rd5.outside_dets(C, keys, pool) + [
        ("%s ~ %s" % tuple(c["pair"]), e["detector"], e["rule"], e["level"]) for a in keys for c in C.of(a)
        if frozenset(c["pair"]) not in pool for e in c["support"] if e["detector"] == ar2.DETECTOR]
    ad = ar2_diag(new["pc"], found5.get("ar2_permuted_control", []), outside)
    ad["helped_dangerous"] = ar2_helped
    cd = asm_cand_diag(cand, new["pc"], pp["unmasked"])
    cd["helped_safety"] = asm_helped
    sd = Counter(triggered=len(strong))
    for x in strong:
        sd[{"yes": "true_composite", "no": "not_composite", "OPEN": "open"}[x["composite"]]] += 1
    drop = pp["dropped_candidates"]
    post_d = {"removed_closed_none": len(drop),
              "removed_by_detector": dict(Counter(x for dd in drop for x in dd["detectors"])),
              "removed_by_source": dict(Counter(s for dd in drop for s in dd["truth"])),
              "strong_on_closed_none": len(pp["strong_on_closed_none"]),
              "became_dangerous_after_review": [u["asset"] for u in pp["unmasked"]],
              "invariant_holds": not pp["unmasked"] and pp["POST_REVIEW_DANGEROUS"] == 0}
    c3 = v3.Ctx(index=v2.load_index(v2.OUT))
    tname = {0: "floor", 1: "wall", 2: "wall", 3: "object"}

    def tinfo(k):                                    # как relation_holdout_v4.do_report
        i = c3.info(k)
        return tname.get(i.get("tile_type"), "none") if i.get("rec") else "none"
    score = {x["asset_id"]: x for x in new["score"]}
    by_layer = {}
    for x in h["items"]:
        s = score[x["asset_id"]]
        L = by_layer.setdefault(x["layer"], Counter())
        L["frames"] += 1
        L["creative"] += s["creative"]
        L["dangerous_pre"] += bool(s["danger"])
        L["dangerous_post"] += x["asset_id"] in post["dangerous"]
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE, "freeze_sha256": d["sha256"],
           "holdout_sha256": h["sha256"], "reference_locked": lk["created"], "n_frames": len(keys),
           "n_target": N_TOTAL, "short": h["short"], "verdict": verdict, "gates": gates,
           "gates_v4_form": new["gates"], "metrics": new["metrics"], "recall": new["recall"],
           "post_review": pp, "post_review_invariant": post_d, "ar2": ad, "asm_candidate": cd,
           "asm_candidate_pairs": cand, "asm_strong": dict(sd), "asm_strong_pairs": strong,
           "diagnostics": hv.diagnostics(new["pc"], {k.upper() for k in keys}, tinfo),
           "claims_outside_pool": new["outside"], "invalid": bad, "truth": dict(Counter(t[0] for t in T.values())),
           "pairs": len(new["pc"]), "rows": new["score"], "dangerous_pre": new["dangerous"],
           "dangerous_post": post["dangerous"], "by_layer": {k: dict(v) for k, v in by_layer.items()},
           "ar2_policy": AR2_POLICY, "known_frozen_defects": d.get("known_frozen_defects", [])}
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    print("вердикт %s; PRE %d, POST %d; отчёт: %s" % (verdict, pp["PRE_REVIEW_DANGEROUS"],
                                                     pp["POST_REVIEW_DANGEROUS"], p(out, "report.md")))
    return res


def write_md(out, res):
    f3 = hv.f3
    L = ["# RELATION_DISCOVERY_V5 — слепой holdout на %d кадрах (цель %d)" % (res["n_frames"], res["n_target"]), "",
         "Вердикт: **%s**. Снимок %s, эталон заморожен %s. AR2 boundary < 0.70 = NOT VALIDATED." % (
             res["verdict"], res["freeze_sha256"][:12], res["reference_locked"]), "",
         "Недобор слоёв (записан до ответов): %s" % (res["short"] or "нет"), "",
         "## Ворота", "", "| ворота | значение | n | нужно | итог |", "|---|---|---|---|---|"]
    for g in res["gates"]:
        L.append("| %s | %s | %s | %s | %s |" % (g["gate"], f3(g["value"]), g["n"], g["need"], g["status"]))
    pi = res["post_review_invariant"]
    L += ["", "## Безопасность после ревью (production invariant)", "",
          "- удалено как CLOSED-NONE: %d; по детекторам %s; по источникам %s" % (
              pi["removed_closed_none"], pi["removed_by_detector"], pi["removed_by_source"]),
          "- STRONG на closed NONE (остаются): %d" % pi["strong_on_closed_none"],
          "- стали опасными после удаления: %s" % (pi["became_dangerous_after_review"] or "нет"),
          "- инвариант держится: %s" % ("да" if pi["invariant_holds"] else "**нет**"),
          "", "## AR2", "", "- %s" % json.dumps(res["ar2"], ensure_ascii=False),
          "", "## ASSEMBLY candidate", "", "- %s" % json.dumps(res["asm_candidate"], ensure_ascii=False),
          "", "## ASSEMBLY STRONG", "", "- %s" % json.dumps(res["asm_strong"], ensure_ascii=False),
          "", "## Прочее", "",
          "- истина пула: %s, пар %d" % (res["truth"], res["pairs"]),
          "- опасные до ревью: %s" % (res["dangerous_pre"] or "нет"),
          "- опасные после ревью: %s" % (res["dangerous_post"] or "нет"),
          "- утверждения вне пула: %d" % len(res["claims_outside_pool"]),
          "- по слоям: %s" % json.dumps(res["by_layer"], ensure_ascii=False)]
    if res["invalid"]:
        L += ["", "Ошибки ответов: " + "; ".join(res["invalid"])]
    if res.get("known_frozen_defects"):
        L += ["", "## Известные дефекты замороженного кода", ""]
        for kd in res["known_frozen_defects"]:
            L += ["%s: %s" % (kd["id"], kd["text"]), "", "- где: %s" % kd["where"], "- охват: %s" % kd["reach"]]
    L += ["", "VERIFIED ставит только человек."]
    with open(p(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")


def do_check(out=OUT):
    d = load_freeze(out)
    print("снимок цел: %s" % d["sha256"][:12])
    ch = code_changed(d)
    print("код:", "тот же" if not ch else "ИЗМЕНЁН: " + ", ".join(ch))
    if os.path.exists(p(out, "holdout.json")):
        load_holdout(out)
        print("holdout цел")
    if os.path.exists(p(out, "relations.lock.json")):
        rh.load_relations(out)
        h7.load_detectors(out)
        load_found(out)
        print("детекторы целы")
    if os.path.exists(p(out, "reference.lock.json")):
        do_verify(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["pools", "freeze", "select", "relations", "cards", "pairs", "pack", "lockref",
                                    "verify", "report", "check"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    {"pools": do_pools, "freeze": freeze, "select": do_select, "relations": do_relations, "cards": do_cards,
     "pairs": do_pairs, "pack": do_pack, "lockref": do_lockref, "verify": do_verify, "report": do_report,
     "check": do_check}[a.cmd](a.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
