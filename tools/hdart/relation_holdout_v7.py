#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""RELATION_SAFETY_MODEL_V7 - заморозка и новый слепой holdout (специалист 02.10, передал Vitali в чате). CPU.

Решение: «Да - V7 теперь можно замораживать и запускать новый blind holdout. Утверждаю.» Обе группы hard-ворот
одновременно (PRE/POST = 0 и related_frame_safety_recall >= 0.90). После freeze - новый слепой holdout и только потом
ось A от специалиста; никаких новых детекторов и правок до окончательного вердикта.

Система V7 - модель RELATION_SAFETY_MODEL_V7_PREP как есть: маршрут V8, V3, V4, ASM V1, AR2 (границы >= 0.70), AG
(assembly_group_v1), TC (two_component_v1), RC (assembly_repeated_v1) - переписан в REPEATED_ASSEMBLY_RELATION
(CANDIDATE, TYPE_OPEN, без голоса в составном); классы доводов v5_ar2_recount.V5AR2Claims; безопасность после ревью
post_review_safety. Замороженные модули (relation_safety_v7_prep и все ниже) только читаются.

FREEZE.json пишется ДО отбора: хэши кода (relation_safety_v7_prep с тестом, детекторы, post_review_safety, подсчёт и
отчёт, holdout V5/V4, маршрут V8, этот модуль), spec и отчёт V7_PREP, политика RAR, определение
related_frame_safety_recall и порог 0.90, ворота hard / typed / review / handoff, список «только диагностика»
(composite_frame_recall, composite_pair_recall, module recall), параметры и политики AR2 / ASM / TC / AG / RC,
хэши источников разработки и контроля, слои, зерно, список исключённых ключей (excluded_keys.json), правило пар.

Ворота (доля с закрытыми случаями меньше N_MIN = 10 - INSUFFICIENT_SAMPLE):
  hard     PRE_REVIEW_DANGEROUS = 0, POST_REVIEW_DANGEROUS = 0, relation_existence_precision >= 0.95,
           related_frame_safety_recall >= 0.90, automatic_action_precision >= 0.95
  typed    derived_recolor_discovery >= 0.70, state_discovery >= 0.70
  review   ASSEMBLY_candidate_existence_precision >= 0.95, ASSEMBLY_STRONG_composite_precision >= 0.95
  handoff  handoff_unassigned = 0

Отбор: около 80 новых кадров, один на набор PCK; цели всех прежних holdout и раундов разработки исключены по ключу;
недобор слоя пишется в holdout.json до ответов и в другие слои не переносится; после просмотра карточек ничего не
переносится.

    pools      до заморозки: исключения и размеры пулов (без детекторов)
    freeze     снимок -> FREEZE.json и excluded_keys.json
    select     ленивый проход детекторов по очереди и отбор -> holdout.json
    relations  замороженные детекторы на кадрах: маршрут V8, V3, V4, AR2 (с перемешанным контролем), ASM, AG, TC, RC
    cards      страница оси A - сразу по белому списку полей (R-187), без гипотез модели
    pairs      пул пар эталона (key.json вне пакета)
    pack       слепой пакет в нейтральной папке PACK (два судьи на пару)
    lockref    эталон из ответов судей и машинных фактов - до ответов оси A
    axiszip    ZIP карточек оси A для специалиста - только после lockref и до ответов
    verify     замок эталона цел
    report     ворота V7 и обязательная диагностика
    check      хэши целы

    py -3.13 tools/hdart/relation_holdout_v7.py <команда>
VERIFIED ставит только человек.
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import zipfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import relation_safety_v7_prep as s7              # noqa: E402  (ставит ASMG/ASMR/ASM2/RAR в rc.DETECTOR_ORDER)
import aligned_recolor_v2 as ar2                  # noqa: E402
import assembly_discovery_v1 as asm               # noqa: E402
import assembly_group_v1 as ag                    # noqa: E402
import assembly_repeated_v1 as arc                # noqa: E402
import identity_routing as ir                     # noqa: E402
import post_review_safety as prs                  # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_discovery_v5 as rd5               # noqa: E402
import relation_holdout_v4 as hv                  # noqa: E402
import relation_holdout_v5 as h5                  # noqa: E402
import relation_taxonomy as tx                    # noqa: E402
import routing_holdout as rh                      # noqa: E402
import routing_holdout_v7 as h7                   # noqa: E402
import routing_holdout_v8 as h8                   # noqa: E402
import two_component_v1 as tc                     # noqa: E402
import v5_ar2_recount as rc                       # noqa: E402

ENC = ir.ENC
PROFILE = "RELATION_SAFETY_MODEL_V7_HOLDOUT"
OUT = os.path.join(ir.PROBES, "relation-holdout-v7")
PACK = os.path.join(ir.PROBES, "pairset-2741")       # слепой пакет судей: имя папки нейтральное
SEED = "relation-holdout-v7-2026-10-03"
h7.SEED = SEED                       # ленивые пулы h7.pools берут зерно из своего модуля; код V7/V8 не меняется
N_TOTAL = 80
N_MIN = h5.N_MIN
EDGE_STRONG = h5.EDGE_STRONG
INPUTS = dict(h5.INPUTS)
SELF = "tools/hdart/relation_holdout_v7.py"
DET_CODE = ["tools/hdart/assembly_group_v1.py", "tools/test_assembly_group_v1.py",
            "tools/hdart/two_component_v1.py", "tools/test_two_component_v1.py",
            "tools/hdart/assembly_repeated_v1.py", "tools/test_assembly_repeated_v1.py",
            "tools/hdart/assembly_evidence_v2_prep.py", "tools/hdart/relation_v6_prep.py"]
CODE = [SELF, "tools/test_relation_holdout_v7.py", s7.SELF, "tools/test_relation_safety_v7_prep.py",
        "tools/hdart/axis_a_clean_v5.py"] + DET_CODE + [c for c in h5.CODE if c not in DET_CODE]
V7P = s7.OUT
V5H = h5.OUT
DEV_SOURCES = dict(h5.DEV_SOURCES, **{
    "v5_freeze": os.path.join(V5H, "FREEZE.json"),
    "v5_holdout": os.path.join(V5H, "holdout.json"),
    "v5_relations_lock": os.path.join(V5H, "relations.lock.json"),
    "v5_found": os.path.join(V5H, "relations", "found_v5.json"),
    "v5_key": os.path.join(V5H, "key.json"),
    "v5_reference_lock": os.path.join(V5H, "reference.lock.json"),
    "v5_truth": os.path.join(V5H, "truth.json"),
    "v5_answers": os.path.join(V5H, "answers_vitali.tsv"),
    "v5_report": os.path.join(V5H, "report.json"),
    "v6_prep_spec": os.path.join(s7.V6D, "spec.json"),
    "v6_prep_found_group": os.path.join(s7.V6D, "found_group.json"),
    "v6_prep_report": os.path.join(s7.V6D, "report.json"),
    "ae2_spec": os.path.join(s7.AE2D, "spec.json"),
    "ae2_found": os.path.join(s7.AE2D, "found_evidence.json"),
    "ae2_report": os.path.join(s7.AE2D, "report.json"),
    "v7_prep_spec": os.path.join(V7P, "spec.json"),
    "v7_prep_found_v4": os.path.join(V7P, "found_v4.json"),
    "v7_prep_found_v4_lock": os.path.join(V7P, "found_v4.lock.json"),
    "v7_prep_report": os.path.join(V7P, "report.json")})
