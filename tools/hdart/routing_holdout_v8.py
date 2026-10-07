#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ROUTING_MODEL_V8 - заморозка и слепой holdout на 60 новых кадрах (специалист 02.10, передал Vitali в чате). CPU.

Проверка реализации V8 на тех же 60 V7 (probes/routing-model-v8-freeze-check) - диагностика, не приёмка. Здесь V8
замораживается ДО отбора новых кадров, и после заморозки ничего не меняется до окончательного отчёта: ни модель, ни
ворота, ни правила подсчёта. Замороженные V3-V7, их папки и папки V8 до заморозки только читаются.

Что заморожено (FREEZE.json): routing_model_v8.py и хэш; онтология A (v2 и граница OBJECT_PART / STRUCTURAL_SURFACE
V8) и отображение A -> B; определения B_SAFETY и E2E_SAFETY; схема рёбер C, RECOLOR_PEER, render_group_id /
render_anchor; D1 PROVISIONAL, L1 INACTIVE; досье R-171 (входящие и исходящие рёбра MCD); правила STRONG / CANDIDATE
(подготовка V7 как есть); ворота и правила подсчёта; копии и хэши всех входов. Инвариант графа: одна фактическая связь
- одно хранимое ребро, обратное чтение - не второе утверждение.

Ворота V8 (GATES): B_SAFETY = 0, E2E_SAFETY = 0, pipeline_logic_accuracy >= 0.95, pipeline_logic_coverage >= 0.70,
STRONG >= 0.95 при >= 10 независимо закрытых, semantic_axis_accuracy >= 0.85, handoff_unassigned = 0. Только
диагностика: CANDIDATE, end_to_end, пересечение связей, группы рисования, RECOLOR_PEER, D1, MCD, R-171.

Порядок (каждый шаг отказывается, если предыдущего нет или свой уже сделан):
    pools      до заморозки: только размеры пулов отбора на живых входах (содержимое не печатается)
    freeze     снимок (FREEZE.json, inputs/)
    select     60 кадров автоматически по слоям V7 (12 / 10 / 10 / 10 / 8 / 10), зерно SEED; исключены наборы
               разработки V3-V7, holdout V4_R1, V5 и V7 с роднёй, всё с решением человека; один набор PCK на holdout;
               недобор фиксируется
    relations  замороженные детекторы на 60 (relation_probe.discover, детекторы маршрута V7) - и замок
    cards      страница: только ось A (онтология V8), final_identity, missing_context, note
    dossier    пакет судьи: досье R-171 (рёбра MCD в обе стороны, двери, окрестность), картинки без панелей
               семейства и похожих; родня - все утверждения правил и похожие вперемешку, без источника и уверенности
    lockref    заморозить эталон до ответов (проверка формата V8: набор связей кадра, ребро MCD не NONE)
    report     V8 из оси A ответов и замороженных выходов детекторов; ворота, вердикт, диагностика
    check      все хэши целы

    py -3.13 tools/hdart/routing_holdout_v8.py pools|freeze|select|relations|cards|dossier|lockref|report|check
