#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""RELATION_DISCOVERY_V4 - заморозка и слепой holdout на 80 новых кадрах (специалист 02.10, передал Vitali в чате). CPU.

Диагностический пересчёт V4 (probes/relation-discovery-v4-prep) прошёл шесть условий на тех же 60 и контроле - это
не приёмка: связки клеток и R4 придуманы на той же выборке. Здесь V4 замораживается ДО отбора новых кадров, и после
заморозки ничего не меняется до финального отчёта: ни детекторы, ни пороги, ни политики, ни ворота, ни подсчёт,
даже если первые карточки покажут очевидную дыру. Замороженные V2-V8, их папки и истина v2 только читаются.

Что заморожено (FREEZE.json): код и хэши relation_discovery_v2/v3/v4, relation_taxonomy, relation_truth_v2,
маршрута V8 и этого модуля с отборщиком и подсчётом; все пороги детекторов; политика TYPE_STRONG / TYPE_OPEN и
автоматического действия; MIRRORED_RECOLOR - существование STRONG, подтип MIRRORED_RECOLOR_CANDIDATE (TYPE_OPEN);
определения составного, состояния и безопасности; снимок истины v2 и её хэш (истина v2 - только разработка и
контроль, в эталон holdout не идёт); схема эталона; ворота ровно как прошли; слои отбора и правило переноса недобора;
копии и хэши всех входов.

Ворота (GATES, ровно шесть плюс технический handoff; CI, подтипа зеркала и модуля нет):
dangerous_creative_standalone = 0, relation_existence_precision >= 0.95, derived_recolor_discovery >= 0.70,
state_discovery >= 0.70, true_composite_recall >= 0.70, automatic_action_precision >= 0.95, handoff_unassigned = 0.

Порядок (каждый шаг отказывается, если предыдущего нет или свой уже сделан):
    pools      до заморозки: только размеры пулов отбора на живых входах (содержимое не печатается)
    freeze     снимок (FREEZE.json, inputs/, inputs/truth_v2.json)
    select     80 кадров автоматически: родство 18, состояние MCD 12, кусок / составной 14, поверхность конструкции 12,
               рельеф / не предмет 8, обычный одиночный 16; один кадр на набор PCK; исключены кадры и наборы
               holdout V4_R1 / V5 / V7 / V8 с роднёй, кадры разработки V2 / V3 / V4 (истина v2, контроль,
               слепое зеркало, первый пакет) и их наборы; недобор переносится по замороженному правилу и пишется
    relations  замороженные детекторы на 80: маршрут V8 (relation_probe, детекторы V7), V3 (с V2), V4 - и замок
    cards      страница специалиста: только ось A, как в V8
    pairs      пул пар для эталона: все утверждения системы на кадре (при любом ответе оси A) плюс независимые
               кандидаты (побайтовые копии, рёбра MCD в обе стороны, соседние номера, соседи на картах, похожий
               силуэт прямо и в отражении) - key.json вне пакета
    pack       слепой пакет: два независимых судьи на пару, без источника, уровня и кадра «B mirrored»
    lockref    истина holdout из ответов судей (схема истины v2) - заморозить до ответов специалиста
    report     ворота, вердикт и обязательная диагностика по ответам оси A и замороженным выходам
    check      все хэши целы

    py -3.13 tools/hdart/relation_holdout_v4.py pools|freeze|select|relations|cards|pairs|pack|lockref|report|check