DEV_PAIR_KEYS = h5.DEV_PAIR_KEYS + ("v5_key",)
# закрытые независимые эталоны для POST_REVIEW (кроме своего): holdout V5, holdout V4, проверка компонентов, полоса AR
NONE_SOURCES = (("holdout V5", "v5_truth"),) + h5.NONE_SOURCES

# ---------------------------------------------------------------- модель и ворота (всё - из V7_PREP, без правок)

GATES = tuple(s7.GATES) + (("handoff_unassigned", "count", 0, "handoff"),)
GATE_DEFS = dict(s7.GATE_DEFS, handoff_unassigned="строки маршрута V8 с pipeline_target вне "
                                                  "routing_model_v8.PIPELINES (в V7_PREP - диагностика, здесь ворота)",
                 sample="ворота-доли с закрытыми случаями меньше N_MIN = 10 - INSUFFICIENT_SAMPLE (и при FAIL); "
                        "счётчики - PASS только при 0")
VERDICT_RULE = ("FAIL - хоть одни ворота FAIL; иначе INCONCLUSIVE при INSUFFICIENT_SAMPLE или NO_DATA; иначе PASS. "
                "Ворота всех четырёх групп (hard, typed, review, handoff) входят в вердикт одинаково")
DIAGNOSTIC_ONLY = ("composite_frame_recall", "composite_pair_recall", "composite_strong_recall", "module_recall")
DIAG_DEFS = dict(h5.DIAG_DEFS, **{
    "related_frame_safety": "found / total, промахи по кадрам с парами и утверждениями, лучшее действие по кадрам",
    "rar": "REPEATED_ASSEMBLY_RELATION: triggered (пары пула с доводом RAR), закрытые RELATED / NONE, OPEN, "
           "вне пула; unique safety saves - кадры, найденные frame safety только благодаря RAR (без доводов RAR - "
           "промах), и кадры, опасные без RAR",
    "composite": "только диагностика: frame recall (подтип COMPOSITE по кадру), pair recall, STRONG-only",
    "module": "только диагностика: пары с закрытым MODULAR_SECTION - найдено группой modular / любым утверждением",
    "ar2": h5.DIAG_DEFS["ar2"],
    "post_review": "удалено как CLOSED-NONE (по детекторам и источникам), STRONG на closed NONE, кадры, ставшие "
                   "опасными после удаления"})
RAR_POLICY = {"from": "REPEATED_COMPONENT (assembly_repeated_v1, ASMR, RC)",
              "to": "%s: existence CANDIDATE, subtype TYPE_OPEN, группа %s, детектор %s" % (
                  s7.RAR_TYPE, s7.RAR_GROUP, s7.RAR_DETECTOR),
              "composite_vote": "нет: в composite_*_recall и подтип COMPOSITE не голосует",
              "how": "relation_safety_v7_prep.reclass_rc при сборке утверждений; файл детектора не меняется"}
DETECTORS = {
    "AR2": {"code": "tools/hdart/aligned_recolor_v2.py", "params": ar2.PARAMS, "policy": h5.AR2_POLICY},
    "ASM": {"code": "tools/hdart/assembly_discovery_v1.py", "params": asm.PARAMS, "policy": h5.ASM_POLICY},
    "AG": {"code": "tools/hdart/assembly_group_v1.py", "params": ag.PARAMS,
           "policy": "как V6_PREP: доводы ASMG по relation_v6_prep.run_ag, в утверждения как есть"},
    "TC": {"code": "tools/hdart/two_component_v1.py", "params": tc.PARAMS,
           "policy": "как ASSEMBLY_EVIDENCE_V2_PREP: COMPOSITE_PART, CANDIDATE; TC_FLOOR_OBJECT_DIAG в утверждения "
                     "не входит (discover без diag)"},
    "RC": {"code": "tools/hdart/assembly_repeated_v1.py", "params": arc.PARAMS, "policy": RAR_POLICY}}
POLICY = dict(h5.POLICY, claims_class="v5_ar2_recount.V5AR2Claims: доводы V8, V3, V4, ASM, AR2 (AR1 нет), AG, TC и "
                                      "RC -> REPEATED_ASSEMBLY_RELATION",
              detectors={k: v["policy"] for k, v in DETECTORS.items()})
KNOWN_OPEN = [{"id": "U_BASE_VR:53", "text": "промах frame safety V7_PREP на holdout V5; гипотеза про R-075 (чтение PCK "
                                             "по смещениям TAB) не проверяется и не чинится до вердикта",
               "decided": "специалист 02.10, передал Vitali в чате"}]

# ---------------------------------------------------------------- исключения

# раунды probes, чьи файлы - не цели: сканы всей очереди; свой holdout и свой пакет
WHOLE_QUEUE_ROUNDS = ("families-recolor-v2",)
SKIP_DIRS = ("inputs", "index", "img", "blind")             # снимки данных игры и картинки
SKIP_FILES = ("mcd_state_relations.json", "scan_recolor.tsv", "frames.json", "frames.tsv", "generation.tsv")
KEY_RX = re.compile(r"[A-Za-z0-9_\-+.]+:\d+")
EXCLUSION_RULE = (
    "цели holdout - новые кадры, исключение по КЛЮЧУ (кадр и asset_id); наборы PCK не исключаются. Исключены: "
    "(1) всё, что исключал holdout V5 (relation_holdout_v5.dev_keys: исключения V8 и V2-V4, holdout V4 с роднёй, обе "
    "стороны пар V4 и проверок, стороны доводов V5_PREP и пересчёта); (2) holdout V5: 80 кадров, их родня, обе стороны "
    "пар пула, стороны доводов found_v5; стороны доводов V6_PREP (AG), ASSEMBLY_EVIDENCE_V2_PREP (TC, RC, AG) и "
    "V7_PREP (found_v4); (3) все прежние раунды probes: любой ключ очереди, названный в их json / tsv - кроме "
    "снимков данных (папки %s; файлы %s) и раундов-сканов всей очереди (%s). Список ключей заморожен в "
    "excluded_keys.json до отбора" % ("/".join(SKIP_DIRS), ", ".join(SKIP_FILES), ", ".join(WHOLE_QUEUE_ROUNDS)))

# ---------------------------------------------------------------- слои