"""
import argparse
import json
import os
import shutil
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import family_relation_v2 as fr2m     # noqa: E402
import identity_routing as ir          # noqa: E402
import mcd_state as ms                 # noqa: E402
import routing_holdout as rh           # noqa: E402
import routing_holdout_v5 as h5        # noqa: E402
import routing_holdout_v7 as h7        # noqa: E402
import routing_model_v8 as v8          # noqa: E402
import routing_rules as rr             # noqa: E402
import routing_rules_v7 as v7          # noqa: E402

ROOT = ir.ROOT
ENC = ir.ENC
OUT = os.path.join(ir.PROBES, "routing-holdout-v8")
SEED = "routing-holdout-v8-2026-10-02"
N_TOTAL = 60
# отбор V7 (h7.pools, h7.select, h7.order) берёт зерно из своего модуля: подставляется зерно V8, код V7 не меняется
h7.SEED = SEED
INPUTS = dict(h7.INPUTS)
CODE = ["tools/hdart/routing_model_v8.py", "tools/hdart/routing_holdout_v8.py", "tools/test_routing_model_v8.py",
        "tools/test_routing_holdout_v8.py"] + list(h7.CODE)
LAYERS = h7.LAYERS

SEM_DEFS = dict(h7.SEM_DEFS)
for _k in ("STRUCTURAL_SURFACE", "OBJECT_PART"):
    SEM_DEFS[_k] = "%s. V8: %s (например: %s). Проверка: %s" % (
        h7.SEM_DEFS[_k], v8.ONTOLOGY_V8[_k]["def"], ", ".join(v8.ONTOLOGY_V8[_k]["examples"]), v8.ONTOLOGY_V8["test"])
PIPELINES_OK = set(v8.PIPELINES)

MODEL = {"version": "ROUTING_MODEL_V8", "doc": v8.__doc__.strip(), "semantic": v8.SEMANTIC,
         "ontology_A": {"semantic_kind": SEM_DEFS, "v8_boundary": v8.ONTOLOGY_V8},
         "pipeline_of": v8.PIPELINE_OF, "pipelines": v8.PIPELINES, "roles": v8.ROLES, "role_group": v8.ROLE_GROUP,
         "groups": v8.GROUPS, "inverse": v8.INVERSE, "symmetric": list(v8.SYMMETRIC),
         "D1": "PROVISIONAL", "L1": "INACTIVE", "RECOLOR_PEER": v8.GATE_DEFS["RECOLOR_PEER"],
         "render_group": v8.render_group.__doc__.strip(), "relations": v8.relations.__doc__.strip(),
         "prep": "подготовка V7 как есть (routing_rules_v7.prepare, V7_OPTS)"}
INVARIANTS = {"graph": "одна фактическая связь - одно хранимое ребро (Graph.key); обратное чтение relations_in - не "
                       "второе утверждение и не второй довод; утверждения считаются по неупорядоченной паре",
              "handoff": "handoff_unassigned = 0: у каждого кадра pipeline_target из PIPELINES (REVIEW - передача "
                         "человеку, тоже назначение); пусто или вне списка - ERROR_UNASSIGNED"}
DOSSIER = {"r171": "в досье рёбра MCD своей записи (исходящие: die, alt, анимация), чужих записей на этот кадр "
                   "(входящие) с флагами двери и окрестность в один шаг (routing_model_v8.dossier_lines); факт связи "
                   "отдельно от толкования",
           "hidden": ["правила маршрута и их имена", "уровень и уверенность детекторов (STRONG / CANDIDATE, sim)",
                      "группы рисования и якоря", "ответы по оси A", "слои отбора", "панели семейства и похожих "
                      "(в них оценки сходства)", "строки семейства в фактах и заметках"],
           "mcd_pairs": "если между кадром и родственником есть ребро MCD, судья не решает, есть ли связь: только её "
                        "смысл. ref_pair_relation такой пары не NONE (OPEN допустим - смысл не установлен)"}
REF_HEAD = ["asset_id", "ref_semantic_kind", "ref_roles", "truth_identity", "sources", "evidence"]
PAIR_HEAD = list(rh.PAIR_HEAD)
REF_RELATIONS = list(h7.REF_RELATIONS)
DIRECTIONS = ["asset_derived", "relative_derived", "none", "open"]
REF_ROLE_DEFS = {"canonical": "самостоятельная вещь: рисуется сама, ни одной связи из списка ниже (исключает другие)",
                 "composite": "кусок составного предмета на несколько клеток",
                 "modular": "модуль конструкции, стыкуемый с копиями себя",
                 "state": "другое состояние вещи из другого кадра (разрушенная, открытая дверь, повреждённая)",
                 "animation": "кадр петли анимации вещи из другого кадра",
                 "derived": "перекраска, вариант материала или иной вывод из другого кадра (направление может быть "
                            "неизвестно)"}
SCORING = {
    "reference": "эталон V8: ref_semantic_kind (ось A), ref_roles - НАБОР групп связи кадра через | или open, пары "
                 "reference_pairs.tsv; ref_pipeline = PIPELINE_OF[ref_semantic_kind]; связь кадра judged, если "
                 "ref_roles не open. Досье показывает все рёбра MCD - статуса uninformed нет",
    "rows": "routing_model_v8.decide: ось A ответов (end-to-end, E2E_SAFETY) и ось A эталона (logic, B_SAFETY и "
            "pipeline_logic)",
    "claims": "утверждения - routing_rules_v7.claims_of на замороженных детекторах, смысл двери - D1 как "
              "routing_model_v8.claims_v8; fact_only нет (досье показывало всё). Независимые: одна неупорядоченная "
              "пара - одно утверждение (инвариант графа): верно, если все её закрытые утверждения верны; неверно, "
              "если хоть одно неверно; уровень пары - старший",
    "gates": "verdict - все ворота (маршрут, семантика, handoff); routing_verdict - только ворота маршрута, "
             "диагностика того, где узкое место",
    "diagnostics": ["CANDIDATE precision", "end_to_end_pipeline_accuracy", "wrong_pipeline_classification",
                    "relation_by_type (набор против набора)", "RECOLOR_PEER / D1 triggered-correct-wrong-unresolved",
                    "MCD: animation (R3a), die (R3m), door-state (D1)", "R-171: где входящее ребро повлияло",
                    "render_group: групп, якорь из оригинальных данных, якорь по ключу", "граф", "сверка с V7",
                    "по слоям отбора"]}
GATES = dict(v8.GATES_V8, **v8.SEMANTIC_GATE, handoff_unassigned_max=0)
GATE_DEFS = dict(v8.GATE_DEFS, handoff_unassigned=INVARIANTS["handoff"],
                 strong_independent="STRONG считается по неупорядоченной паре: одна связь - одно утверждение")
BODY = ("model", "invariants", "dossier", "routing", "r7t", "animation_copy", "family_relation", "relation_discovery",
        "mcd", "strength", "ref_head", "pair_head", "ref_relations", "ref_role_defs", "directions", "scoring", "gates",
        "gate_defs", "seed", "n_total", "layers", "struct_rx", "inputs_source", "inputs", "input_sha256",
        "code_sha256")
file_sha = rh.file_sha
pset = rh.pset


def p(out, name):
    return os.path.join(out, name)


order = h7.order


# ---------------------------------------------------------------- freeze

def freeze(out=OUT, inputs=None, code=None):
    if os.path.exists(p(out, "FREEZE.json")):
        raise SystemExit("снимок уже заморожен: %s" % p(out, "FREEZE.json"))
    if os.path.exists(p(out, "holdout.json")):
        raise SystemExit("кадры уже отобраны - снимок после отбора не делается")
    inputs = inputs or INPUTS
    code = CODE if code is None else code
    os.makedirs(p(out, "inputs"), exist_ok=True)
    snap = {}
    for k, src in inputs.items():
        dst = p(p(out, "inputs"), os.path.basename(src))
        if os.path.exists(dst):
            raise SystemExit("в inputs/ два входа с именем %s" % os.path.basename(src))
        shutil.copyfile(src, dst)
        snap[k] = dst.replace(os.sep, "/")
    body = {"model": MODEL, "invariants": INVARIANTS, "dossier": DOSSIER, "routing": h7.ROUTING, "r7t": h7.R7T,
            "animation_copy": h7.ANIMATION_COPY, "family_relation": h7.FAMILY_RELATION,
            "relation_discovery": rh.RELATION_DISCOVERY, "mcd": h7.MCD, "strength": h7.STRENGTH,
            "ref_head": REF_HEAD, "pair_head": PAIR_HEAD, "ref_relations": REF_RELATIONS,
            "ref_role_defs": REF_ROLE_DEFS, "directions": DIRECTIONS, "scoring": SCORING, "gates": GATES,
            "gate_defs": GATE_DEFS, "seed": SEED, "n_total": N_TOTAL,
            "layers": [[n, q, [list(s) for s in sub]] for n, q, sub in LAYERS],
            "struct_rx": {k: rx.pattern for k, rx in h7.STRUCT_RX.items()},
            "inputs_source": {k: v.replace(os.sep, "/") for k, v in inputs.items()},
            "inputs": snap, "input_sha256": {k: file_sha(v) for k, v in snap.items()},
            "code_sha256": {c: file_sha(c) for c in code}}
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                decided="специалист 02.10, передал Vitali в чате: V8 freeze утверждён после проверки реализации на "
                        "тех же 60 (B_SAFETY 0, E2E_SAFETY 0, logic 1.000 / 0.950, STRONG 1.000, semantic 0.850); "
                        "новый слепой holdout на 60 новых кадрах без правок до окончательного отчёта",
                rule="после заморозки ничего из этого не меняется до конца holdout")
    ir.dump_json(p(out, "FREEZE.json"), data)
    print("V8 заморожен (sha256 %s): входов %d, файлов кода %d" % (data["sha256"][:12], len(snap), len(code)))
    return data


def load_freeze(out=OUT):
    d = ir.load_json(p(out, "FREEZE.json"))
    if ir.sha({k: d[k] for k in BODY}) != d["sha256"]:
        raise SystemExit("FREEZE.json изменён после заморозки: хэш не сходится")
    bad = [k for k, v in d["inputs"].items() if file_sha(v) != d["input_sha256"][k]]
    if bad:
        raise SystemExit("снимок входов изменён: %s" % ", ".join(bad))
    return d


code_changed = h7.code_changed
guard = h7.guard
live_same = h5.live_same


# ---------------------------------------------------------------- select

def exclusions(inp):
    """Исключения V7 (разработка V3-V7, holdout V4_R1 и V5 с роднёй) плюс holdout V7 - он же набор разработки V8:
    его кадры, наборы, родня детекторов, FR2, MCD и пары эталона."""
    ex_sets, ex_keys = h7.exclusions(inp)
    fr2 = fr2m.load(inp["family_relation_v2"])
    mcd = ms.index(ir.load_json(inp["mcd_state"])["relations"])
    out = h7.OUT
    ks = [x["asset_id"] for x in rh.load_holdout(out)["items"]]
    ex_keys |= {k.upper() for k in ks}
    ex_sets |= {pset(k) for k in ks}
    for k, rs in rh.load_relations(out).items():
        ex_sets |= {pset(r["relative"]) for r in rs}
    for k in ks:
        ex_sets |= {pset(e["relative"]) for e in fr2.get(k.upper(), [])}
        ex_sets |= {pset(x["relative"]) for x in mcd.get(k.upper(), [])}
    for r in ir.read_tsv(p(out, "reference_pairs.tsv")):
        ex_sets |= {pset(r["asset_id"]), pset(r["relative"])}
    return ex_sets, ex_keys


def do_pools(out=OUT):
    if os.path.exists(p(out, "FREEZE.json")):
        raise SystemExit("уже заморожено - пулы смотрит select")
    inp = dict(INPUTS)
    gen = ir.read_tsv(inp["generation"])
    ex_sets, ex_keys = exclusions(inp)
    pool = h7.pools(inp, gen, ex_sets, ex_keys)
    print("исключено наборов %d, ключей %d" % (len(ex_sets), len(ex_keys)))
    for layer, q, sub in LAYERS:
        print("%-11s %2d: %s" % (layer, q, ", ".join("%s %d/%d" % (s, len({x[0].upper() for x in pool[s]}), m)
                                                      for s, m in sub)))
    _items, short = h7.select(pool)
    print("недобор при отборе (с учётом одного набора на holdout):", short or "нет")


def do_select(out=OUT):
    if os.path.exists(p(out, "holdout.json")):
        raise SystemExit("holdout уже отобран: перевыбор запрещён")
    d = load_freeze(out)
    guard(d)
    live_same(d)
    inp = d["inputs"]
    gen = ir.read_tsv(inp["generation"])
    ex_sets, ex_keys = exclusions(inp)
    pool = h7.pools(inp, gen, ex_sets, ex_keys)
    items, short = h7.select(pool)
    data = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"], "seed": SEED,
            "n": len(items), "pool": {k: len(v) for k, v in pool.items()}, "short": short,
            "excluded_sets": sorted(ex_sets), "excluded_keys_n": len(ex_keys), "sha256": rh.digest(items),
            "items": items, "rule": "список заморожен до ответов и эталона; слой в карточку и пакет судьи не идёт; "
                                    "недобор фиксируется, руками не добирается"}
    ir.dump_json(p(out, "holdout.json"), data)
    print("отобрано %d (sha256 %s): %s" % (len(items), data["sha256"][:12], dict(Counter(x["layer"] for x in items))))
    print("недобор:", short or "нет")
    return data


load_holdout = rh.load_holdout
load_relations = rh.load_relations


# ---------------------------------------------------------------- relations: замок выходов детекторов

def do_relations(out=OUT):
    lock = p(out, "relations.lock.json")
    if os.path.exists(lock):
        raise SystemExit("детекторы уже посчитаны и заморожены: %s" % lock)
    d, h = load_freeze(out), load_holdout(out)
    guard(d)
    live_same(d)
    import relation_probe as rp
    keys = [x["asset_id"] for x in h["items"]]
    ctx = rp.Ctx()
    rp.discover(ctx, keys, p(out, "relations"))
    path = p(p(out, "relations"), "relations.json")
    rels = ir.load_json(path)["relations"]
    det = v7.detect(ctx, d["inputs"], keys, rels)
    dpath = p(p(out, "relations"), "detectors.json")
    ir.dump_json(dpath, det)
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"],
                        "holdout_sha256": h["sha256"], "relations_sha256": file_sha(path),
                        "path": path.replace(os.sep, "/"), "detectors_sha256": file_sha(dpath),
                        "detectors_path": dpath.replace(os.sep, "/")})
    print("детекторы заморожены: relations %s, detectors %s (MCD наборов %d, вариантов %d, подписей петель %d)" % (
        file_sha(path)[:12], file_sha(dpath)[:12], len(det["by_set"]), sum(map(len, det["variants"].values())),
        len(det["sigs"])))


def prepared(out, d, h):
    return h7.prepared(out, d, h)          # только inputs снимка и замок детекторов этой папки


# ---------------------------------------------------------------- карточки

def do_cards(out=OUT):
    d, h = load_freeze(out), load_holdout(out)
    guard(d)
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("ответы уже есть - карточки не перестраиваются")
    ic, cards = rh.build_cards(out, h["items"], d["inputs"])
    data = [{k: v for k, v in c.items()} for c in cards]
    title = "Holdout маршрута: 40 новых предметов"
    if title not in rh.PAGE_V:
        raise SystemExit("заголовок страницы V4_R1 не найден - страница сказала бы «40»")
    page = (rh.PAGE_V.replace(title, "Holdout V8: %d новых кадров - только ось A" % len(cards))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__MISS__", json.dumps(ic.MISSING)).replace("__SEM__", json.dumps(v8.SEMANTIC))
            .replace("__DEFS__", json.dumps({"semantic_kind": SEM_DEFS}, ensure_ascii=False))
            .replace("__KEY__", "routing-holdout-v8-" + h["sha256"][:8]))
    with open(p(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    ir.dump_json(p(out, "cards.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "holdout_sha256": h["sha256"], "img_sha256": ir.img_digest(p(out, "img")),
                                        "assets": [c["asset"] for c in cards], "cards": data})
    rel = os.path.relpath(os.path.abspath(out), os.path.abspath(os.path.join("art", "objects", "generation")))
    print("карточек %d; страница: http://localhost:8778/%s/index.html" % (len(cards), rel.replace(os.sep, "/")))


# ---------------------------------------------------------------- пакет судьи

HIDDEN_PANEL = ("family", "similar")


def pack_entry(c, mcd, allc):
    """Запись досье без скрытого (DOSSIER["hidden"]): панели без семейства и похожих, факты и заметки без строк
    семейства, MCD R-171 текстом, у каждого родственника - факт ребра MCD, если он есть."""
    a = c["asset"]
    panels = [[t, f] for t, f in c["panels"] if not f.split("_", 1)[1].startswith(HIDDEN_PANEL)]
    facts = "\n".join(line for line in c["facts"].split("\n") if not rh.FAMILY_LINE.match(line))
    notes = [x for x in c["notes"] if "семейств" not in x]
    fs = v8.facts(mcd, a)
    by_rel = {}
    for x in fs:
        by_rel.setdefault(x["relative"], []).append(v8.fact_line(x))
    return {"n": c["n"], "asset_id": a, "panels": panels, "facts": facts, "notes": notes,
            "mcd": v8.dossier_lines(mcd, a), "candidate_relatives": allc,
            "mcd_edge_with": {b: by_rel[b] for b in allc if b in by_rel}}


def do_dossier(out=OUT):
    d, h = load_freeze(out), load_holdout(out)
    guard(d)
    live_same(d)
    if os.path.exists(p(out, "reference.lock.json")):
        raise SystemExit("эталон уже заморожен - пакет не перестраивается")
    import map_mockup as mm
    rels = load_relations(out)
    inp, keys, pr = prepared(out, d, h)
    cj = ir.load_json(p(out, "cards.json"))
    pack = p(out, "reference_pack")
    os.makedirs(p(pack, "img"), exist_ok=True)
    fr2 = fr2m.load(inp["family_relation_v2"])
    raw, _dropped, _conv = v7.claims_of(pr, keys, rels, fr2)
    idx = ms.index(pr["by_set"])
    mcd = v8.Mcd(mm.World())
    must = {}
    for k, rel_to, *_ in raw:
        must.setdefault(k, set()).add(rel_to)
    for k in keys:
        for e in fr2.get(k.upper(), []):
            must.setdefault(k, set()).add(e["relative"])
        for c in rels.get(k, []):
            must.setdefault(k, set()).add(c["relative"])
        for x in idx.get(k.upper(), []):
            must.setdefault(k, set()).add(x["relative"])
        for v in pr["variants"].get(k, []):
            must.setdefault(k, set()).add(v["relative"])
        for x in v8.facts(mcd, k):                                   # R-171: и входящие
            must.setdefault(k, set()).add(x["relative"])
    cand, ctx = rh.candidates(out, h, inp, rels)
    entries, pairs = [], []
    for c in cj["cards"]:
        a = c["asset"]
        m = sorted({x for x in must.get(a, set()) if x.upper() != a.upper()})
        rest = [x for x in cand.get(a, []) if x not in m]
        allc = sorted(m + rest[:max(0, 12 - len(m))], key=lambda z: order("cand|" + a + "|" + z))
        e = pack_entry(c, mcd, allc)
        for _t, f in e["panels"]:
            shutil.copyfile(p(p(out, "img"), f), p(p(pack, "img"), f))
        e["panels"] = [[t, "img/" + f] for t, f in e["panels"]]
        sheets = []
        for b in allc:
            fn = "pair_%02d_%s__%s.png" % (c["n"], a.replace(":", "-"), b.replace(":", "-"))
            if rh.pair_sheet(ctx, a, b, p(p(pack, "img"), fn)):
                sheets.append([b, "img/" + fn])
            pairs.append([a, b])
        e["pair_sheets"] = sheets
        entries.append(e)
    missing = [(k, x) for k, xs in must.items() for x in xs if [k, x] not in pairs and x.upper() != k.upper()]
    if missing:
        raise SystemExit("утверждения не попали в пакет: %s" % missing[:5])
    spec = {"semantic_kind": SEM_DEFS, "ontology": "ONTOLOGY_V8", "ref_roles": REF_ROLE_DEFS,
            "ref_relations": REF_RELATIONS, "directions": DIRECTIONS, "mcd_pairs": DOSSIER["mcd_pairs"],
            "ref_relation_note": "ANIMATION_FRAME_OF - фаза анимации; STATE_VARIANT_OF - другое состояние той же вещи "
                                 "(разрушенная, открытая); RECOLOR_OF / DERIVED_FROM - перекраска / вывод, direction "
                                 "open, если основа не доказана; STRUCTURAL_RELATION - соседний кусок одной "
                                 "конструкции; недоказанное - OPEN, сходство истиной не делается"}
    ir.dump_json(p(pack, "dossier.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                           "holdout_sha256": h["sha256"], "items": entries, "spec_v8": spec})
    with open(p(out, "reference.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(REF_HEAD) + "\n" + "".join(e["asset_id"] + "\t" * (len(REF_HEAD) - 1) + "\n"
                                                     for e in entries))
    with open(p(out, "reference_pairs.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(PAIR_HEAD) + "\n" + "".join("%s\t%s\t\t\t\n" % (a, b) for a, b in pairs))
    n_mcd = sum(len(e["mcd_edge_with"]) for e in entries)
    print("пакет судьи: %d кадров, пар %d (утверждений и связей правил %d, пар с ребром MCD %d) -> %s" % (
        len(entries), len(pairs), sum(len(v) for v in must.values()), n_mcd, pack))


# ---------------------------------------------------------------- эталон

def mcd_pairs(dossier):
    """{(кадр, родственник) в верхнем регистре} - пары, где досье показало ребро MCD."""
    return {(e["asset_id"].upper(), b.upper()) for e in dossier["items"] for b in e.get("mcd_edge_with", {})}


def check_reference(ref, refp, keys, mpairs=frozenset()):
    bad = []
    for a in keys:
        r = ref.get(a)
        if not r:
            bad.append("%s: нет строки эталона" % a)
            continue
        if (r.get("ref_semantic_kind") or "open") not in v8.SEMANTIC[:-1] + ["open"]:
            bad.append("%s: ref_semantic_kind '%s'" % (a, r.get("ref_semantic_kind")))
        roles = (r.get("ref_roles") or "open").split("|")
        if roles != ["open"] and (set(roles) - set(v8.GROUPS) or ("canonical" in roles and len(roles) > 1)):
            bad.append("%s: ref_roles '%s'" % (a, r.get("ref_roles")))
    for r in refp:
        rel = r.get("ref_pair_relation") or ""
        if rel not in REF_RELATIONS:
            bad.append("%s~%s: ref_pair_relation '%s'" % (r["asset_id"], r["relative"], rel))
        if (r.get("direction") or "open") not in DIRECTIONS:
            bad.append("%s~%s: direction '%s'" % (r["asset_id"], r["relative"], r.get("direction")))
        if rel == "NONE" and (r["asset_id"].upper(), r["relative"].upper()) in mpairs:
            bad.append("%s~%s: ребро MCD есть - NONE нельзя, только смысл или OPEN" % (r["asset_id"], r["relative"]))
    return bad


def do_lockref(out=OUT):
    lock = p(out, "reference.lock.json")
    if os.path.exists(lock):
        raise SystemExit("эталон уже заморожен: %s" % lock)
    h = load_holdout(out)
    ref = {r["asset_id"]: r for r in ir.read_tsv(p(out, "reference.tsv"))}
    refp = ir.read_tsv(p(out, "reference_pairs.tsv"))
    mp = mcd_pairs(ir.load_json(p(p(out, "reference_pack"), "dossier.json")))
    bad = check_reference(ref, refp, [x["asset_id"] for x in h["items"]], mp)
    if bad:
        raise SystemExit("эталон с ошибками: " + "; ".join(bad[:20]))
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "holdout_sha256": h["sha256"],
                        "reference_sha256": file_sha(p(out, "reference.tsv")),
                        "reference_pairs_sha256": file_sha(p(out, "reference_pairs.tsv")),
                        "answers_present_at_lock": os.path.exists(p(out, "answers_vitali.tsv"))})
    print("эталон заморожен")


load_reference = rh.load_reference


# ---------------------------------------------------------------- подсчёт

def ref_axes(r):
    """(ref_pipeline, группы | None, статус): эталон V8 - набор групп связи, без uninformed (досье показало всё)."""
    sk = r.get("ref_semantic_kind") or "open"
    pipe = v8.PIPELINE_OF.get(sk, "open")
    roles = (r.get("ref_roles") or "open").strip()
    if roles in ("", "open"):
        return pipe, None, "open"
    return pipe, set(roles.split("|")), "judged"


def build_rows(pr, keys, ans, ref, refp_by, fsets, umap, layer, axis="answers", **opts):
    rows = []
    for a in keys:
        sk = ans.get(a, {}).get("semantic_kind", "")
        if axis == "ref":
            rs = ref.get(a, {}).get("ref_semantic_kind")
            sk = rs if rs not in (None, "", "open") else sk
        row = v8.decide(a, sk, pr, umap, fsets[a.upper()], opts)
        rp, rg, st = ref_axes(ref.get(a, {}))
        x = layer.get(a, {})
        row.update({"axis": axis, "layer": x.get("layer", ""), "sub": x.get("sub", ""),
                    "ref_semantic_kind": ref.get(a, {}).get("ref_semantic_kind") or "open", "ref_pipeline": rp,
                    "ref_role_groups": sorted(rg) if rg else [], "ref_role_status": st,
                    "handoff_unassigned": row["pipeline_target"] not in PIPELINES_OK})
        row["d1"] = v8.d1_outcome(row, refp_by.get(a, []))
        row["rp"] = v8.rp_outcomes(row, refp_by.get(a, []))
        rows.append(row)
    return rows


def claims_holdout(raw, fsets, refp, door=True):
    """Утверждения V7 в V8: D1 меняет смысл ребра двери; fact_only нет - досье показывало все рёбра MCD."""
    conv = []
    for k, rel_to, kind, level, side, src in raw:
        link = [x for x in fsets.get(k.upper(), []) if x["relative"].upper() == rel_to.upper()]
        if door and src == "mcd_anim" and any(x["meaning"] in ("DOOR_OPEN_STATE", "DOOR_STATE") for x in link):
            kind = "STATE_VARIANT_OF"
        conv.append((k, rel_to, kind, level, side, src))
    out = v7.score(conv, refp)
    for c in out:
        link = [x for x in fsets.get(c["asset_id"].upper(), []) if x["relative"].upper() == c["relative"].upper()]
        c["fact"] = ";".join(sorted({"%s %s %s" % (x["dir"], x["via"], x["meaning"]) for x in link}))
    return out


def independent(claims):
    """Инвариант графа в подсчёте: одна неупорядоченная пара - одно утверждение. Уровень - старший (STRONG, если
    хоть одно STRONG); статус - wrong, если хоть одно закрытое неверно, ok - если все закрытые верны, иначе open."""
    by = {}
    for c in claims:
        by.setdefault(frozenset((c["asset_id"].upper(), c["relative"].upper())), []).append(c)
    out = []
    for key, cs in sorted(by.items(), key=lambda kv: sorted(kv[0])):
        st = [c["status"] for c in cs]
        status = "wrong" if "wrong" in st else ("ok" if "ok" in st else st[0])
        out.append({"pair": sorted(key), "level": "STRONG" if any(c["level"] == "STRONG" for c in cs) else "CANDIDATE",
                    "status": status, "claims": len(cs), "kinds": sorted({c["kind"] for c in cs}),
                    "sources": sorted({c["source"] for c in cs}), "fact_only": 0, "excluded": 0})
    return out


def precision_split(claims):
    u = independent(claims)
    return {"all": v8.precision(u), "strong": v8.precision([c for c in u if c["level"] == "STRONG"]),
            "candidate": v8.precision([c for c in u if c["level"] != "STRONG"]), "raw_claims": len(claims),
            "independent_pairs": len(u)}


MCD_EXPECT = {"R3a": "ANIMATION_FRAME_OF", "R3m": "STATE_VARIANT_OF", "D1": "STATE_VARIANT_OF"}
MCD_NAME = {"R3a": "animation", "R3m": "die", "D1": "door_state"}


def mcd_outcomes(rows, refp_by):
    """Рёбра MCD (R3a анимация, R3m разрушение, D1 состояние двери) против пары эталона: correct - смысл пары тот,
    что даёт правило; wrong - другой закрытый смысл; unresolved - OPEN или пары нет."""
    res = {n: Counter() for n in MCD_NAME.values()}
    for r in rows:
        for e in r["edges"]:
            if e["rule"] not in MCD_EXPECT or not e["target"]:
                continue
            n = MCD_NAME[e["rule"]]
            pr_ = [x for x in refp_by.get(r["asset_id"], []) if x["relative"].upper() == e["target"].upper()]
            rel = pr_[0]["ref_pair_relation"] if pr_ else "OPEN"
            res[n]["triggered"] += 1
            res[n]["correct" if rel == MCD_EXPECT[e["rule"]] else ("unresolved" if rel in ("", "OPEN") else "wrong")] += 1
    return {n: {k: c[k] for k in ("triggered", "correct", "wrong", "unresolved")} for n, c in res.items()}


def r171(rows, fsets, refp_by):
    """Где входящее ребро MCD повлияло: кадры, у которых есть входящее ребро, которого досье V7 (только своя запись)
    не показало бы; из них - сколько пар по такому ребру эталон закрыл смыслом, и сколько кадров с судимой связью."""
    out = {"frames_with_incoming": 0, "incoming_only_frames": 0, "incoming_only_pairs_closed": 0,
           "incoming_only_pairs_open": 0, "incoming_only_frames_judged": 0, "assets": []}
    for r in rows:
        fs = fsets[r["asset_id"].upper()]
        inc = [x for x in fs if x["dir"] == "IN"]
        if not inc:
            continue
        out["frames_with_incoming"] += 1
        only = sorted({x["relative"] for x in inc if not v8.shown_in_v7(fs, x["relative"])})
        if not only:
            continue
        out["incoming_only_frames"] += 1
        out["incoming_only_frames_judged"] += r["ref_role_status"] == "judged"
        rels = []
        for b in only:
            pr_ = [x for x in refp_by.get(r["asset_id"], []) if x["relative"].upper() == b.upper()]
            rel = pr_[0]["ref_pair_relation"] if pr_ else "OPEN"
            out["incoming_only_pairs_closed" if rel not in ("", "OPEN") else "incoming_only_pairs_open"] += 1
            rels.append("%s %s" % (b, rel or "OPEN"))
        out["assets"].append("%s: %s; эталон кадра %s" % (r["asset_id"], ", ".join(rels),
                                                         "|".join(r["ref_role_groups"]) or r["ref_role_status"]))
    return out


def render_stats(rows, origin):
    """Группы рисования: сколько, якорь из оригинальных данных игры, якорь по ключу (в группе нет кадра оригинала)."""
    groups = {}
    for r in rows:
        if r.get("render_group_id"):
            groups[r["render_group_id"]] = r["render_anchor"]
    from_origin = sum(a.split(":")[0].upper() in origin for a in groups.values())
    return {"groups": len(groups), "anchor_from_origin": from_origin, "anchor_by_key": len(groups) - from_origin}


def gate_checks(m, lm, ps, rows, g):
    c = v8.gate_checks(m, lm, ps, g)
    c["semantic_axis_accuracy >= %.2f" % g["semantic_axis_accuracy_min"]] = v8.semantic_check(m, g)
    c["handoff_unassigned = %d" % g["handoff_unassigned_max"]] = sum(r["handoff_unassigned"] for r in rows) <= \
        g["handoff_unassigned_max"]
    return c


def routing_verdict(checks):
    return v8.verdict({k: v for k, v in checks.items() if not k.startswith(("semantic_axis", "handoff"))})


def do_report(out=OUT):
    d, h = load_freeze(out), load_holdout(out)
    ch = code_changed(d)
    if ch:
        raise SystemExit("код изменён после заморозки: %s - отчёт по замороженной модели невозможен" % ", ".join(ch))
    live_same(d)
    import map_mockup as mm
    rels = load_relations(out)
    ref, refp, lk = load_reference(out)
    ans_p = p(out, "answers_vitali.tsv")
    if not os.path.exists(ans_p):
        raise SystemExit("нет %s" % ans_p)
    ans = {r["asset_id"]: r for r in ir.read_tsv(ans_p)}
    inp, keys, pr = prepared(out, d, h)
    layer = {x["asset_id"]: x for x in h["items"]}
    mp = mcd_pairs(ir.load_json(p(p(out, "reference_pack"), "dossier.json")))
    bad = ["%s: нет ответа" % a for a in keys if a not in ans]
    bad += ["%s: semantic_kind '%s'" % (a, ans[a].get("semantic_kind")) for a in keys
            if a in ans and ans[a].get("semantic_kind") not in v8.SEMANTIC]
    bad += check_reference(ref, refp, keys, mp)
    umap = d["routing"]["relation_unit"]
    mcd = v8.Mcd(mm.World())
    fsets = {a.upper(): v8.facts(mcd, a) for a in keys}
    refp_by = {}
    for x in refp:
        refp_by.setdefault(x["asset_id"], []).append(x)
    g = d["gates"]
    rows = build_rows(pr, keys, ans, ref, refp_by, fsets, umap, layer)
    lrows = build_rows(pr, keys, ans, ref, refp_by, fsets, umap, layer, axis="ref")
    for r in rows:
        r["final_identity"] = ans.get(r["asset_id"], {}).get("final_identity", "")
        r["truth_identity"] = ref.get(r["asset_id"], {}).get("truth_identity", "")
    m, lm = v8.metrics(rows), v8.metrics(lrows)
    fr2 = fr2m.load(inp["family_relation_v2"])
    raw, dropped, conv = v7.claims_of(pr, keys, rels, fr2)
    claims = claims_holdout(raw, fsets, refp)
    ps = precision_split(claims)
    checks = gate_checks(m, lm, ps, rows, g)
    graph = v8.build_graph(rows, pr, mcd)
    for r in rows:
        r["relations_out"], r["relations_in"] = graph.relations_out(r["asset_id"]), graph.relations_in(r["asset_id"])
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "ROUTING_MODEL_V8_HOLDOUT",
           "freeze_sha256": d["sha256"], "holdout_sha256": h["sha256"], "reference_locked": lk["created"],
           "answers_present_at_ref_lock": lk["answers_present_at_lock"],
           "verdict": v8.verdict(checks), "routing_verdict": routing_verdict(checks), "checks": checks, "gates": g,
           "metrics_end_to_end": m, "metrics_logic": lm, "relations": ps,
           "by_source": {s: v8.precision(independent([c for c in claims if c["source"] == s]))
                         for s in sorted({c["source"] for c in claims})},
           "mcd": {"end_to_end": mcd_outcomes(rows, refp_by), "logic": mcd_outcomes(lrows, refp_by)},
           "r171": r171(rows, fsets, refp_by), "render": render_stats(rows, pr["origin"]),
           "graph": {"stored_edges": len(graph.edges),
                     "row_edges": sum(e["relation_type"] != "CANONICAL" and bool(e["target"])
                                      for r in rows for e in r["edges"]),
                     "inverse_views": sum(len(r["relations_in"]) for r in rows),
                     "inverse_by_type": dict(Counter(x["relation_type"] for r in rows for x in r["relations_in"]))},
           "consistency_with_v7": {a: b for a in keys for b in [v8.consistency(a, pr, umap, fsets[a.upper()])] if b},
           "layers": {n: v8.metrics([r for r in rows if r["layer"] == n]) for n, _q, _s in LAYERS},
           "layers_logic": {n: v8.metrics([r for r in lrows if r["layer"] == n]) for n, _q, _s in LAYERS},
           "rules_fired": dict(Counter(x for r in rows for x in r["rules"])), "anim_copy_claims": conv,
           "dropped": dropped, "invalid": bad, "claims": claims, "rows": rows, "rows_logic": lrows}
    ir.dump_json(p(out, "report.json"), res)
    v8.write_edges(p(out, "relation_edges.tsv"), rows)
    write_md(out, res)
    return res


def write_md(out, res):
    yes = {True: "да", False: "**нет**", None: "мало данных"}
    m, lm, ps = res["metrics_end_to_end"], res["metrics_logic"], res["relations"]

    def pr_(x):
        return "%s (%d/%d)" % (x["relation_precision"], x["ok"], x["closed"])
    vals = ["%d %s" % (lm["dangerous_creative_standalone"], " ".join(lm["dangerous_assets"])),
            "%d %s" % (m["dangerous_creative_standalone"], " ".join(m["dangerous_assets"])),
            "%s (%d/%d)" % (lm["pipeline_accuracy"], lm["pipeline_ok"], lm["pipeline_decided"]),
            "%s (%d/%d)" % (lm["pipeline_coverage"], lm["pipeline_decided"], lm["pipeline_closed"]),
            "%s, независимых пар" % pr_(ps["strong"]),
            "%s (n %d)" % (m["semantic_axis_accuracy"], m["semantic_n"]),
            str(sum(r["handoff_unassigned"] for r in res["rows"]))]
    L = ["# ROUTING_MODEL_V8 - слепой holdout: %s" % res["verdict"], "",
         "снимок %s, holdout %s; ось A - ответы, эталон - независимый (заморожен %s%s)." % (
             res["freeze_sha256"][:12], res["holdout_sha256"][:12], res["reference_locked"],
             ", ответы уже были" if res["answers_present_at_ref_lock"] else ", до ответов"), "",
         "## Ворота", "", "| ворота | значение | пройдено |", "|---|---|---|"]
    for (k, v), val in zip(res["checks"].items(), vals):
        L.append("| %s | %s | %s |" % (k, val, yes[v]))
    L += ["", "Вердикт: **%s**. Только ворота маршрута: %s." % (res["verdict"], res["routing_verdict"]), "",
          "## Диагностика (не ворота)", "", "| мера | значение |", "|---|---|",
          "| CANDIDATE (независимые пары) | %s |" % pr_(ps["candidate"]),
          "| утверждений / независимых пар | %d / %d |" % (ps["raw_claims"], ps["independent_pairs"]),
          "| end_to_end_pipeline_accuracy | %s (%d/%d), охват %s |" % (
              m["pipeline_accuracy"], m["pipeline_ok"], m["pipeline_decided"], m["pipeline_coverage"]),
          "| wrong_pipeline_classification, ось A ответов / эталона | %d / %d |" % (
              m["wrong_pipeline_classification"], lm["wrong_pipeline_classification"]),
          "| RECOLOR_PEER: triggered / correct / wrong / unresolved | %d / %d / %d / %d |" % (
              m["RECOLOR_PEER_triggered"], m["RECOLOR_PEER_correct"], m["RECOLOR_PEER_wrong"],
              m["RECOLOR_PEER_unresolved"]),
          "| D1: triggered / correct / wrong / unresolved | %d / %d / %d / %d |" % (
              m["D1_triggered"], m["D1_correct"], m["D1_wrong"], m["D1_unresolved"])]
    for n, v in res["mcd"]["end_to_end"].items():
        L.append("| MCD %s: triggered / correct / wrong / unresolved | %d / %d / %d / %d |" % (
            n, v["triggered"], v["correct"], v["wrong"], v["unresolved"]))
    r1, rg, gr = res["r171"], res["render"], res["graph"]
    L += ["| R-171: кадров со входящим ребром / только входящее / из них связь судима | %d / %d / %d |" % (
              r1["frames_with_incoming"], r1["incoming_only_frames"], r1["incoming_only_frames_judged"]),
          "| R-171: пар по входящему ребру закрыто смыслом / OPEN | %d / %d |" % (
              r1["incoming_only_pairs_closed"], r1["incoming_only_pairs_open"]),
          "| группы рисования / якорь из оригинальных данных / по ключу | %d / %d / %d |" % (
              rg["groups"], rg["anchor_from_origin"], rg["anchor_by_key"]),
          "| граф: хранимых рёбер / рёбер в строках / обратных чтений | %d / %d / %d |" % (
              gr["stored_edges"], gr["row_edges"], gr["inverse_views"]),
          "| связь (группы): пересечение / точно / охват | %s / %s / %s |" % (
              m["role_overlap"], m["role_exact"], m["role_coverage"]),
          "| сверка с маршрутом V7 | %s |" % ("сходится на всех" if not res["consistency_with_v7"] else
                                             "расходится: %d" % len(res["consistency_with_v7"])),
          "| конвейеры (ответы) | %s |" % ", ".join("%s %d" % kv for kv in sorted(m["pipelines"].items())),
          "| рёбра по видам | %s |" % ", ".join("%s %d" % kv for kv in sorted(m["roles"].items())),
          "| правила | %s |" % ", ".join("%s %d" % kv for kv in sorted(res["rules_fired"].items())), "",
          "## Связь по видам (набор против набора)", "", "| группа | точность | V8 дал | полнота | в эталоне |",
          "|---|---|---|---|---|"]
    for gname, v in m["relation_by_type"].items():
        L.append("| %s | %s | %d | %s | %d |" % (gname, v["precision"], v["predicted"], v["recall"], v["reference"]))
    L += ["", "## По слоям отбора", "", "| слой | n | B опасных | E2E опасных | logic точн. | logic охват |",
          "|---|---|---|---|---|---|"]
    for n, x in res["layers"].items():
        lx = res["layers_logic"][n]
        L.append("| %s | %d | %d | %d | %s | %s |" % (n, x["n"], lx["dangerous_creative_standalone"],
                                                     x["dangerous_creative_standalone"], lx["pipeline_accuracy"],
                                                     lx["pipeline_coverage"]))
    for title, rows in (("ось A эталона", res["rows_logic"]), ("ось A ответов", res["rows"])):
        wrong = [r for r in rows if v8.wrong_pipeline(r) or v8.dangerous_creative_standalone(r)]
        L += ["", "## Неверный конвейер или опасный, %s (%d)" % (title, len(wrong)), ""]
        L += ["- %s (%s/%s): V8 %s (A %s), эталон %s (%s), связи %s%s" % (
            r["asset_id"], r["layer"], r["sub"], r["pipeline_target"], r["semantic_eff"], r["ref_pipeline"],
            "|".join(r["ref_role_groups"]) or r["ref_role_status"], "+".join(r["relation_roles"]) or "нет (улики)",
            " - **опасный творческий**" if v8.dangerous_creative_standalone(r) else "") for r in wrong]
    if r1["assets"]:
        L += ["", "## R-171: только входящее ребро", ""] + ["- " + x for x in r1["assets"]]
    bad = [c for c in independent(res["claims"]) if c["level"] == "STRONG" and c["status"] == "wrong"]
    L += ["", "## STRONG неверные (%d)" % len(bad), ""]
    L += ["- %s: %s, %s" % (" ~ ".join(c["pair"]), "+".join(c["kinds"]), "+".join(c["sources"])) for c in bad]
    L += ["", "## По кадрам", "", "| кадр | слой | A ответ / эталон | конвейер | эталон | связи V8 | эталон связи |",
          "|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        L.append("| %s | %s/%s | %s / %s | %s | %s | %s | %s |" % (
            r["asset_id"], r["layer"], r["sub"], r["semantic_kind"], r["ref_semantic_kind"], r["pipeline_target"],
            r["ref_pipeline"], "+".join(r["relation_roles"]) or "улики", "|".join(r["ref_role_groups"]) or
            r["ref_role_status"]))
    if res["invalid"]:
        L += ["", "Ошибки в ответах или эталоне: " + "; ".join(res["invalid"])]
    with open(p(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:22]))


def do_check(out=OUT):
    d = load_freeze(out)
    print("снимок цел: %s, заморожен %s; входов %d" % (d["sha256"][:12], d["created"], len(d["inputs"])))
    ch = code_changed(d)
    print("код: %s" % ("тот же" if not ch else "ИЗМЕНЁН: " + ", ".join(ch)))
    if os.path.exists(p(out, "holdout.json")):
        h = load_holdout(out)
        print("holdout цел: %d, %s" % (h["n"], h["sha256"][:12]))
    if os.path.exists(p(out, "relations.lock.json")):
        load_relations(out)
        h7.load_detectors(out)
        print("родство и детекторы целы")
    if os.path.exists(p(out, "reference.lock.json")):
        load_reference(out)
        print("эталон цел")
    print("ответов: %s" % ("ЕСТЬ" if os.path.exists(p(out, "answers_vitali.tsv")) else "нет"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["pools", "freeze", "select", "relations", "cards", "dossier", "lockref", "report",
                                    "check"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.chdir(ROOT)
    {"pools": do_pools, "freeze": freeze, "select": do_select, "relations": do_relations, "cards": do_cards,
     "dossier": do_dossier, "lockref": do_lockref, "report": do_report, "check": do_check}[a.cmd](a.out)


if __name__ == "__main__":
    main()