"""
import argparse
import json
import math
import os
import shutil
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir                     # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_taxonomy as tx                    # noqa: E402
import routing_holdout as rh                      # noqa: E402
import routing_holdout_v5 as h5                   # noqa: E402
import routing_holdout_v7 as h7                   # noqa: E402
import routing_holdout_v8 as h8                   # noqa: E402   (импорт ставит h7.SEED = зерно V8 - ниже своё)
import routing_rules as rr                        # noqa: E402

ENC = ir.ENC
OUT = os.path.join(ir.PROBES, "relation-holdout-v4")
SEED = "relation-holdout-v4-2026-10-02"
h7.SEED = SEED                       # ленивые пулы h7.pools берут зерно из своего модуля; код V7/V8 не меняется
N_TOTAL = 80
INPUTS = dict(h8.INPUTS)
CODE = ["tools/hdart/relation_holdout_v4.py", "tools/test_relation_holdout_v4.py",
        "tools/hdart/relation_discovery_v4.py", "tools/test_relation_discovery_v4.py",
        "tools/hdart/relation_discovery_v3.py", "tools/hdart/relation_discovery_v2.py",
        "tools/hdart/relation_taxonomy.py", "tools/hdart/relation_truth_v2.py"] + list(h8.CODE)
DETECTOR_INPUTS = {"v2_index": os.path.join(v2.OUT, "index", "frames.json"),
                   "v3_masks": os.path.join(v3.OUT, "index", "masks.npz")}
TRUTH_V2_SOURCES = [os.path.join(tx.OUT, "blind_key.json"), os.path.join(tx.OUT, "pack.lock.json"),
                    os.path.join(ir.PROBES, "relation-truth-v2", "key.json"),
                    os.path.join(ir.PROBES, "relation-truth-v2", "pack.lock.json")]
DEV = {"truth_v2": "истина v2: все пары (первый пакет, 60 V8, контроль)",
       "mirror_blind": os.path.join(ir.PROBES, "mirror-recolor-blind-v1", "key.json"),
       "taxonomy_key": os.path.join(tx.OUT, "blind_key.json"),
       "v3_controls": os.path.join(v3.OUT, "controls.json"),
       "v4_controls": os.path.join(v4.OUT, "controls_v4.json"),
       "v4_relations": os.path.join(v4.OUT, "relations_v4.json")}
# кадры разработки исключаются по ключу; их наборы - нет: при исключении наборов (474) пулы до заморозки давали 64 из
# 80, слой состояния MCD - 1 из 12, обычный одиночный - 5 из 16 (замер pools 02.10). Кадр разработки и обе стороны
# его пар исключены, родня - только в пуле пар как контекст
DEV_SETS = False

# слои: подслои V7 с квотами под 80 (специалист: 18 / 12 / 14 / 12 / 8 / 16)
LAYERS = (("relation", 18, (("fr2_new", 4), ("fr2_verified", 3), ("legacy_recolor", 3), ("material_variant", 3),
                            ("family_mirror", 3), ("family_open", 2))),
          ("mcd_state", 12, (("mcd_die", 4), ("mcd_alt", 2), ("mcd_anim", 2), ("mcd_dominance", 1),
                             ("mcd_candidate", 3))),
          ("part", 14, (("part_suspect", 4), ("part_words", 3), ("composite", 4), ("modular_words", 3))),
          ("structural", 12, (("stairs", 2), ("door", 2), ("hull", 2), ("roof", 1), ("panel", 1), ("wall", 3),
                              ("vehicle_body", 1))),
          ("terrain", 8, (("floor", 2), ("relief", 3), ("object_or_relief", 2), ("surface_mcd", 1))),
          ("standalone", 16, (("standalone", 16),)))
# порядок заполнения слоёв: редкие первыми, иначе один набор на holdout отдаёт их наборы богатым слоям (замер pools
# 02.10 до заморозки: в очереди после исключений 287 кадров в 97 наборах; при порядке LAYERS одиночный 1 из 16 при 6
# кандидатах, состояние MCD 3 из 12). Квоты и ворота от порядка не зависят
FILL_ORDER = ("mcd_state", "standalone", "terrain", "structural", "part", "relation")
SELECT_RULE = ("слои в порядке FILL_ORDER, подслои по порядку, внутри - зерно SEED; ключ один раз, набор PCK один раз на весь "
               "holdout. Недобор подслоя добирается другими подслоями того же слоя по кругу (как V7). Недобор слоя "
               "после этого переносится в другие слои по кругу в порядке FILL_ORDER (по одному кадру на слой за круг, из "
               "оставшихся кандидатов его подслоёв); перенос и недобор пишутся в holdout.json, руками не добираются")

# пул пар эталона (до ответов, вне пакета)
EXACT_CAP = 3          # побайтовых копий / отражений на кадр: утверждения EXACT и авторитет вместе, по зерну
NEIGH = 2              # соседние номера в том же наборе: f-2..f+2
COPLACE_TOP, COPLACE_MIN = 3, 2      # соседи на картах (27 сдвигов, все слои): верхние по числу мест, мест не меньше
SIM_TOP, SIM_MIN = 3, 0.85           # похожий силуэт (маски V3): прямо и в отражении, IoU не меньше
CAND_TOTAL, CAND_MIN_INDEP = 14, 4   # на кадр: обязательные + независимые до 14, независимых не меньше 4
BATCH_PAIRS = 40                     # пар в партии судьи; партий 2 * ceil(n / 40), каждая пара у двух судей
SEMANTIC_ALL = ["OBJECT", "OBJECT_PART", "STRUCTURAL_SURFACE", "TERRAIN_RELIEF", "NOT_OBJECT", "UNSURE"]
PAIR_RULE = ("пул пар до ответов: (1) все утверждения системы V4 на кадре holdout - маршрут V8 при каждом из шести "
             "значений оси A (объединение), V3 с V2 после convert_v3, V4 - кроме чисто побайтовых сверх EXACT_CAP; "
             "(2) авторитет: все рёбра MCD в обе стороны (routing_model_v8.facts), побайтовые копии и отражения до "
             "EXACT_CAP вместе с утверждёнными; (3) независимые, по кругу: соседние номера f-2..f+2, соседи на "
             "картах (COPLACE_TOP при COPLACE_MIN местах), похожий силуэт прямо и в отражении (SIM_TOP при IoU >= "
             "SIM_MIN) - до CAND_TOTAL на кадр, но не меньше CAND_MIN_INDEP независимых. Пара неупорядочена, один "
             "раз на весь пул; источник в пакет не идёт")

# политика (как в диагностике V4, вариант «MR открыт»)
POLICY = {
    "claims_class": "relation_discovery_v4.V4Claims (TaxClaims поверх _Base4): MR4 - TYPE_OPEN",
    "type_strong": "довод TYPE_STRONG, если существование STRONG и нет причин открыть тип (кандидат, только "
                   "диагностический детектор, спор типа, спор направления); R4 и ATTACHMENT_CANDIDATE - всегда "
                   "TYPE_OPEN; анимация и перекраска сосуществуют (перекраска при STRONG-анимации - улика, "
                   "production = False)",
    "auto_action": "relation_taxonomy.auto_claim: существование STRONG, TYPE_STRONG, production",
    "mirrored_recolor": {"existence": "STRONG", "subtype": "MIRRORED_RECOLOR_CANDIDATE", "type_level": "TYPE_OPEN",
                         "derivation": "нет независимого рисования и нет автоматического вывода зеркалом / перекраской",
                         "promotion": "только в следующей версии при подтипе >= 0.95 на новом независимом материале"},
    "composite": "составной - довод группы composite (PLACE4: P3L / P3Lx / P3Lc, P5r STRONG при двух уликах вне карты, "
                 "P5rc - кандидат; маршрут V8); ATTACHMENT_CANDIDATE (A1 / A1r) - только улика, в составной не идёт",
    "state": "состояние - довод группы state (MCD die / alt, маршрут V8 R3m / D1)",
    "creative": "кадр творческий: routing_model_v8.pipeline_of(semantic_eff, surface, v4.pipe_roles) = "
                "OBJECT_PIPELINE, не v4.bound и не v3.has_evidence (как в пересчёте V4)",
    "thresholds": v4.THRESHOLDS,
    "relation_unit": rr.RELATION_UNIT_HOLDOUT,
    "routing": "routing_model_v8.decide с пустыми opts и build_graph (как отчёт V8): рёбра и обратные чтения - вход "
               "relation_discovery_v3.claims_from_v8"}
# безопасность: правило V2 (danger_v2) на схеме истины v2 - без направления от судьи
JOINT_LABELS = ("EXACT_COPY", "RECOLOR_PEER", "MIRRORED_VARIANT_PEER", "DERIVED", "STATE_VARIANT",
                "ANIMATION_FAMILY", "COMPOSITE", "MODULAR_SECTION")
DIRECTED = ("RECOLOR_PEER", "MIRRORED_VARIANT_PEER", "DERIVED", "STATE_VARIANT", "ANIMATION_FAMILY", "EXACT_COPY")
SAFETY = {"dangerous_creative_standalone":
          "кадр творческий (POLICY.creative) по ответу оси A специалиста И есть пара пула, где истина RELATED и среди "
          "закрытых ярлыков есть JOINT_LABELS, и при этом: (а) для ярлыков вывода, состояния и анимации направление "
          "по v2.eff_direction с direction open (судья направления не даёт): asset_derived (входящее ребро MCD) - "
          "опасно всегда; relative_derived (своя запись MCD называет родственника) - не опасно; симметрично - "
          "опасно, если на паре нет ни одного довода; (б) для COMPOSITE и MODULAR_SECTION - опасно, если на паре нет "
          "ни одного довода. RELATED с открытым подтипом в ворота не идёт (как OPEN_REL в V2), считается отдельно",
          "axis": "одна ось - ответы специалиста (end-to-end); эталона по оси A у судей нет, поэтому правило V2 "
                  "«эталону нужен не OBJECT» и «роль без пары» здесь неприменимы",
          "labels": list(JOINT_LABELS)}
REF_SCHEMA = {"existence": ["RELATED", "NONE", "OPEN"],
              "allowed_subtype_set": "закрытые ярлыки (relation_truth_v2.combine_pair): ярлык у обоих судей или "
                                     "общая группа; остальные - открытые",
              "confidence": "берутся high и medium (relation_taxonomy.truth_of); low и UNSURE не берутся",
              "authority": "побайтовая копия / отражение или ребро MCD в любую сторону закрывают существование "
                           "RELATED (relation_truth_v2.authority); подтип решают судьи",
              "judges": "два независимых судьи-модели на пару, разные партии; специалист не судит пары",
              "frozen": "истина пишется и замораживается до файла ответов оси A"}
GATES = {"dangerous_creative_standalone": 0, "relation_existence_precision": 0.95, "derived_recolor_discovery": 0.70,
         "state_discovery": 0.70, "true_composite_recall": 0.70, "automatic_action_precision": 0.95,
         "handoff_unassigned": 0}
GATE_FROM_V4 = {"dangerous_creative_standalone": "dangerous", "relation_existence_precision": "existence_precision",
                "derived_recolor_discovery": "derived_discovery", "state_discovery": "state_discovery",
                "true_composite_recall": "composite_discovery", "automatic_action_precision": "auto_action_precision"}
GATE_DEFS = {"relation_existence_precision": "v4.metrics: пары пула с доводом существования STRONG и закрытой "
                                             "истиной; доля RELATED",
             "derived_recolor_discovery": "v4.recall derived: пары RELATED с закрытым RECOLOR_PEER / "
                                          "MIRRORED_VARIANT_PEER / DERIVED (без EXACT_COPY); доля с доводом группы "
                                          "derived любого уровня",
             "state_discovery": "v4.recall state: закрытый STATE_VARIANT; доля с доводом группы state",
             "true_composite_recall": "v4.recall composite: закрытый COMPOSITE; доля с доводом группы composite",
             "automatic_action_precision": "v4.metrics: доводы auto_claim на парах с закрытой истиной; доля ok по "
                                           "relation_truth_v2.claim_state",
             "handoff_unassigned": "строки маршрута V8 с pipeline_target вне routing_model_v8.PIPELINES",
             "no_data": "знаменатель 0 - NO_DATA; вердикт PASS - все ворота прошли, FAIL - хоть одно не прошло, "
                        "INCONCLUSIVE - ни одно не провалено, но есть NO_DATA"}
DIAG_DEFS = ["EXACT_COPY precision / recall", "MIRRORED_RECOLOR: existence precision, subtype precision, "
             "triggered / closed / open", "COMPOSITE: item recall, pair recall, пол / стена / предмет, чем закрыта "
             "каждая пара", "DERIVED/RECOLOR: полнота по семейству детекторов и пары, не найденные ничем",
             "STATE: STRONG-only recall и STRONG+CANDIDATE discovery recall",
             "автоматические действия по типу: correct / wrong / open",
             "связки клеток P5r / P5rc: triggered / helped / unnecessary / hurt",
             "R4b / R4d / R4c: triggered / correct existence / wrong existence / subtype open",
             "опасные с открытым подтипом (вне ворот), утверждения вне пула (должно быть 0)"]
BODY = ("policy", "safety", "ref_schema", "gates", "gate_defs", "gate_from_v4", "diag_defs", "seed", "n_total",
        "layers", "fill_order", "dev_sets", "select_rule", "pair_rule", "pair_params", "struct_rx", "dev_sources", "truth_v2",
        "detector_inputs_sha256", "inputs_source", "inputs", "input_sha256", "code_sha256")
file_sha = rh.file_sha
pset = rh.pset
pk = tx.pk


def p(out, *name):
    return os.path.join(out, *name)


def order(key):
    import hashlib
    return hashlib.sha256((SEED + "|" + key).encode()).hexdigest()


# ---------------------------------------------------------------- freeze

def truth_v2_snapshot():
    """Истина v2 как есть (relation_truth_v2.truth_v2) - список пар; только разработка и контроль."""
    import relation_truth_v2 as tv
    T, _rows, bad, _j2 = tv.truth_v2()
    pairs = sorted([sorted(k), v[0], sorted(v[1]), sorted(v[2]), v[3]] for k, v in T.items())
    return {"pairs": [{"a": k[0], "b": k[1], "existence": ex, "closed": c, "open": o, "source": s}
                      for k, ex, c, o, s in pairs],
            "format_errors": bad, "existence": dict(Counter(x[1] for x in pairs))}


def freeze(out=OUT, inputs=None, code=None, truth=None):
    if os.path.exists(p(out, "FREEZE.json")):
        raise SystemExit("снимок уже заморожен: %s" % p(out, "FREEZE.json"))
    if os.path.exists(p(out, "holdout.json")):
        raise SystemExit("кадры уже отобраны - снимок после отбора не делается")
    inputs = inputs or INPUTS
    code = CODE if code is None else code
    os.makedirs(p(out, "inputs"), exist_ok=True)
    snap = {}
    for k, src in inputs.items():
        dst = p(out, "inputs", os.path.basename(src))
        if os.path.exists(dst):
            raise SystemExit("в inputs/ два входа с именем %s" % os.path.basename(src))
        shutil.copyfile(src, dst)
        snap[k] = dst.replace(os.sep, "/")
    tpath = p(out, "inputs", "truth_v2.json")
    ir.dump_json(tpath, truth if truth is not None else truth_v2_snapshot())
    body = {"policy": POLICY, "safety": SAFETY, "ref_schema": REF_SCHEMA, "gates": GATES, "gate_defs": GATE_DEFS,
            "gate_from_v4": GATE_FROM_V4, "diag_defs": DIAG_DEFS, "seed": SEED, "n_total": N_TOTAL,
            "layers": [[n, q, [list(s) for s in sub]] for n, q, sub in LAYERS], "fill_order": list(FILL_ORDER),
            "dev_sets": DEV_SETS, "select_rule": SELECT_RULE,
            "pair_rule": PAIR_RULE,
            "pair_params": {"EXACT_CAP": EXACT_CAP, "NEIGH": NEIGH, "COPLACE_TOP": COPLACE_TOP,
                            "COPLACE_MIN": COPLACE_MIN, "SIM_TOP": SIM_TOP, "SIM_MIN": SIM_MIN,
                            "CAND_TOTAL": CAND_TOTAL, "CAND_MIN_INDEP": CAND_MIN_INDEP, "BATCH_PAIRS": BATCH_PAIRS,
                            "SEMANTIC_ALL": SEMANTIC_ALL},
            "struct_rx": {k: rx.pattern for k, rx in h7.STRUCT_RX.items()},
            "dev_sources": {k: v.replace(os.sep, "/") for k, v in DEV.items()},
            "truth_v2": {"path": tpath.replace(os.sep, "/"), "sha256": file_sha(tpath),
                         "sources_sha256": {s.replace(os.sep, "/"): file_sha(s) for s in TRUTH_V2_SOURCES
                                            if os.path.exists(s)},
                         "use": "только разработка и контроль; в эталон holdout не идёт"},
            "detector_inputs_sha256": {k: file_sha(v) for k, v in DETECTOR_INPUTS.items() if os.path.exists(v)},
            "inputs_source": {k: v.replace(os.sep, "/") for k, v in inputs.items()},
            "inputs": snap, "input_sha256": {k: file_sha(v) for k, v in snap.items()},
            "code_sha256": {c: file_sha(c) for c in code}}
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                decided="специалист 02.10, передал Vitali в чате: freeze RELATION_DISCOVERY_V4 утверждён (diagnostic "
                        "gates PASS 6/6, acceptance NOT YET VALIDATED); MIRRORED_RECOLOR - existence STRONG, subtype "
                        "CANDIDATE / TYPE_OPEN; новый слепой holdout на 80 кадрах, отбор автоматический; ворота ровно "
                        "те шесть плюс handoff; истина v2 - не эталон holdout",
                rule="после заморозки ничего из этого не меняется до финального отчёта, даже если первые карточки "
                     "покажут очевидную дыру")
    ir.dump_json(p(out, "FREEZE.json"), data)
    print("V4 заморожен (sha256 %s): входов %d, файлов кода %d, истина v2 %s" % (
        data["sha256"][:12], len(snap), len(code), body["truth_v2"]["sha256"][:12]))
    return data


def load_freeze(out=OUT):
    d = ir.load_json(p(out, "FREEZE.json"))
    if ir.sha({k: d[k] for k in BODY}) != d["sha256"]:
        raise SystemExit("FREEZE.json изменён после заморозки: хэш не сходится")
    bad = [k for k, v in d["inputs"].items() if file_sha(v) != d["input_sha256"][k]]
    if file_sha(d["truth_v2"]["path"]) != d["truth_v2"]["sha256"]:
        bad.append("truth_v2")
    if bad:
        raise SystemExit("снимок входов изменён: %s" % ", ".join(bad))
    return d


def code_changed(d):
    return [c for c, h in d["code_sha256"].items() if not os.path.exists(c) or file_sha(c) != h]


def guard(d):
    ch = code_changed(d)
    if ch:
        raise SystemExit("код изменён после заморозки: %s" % ", ".join(ch))


def detectors_same(d):
    bad = [k for k, h in d["detector_inputs_sha256"].items() if file_sha(DETECTOR_INPUTS[k]) != h]
    if bad:
        raise SystemExit("индексы детекторов изменены после заморозки: %s" % ", ".join(bad))


live_same = h5.live_same


# ---------------------------------------------------------------- select

def dev_frames(truth):
    """Кадры разработки V2 / V3 / V4: истина v2 (обе стороны), слепое зеркало, первый пакет, контроль V3 / V4,
    утверждения V4 на 60. Только чтение замороженных папок."""
    ks = set()
    for x in truth["pairs"]:
        ks |= {x["a"].upper(), x["b"].upper()}
    for name in ("mirror_blind", "taxonomy_key"):
        if os.path.exists(DEV[name]):
            for it in ir.load_json(DEV[name])["items"]:
                ks |= {it["a"].upper(), it["b"].upper()}
    for name in ("v3_controls", "v4_controls"):
        if os.path.exists(DEV[name]):
            for r in ir.load_json(DEV[name])["pairs"]:
                ks |= {r["asset_id"].upper(), r["relative"].upper()}
    if os.path.exists(DEV["v4_relations"]):
        f4 = ir.load_json(DEV["v4_relations"])
        ks |= {k.upper() for k in f4["keys"]}
        for e in f4["edges"]:
            ks |= {e["source"].upper(), e["target"].upper()}
    ks.discard("")
    return ks


def exclusions(inp, truth):
    """Исключения V8 (разработка V3-V7, holdout V4_R1 / V5 / V7 с роднёй) плюс holdout V8 с роднёй (как V8 исключал
    V7) плюс кадры разработки V2 / V3 / V4 и их наборы."""
    import family_relation_v2 as fr2m
    import mcd_state as ms
    ex_sets, ex_keys = h8.exclusions(inp)
    fr2 = fr2m.load(inp["family_relation_v2"])
    mcd = ms.index(ir.load_json(inp["mcd_state"])["relations"])
    ks = [x["asset_id"] for x in rh.load_holdout(h8.OUT)["items"]]
    ex_keys |= {k.upper() for k in ks}
    ex_sets |= {pset(k) for k in ks}
    for k, rs in rh.load_relations(h8.OUT).items():
        ex_sets |= {pset(r["relative"]) for r in rs}
    for k in ks:
        ex_sets |= {pset(e["relative"]) for e in fr2.get(k.upper(), [])}
        ex_sets |= {pset(x["relative"]) for x in mcd.get(k.upper(), [])}
    for r in ir.read_tsv(p(h8.OUT, "reference_pairs.tsv")):
        ex_sets |= {pset(r["asset_id"]), pset(r["relative"])}
    dev = dev_frames(truth)
    ex_keys |= dev
    if DEV_SETS:
        ex_sets |= {pset(k) for k in dev}
    return ex_sets, ex_keys


def select(pool, layers=LAYERS, n_total=N_TOTAL, fill=None):
    """SELECT_RULE: как h7.select, но слои в порядке fill (FILL_ORDER), плюс перенос недобора слоя в другие слои."""
    fill = list(fill if fill is not None else [n for n, _q, _s in layers])
    layers = sorted(layers, key=lambda L: fill.index(L[0]) if L[0] in fill else len(fill))
    pick, short, moved_in, used_sets, used_keys = [], {}, Counter(), set(), set()

    def cands(name):
        seen, out = set(), []
        for x in sorted(pool.get(name, []), key=lambda x: order(name + "|" + x[0].upper())):
            if x[0].upper() not in seen:
                seen.add(x[0].upper())
                out.append(x)
        return out

    def take(layer, name, it, note_extra=""):
        for k, r, note in it:
            if k.upper() in used_keys or pset(k) in used_sets:
                continue
            used_keys.add(k.upper())
            used_sets.add(pset(k))
            pick.append({"asset_id": k, "layer": layer, "sub": name, "family_asset": r["asset_id"],
                         "rank": int(r["rank"]), "kind": r["kind"], "action": r["action"],
                         "places": int(r["places"] or 0), "why_selected": note + note_extra})
            return True
        return False

    left, deficit = {}, 0
    for layer, q, sub in layers:
        left[layer] = {name: iter(cands(name)) for name, _n in sub}
        got = Counter()
        for name, n in sub:
            while got[name] < n and take(layer, name, left[layer][name]):
                got[name] += 1
            if got[name] < n:
                short[name] = "%d из %d (кандидатов %d)" % (got[name], n, len(cands(name)))
        while sum(got.values()) < q:
            moved = False
            for name, _n in sub:
                if sum(got.values()) >= q:
                    break
                if take(layer, name, left[layer][name], " (добор слоя)"):
                    got[name] += 1
                    moved = True
            if not moved:
                short[layer] = "слой %d из %d" % (sum(got.values()), q)
                deficit += q - sum(got.values())
                break
    while deficit > 0:                               # перенос недобора слоя в другие слои по кругу
        moved = False
        for layer, _q, sub in layers:
            if deficit <= 0:
                break
            for name, _n in sub:
                if take(layer, name, left[layer][name], " (перенос недобора)"):
                    moved_in[layer] += 1
                    deficit -= 1
                    moved = True
                    break
        if not moved:
            short["total"] = "отобрано %d из %d" % (len(pick), n_total)
            break
    pick.sort(key=lambda x: order("card|" + x["asset_id"].upper()))
    return pick, short, dict(moved_in)


def do_pools(out=OUT):
    if os.path.exists(p(out, "FREEZE.json")):
        raise SystemExit("уже заморожено - пулы смотрит select")
    inp = dict(INPUTS)
    gen = ir.read_tsv(inp["generation"])
    truth = truth_v2_snapshot()
    ex_sets, ex_keys = exclusions(inp, truth)
    pool = h7.pools(inp, gen, ex_sets, ex_keys)
    print("исключено наборов %d, ключей %d (кадров разработки V2-V4 %d)" % (len(ex_sets), len(ex_keys),
                                                                          len(dev_frames(truth))))
    for layer, q, sub in LAYERS:
        print("%-11s %2d: %s" % (layer, q, ", ".join("%s %d/%d" % (s, len({x[0].upper() for x in pool.get(s, [])}),
                                                                    m) for s, m in sub)))
    items, short, moved = select(pool, fill=FILL_ORDER)
    print("отобралось бы %d: %s; недобор: %s; перенос: %s" % (len(items), dict(Counter(x["layer"] for x in items)),
                                                          short or "нет", moved or "нет"))


def do_select(out=OUT):
    if os.path.exists(p(out, "holdout.json")):
        raise SystemExit("holdout уже отобран: перевыбор запрещён")
    d = load_freeze(out)
    guard(d)
    live_same(d)
    inp = d["inputs"]
    gen = ir.read_tsv(inp["generation"])
    truth = ir.load_json(d["truth_v2"]["path"])
    ex_sets, ex_keys = exclusions(inp, truth)
    pool = h7.pools(inp, gen, ex_sets, ex_keys)
    items, short, moved = select(pool, fill=d["fill_order"])
    data = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"], "seed": SEED,
            "n": len(items), "pool": {k: len(v) for k, v in pool.items()}, "short": short, "moved_in": moved,
            "excluded_sets": sorted(ex_sets), "excluded_keys_n": len(ex_keys), "sha256": rh.digest(items),
            "items": items, "rule": "список заморожен до ответов и эталона; слой в карточку и пакет судьи не идёт; "
                                    "недобор и перенос фиксируются, руками не добираются"}
    ir.dump_json(p(out, "holdout.json"), data)
    print("отобрано %d (sha256 %s): %s" % (len(items), data["sha256"][:12], dict(Counter(x["layer"] for x in items))))
    print("недобор:", short or "нет", "перенос:", moved or "нет")
    return data


load_holdout = rh.load_holdout


def keys_of(h):
    return [x["asset_id"] for x in h["items"]]


# ---------------------------------------------------------------- relations: замок выходов всех детекторов

def ctx_v3():
    return v3.Ctx(index=v2.load_index(v2.OUT), masks=v3.load_masks(v3.OUT))


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
    det = v7.detect(ctx, d["inputs"], keys, rels)
    dpath = p(out, "relations", "detectors.json")
    ir.dump_json(dpath, det)
    c3 = ctx_v3()
    f3 = p(out, "relations", "relations_v3.json")
    ir.dump_json(f3, v3.discover(c3, keys))
    f4 = p(out, "relations", "relations_v4.json")
    ir.dump_json(f4, v4.discover(c3, keys))
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"],
                        "holdout_sha256": h["sha256"], "relations_sha256": file_sha(path),
                        "path": path.replace(os.sep, "/"), "detectors_sha256": file_sha(dpath),
                        "detectors_path": dpath.replace(os.sep, "/"),
                        "v3_path": f3.replace(os.sep, "/"), "v3_sha256": file_sha(f3),
                        "v4_path": f4.replace(os.sep, "/"), "v4_sha256": file_sha(f4)})
    print("детекторы заморожены: relations %s, detectors %s, V3 %s, V4 %s" % (
        file_sha(path)[:12], file_sha(dpath)[:12], file_sha(f3)[:12], file_sha(f4)[:12]))


def load_found(out=OUT):
    lk = ir.load_json(p(out, "relations.lock.json"))
    for k in ("v3", "v4"):
        if file_sha(lk[k + "_path"]) != lk[k + "_sha256"]:
            raise SystemExit("%s изменён после заморозки" % lk[k + "_path"])
    return ir.load_json(lk["v3_path"]), ir.load_json(lk["v4_path"])


# ---------------------------------------------------------------- карточки оси A (как V8)

def do_cards(out=OUT):
    import routing_model_v8 as v8
    d, h = load_freeze(out), load_holdout(out)
    guard(d)
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("ответы уже есть - карточки не перестраиваются")
    ic, cards = rh.build_cards(out, h["items"], d["inputs"])
    data = [{k: v for k, v in c.items()} for c in cards]
    title = "Holdout маршрута: 40 новых предметов"
    if title not in rh.PAGE_V:
        raise SystemExit("заголовок страницы V4_R1 не найден - страница сказала бы «40»")
    page = (rh.PAGE_V.replace(title, "Holdout связей V4: %d новых кадров - только ось A" % len(cards))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__MISS__", json.dumps(ic.MISSING)).replace("__SEM__", json.dumps(v8.SEMANTIC))
            .replace("__DEFS__", json.dumps({"semantic_kind": h8.SEM_DEFS}, ensure_ascii=False))
            .replace("__KEY__", "relation-holdout-v4-" + h["sha256"][:8]))
    with open(p(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    ir.dump_json(p(out, "cards.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "holdout_sha256": h["sha256"], "img_sha256": ir.img_digest(p(out, "img")),
                                        "assets": [c["asset"] for c in cards], "cards": data})
    rel = os.path.relpath(os.path.abspath(out), os.path.abspath(os.path.join("art", "objects", "generation")))
    print("карточек %d; страница: http://localhost:8778/%s/index.html" % (len(cards), rel.replace(os.sep, "/")))


# ---------------------------------------------------------------- система V4 на holdout

def routing_base(out, d, h):
    """Входы маршрута V8 один раз: ключи, подготовка детекторов, MCD, факты кадров, единица связи."""
    import map_mockup as mm
    import routing_model_v8 as v8
    _inp, keys, pr = h7.prepared(out, d, h)
    mcd = v8.Mcd(mm.World())
    return {"keys": keys, "pr": pr, "mcd": mcd, "umap": d["policy"]["relation_unit"],
            "fsets": {a.upper(): v8.facts(mcd, a) for a in keys}}


def routing_rows(base, sk_of):
    """Строки маршрута V8 (как routing_holdout_v8.build_rows, opts пустые) с обратными чтениями графа."""
    import routing_model_v8 as v8
    rows = [v8.decide(a, sk_of(a), base["pr"], base["umap"], base["fsets"][a.upper()], {}) for a in base["keys"]]
    graph = v8.build_graph(rows, base["pr"], base["mcd"])
    for r in rows:
        r["relations_in"] = graph.relations_in(r["asset_id"])
    return rows


def system_claims(rows, found3, found4):
    return v4.claims_60({"rows": rows}, found3, found4, v4.V4Claims)


# ---------------------------------------------------------------- пул пар эталона

def coplace(ctx, a, top=COPLACE_TOP, least=COPLACE_MIN):
    """Соседи на картах по всем 27 сдвигам и всем слоям: верхние по числу мест."""
    A, cnt = a.upper(), Counter()
    for _t, _blk, grid, (x, y, z), _la in ctx.places.of(a):
        seen = set()
        for o in v2.OFFSETS:
            for _lb, kb in grid.get((x + o[0], y + o[1], z + o[2]), []):
                if kb != A:
                    seen.add(kb)
        cnt.update(seen)
    return [k for k, n in sorted(cnt.items(), key=lambda kv: (-kv[1], order("co|" + A + "|" + kv[0])))
            if n >= least][:top]


def similar(ctx, a, top=SIM_TOP, least=SIM_MIN):
    A = ctx.rgba(a)
    if A is None or ctx.masks is None:
        return [], []
    m = A[..., 3] > 0
    if m.shape != ctx.masks.shape:
        return [], []
    skip = {a.upper()} | ctx.ix.exact(a) | ctx.ix.mirror(a)
    res = []
    for arr in (ctx.masks.iou(m), ctx.masks.iou(m[:, ::-1])):
        xs = [(float(arr[i]), ctx.masks.keys[i]) for i in arr.argsort()[::-1][:top + len(skip) + 8]]
        res.append([k for s, k in sorted(xs, key=lambda t: (-t[0], t[1])) if s >= least and k not in skip][:top])
    return res[0], res[1]


def neighbours(ctx, a, n=NEIGH):
    s, f = v2.split(a)
    out = []
    for g in range(f - n, f + n + 1):
        k = "%s:%d" % (s, g)
        if g >= 0 and g != f and ctx.ix.get(k) is not None:
            out.append(k.upper())
    return out


def item_pairs(a, claimed, exact_claimed, mcd_rel, byte_rel, indep):
    """Пары одного кадра по PAIR_RULE. claimed - не побайтовые утверждения (все), exact_claimed - утверждения только
    побайтовые, mcd_rel - рёбра MCD, byte_rel - побайтовые копии и отражения, indep - [(источник, [кандидаты])]."""
    A = a.upper()
    picked, why = [], {}

    def add(b, src):
        b = b.upper()
        if b == A:
            return False
        why.setdefault(b, [])
        if src not in why[b]:
            why[b].append(src)
        if b in picked:
            return False
        picked.append(b)
        return True
    for b in sorted(claimed):
        add(b, "claim")
    ex = sorted(exact_claimed, key=lambda b: order("ex|" + A + "|" + b))
    rest = sorted(set(byte_rel) - set(exact_claimed), key=lambda b: order("ex|" + A + "|" + b))
    for b in (ex + rest)[:EXACT_CAP]:
        add(b, "claim_exact" if b in exact_claimed else "byte")
    for b in sorted(mcd_rel):
        add(b, "mcd")
    must = len(picked)
    room = max(CAND_MIN_INDEP, CAND_TOTAL - must)
    lists = [(src, list(xs)) for src, xs in indep]
    got = 0
    while got < room and any(xs for _s, xs in lists):
        for src, xs in lists:                        # по кругу: по одному новому кадру из каждого источника
            while xs:
                if add(xs.pop(0), src):
                    got += 1
                    break
            if got >= room:
                break
    return [(b, why[b]) for b in picked], must


def do_pairs(out=OUT):
    if os.path.exists(p(out, "key.json")):
        raise SystemExit("пул пар уже построен: %s" % p(out, "key.json"))
    import routing_model_v8 as v8
    d, h = load_freeze(out), load_holdout(out)
    guard(d)
    live_same(d)
    detectors_same(d)
    keys = keys_of(h)
    found3, found4 = load_found(out)
    base = routing_base(out, d, h)
    claimed, exact_claimed = defaultdict(set), defaultdict(set)
    for sk in SEMANTIC_ALL:                          # утверждения при любом ответе оси A
        rows = routing_rows(base, lambda a, sk=sk: sk)
        C = system_claims(rows, found3, found4)
        for a in keys:
            for c in C.of(a):
                b = [x for x in c["pair"] if x != a.upper()][0]
                if all(e["type"] in v3.EXACT_TYPES for e in c["support"]):
                    exact_claimed[a.upper()].add(b)
                else:
                    claimed[a.upper()].add(b)
    ctx = ctx_v3()
    items, seen, per_item = [], {}, {}
    for a in keys:
        A = a.upper()
        mrel = {x["relative"].upper() for x in base["fsets"][A]}
        byte = set(ctx.ix.exact(a)) | set(ctx.ix.mirror(a))
        sd, sm = similar(ctx, a)
        indep = [("neighbour", neighbours(ctx, a)), ("coplace", coplace(ctx, a)), ("similar", sd),
                 ("similar_mirror", sm)]
        prs, must = item_pairs(a, claimed[A], exact_claimed[A] - claimed[A], mrel, byte, indep)
        per_item[A] = {"pairs": len(prs), "must": must, "claimed": len(claimed[A]),
                       "exact_claimed": len(exact_claimed[A] - claimed[A])}
        for b, why in prs:
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
    tv2 = {pk(x["a"], x["b"]) for x in truth["pairs"]}
    overlap = [it["q"] for it in items if pk(it["a"], it["b"]) in tv2]
    if overlap:
        raise SystemExit("пары пула есть в истине v2: %s" % overlap[:10])
    ir.dump_json(p(out, "key.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "holdout_sha256": h["sha256"],
                                      "rule": PAIR_RULE, "per_item": per_item, "items": items,
                                      "note": "ключ вне пакета: источник пары судье не показывается"})
    print("пар %d (обязательных %d, независимых %d); на кадр: мин %d, макс %d" % (
        len(items), sum(v["must"] for v in per_item.values()),
        sum(v["pairs"] - v["must"] for v in per_item.values()),
        min(v["pairs"] for v in per_item.values()), max(v["pairs"] for v in per_item.values())))
    print("по источникам:", dict(Counter(w for it in items for w in it["why"])))


def do_pack(out=OUT):
    import relation_truth_v2 as tv
    d = load_freeze(out)
    guard(d)
    key = ir.load_json(p(out, "key.json"))
    if os.path.exists(p(out, "pack.lock.json")):
        raise SystemExit("пакет уже собран: %s" % p(out, "pack.lock.json"))
    n = len(key["items"])
    batches = 2 * math.ceil(n / BATCH_PAIRS)
    tv.write_pack(out, [{"q": it["q"], "a": it["a"], "b": it["b"]} for it in key["items"]], batches, SEED,
                  judges_per_item=2)


# ---------------------------------------------------------------- эталон

def holdout_truth(out, lock, key):
    """q -> истина по схеме v2 из двух судей и авторитета."""
    import routing_model_v8 as v8
    import relation_truth_v2 as tv
    js, bad = tv.read_by_judge(out, lock)
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
        rows.append({"q": q, "a": it["a"], "b": it["b"], "existence": ex, "closed": sorted(closed),
                     "open": sorted(opn), "authority": au, "judge1": sorted(got[0]["taken"]),
                     "judge2": sorted(got[1]["taken"]), "raw1": got[0]["raw"], "raw2": got[1]["raw"]})
    return rows, bad, missing


def do_lockref(out=OUT):
    lock = p(out, "reference.lock.json")
    if os.path.exists(lock):
        raise SystemExit("эталон уже заморожен: %s" % lock)
    d, h = load_freeze(out), load_holdout(out)
    guard(d)
    detectors_same(d)
    key = ir.load_json(p(out, "key.json"))
    plock = ir.load_json(p(out, "pack.lock.json"))
    rows, bad, missing = holdout_truth(out, plock, key)
    if bad or missing:
        raise SystemExit("ответы судей неполны или с ошибками: %s; без двух ответов: %s" % (bad[:10], missing[:10]))
    tpath = p(out, "truth.json")
    ir.dump_json(tpath, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "schema": REF_SCHEMA, "pairs": rows,
                         "existence": dict(Counter(r["existence"] for r in rows)),
                         "closed_labels": dict(Counter(l for r in rows for l in r["closed"]))})
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "holdout_sha256": h["sha256"],
                        "key_sha256": file_sha(p(out, "key.json")), "pack_sha256": plock["pack_sha256"],
                        "truth_sha256": file_sha(tpath),
                        "answers_present_at_lock": os.path.exists(p(out, "answers_vitali.tsv"))})
    print("эталон заморожен: пар %d, %s" % (len(rows), dict(Counter(r["existence"] for r in rows))))


def load_truth(out=OUT):
    lk = ir.load_json(p(out, "reference.lock.json"))
    if file_sha(p(out, "truth.json")) != lk["truth_sha256"]:
        raise SystemExit("truth.json изменён после заморозки")
    T = {pk(r["a"], r["b"]): (r["existence"], set(r["closed"]), set(r["open"])) for r in
         ir.load_json(p(out, "truth.json"))["pairs"]}
    return T, lk


# ---------------------------------------------------------------- подсчёт

def danger(a, creative, C, tpairs, fs):
    """SAFETY: tpairs - [(b, (существование, закрытые, открытые))] пар пула с кадром a. -> (причины, открытые)."""
    if not creative:
        return [], []
    why, opn = [], []
    for b, (ex, closed, op) in tpairs:
        if ex != "RELATED":
            continue
        labs = set(closed) & set(JOINT_LABELS)
        if not labs:
            if set(op) & set(JOINT_LABELS) and not C.between(a, b):
                opn.append("%s: подтип открыт (%s)" % (b, "|".join(sorted(op))))
            continue
        has = bool(C.between(a, b))
        dlabs = labs & set(DIRECTED)
        if dlabs:
            dirn, src = v2.eff_direction({"relative": b, "direction": "open"}, fs)
            if dirn == "asset_derived" or (dirn == "symmetric" and not has):
                why.append("%s %s: %s (%s)" % ("|".join(sorted(dlabs)), b, dirn, src))
                continue
        if labs - set(DIRECTED) and not has:
            why.append("%s %s: на паре нет довода" % ("|".join(sorted(labs - set(DIRECTED))), b))
    return why, opn


def creative_of(row, C):
    import routing_model_v8 as v8
    a = row["asset_id"]
    pipe, _w = v8.pipeline_of(row["semantic_eff"], row["surface"], v4.pipe_roles(C, a))
    return pipe, pipe == "OBJECT_PIPELINE" and not v4.bound(C, a) and not v3.has_evidence(C, a)


def gate_rows(vals):
    """vals: {ворота: (значение, n)} -> [строка], вердикт."""
    out = []
    for g, need in GATES.items():
        v, n = vals[g]
        if g in ("dangerous_creative_standalone", "handoff_unassigned"):
            st = "PASS" if v == need else "FAIL"
        elif v is None or not n:
            st = "NO_DATA"
        else:
            st = "PASS" if v >= need else "FAIL"
        out.append({"gate": g, "value": v, "n": n, "need": need, "status": st})
    sts = {r["status"] for r in out}
    verdict = "FAIL" if "FAIL" in sts else ("INCONCLUSIVE" if "NO_DATA" in sts else "PASS")
    return out, verdict


def fam_of(e):
    return e["rule"] if e["detector"] == "R4" else e["detector"]


def diagnostics(pc, items, ctx_info):
    """Обязательная диагностика специалиста по парам пула pc = [(a, b, истина, доводы)]."""
    st = tv_state
    res = {}
    # EXACT_COPY
    ex_claims = [(t, c) for _a, _b, t, cs in pc for c in cs if t and c["exact"]]
    ok = sum(t[0] == "RELATED" and "EXACT_COPY" in t[1] for t, _c in ex_claims)
    judged = sum(t[0] != "OPEN" and (t[0] == "NONE" or bool(t[1])) for t, _c in ex_claims)
    pos = [(t, cs) for _a, _b, t, cs in pc if t and t[0] == "RELATED" and "EXACT_COPY" in t[1]]
    res["exact_copy"] = {"precision": v2.rate(ok, judged), "judged": judged, "triggered": len(ex_claims),
                         "recall": v2.rate(sum(any(c["exact"] for c in cs) for _t, cs in pos), len(pos)),
                         "n": len(pos)}
    # MIRRORED_RECOLOR
    mr = [(t, c) for _a, _b, t, cs in pc for c in cs if any(e["type"] == "MIRRORED_RECOLOR" for e in c["support"])]
    m = Counter()
    for t, c in mr:
        m["triggered"] += 1
        if not t or t[0] == "OPEN":
            m["existence_open"] += 1
            continue
        m["existence_" + ("ok" if t[0] == "RELATED" else "wrong")] += 1
        if t[0] != "RELATED":
            continue
        if "MIRRORED_VARIANT_PEER" in t[1]:
            m["subtype_ok"] += 1
        elif t[1]:
            m["subtype_wrong"] += 1
        else:
            m["subtype_open"] += 1
    res["mirrored_recolor"] = dict(m, existence_precision=v2.rate(m["existence_ok"], m["existence_ok"] +
                                                                  m["existence_wrong"]),
                                   subtype_precision=v2.rate(m["subtype_ok"], m["subtype_ok"] + m["subtype_wrong"]))
    # COMPOSITE
    comp = [(a, b, cs) for a, b, t, cs in pc if t and t[0] == "RELATED" and "COMPOSITE" in t[1]]
    by_item = defaultdict(list)
    for a, b, cs in comp:
        for x in (a, b):
            if x in items:
                by_item[x].append(any(c["group"] == "composite" for c in cs))
    tile = Counter()
    closed_by = []
    for a, b, cs in comp:
        side = a if a in items else b
        tt = ctx_info(side)
        found = [c for c in cs if c["group"] == "composite"]
        tile["%s %s" % (tt, "found" if found else "missed")] += 1
        closed_by.append("%s ~ %s [%s]: %s" % (a, b, tt, "; ".join(
            "%s %s" % (e["rule"], e["level"]) for c in found for e in c["support"]) or "не найдено"))
    res["composite"] = {"pairs": len(comp), "pair_recall": v2.rate(sum("не найдено" not in x for x in closed_by),
                                                                     len(comp)),
                        "items": len(by_item), "item_recall": v2.rate(sum(any(v) for v in by_item.values()),
                                                                      len(by_item)),
                        "by_tile": dict(tile), "closed_by": closed_by}
    # DERIVED / RECOLOR
    der = [(a, b, t, cs) for a, b, t, cs in pc if t and t[0] == "RELATED" and t[1] & set(tx.DERIVED_LABELS)
           and "EXACT_COPY" not in t[1]]
    fam, only, missed = Counter(), Counter(), []
    for a, b, t, cs in der:
        fs = {fam_of(e) for c in cs if c["group"] == "derived" for e in c["support"]}
        fam.update(fs)
        if len(fs) == 1:
            only.update(fs)
        if not cs:
            missed.append("%s ~ %s: %s" % (a, b, "|".join(sorted(t[1]))))
        elif not fs:
            missed.append("%s ~ %s: %s (доводы других групп: %s)" % (a, b, "|".join(sorted(t[1])),
                                                                      "|".join(sorted({c["group"] for c in cs}))))
    res["derived"] = {"n": len(der), "by_family": dict(fam), "only_family": dict(only), "missed": missed,
                      "missed_completely": sum(1 for x in missed if "доводы других групп" not in x)}
    # STATE
    sta = [cs for _a, _b, t, cs in pc if t and t[0] == "RELATED" and "STATE_VARIANT" in t[1]]
    res["state"] = {"n": len(sta),
                    "strong_recall": v2.rate(sum(any(c["group"] == "state" and c["existence"] == v4.STRONG
                                                     for c in cs) for cs in sta), len(sta)),
                    "discovery_recall": v2.rate(sum(any(c["group"] == "state" for c in cs) for cs in sta), len(sta))}
    # авто по типу действия
    au = defaultdict(Counter)
    for _a, _b, t, cs in pc:
        for c in cs:
            if tx.auto_claim(c):
                au["%s %s" % (c["group"], c["type"])][st(c, t)] += 1
    res["auto_by_type"] = {k: dict(v) for k, v in sorted(au.items())}
    # связки клеток
    p5 = Counter()
    for _a, _b, t, cs in pc:
        for c in cs:
            rules = [e for e in c["support"] if e["rule"] in ("P5r", "P5rc")]
            if not rules:
                continue
            p5["triggered"] += 1
            s = st(c, t)
            if s == "wrong":
                p5["hurt"] += 1
            elif s == "ok":
                p5["helped" if len(rules) == len(c["support"]) else "unnecessary"] += 1
            else:
                p5["open"] += 1
    res["cell_bundle"] = dict(p5)
    # R4
    r4 = defaultdict(Counter)
    for _a, _b, t, cs in pc:
        for c in cs:
            for e in c["support"]:
                if e["detector"] != "R4":
                    continue
                r = r4[e["rule"]]
                r["triggered"] += 1
                if not t or t[0] == "OPEN":
                    r["existence_open"] += 1
                elif t[0] == "NONE":
                    r["wrong_existence"] += 1
                else:
                    r["correct_existence"] += 1
                    r["subtype_open"] += 1                 # тип R4 всегда TYPE_OPEN
                    for l in t[1]:
                        r["truth_" + l] += 1
    res["r4"] = {k: dict(v) for k, v in sorted(r4.items())}
    return res


def tv_state(c, t):
    import relation_truth_v2 as tv
    return "open" if not t else tv.claim_state(c, t)


def do_report(out=OUT):
    import routing_model_v8 as v8
    d, h = load_freeze(out), load_holdout(out)
    ch = code_changed(d)
    if ch:
        raise SystemExit("код изменён после заморозки: %s - отчёт по замороженной системе невозможен" % ", ".join(ch))
    live_same(d)
    detectors_same(d)
    T, lk = load_truth(out)
    ans_p = p(out, "answers_vitali.tsv")
    if not os.path.exists(ans_p):
        raise SystemExit("нет %s" % ans_p)
    ans = {r["asset_id"]: r for r in ir.read_tsv(ans_p)}
    keys = keys_of(h)
    bad = ["%s: нет ответа" % a for a in keys if a not in ans]
    bad += ["%s: semantic_kind '%s'" % (a, ans[a].get("semantic_kind")) for a in keys
            if a in ans and ans[a].get("semantic_kind") not in v8.SEMANTIC]
    found3, found4 = load_found(out)
    base = routing_base(out, d, h)
    fsets = base["fsets"]
    rows = routing_rows(base, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    C = system_claims(rows, found3, found4)
    key = ir.load_json(p(out, "key.json"))
    pool = {pk(it["a"], it["b"]) for it in key["items"]}
    pc = [(it["a"], it["b"], T.get(pk(it["a"], it["b"])), C.pair(it["a"], it["b"])) for it in key["items"]]
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
        pipe, creative = creative_of(row, C)
        why, opn = danger(a, creative, C, tp.get(a.upper(), []), fsets[a.upper()])
        score.append({"asset_id": a, "layer": layer[a]["layer"], "sub": layer[a]["sub"],
                      "semantic_kind": row["semantic_kind"], "pipeline": pipe, "creative": creative,
                      "danger": why, "danger_open": opn,
                      "handoff_unassigned": row["pipeline_target"] not in v8.PIPELINES})
    dangerous = [x for x in score if x["danger"]]
    vals = {"dangerous_creative_standalone": (len(dangerous), len(score)),
            "relation_existence_precision": (m["existence_precision"], m["existence_judged"]),
            "derived_recolor_discovery": (r["derived"].get("discovery_rate"), r["derived"]["n"]),
            "state_discovery": (r["state"].get("discovery_rate"), r["state"]["n"]),
            "true_composite_recall": (r["composite"].get("discovery_rate"), r["composite"]["n"]),
            "automatic_action_precision": (m["auto_action_precision"], m["auto_action_judged"]),
            "handoff_unassigned": (sum(x["handoff_unassigned"] for x in score), len(score))}
    gates, verdict = gate_rows(vals)
    c3 = v3.Ctx(index=v2.load_index(v2.OUT))
    tname = {0: "floor", 1: "wall", 2: "wall", 3: "object"}

    def tinfo(k):
        i = c3.info(k)
        return tname.get(i.get("tile_type"), "none") if i.get("rec") else "none"
    diag = diagnostics(pc, {k.upper() for k in keys}, tinfo)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "RELATION_DISCOVERY_V4_HOLDOUT",
           "freeze_sha256": d["sha256"], "holdout_sha256": h["sha256"], "reference_locked": lk["created"],
           "answers_present_at_ref_lock": lk["answers_present_at_lock"], "verdict": verdict, "gates": gates,
           "metrics": m, "recall": r, "diagnostics": diag, "claims_outside_pool": outside, "invalid": bad,
           "truth": dict(Counter(t[0] for t in T.values())), "pairs": len(pc), "rows": score,
           "dangerous": {x["asset_id"]: x["danger"] for x in dangerous},
           "danger_open": {x["asset_id"]: x["danger_open"] for x in score if x["danger_open"]},
           "by_layer": {n: {"creative": sum(x["creative"] for x in score if x["layer"] == n),
                            "dangerous": sum(bool(x["danger"]) for x in score if x["layer"] == n)}
                        for n, _q, _s in LAYERS}}
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    print("вердикт %s; отчёт: %s" % (verdict, p(out, "report.md")))
    return res


def f3(x):
    return "-" if x is None else ("%.3f" % x if isinstance(x, float) else str(x))


def write_md(out, res):
    L = ["# RELATION_DISCOVERY_V4 — слепой holdout на %d кадрах" % len(res["rows"]), "",
         "Вердикт: **%s**. Снимок %s, эталон заморожен %s (ответы оси A при заморозке эталона: %s)." % (
             res["verdict"], res["freeze_sha256"][:12], res["reference_locked"],
             "были" if res["answers_present_at_ref_lock"] else "не было"), "",
         "## Ворота", "", "| ворота | значение | n | нужно | итог |", "|---|---|---|---|---|"]
    for g in res["gates"]:
        L.append("| %s | %s | %s | %s | %s |" % (g["gate"], f3(g["value"]), g["n"], g["need"], g["status"]))
    dg = res["diagnostics"]
    L += ["", "## Диагностика", "",
          "- истина пула: %s, пар %d" % (res["truth"], res["pairs"]),
          "- EXACT_COPY: precision %s (судимо %d), recall %s (n %d)" % (
              f3(dg["exact_copy"]["precision"]), dg["exact_copy"]["judged"], f3(dg["exact_copy"]["recall"]),
              dg["exact_copy"]["n"]),
          "- MIRRORED_RECOLOR: %s" % json.dumps(dg["mirrored_recolor"], ensure_ascii=False),
          "- COMPOSITE: pair recall %s (%d), item recall %s (%d), по клетке %s" % (
              f3(dg["composite"]["pair_recall"]), dg["composite"]["pairs"], f3(dg["composite"]["item_recall"]),
              dg["composite"]["items"], dg["composite"]["by_tile"])]
    L += ["  - " + x for x in dg["composite"]["closed_by"]]
    L += ["- DERIVED/RECOLOR (n %d): по семействам %s, только одним %s, не найдено ничем %d" % (
              dg["derived"]["n"], dg["derived"]["by_family"], dg["derived"]["only_family"],
              dg["derived"]["missed_completely"])]
    L += ["  - " + x for x in dg["derived"]["missed"]]
    L += ["- STATE (n %d): STRONG-only %s, STRONG+CANDIDATE %s" % (
              dg["state"]["n"], f3(dg["state"]["strong_recall"]), f3(dg["state"]["discovery_recall"])),
          "- автоматические действия по типу: %s" % json.dumps(dg["auto_by_type"], ensure_ascii=False),
          "- связки клеток P5r / P5rc: %s" % (dg["cell_bundle"] or "не сработали"),
          "- R4: %s" % json.dumps(dg["r4"], ensure_ascii=False),
          "- утверждения вне пула: %d" % len(res["claims_outside_pool"]),
          "- опасные: %s" % (res["dangerous"] or "нет"),
          "- опасные с открытым подтипом (вне ворот): %s" % (res["danger_open"] or "нет"),
          "- по слоям: %s" % res["by_layer"]]
    if res["invalid"]:
        L += ["", "Ошибки ответов: " + "; ".join(res["invalid"])]
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
        load_truth(out)
        print("эталон цел")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["pools", "freeze", "select", "relations", "cards", "pairs", "pack", "lockref",
                                    "report", "check"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    {"pools": do_pools, "freeze": freeze, "select": do_select, "relations": do_relations, "cards": do_cards,
     "pairs": do_pairs, "pack": do_pack, "lockref": do_lockref, "report": do_report, "check": do_check}[a.cmd](a.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