# (имя, квота, ((подслой, квота), ...)); подслой с квотой 0 - только добор внутри слоя
LAYERS = (("ar2", 8, (("ar2", 8),)),
          ("rar", 8, (("rar", 8),)),
          ("asm_strong", 6, (("asm_strong", 6),)),
          ("assembly_candidate", 6, (("asm_candidate", 4), ("tc", 1), ("ag", 1))),
          ("mcd_state", 10, (("mcd_die", 4), ("mcd_alt", 1), ("mcd_anim", 1), ("mcd_dominance", 1),
                             ("mcd_candidate", 3))),
          ("sparse", 8, (("single_place", 6), ("sparse_place", 2))),
          ("derived", 12, (("fr2_new", 2), ("fr2_verified", 3), ("legacy_recolor", 2), ("material_variant", 2),
                           ("family_mirror", 2), ("family_open", 1))),
          ("composite", 6, (("part_suspect", 1), ("part_words", 1), ("composite", 3), ("modular_words", 1))),
          ("structural", 3, (("wall", 1), ("door", 1), ("stairs", 1), ("hull", 0), ("roof", 0), ("panel", 0),
                             ("vehicle_body", 0))),
          ("terrain", 3, (("relief", 1), ("floor", 1), ("object_or_relief", 1), ("surface_mcd", 0))),
          ("standalone", 10, (("standalone", 10),)))
DETECTOR_LAYERS = ("ar2", "rar", "asm_strong", "asm_candidate", "tc", "ag")
SCAN_MAX = 2500
SCAN_FOUND = 60
SPARSE_RULE = {"single_place": "action GENERATE, asset_class object, places = 1 (одна расстановка на картах)",
               "sparse_place": "action GENERATE, asset_class object, places 2-3"}
SELECT_RULE = ("слои по порядку LAYERS, подслои по порядку, внутри - зерно SEED; ключ один раз, набор PCK один раз "
               "на весь holdout. Недобор подслоя добирается другими подслоями ТОГО ЖЕ слоя по кругу; недобор слоя "
               "в другие слои НЕ переносится - пишется в holdout.json до ответов. Слои детекторов: ленивый проход "
               "очереди по зерну SEED (ar2 - доводы AR2; rar - доводы RC; asm_strong - ASM STRONG; asm_candidate - "
               "ASM без STRONG; tc - доводы TC; ag - доводы AG) до SCAN_FOUND наборов на подслой или SCAN_MAX "
               "кадров; детектор перестаёт считаться, когда его подслой полон (ASM - когда полны оба)")
BODY = ("profile", "decision", "policy", "metric", "gates", "gate_defs", "verdict_rule", "diagnostic_only",
        "diag_defs", "rar_policy", "detectors", "n_min", "seed", "n_total", "layers", "detector_layers", "scan",
        "sparse_rule", "select_rule", "exclusion_rule", "excluded", "known_open", "known_frozen_defects",
        "pair_rule", "pair_params", "ref_schema", "ref_addendum", "pack_dir", "struct_rx", "v7_prep",
        "dev_sources_sha256", "truth_v2", "detector_inputs_sha256", "inputs_source", "inputs", "input_sha256",
        "code_sha256")
file_sha = rh.file_sha
pset = rh.pset
pk = tx.pk
guard = hv.guard
code_changed = hv.code_changed
detectors_same = hv.detectors_same
live_same = h5.live_same
load_holdout = rh.load_holdout
keys_of = hv.keys_of


def p(out, *name):
    return os.path.join(out, *name)


def order(key):
    return hashlib.sha256((SEED + "|" + key).encode()).hexdigest()


def jsha(obj):
    return h5.jsha(obj)


# ---------------------------------------------------------------- исключения

def round_keys(probes, allkeys, skip_rounds):
    """{раунд: ключи очереди, названные в его json / tsv} без снимков данных и раундов-сканов."""
    per = {}
    for d in sorted(os.listdir(probes)):
        full = os.path.join(probes, d)
        if not os.path.isdir(full) or d in skip_rounds:
            continue
        ks = set()
        for root, _dirs, files in os.walk(full):
            rel = os.path.relpath(root, full).replace(os.sep, "/").split("/")
            if set(rel) & set(SKIP_DIRS):
                continue
            for f in sorted(files):
                if not f.endswith((".json", ".tsv")) or f in SKIP_FILES:
                    continue
                with open(os.path.join(root, f), encoding="utf-8-sig", errors="replace") as fh:
                    ks |= {m.upper() for m in KEY_RX.findall(fh.read())} & allkeys
        if ks:
            per[d] = ks
    return per


def v5_dev_keys(inp):
    """Holdout V5 и доводы prep-раундов V6 / V2 / V7: кадры, родня, стороны пар и доводов."""
    import family_relation_v2 as fr2m
    import mcd_state as ms
    fr2 = fr2m.load(inp["family_relation_v2"])
    mcd = ms.index(ir.load_json(inp["mcd_state"])["relations"])
    ks5 = {x["asset_id"].upper() for x in rh.load_holdout(V5H)["items"]}
    rel = set()
    for _k, rs in rh.load_relations(V5H).items():
        rel |= {r["relative"].upper() for r in rs}
    for k in ks5:
        rel |= {e["relative"].upper() for e in fr2.get(k, [])}
        rel |= {x["relative"].upper() for x in mcd.get(k, [])}
    pairs = set()
    for it in ir.load_json(DEV_SOURCES["v5_key"])["items"]:
        pairs |= {it["a"].upper(), it["b"].upper()}
    es = list(ir.load_json(DEV_SOURCES["v5_found"])["edges"]) + list(ir.load_json(
        DEV_SOURCES["v6_prep_found_group"])["edges"])
    for name in ("ae2_found", "v7_prep_found_v4"):
        for lst in ir.load_json(DEV_SOURCES[name])["edges"].values():
            es += lst
    found = set()
    for e in es:
        found |= {e["source"].upper(), e["target"].upper()}
    return ks5 | rel | pairs | found, {"v5_holdout": len(ks5), "v5_relatives": len(rel), "v5_pair_sides": len(pairs),
                                       "prep_found_sides": len(found)}


def exclusion(inp, truth, gen, skip=None):
    """-> (ключи, счётчики, ключи по раундам probes)."""
    allkeys = {r["key"].upper() for r in gen} | {r["asset_id"].upper() for r in gen}
    e5, i5 = h5.dev_keys(inp, truth)
    e7, i7 = v5_dev_keys(inp)
    skip = set(WHOLE_QUEUE_ROUNDS) | {os.path.basename(OUT), os.path.basename(PACK)} | set(skip or ())
    per = round_keys(ir.PROBES, allkeys, skip)
    ks = set(e5) | e7
    new = {d: len(v - ks) for d, v in per.items()}
    for v in per.values():
        ks |= v
    ks.discard("")
    info = dict(as_v5=i5, v5_dev=i7, rounds={d: len(v) for d, v in per.items()}, rounds_new=new, total=len(ks))
    return ks, info


def eligible(gen, ex_keys):
    return h5.eligible(gen, ex_keys)


def sparse_pools(rows):
    out = {"single_place": [], "sparse_place": []}
    for r in rows:
        if r["action"] != "GENERATE" or r["asset_class"] != "object":
            continue
        n = int(r["places"] or 0)
        if n == 1:
            out["single_place"].append((r["key"], r, "одна расстановка"))
        elif 2 <= n <= 3:
            out["sparse_place"].append((r["key"], r, "расстановок %d" % n))
    return out


def meta_pools(inp, gen, ex):
    pool = h7.pools(inp, gen, set(), ex)
    pool.update(sparse_pools(eligible(gen, ex)))
    return pool


# ---------------------------------------------------------------- отбор

def classify(by):
    """by {детектор: доводы кадра} -> подслои детекторов кадра."""
    out = []
    if by.get("AR2"):
        out.append("ar2")
    if by.get("RC"):
        out.append("rar")
    ea = by.get("ASM") or []
    if any(e["level"] == EDGE_STRONG for e in ea):
        out.append("asm_strong")
    elif ea:
        out.append("asm_candidate")
    if by.get("TC"):
        out.append("tc")
    if by.get("AG"):
        out.append("ag")
    return out


NEED = {"AR2": ("ar2",), "RC": ("rar",), "ASM": ("asm_strong", "asm_candidate"), "TC": ("tc",), "AG": ("ag",)}


def scan(rows, discover, found=SCAN_FOUND, cap=SCAN_MAX, log=None):
    """Ленивый проход: discover {детектор: функция(ключ) -> доводы}. -> (пулы подслоёв детекторов, счётчики)."""
    pools = {L: [] for L in DETECTOR_LAYERS}
    sets = {L: set() for L in DETECTOR_LAYERS}
    stat = Counter()
    for r in sorted(rows, key=lambda r: order("scan|" + r["key"].upper()))[:cap]:
        if all(len(sets[L]) >= found for L in DETECTOR_LAYERS):
            break
        k = r["key"]
        stat["scanned"] += 1
        by = {}
        for det, fn in discover.items():
            if any(len(sets[L]) < found for L in NEED[det]):
                by[det] = fn(k)
                stat[det + "_run"] += 1
        for L in classify(by):
            if len(sets[L]) >= found and pset(k) not in sets[L]:
                continue
            es = by[{"ar2": "AR2", "rar": "RC", "asm_strong": "ASM", "asm_candidate": "ASM", "tc": "TC",
                     "ag": "AG"}[L]]
            note = "; ".join(sorted({"%s %s %s" % (e["rule"], e["level"], e["target"]) for e in es}))[:200]
            pools[L].append((k, r, note))
            sets[L].add(pset(k))
        if log and stat["scanned"] % 100 == 0:
            log("просмотрено %d: %s" % (stat["scanned"], {L: len(sets[L]) for L in DETECTOR_LAYERS}))
    stat.update({"found_" + L: len(sets[L]) for L in DETECTOR_LAYERS})
    return pools, dict(stat)


def select(pool, layers=LAYERS):
    """SELECT_RULE (как relation_holdout_v5.select, свои слои и зерно)."""
    saved = h5.order
    try:
        h5.order = order
        return h5.select(pool, layers)
    finally:
        h5.order = saved


# ---------------------------------------------------------------- freeze

def v7_prep_record():
    sp, rep = ir.load_json(DEV_SOURCES["v7_prep_spec"]), ir.load_json(DEV_SOURCES["v7_prep_report"])
    return {"spec_sha256": file_sha(DEV_SOURCES["v7_prep_spec"]),
            "report_sha256": file_sha(DEV_SOURCES["v7_prep_report"]), "verdict": rep["verdict"],
            "spec_code": sp["code"], "metric": sp["metric"], "reclassification": sp["reclassification"],
            "frozen_inputs": sp["frozen_inputs"]}


def do_pools(out=OUT):
    if os.path.exists(p(out, "FREEZE.json")):
        raise SystemExit("уже заморожено - пулы смотрит select")
    inp = dict(INPUTS)
    gen = ir.read_tsv(inp["generation"])
    ex, info = exclusion(inp, hv.truth_v2_snapshot(), gen)
    rows = eligible(gen, ex)
    print("исключено ключей %d: как V5 %s; V5-разработка %s" % (info["total"], info["as_v5"], info["v5_dev"]))
    print("раунды probes (новых к исключению):", {d: n for d, n in info["rounds_new"].items() if n})
    print("строк очереди %d в %d наборах" % (len(rows), len({pset(r["key"]) for r in rows})))
    pool = meta_pools(inp, gen, ex)
    for layer, q, sub in LAYERS:
        if all(s in DETECTOR_LAYERS for s, _m in sub):
            print("%-18s %2d: ленивый проход детекторов при select" % (layer, q))
            continue
        print("%-18s %2d: %s" % (layer, q, ", ".join(
            "%s %d/%d" % (s, len({pset(x[0]) for x in pool.get(s, [])}), m) if s not in DETECTOR_LAYERS
            else "%s (детектор)/%d" % (s, m) for s, m in sub)))


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
    s7.load_spec(V7P)                              # V7_PREP цел: spec, замороженные входы и его код
    s7.load_found_v4(V7P)
    if ir.load_json(DEV_SOURCES["v7_prep_report"])["verdict"] != "PASS":
        raise SystemExit("V7_PREP не PASS - замораживать нечего")
    os.makedirs(p(out, "inputs"), exist_ok=True)
    snap = {}
    for k, src in inputs.items():
        dst = p(out, "inputs", os.path.basename(src))
        if os.path.exists(dst):
            raise SystemExit("в inputs/ два входа с именем %s" % os.path.basename(src))
        shutil.copyfile(src, dst)
        snap[k] = dst.replace(os.sep, "/")
    tpath = p(out, "inputs", "truth_v2.json")
    tv2 = truth if truth is not None else hv.truth_v2_snapshot()
    ir.dump_json(tpath, tv2)
    ex, info = exclusion(snap, tv2, ir.read_tsv(snap["generation"]))
    xpath = p(out, "excluded_keys.json")
    ir.dump_json(xpath, {"rule": EXCLUSION_RULE, "counts": info, "keys": sorted(ex)})
    body = {"profile": PROFILE,
            "decision": "специалист 02.10, передал Vitali в чате: «Да - V7 теперь можно замораживать и запускать новый "
                        "blind holdout. Утверждаю.» Обе группы hard-ворот одновременно; handoff_unassigned = 0 - "
                        "ворота; после freeze - новый blind holdout и только потом ось A; никаких новых детекторов и "
                        "правок до окончательного вердикта",
            "policy": POLICY, "metric": s7.METRIC,
            "gates": [{"gate": g, "kind": k, "need": n, "group": grp} for g, k, n, grp in GATES],
            "gate_defs": GATE_DEFS, "verdict_rule": VERDICT_RULE, "diagnostic_only": list(DIAGNOSTIC_ONLY),
            "diag_defs": DIAG_DEFS, "rar_policy": RAR_POLICY,
            "detectors": {k: {"code": v["code"], "code_sha256": file_sha(v["code"]), "params": v["params"],
                              "policy": v["policy"]} for k, v in DETECTORS.items()},
            "n_min": N_MIN, "seed": SEED, "n_total": N_TOTAL,
            "layers": [[n, q, [list(s) for s in sub]] for n, q, sub in LAYERS],
            "detector_layers": list(DETECTOR_LAYERS), "scan": {"SCAN_MAX": SCAN_MAX, "SCAN_FOUND": SCAN_FOUND},
            "sparse_rule": SPARSE_RULE, "select_rule": SELECT_RULE, "exclusion_rule": EXCLUSION_RULE,
            "excluded": {"path": xpath.replace(os.sep, "/"), "sha256": file_sha(xpath), "counts": info},
            "known_open": KNOWN_OPEN, "known_frozen_defects": h5.KNOWN_FROZEN_DEFECTS,
            "pair_rule": hv.PAIR_RULE + ". Утверждения системы - модель V7 (V5AR2Claims: V8, V3, V4, ASM, AR2, AG, TC, "
                                        "RC -> RAR); функции пула пар relation_holdout_v4",
            "pair_params": {"EXACT_CAP": hv.EXACT_CAP, "NEIGH": hv.NEIGH, "COPLACE_TOP": hv.COPLACE_TOP,
                            "COPLACE_MIN": hv.COPLACE_MIN, "SIM_TOP": hv.SIM_TOP, "SIM_MIN": hv.SIM_MIN,
                            "CAND_TOTAL": hv.CAND_TOTAL, "CAND_MIN_INDEP": hv.CAND_MIN_INDEP,
                            "BATCH_PAIRS": hv.BATCH_PAIRS, "SEMANTIC_ALL": hv.SEMANTIC_ALL},
            "ref_schema": hv.REF_SCHEMA, "ref_addendum": dict(ref.ADDENDUM, n_min=N_MIN),
            "pack_dir": PACK.replace(os.sep, "/"),
            "struct_rx": {k: rx.pattern for k, rx in h7.STRUCT_RX.items()},
            "v7_prep": v7_prep_record(),
            "dev_sources_sha256": {k: file_sha(v) for k, v in DEV_SOURCES.items()},
            "truth_v2": {"path": tpath.replace(os.sep, "/"), "sha256": file_sha(tpath),
                         "use": "только исключение кадров разработки; в эталон holdout не идёт"},
            "detector_inputs_sha256": {k: file_sha(v) for k, v in hv.DETECTOR_INPUTS.items() if os.path.exists(v)},
            "inputs_source": {k: v.replace(os.sep, "/") for k, v in inputs.items()},
            "inputs": snap, "input_sha256": {k: file_sha(v) for k, v in snap.items()},
            "code_sha256": {c: file_sha(c) for c in code}}
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                rule="после заморозки ничего из этого не меняется до финального отчёта, даже если первые карточки "
                     "покажут очевидную дыру")
    ir.dump_json(p(out, "FREEZE.json"), data)
    print("V7 заморожен (sha256 %s): входов %d, файлов кода %d, источников разработки %d, исключено ключей %d" % (
        data["sha256"][:12], len(snap), len(code), len(DEV_SOURCES), len(ex)))
    return data


def load_freeze(out=OUT):
    d = ir.load_json(p(out, "FREEZE.json"))
    if ir.sha({k: d[k] for k in BODY}) != d["sha256"]:
        raise SystemExit("FREEZE.json изменён после заморозки: хэш не сходится")
    bad = [k for k, v in d["inputs"].items() if file_sha(v) != d["input_sha256"][k]]
    if file_sha(d["truth_v2"]["path"]) != d["truth_v2"]["sha256"]:
        bad.append("truth_v2")
    if file_sha(d["excluded"]["path"]) != d["excluded"]["sha256"]:
        bad.append("excluded_keys")
    bad += [k for k, h in d["dev_sources_sha256"].items() if file_sha(DEV_SOURCES[k]) != h]
    if bad:
        raise SystemExit("снимок входов или источников разработки изменён: %s" % ", ".join(bad))
    return d


def excluded_of(d):
    return set(ir.load_json(d["excluded"]["path"])["keys"])


def do_select(out=OUT):
    if os.path.exists(p(out, "holdout.json")):
        raise SystemExit("holdout уже отобран: перевыбор запрещён")
    d = load_freeze(out)
    guard(d)
    live_same(d)
    detectors_same(d)
    inp = d["inputs"]
    gen = ir.read_tsv(inp["generation"])
    ex = excluded_of(d)
    t0 = time.time()
    pool = meta_pools(inp, gen, ex)
    print("пулы метаданных %.0f с" % (time.time() - t0), flush=True)
    ctx = hv.ctx_v3()
    si, A = v4.SetIndex(ctx), asm.Assembly(ctx)
    cp = s7.ae2.ctx_places()                      # как V7_PREP: AG, TC, RC на контексте расстановок
    W, Fp, G = tc.Windows(cp), arc.Footprints(cp), ag.Groups(cp)
    disc = {"AR2": lambda k: ar2.discover(ctx, si, k), "ASM": lambda k: asm.discover(A, k),
            "RC": lambda k: arc.discover(Fp, k), "TC": lambda k: tc.discover(W, k), "AG": lambda k: ag.discover(G, k)}
    det, stat = scan(eligible(gen, ex), disc, log=lambda s: print(s, "%.0f с" % (time.time() - t0), flush=True))
    pool.update(det)
    items, short = select(pool)
    data = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"], "seed": SEED,
            "n": len(items), "n_target": N_TOTAL, "pool": {k: len(v) for k, v in pool.items()},
            "pool_sets": {k: len({pset(x[0]) for x in v}) for k, v in pool.items()}, "scan": stat,
            "short": short, "excluded_keys": d["excluded"]["counts"]["total"], "sha256": rh.digest(items),
            "items": items,
            "rule": "список заморожен до ответов и эталона; слой в карточку и пакет судьи не идёт; недобор слоёв "
                    "записан здесь до ответов и в другие слои не переносился"}
    ir.dump_json(p(out, "holdout.json"), data)
    print("отобрано %d из %d (sha256 %s): %s" % (len(items), N_TOTAL, data["sha256"][:12],
                                                 dict(Counter(x["layer"] for x in items))))
    print("проход детекторов:", stat)
    print("недобор:", short or "нет")
    return data


# ---------------------------------------------------------------- relations

FOUND_KEYS = ("AR2", "ASM", "AG", "TC", "RC")


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
    t0 = time.time()
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
    print("маршрут, V3, V4 %.0f с" % (time.time() - t0), flush=True)
    si, A = v4.SetIndex(c3), asm.Assembly(c3)
    cp = s7.ae2.ctx_places()
    W, Fp, G = tc.Windows(cp), arc.Footprints(cp), ag.Groups(cp)
    edges, perm = {k: [] for k in FOUND_KEYS}, []
    for a in keys:
        es = ar2.discover(c3, si, a)
        for e in es:
            fired = bool(ar2.pair(c3, si, e["source"], e["target"], B=v3.permuted(c3, e["target"], 7)))
            perm.append({"pair": [e["source"], e["target"]], "fired": fired})
        edges["AR2"] += es
        edges["ASM"] += asm.discover(A, a)
        edges["AG"] += ag.discover(G, a)
        edges["TC"] += tc.discover(W, a)
        edges["RC"] += arc.discover(Fp, a)
    f7 = p(out, "relations", "found_v7.json")
    ir.dump_json(f7, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "keys": keys, "edges": edges,
                      "ar2_permuted_control": perm,
                      "note": "доводы AR2, ASM, AG, TC, RC; RC переписывается в REPEATED_ASSEMBLY_RELATION при сборке "
                              "утверждений; не маршрут; VERIFIED ставит человек"})
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"],
                        "holdout_sha256": h["sha256"], "relations_sha256": file_sha(path),
                        "path": path.replace(os.sep, "/"), "detectors_sha256": file_sha(dpath),
                        "detectors_path": dpath.replace(os.sep, "/"),
                        "v3_path": f3.replace(os.sep, "/"), "v3_sha256": file_sha(f3),
                        "v4_path": f4.replace(os.sep, "/"), "v4_sha256": file_sha(f4),
                        "v7_path": f7.replace(os.sep, "/"), "v7_sha256": file_sha(f7)})
    print("детекторы заморожены за %.0f с: %s; ASM STRONG %d; перемешанный контроль AR2 %d из %d" % (
        time.time() - t0, {k: len(v) for k, v in edges.items()},
        sum(e["level"] == EDGE_STRONG for e in edges["ASM"]), sum(x["fired"] for x in perm), len(perm)))


def load_found(out=OUT):
    lk = ir.load_json(p(out, "relations.lock.json"))
    for k in ("v3", "v4", "v7"):
        if file_sha(lk[k + "_path"]) != lk[k + "_sha256"]:
            raise SystemExit("%s изменён после заморозки" % lk[k + "_path"])
    return ir.load_json(lk["v3_path"]), ir.load_json(lk["v4_path"]), ir.load_json(lk["v7_path"])


def claim_edges(E, drop=()):
    """Доводы модели V7 из found_v7 edges {детектор: [...]}; drop - детекторы, которые не берутся (диагностика)."""
    out = []
    for k in FOUND_KEYS:
        if k in drop:
            continue
        out += [s7.reclass_rc(e) for e in E[k]] if k == "RC" else list(E[k])
    return out


def system_claims(rows, found3, found4, E, drop=()):
    return rc.claims(rows, found3, found4, claim_edges(E, drop))


# ---------------------------------------------------------------- карточки оси A (сразу чистые, R-187)

def clean_page(raw_page, key):
    """Страница оси A по белому списку полей (axis_a_clean_v5) со своим ключом хранилища; проверка всей страницы."""
    import axis_a_clean_v5 as az5
    import relation_holdout_v4_axis_zip as az
    head, data, tail = az.split_page(raw_page)
    new = [az5.clean_card(c) for c in data]
    cut = "\x00DATA\x00"
    head, tail = az5.clean_template(head + cut + tail).split(cut)
    marker = 'KEY = "%s' % key
    if tail.count(marker) != 1:
        raise SystemExit("ключ хранилища страницы не найден ровно один раз")
    blob = json.dumps(new, ensure_ascii=False)
    full = head + blob + tail
    bad = [w for w in az.FORBIDDEN if w in blob] + [w for w in az5.PAGE_FORBIDDEN if w in full]
    if bad:
        raise SystemExit("на странице осталось запрещённое: %s" % bad)
    if az5.EXPORT not in full:
        raise SystemExit("выгрузка страницы не в пять столбцов")
    return full, new, sorted({k for c in data for k in c} - set(az5.KEEP))


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
    key = "relation-holdout-v7-axisA-" + h["sha256"][:8]
    raw = (rh.PAGE_V.replace(title, "Holdout связей V7: %d новых кадров - только ось A" % len(cards))
           .replace("__DATA__", json.dumps(data, ensure_ascii=False))
           .replace("__MISS__", json.dumps(ic.MISSING)).replace("__SEM__", json.dumps(v8.SEMANTIC))
           .replace("__DEFS__", json.dumps({"semantic_kind": h8.SEM_DEFS}, ensure_ascii=False))
           .replace("__KEY__", key))
    page, clean, dropped = clean_page(raw, key)
    with open(p(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    ir.dump_json(p(out, "cards.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "holdout_sha256": h["sha256"], "img_sha256": ir.img_digest(p(out, "img")),
                                        "assets": [c["asset"] for c in clean], "cards": clean,
                                        "dropped_fields": dropped, "storage_key": key})
    print("карточек %d (белый список полей, убраны %s): %s" % (len(clean), dropped, p(out, "index.html")))


def do_axiszip(out=OUT):
    import axis_a_clean_v5 as az5
    if not os.path.exists(p(out, "reference.lock.json")):
        raise SystemExit("эталон ещё не заморожен - ZIP оси A только после lockref")
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("ответы оси A уже есть")
    page = open(p(out, "index.html"), encoding="utf-8").read()
    cards = ir.load_json(p(out, "cards.json"))["cards"]
    dest = p(out, "axisA_cards")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(p(dest, "img"))
    with open(p(dest, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    imgs = sorted({fn for c in cards for _t, fn in c["panels"]})
    for fn in imgs:
        shutil.copy2(p(out, "img", fn), p(dest, "img", fn))
    zp = dest + ".zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(dest):
            for fn in files:
                fp = os.path.join(root, fn)
                z.write(fp, os.path.relpath(fp, out))
    az5.recheck(zp)
    sha = file_sha(zp)
    ir.dump_json(dest + ".json", {"cards": len(cards), "images": len(imgs), "card_fields": list(az5.KEEP),
                                  "answer_columns": json.loads(az5.EXPORT), "zip": os.path.basename(zp),
                                  "zip_sha256": sha,
                                  "reference_lock_sha256": file_sha(p(out, "reference.lock.json"))})
    print("ZIP оси A: карточек %d, картинок %d; %s (sha256 %s)" % (len(cards), len(imgs), zp, sha[:12]))


# ---------------------------------------------------------------- пул пар

def dev_pairs():
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
    found3, found4, f7 = load_found(out)
    base = hv.routing_base(out, d, h)
    claimed, exact_claimed = defaultdict(set), defaultdict(set)
    for sk in hv.SEMANTIC_ALL:                       # утверждения при любом ответе оси A
        rows = hv.routing_rows(base, lambda a, sk=sk: sk)
        C = system_claims(rows, found3, found4, f7["edges"])
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
        raise SystemExit("пары пула уже были в разработке (истина v2, V4, V5, проверки): %s" % overlap[:10])
    ir.dump_json(p(out, "key.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "holdout_sha256": h["sha256"],
                                      "rule": d["pair_rule"], "per_item": per_item, "items": items,
                                      "note": "ключ вне пакета: источник пары судье не показывается"})
    print("пар %d (обязательных %d, независимых %d); на кадр: мин %d, макс %d" % (
        len(items), sum(v["must"] for v in per_item.values()),
        sum(v["pairs"] - v["must"] for v in per_item.values()),
        min(v["pairs"] for v in per_item.values()), max(v["pairs"] for v in per_item.values())))
    print("по источникам:", dict(Counter(w for it in items for w in it["why"])))


def do_pack(out=OUT, pack=PACK):
    d = load_freeze(out)
    guard(d)
    key = ir.load_json(p(out, "key.json"))
    if os.path.exists(p(out, "pack.lock.json")):
        raise SystemExit("пакет уже собран: %s" % p(out, "pack.lock.json"))
    n = len(key["items"])
    h5.write_pack(out, pack, [{"q": it["q"], "a": it["a"], "b": it["b"]} for it in key["items"]],
                  2 * math.ceil(n / hv.BATCH_PAIRS), SEED)


# ---------------------------------------------------------------- эталон

build_truth = h5.build_truth
judge_files = h5.judge_files


def ref_code():
    return {c: file_sha(c) for c in (SELF, "tools/hdart/relation_holdout_v5.py", "tools/hdart/relation_holdout_v4_ref.py",
                                     "tools/hdart/relation_truth_v2.py", "tools/hdart/relation_taxonomy.py",
                                     "tools/hdart/relation_holdout_v4.py")}


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
    return h5.load_truth(out)


def closed_none_sources(out):
    own = [(r["a"], r["b"], r["existence"]) for r in ir.load_json(p(out, "truth.json"))["pairs"]]
    srcs = [("holdout V7", own)]
    for name, k in NONE_SOURCES:
        srcs.append((name, [(r["a"], r["b"], r["existence"]) for r in ir.load_json(DEV_SOURCES[k])["pairs"]]))
    return srcs


# ---------------------------------------------------------------- подсчёт

def gates_v7(r):
    """Таблица ворот V7_PREP (s7.evaluate_v7) плюс handoff_unassigned -> (строки ворот с группами, вердикт)."""
    vals = {g["gate"]: (g["value"], g["n"]) for g in r["gates"]}
    vals["handoff_unassigned"] = r["legacy"]["handoff_unassigned"]
    gates, verdict = h5.acceptance(vals, tuple(g[:3] for g in GATES), N_MIN)
    grp = {g[0]: g[3] for g in GATES}
    for g in gates:
        g["group"] = grp[g["gate"]]
    return gates, verdict


def unique_saves(full, without):
    """Кадры, которые frame safety находит только с доводами детектора, и кадры, опасные без них."""
    return {"frame_safety_only_with": sorted(set(without["frame_safety"]["missed"]) -
                                             set(full["frame_safety"]["missed"])),
            "dangerous_without": sorted(set(without["pp"]["pre_dangerous"]) - set(full["pp"]["pre_dangerous"])),
            "dangerous_post_without": sorted(set(without["pp"]["post_dangerous"]) -
                                             set(full["pp"]["post_dangerous"]))}


def rar_diag(pc, C, keys, pool):
    st = Counter()
    for _a, _b, t, cs in pc:
        if not any(e["detector"] == s7.RAR_DETECTOR for c in cs for e in c["support"]):
            continue
        st["triggered"] += 1
        st["true_relation" if t and t[0] == "RELATED" else "none" if t and t[0] == "NONE" else "open"] += 1
        if t and t[0] == "RELATED" and "COMPOSITE" in t[1]:
            st["closed_composite"] += 1
    st["outside_pool"] = sum(1 for a in keys for c in C.of(a) if frozenset(c["pair"]) not in pool
                             for e in c["support"] if e["detector"] == s7.RAR_DETECTOR)
    return dict(st, existence_precision=v2.rate(st["true_relation"], st["true_relation"] + st["none"]))


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
    found3, found4, f7 = load_found(out)
    E = f7["edges"]
    base = hv.routing_base(out, d, h)
    rows = hv.routing_rows(base, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    items = ir.load_json(p(out, "key.json"))["items"]
    pool = {pk(it["a"], it["b"]) for it in items}
    args = (T, items, keys, h, base["fsets"])
    none_pairs = prs.closed_none(*closed_none_sources(out))
    c3 = v3.Ctx(index=v2.load_index(v2.OUT))
    tinfo = s7.tinfo_of(c3)

    def ev(drop=()):
        C = system_claims(rows, found3, found4, E, drop)
        return C, s7.evaluate_v7(rows, C, args, trow, keys, none_pairs, tinfo)
    C, r = ev()
    gates, verdict = gates_v7(r)
    new, pp = r["ev"], r["pp"]
    _c, no_rar = ev(("RC",))
    _c, no_ar2 = ev(("AR2",))
    _c, no_asm = ev(("ASM", "AG", "TC", "RC"))
    cand, strong = h5.asm_pairs(new["pc"], trow)
    outside = rd5.outside_dets(C, keys, pool) + [
        ("%s ~ %s" % tuple(c["pair"]), e["detector"], e["rule"], e["level"]) for a in keys for c in C.of(a)
        if frozenset(c["pair"]) not in pool for e in c["support"] if e["detector"] == ar2.DETECTOR]
    ad = h5.ar2_diag(new["pc"], f7.get("ar2_permuted_control", []), outside)
    ad.update(unique_saves(r, no_ar2))
    cd = h5.asm_cand_diag(cand, new["pc"], pp["unmasked"])
    sd = Counter(triggered=len(strong))
    for x in strong:
        sd[{"yes": "true_composite", "no": "not_composite", "OPEN": "open"}[x["composite"]]] += 1
    rar = dict(rar_diag(new["pc"], C, keys, pool), **unique_saves(r, no_rar))
    drop = pp["dropped_candidates"]
    post_d = {"removed_closed_none": len(drop),
              "removed_by_detector": dict(Counter(x for dd in drop for x in dd["detectors"])),
              "removed_by_source": dict(Counter(s for dd in drop for s in dd["truth"])),
              "strong_on_closed_none": len(pp["strong_on_closed_none"]),
              "became_dangerous_after_review": [u["asset"] for u in pp["unmasked"]],
              "invariant_holds": not pp["unmasked"] and pp["POST_REVIEW_DANGEROUS"] == 0}
    fs, dg = r["frame_safety"], r["diagnostic"]
    score = {x["asset_id"]: x for x in new["score"]}
    by_layer = {}
    for x in h["items"]:
        s = score[x["asset_id"]]
        L = by_layer.setdefault(x["layer"], Counter())
        L["frames"] += 1
        L["creative"] += s["creative"]
        L["dangerous_pre"] += bool(s["danger"])
        L["dangerous_post"] += x["asset_id"] in pp["post_dangerous"]
        L["frame_safety_missed"] += x["asset_id"].upper() in fs["missed"]
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE, "freeze_sha256": d["sha256"],
           "holdout_sha256": h["sha256"], "reference_locked": lk["created"], "n_frames": len(keys),
           "n_target": N_TOTAL, "short": h["short"], "verdict": verdict, "verdict_rule": VERDICT_RULE,
           "gates": gates, "gates_legacy": new["gates"], "metrics": new["metrics"], "recall": new["recall"],
           "frame_safety": fs,
           "composite": {"frame_recall": dg["composite_frame_subtype_recall"], "pair_recall": dg["composite_pair_recall"],
                         "strong_only": dg["composite_strong_recall"], "note": "только диагностика"},
           "module": dict(dg["module_recall"], note="только диагностика"),
           "rar": rar, "rar_pairs": dg["rar_pairs"], "assembly_family_existence": dg["assembly_family_existence"],
           "assembly_unique_saves": unique_saves(r, no_asm),
           "ar2": ad, "asm_candidate": cd, "asm_candidate_pairs": cand, "asm_strong": dict(sd),
           "asm_strong_pairs": strong, "post_review": pp, "post_review_invariant": post_d,
           "diagnostics": hv.diagnostics(new["pc"], {k.upper() for k in keys}, tinfo),
           "claims_outside_pool": new["outside"], "invalid": bad, "truth": dict(Counter(t[0] for t in T.values())),
           "pairs": len(new["pc"]), "rows": new["score"], "dangerous_pre": pp["pre_dangerous"],
           "dangerous_post": pp["post_dangerous"], "by_layer": {k: dict(v) for k, v in by_layer.items()},
           "known_open": d["known_open"], "known_frozen_defects": d["known_frozen_defects"]}
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    print("вердикт %s; PRE %d, POST %d, frame safety %s (%d из %d); отчёт: %s" % (
        verdict, pp["PRE_REVIEW_DANGEROUS"], pp["POST_REVIEW_DANGEROUS"], hv.f3(fs["value"]), fs["hit"], fs["n"],
        p(out, "report.md")))
    return res


def write_md(out, res):
    f3 = hv.f3
    L = ["# RELATION_SAFETY_MODEL_V7 — слепой holdout на %d кадрах (цель %d)" % (res["n_frames"], res["n_target"]),
         "", "Вердикт: **%s**. Снимок %s, эталон заморожен %s. Правило: %s" % (
             res["verdict"], res["freeze_sha256"][:12], res["reference_locked"], res["verdict_rule"]), "",
         "Недобор слоёв (записан до ответов): %s" % (res["short"] or "нет"), "",
         "## Ворота", "", "| группа | ворота | значение | n | нужно | итог |", "|---|---|---|---|---|---|"]
    for g in res["gates"]:
        L.append("| %s | %s | %s | %s | %s | %s |" % (g["group"], g["gate"], f3(g["value"]), g["n"], g["need"],
                                                     g["status"]))
    fs = res["frame_safety"]
    L += ["", "## related_frame_safety_recall", "",
          "- найдено %d из %d (%s); лучшее действие по кадрам %s" % (fs["hit"], fs["n"], f3(fs["value"]),
                                                                     fs["by_best_action"]),
          "- варианты (диагностика): только BLOCK+REVIEW %s; только значимые пары %s; кадры с закрытым значимым "
          "ярлыком %s (n %d)" % (f3(fs["variant_block_review_only"]), f3(fs["variant_relevant_pair_only"]),
                                f3(fs["variant_closed_relevant_frames"]["value"]),
                                fs["variant_closed_relevant_frames"]["n"])]
    L += ["- промахи:"] if fs["missed"] else ["- промахов нет"]
    for f, prs_ in fs["missed"].items():
        L.append("  - %s: %s" % (f, "; ".join("%s %s %s" % (x["other"], x["truth"], x["claims"] or "")
                                              for x in prs_)))
    rar = res["rar"]
    L += ["", "## REPEATED_ASSEMBLY_RELATION", "",
          "- triggered %d: true relation %d (из них закрытый COMPOSITE %d), NONE %d, OPEN %d, вне пула %d; "
          "точность существования %s" % (rar.get("triggered", 0), rar.get("true_relation", 0),
                                         rar.get("closed_composite", 0), rar.get("none", 0), rar.get("open", 0),
                                         rar.get("outside_pool", 0), f3(rar["existence_precision"])),
          "- unique safety saves: frame safety только с RAR %s; опасные без RAR %s (после ревью %s)" % (
              rar["frame_safety_only_with"] or "нет", rar["dangerous_without"] or "нет",
              rar["dangerous_post_without"] or "нет")]
    L += ["- пары:"] + ["  - " + x for x in res["rar_pairs"]] if res["rar_pairs"] else ["- пар с RAR в пуле нет"]
    cm = res["composite"]
    L += ["", "## Составной и модуль (только диагностика)", "",
          "- composite frame recall %s (n %s), pair recall %s (n %s), STRONG-only %s" % (
              f3(cm["frame_recall"]["value"]), cm["frame_recall"]["n"], f3(cm["pair_recall"]["value"]),
              cm["pair_recall"]["n"], {k: (f3(v) if isinstance(v, float) else v)
                                       for k, v in cm["strong_only"].items()}),
          "- module: %s" % res["module"],
          "- детекторы сборки, существование на парах пула: %s" % res["assembly_family_existence"],
          "- без всех детекторов сборки: %s" % res["assembly_unique_saves"]]
    pi = res["post_review_invariant"]
    L += ["", "## AR2", "", "- %s" % json.dumps(res["ar2"], ensure_ascii=False),
          "", "## ASSEMBLY (ASM V1)", "", "- candidate: %s" % json.dumps(res["asm_candidate"], ensure_ascii=False),
          "- STRONG: %s" % json.dumps(res["asm_strong"], ensure_ascii=False),
          "", "## Безопасность после ревью", "",
          "- удалено как CLOSED-NONE: %d; по детекторам %s; по источникам %s" % (
              pi["removed_closed_none"], pi["removed_by_detector"], pi["removed_by_source"]),
          "- STRONG на closed NONE (остаются): %d" % pi["strong_on_closed_none"],
          "- стали опасными после удаления: %s" % (pi["became_dangerous_after_review"] or "нет"),
          "- инвариант держится: %s" % ("да" if pi["invariant_holds"] else "**нет**"),
          "", "## Прочее", "",
          "- истина пула: %s, пар %d" % (res["truth"], res["pairs"]),
          "- опасные до ревью: %s; после: %s" % (res["dangerous_pre"] or "нет", res["dangerous_post"] or "нет"),
          "- утверждения вне пула: %d" % len(res["claims_outside_pool"]),
          "- по слоям: %s" % json.dumps(res["by_layer"], ensure_ascii=False)]
    if res["invalid"]:
        L += ["", "Ошибки ответов: " + "; ".join(res["invalid"])]
    L += ["", "## Известное открытое", ""] + ["- %s: %s (%s)" % (x["id"], x["text"], x["decided"])
                                               for x in res["known_open"]]
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
                                    "axiszip", "verify", "report", "check"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    {"pools": do_pools, "freeze": freeze, "select": do_select, "relations": do_relations, "cards": do_cards,
     "pairs": do_pairs, "pack": do_pack, "lockref": do_lockref, "axiszip": do_axiszip, "verify": do_verify,
     "report": do_report, "check": do_check}[a.cmd](a.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
