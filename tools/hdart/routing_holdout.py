#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ROUTING_RULES_V4_R1 - слепой holdout на 40 новых предметах (специалист 01.10, шаг 5 RELATION_DISCOVERY_V1). CPU.

Диагностика V4_R1 на тех же 28 (опасных 0, точность 16/16) - основание для слепой проверки, не приёмка: пороги
детектора родства и правила R7r / R8a выбраны после того, как опасные были известны. Здесь всё замораживается ДО
отбора новых предметов, и после ответов ничего не меняется. families.json не правится: проверяется «существующие
семейства + кандидаты RELATION_DISCOVERY_V1 -> V4_R1».

Порядок (каждый шаг отказывается, если предыдущего нет или свой уже сделан):
    freeze     снимок: пороги и правила детектора родства, правила V4_R1 и их порядок, ворота с определениями,
               копии входных метаданных в inputs/ и их sha256, sha256 кода (FREEZE.json)
    select     40 предметов по слоям (holdout.json): 10 родство, 8 кусок, 6 составной / модуль, 6 рельеф / стена /
               пол, 10 обычных одиночных. Отбор только по замороженным метаданным, зерном; детектор родства в отбор
               слоёв не входит (иначе его точность мерилась бы на его же находках), кроме подслоя «перекраска вне
               семейства» из скана V1. Исключены наборы диагностики (28 предметов V3 и их родня, пары V1, контроли),
               всё, что уже было на карточках, и всё с решением человека. Один предмет на набор PCK
    relations  замороженный детектор (relation_probe.discover) на 40 - relations/relations.json и замок
    cards      страница для Vitali: только ось A (SEMANTIC_KIND) и final_identity, маршрут он не выбирает
    dossier    пакет для эталона: картинки карточек без панели семейства, факты без меток родства, кандидаты в
               родню из всех источников вперемешку и без подписи источника, листы пар; шаблоны reference*.tsv
    lockref    заморозить эталон (reference.tsv, reference_pairs.tsv); собирается не по ответам Vitali
    report     маршрут V4_R1 из оси A + метаданных + родства, сверка с эталоном, ворота
    check      все хэши целы

Эталон по осям отдельно: ref_semantic_kind, ref_route (значения spec V3 или open) и ref_relation (RECOLOR_OF /
STATE_VARIANT_OF / DERIVED_FROM / STRUCTURAL_RELATION / NONE / OPEN). Недоказанное родство - OPEN: сильное сходство
истиной не делается. Пары: reference_pairs.tsv - asset_id, relative, ref_pair_relation, direction
(asset_derived / relative_derived / none / open), evidence.

    py -3.13 tools/hdart/routing_holdout.py freeze|select|relations|cards|dossier|lockref|report|check
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402
import routing_rules as rr             # noqa: E402

ROOT = ir.ROOT
ENC = ir.ENC
OUT = os.path.join(ir.PROBES, "routing-holdout-v4r1")
SEED = "routing-holdout-v4r1-2026-10-01"
RD = os.path.join(ir.PROBES, "relation-discovery-v1")
DISC = os.path.join("art", "objects", "discovery")
INPUTS = {
    "generation": os.path.join("art", "objects", "generation", "generation.tsv"),
    "families": os.path.join("art", "objects", "families", "families.json"),
    "state_variants": os.path.join(DISC, "state_variants.json"),
    "modular_objects": os.path.join(DISC, "modular_objects.json"),
    "class_decisions": os.path.join(DISC, "class_decisions.tsv"),
    "identity_decisions": os.path.join(DISC, "identity_decisions.tsv"),
    "items": os.path.join(DISC, "items.json"),
    "touch": os.path.join(DISC, "touch.tsv"),
    "proposals": os.path.join(DISC, "proposals.json"),
    "asset_identity": os.path.join(DISC, "asset_identity.tsv"),
    "set_terrains": os.path.join(".index", "mod", "Piratez", "set_terrains.tsv"),
    "negatives": os.path.join(RD, "negatives.tsv"),
    "lookalikes": os.path.join(RD, "lookalikes.tsv"),
    "missed_recolor": os.path.join(RD, "missed_recolor.tsv"),
    "relations_v1": os.path.join(RD, "relations.json"),
}
CODE = ["tools/hdart/relation_probe.py", "tools/hdart/routing_rules.py", "tools/hdart/identity_routing.py",
        "tools/hdart/obj_families.py", "tools/hdart/routing_holdout.py"]

LAYERS = (("relation", 10, (("detector_recolor", 3), ("family_derived", 2), ("family_open", 2), ("mcd_state", 3))),
          ("part", 8, (("part_suspect", 5), ("part_words", 3))),
          ("composite", 6, (("composite", 3), ("modular_words", 3))),
          ("terrain", 6, (("object_or_relief", 2), ("relief", 2), ("wall", 1), ("floor", 1))),
          ("standalone", 10, (("standalone", 10),)))
PART_RX = re.compile(r"\b(fuselage|hull|wing|tail|nose|cockpit|section|segment|panel|half|corner|piece|part|"
                     r"fragment|portion|chunk|rotor|turret|engine|hood|bumper|chassis|end of|edge of|side of|"
                     r"top of|front of|rear of|base of)\b", re.I)
MODULAR_RX = re.compile(r"\b(pipe|pipes|pipeline|column|pillar|post|fence|railing|rail|shelf|shelving|rack|"
                        r"scaffold|scaffolding|girder|beam|pole|ladder|conduit|duct|tube)\b", re.I)

# ---------------------------------------------------------------- что замораживается

RELATION_DISCOVERY = {
    "version": "RELATION_DISCOVERY_V1",
    "rules": {
        "exact_recolor": "RECOLOR_OF: силуэт IoU >= GEO, цвет B - функция цвета A на >= FUNC пикселей общего "
                         "силуэта и обратно (один к одному)",
        "set_level_recolor": "набор-двойник: тот же номер кадра в другом наборе, и в наборе >= SET_SHARE сравнимых "
                             "кадров - точная перекраска кадр в кадр (силуэт >= GEO, B выводится из A >= FUNC, "
                             "одна сторона: много-к-одному тоже перекраска)",
        "recolor_level": "RECOLOR_OF STRONG - есть набор-двойник и MCD тот же (воксели и физика); иначе CANDIDATE",
        "local_edit_on_recolor": "RECOLOR_WITH_LOCAL_EDIT (= DERIVED_FROM, subtype recolor_with_local_edit): "
                                 "набор-двойник есть, силуэт >= GEO, а сам кадр от точной перекраски отступил - "
                                 "CANDIDATE. Пара без набора-двойника - не довод (NONE)",
        "persistent_neighbour": "FIXED_NEIGHBOUR CANDIDATE: в слое предметов (3), в соседней клетке того же этажа "
                                "стоит один и тот же кадр в >= NEIGH_SHARE мест кадра, мест >= NEIGH_MIN",
        "side": "сторона перекраски по числу мест на картах (touch.tsv): чаще стоящий - основа (base), реже - "
                "производный (derived); RECOLOR_OF, из родственника не выводящийся, - base",
        "verified": "verified всегда false: VERIFIED ставит только человек; «сходство высокое -> родство» не делается",
    },
    "thresholds": {"GEO": 0.98, "FUNC": 0.98, "SET_SHARE": 0.80, "NEIGH_SHARE": 0.80, "NEIGH_MIN": 3},
    "unused_constants": {"STATE_LO": 0.60, "SET_FUNC": 0.95},
    "negative_controls": {"file": "negatives.tsv (10 пар: 9 выбраны агентом по lookalikes, 1 HUMAN_REJECTED)",
                          "required": {"RECOLOR_OF": 0, "RECOLOR_WITH_LOCAL_EDIT": 0},
                          "measured_v1": "RECOLOR_OF 0/10, RECOLOR_WITH_LOCAL_EDIT 0/10 при порогах выше"},
}
ROUTING = {
    "version": "V4_R1",
    "precedence": ["R1", "R2", "R0v", "R3", "R4", "R5", "R6", "R7", "R7r", "R8a", "R8", "R9"],
    "relation_unit": rr.RELATION_UNIT_HOLDOUT,
    "open_blockers": list(rr.OPEN_BLOCKERS),
    "object_part_fallback": "R8a: A = OBJECT_PART и ни одно правило выше не сработало -> REVIEW",
    "open_relation": "R7r: кандидат родства без подтверждения человеком (производная сторона RECOLOR_OF / "
                     "RECOLOR_WITH_LOCAL_EDIT, любой FIXED_NEIGHBOUR) -> REVIEW",
}
GATES = {"dangerous_false_standalone_max": 0, "routing_accuracy_min": 0.90, "routing_coverage_min": 0.70,
         "overconservative_rate_max": 0.15, "relation_precision_min": 0.95, "relation_precision_min_n": 5}
DEFINITIONS = {
    "dangerous_false_standalone": "маршрут V4_R1 STANDALONE_RENDER при ref_route %s; все 40" % "/".join(ir.DANGEROUS_REF),
    "routing_accuracy": "верно / решено: предметы с закрытым ref_route (не open), где V4_R1 дал конкретный маршрут "
                        "(не REVIEW)",
    "routing_coverage": "решено V4_R1 (не REVIEW) / предметов с закрытым ref_route",
    "overconservative_rate": "из предметов с ref_route STANDALONE_RENDER - доля, ушедших в любой другой маршрут или "
                             "REVIEW; число от всех 40 печатается рядом, не ворота",
    "relation_precision": "verified_relation_precision: утверждения детектора родства на 40 (каждая пара предмет - "
                          "родственник, любой вид и уровень, обе стороны), которые эталон пар закрыл (не OPEN и не "
                          "пропущено): верно - эталон назвал родство той же группы (производное: RECOLOR_OF / "
                          "DERIVED_FROM / STATE_VARIANT_OF; строение: STRUCTURAL_RELATION), неверно - NONE или другая "
                          "группа. Меньше relation_precision_min_n закрытых - ворота не решены. Точное совпадение "
                          "вида и направления - отдельной строкой",
    "relation_recall": "только метрика: из пар, где эталон закрыл родство, доля, найденных детектором",
    "semantic_accuracy": "только метрика: ось A Vitali против ref_semantic_kind (UNSURE и open вне знаменателя)",
    "layers": "все метрики и по слоям отбора; слои - диагностика, не ворота",
}
REF_ROUTES = ir.ROUTING[:-1]
REF_RELATIONS = ["RECOLOR_OF", "STATE_VARIANT_OF", "DERIVED_FROM", "STRUCTURAL_RELATION", "NONE", "OPEN"]
GROUP = {"RECOLOR_OF": "derived", "DERIVED_FROM": "derived", "STATE_VARIANT_OF": "derived",
         "STRUCTURAL_RELATION": "structure"}
CLAIM_GROUP = {"RECOLOR_OF": "derived", "RECOLOR_WITH_LOCAL_EDIT": "derived", "FIXED_NEIGHBOUR": "structure"}
CLAIM_EXACT = {"RECOLOR_OF": ("RECOLOR_OF",), "RECOLOR_WITH_LOCAL_EDIT": ("DERIVED_FROM",),
               "FIXED_NEIGHBOUR": ("STRUCTURAL_RELATION",)}
ANS_HEAD = ["asset_id", "final_identity", "semantic_kind", "missing_context", "note"]
REF_HEAD = ["asset_id", "ref_semantic_kind", "ref_route", "ref_relation", "ref_relation_to", "truth_identity",
            "sources", "evidence"]
PAIR_HEAD = ["asset_id", "relative", "ref_pair_relation", "direction", "evidence"]


def file_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def order(key):
    return hashlib.sha256((SEED + "|" + key).encode()).hexdigest()


def pset(key):
    return key.split(":")[0].upper()


def p(out, name):
    return os.path.join(out, name)


# ---------------------------------------------------------------- freeze

def freeze(out=OUT, inputs=None, code=None):
    if os.path.exists(p(out, "FREEZE.json")):
        raise SystemExit("снимок уже заморожен: %s" % p(out, "FREEZE.json"))
    if os.path.exists(p(out, "holdout.json")):
        raise SystemExit("предметы уже отобраны - снимок после отбора не делается")
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
    rules = dict(rr.RULES_R1)
    rules["R0v"] = ("родство подтверждено человеком (verified) -> по родству: RECOLOR_OF -> DERIVED, "
                    "RECOLOR_WITH_LOCAL_EDIT -> DERIVED (DERIVED_FROM, subtype recolor_with_local_edit; "
                    "STATE_VARIANT - только если человек докажет смену состояния)")
    routing = dict(ROUTING, rules=rules)
    body = {"relation_discovery": RELATION_DISCOVERY, "routing": routing, "gates": GATES, "definitions": DEFINITIONS,
            "seed": SEED, "layers": [[n, q, [list(s) for s in sub]] for n, q, sub in LAYERS],
            "inputs_source": {k: v.replace(os.sep, "/") for k, v in inputs.items()},
            "inputs": snap, "input_sha256": {k: file_sha(v) for k, v in snap.items()},
            "code_sha256": {c: file_sha(c) for c in code}}
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                decided="специалист 01.10 (шаг 5 RELATION_DISCOVERY_V1), передал Vitali в чате: заморозить "
                        "RELATION_DISCOVERY_V1 + ROUTING_RULES_V4_R1 до отбора, families.json не менять",
                rule="после появления ответов holdout ничего из этого не меняется")
    ir.dump_json(p(out, "FREEZE.json"), data)
    print("снимок заморожен (sha256 %s): входов %d, файлов кода %d" % (data["sha256"][:12], len(snap), len(code)))
    return data


def load_freeze(out=OUT):
    d = ir.load_json(p(out, "FREEZE.json"))
    body = {k: d[k] for k in ("relation_discovery", "routing", "gates", "definitions", "seed", "layers",
                              "inputs_source", "inputs", "input_sha256", "code_sha256")}
    if ir.sha(body) != d["sha256"]:
        raise SystemExit("FREEZE.json изменён после заморозки: хэш не сходится")
    bad = [k for k, v in d["inputs"].items() if file_sha(v) != d["input_sha256"][k]]
    if bad:
        raise SystemExit("снимок входов изменён: %s" % ", ".join(bad))
    return d


def code_changed(d):
    return [c for c, h in d["code_sha256"].items() if not os.path.exists(c) or file_sha(c) != h]


# ---------------------------------------------------------------- select

def seen_assets():
    """Всё, что уже было на карточках у человека (любые probes/*/cards.json)."""
    import glob
    out = set()
    for q in glob.glob(os.path.join(ir.PROBES, "*", "cards.json")):
        out.update(a.upper() for a in ir.load_json(q).get("assets", []))
    return out


def exclusions(inp):
    """(наборы, ключи), не идущие в holdout: всё, на чём настраивали V4_R1, и всё, что человек уже видел."""
    sets, keys = set(), set()
    seen = seen_assets()
    keys |= seen
    sets |= {pset(a) for a in seen}
    rel = ir.load_json(inp["relations_v1"])["relations"]
    for k, rs in rel.items():
        sets.add(pset(k))
        sets |= {pset(r["relative"]) for r in rs}
    import relation_probe as rp
    for grp in ("recolor", "state", "positive_controls"):
        for a, b in rp.V1[grp]:
            sets |= {pset(a), pset(b)}
    sets |= {pset(a) for a in rp.V1["part"]}
    for sa, sb in rp.V1["set_pairs"]:
        sets |= {sa.upper(), sb.upper()}
    for name in ("negatives", "lookalikes"):
        for r in ir.read_tsv(inp[name]):
            sets |= {pset(r["a"]), pset(r["b"])}
            keys |= {r["a"].upper(), r["b"].upper()}
    for x in ir.load_json(inp["state_variants"]):           # разобранные случаи - вместе с наборами
        for k in (x["asset_id"], x.get("variant_of") or ""):
            if k:
                keys.add(k.upper())
                sets.add(pset(k))
    for o in ir.load_json(inp["modular_objects"]):
        for q in o.get("parts", []) + o.get("composites", []):
            ks = [q["asset_id"]] + list(q.get("copies", [])) + [x["frame"] for x in q.get("assembly", [])]
            keys |= {k.upper() for k in ks}
            sets |= {pset(k) for k in ks}
    for name in ("class_decisions", "identity_decisions"):
        keys |= {r["asset_id"].upper() for r in ir.read_tsv(inp[name])}
    return sets, keys


def texts(inp):
    """Описание-гипотеза каждого ассета (предложения моделей и прежнее описание) - для подслоёв по словам."""
    out = {}
    for a, x in ir.load_json(inp["proposals"]).items():
        bits = [x.get(k) or "" for k in ("proposed_name", "short_description", "picture_alone")]
        bits += list(x.get("alternatives") or [])
        for k in ("first", "second"):
            y = x.get(k) or {}
            if isinstance(y, dict):
                bits += [y.get("proposed_name") or "", y.get("short_description") or ""]
        out[a.upper()] = " ".join(b for b in bits if isinstance(b, str))
    for r in ir.read_tsv(inp["asset_identity"]):
        out[r["asset_id"].upper()] = (out.get(r["asset_id"].upper(), "") + " " + (r.get("proposed") or "") + " " +
                                      (r.get("identity") or "")).strip()
    return out


def class_why(inp):
    out = {}
    for fam in ir.load_json(inp["families"]):
        for part in ("members", "review"):
            for m in fam.get(part, []):
                for k in m.get("keys", []):
                    out.setdefault(k.upper(), m.get("class_why", ""))
    return out


def verdicts(inp):
    return {a.upper(): x.get("verdict", "") for a, x in ir.load_json(inp["proposals"]).items()}


class StateIndex:
    """Кадр - цель «разрушенного вида» или «второго состояния» другой записи MCD своего набора (данные игры)."""

    def __init__(self):
        self.world = None
        self.cache = {}

    def links(self, s):
        if s not in self.cache:
            if self.world is None:
                import map_mockup as mm
                self.world = mm.World()
            recs = self.world.records(s) or []
            res = {}
            for n, r in enumerate(recs):
                for what in ("die", "alt"):
                    idx = r.get(what)
                    if idx and idx < len(recs) and recs[idx]["frame"] != r["frame"]:
                        res.setdefault(recs[idx]["frame"], []).append((what, r["frame"]))
            self.cache[s] = res
        return self.cache[s]

    def of(self, key):
        s, f = key.split(":")
        try:
            return self.links(s.upper()).get(int(f), [])
        except (Exception, SystemExit):            # noqa: BLE001 - набор не читается: не кандидат
            return []


def pools(inp, gen, ex_sets, ex_keys, state_index=None):
    """Кандидаты подслоёв: {подслой: [(ключ, строка, заметка)]}; каждый ключ - в первом по порядку подслое."""
    txt, why, verd = texts(inp), class_why(inp), verdicts(inp)
    missed = ir.read_tsv(inp["missed_recolor"])
    fam_size = Counter()
    for fam in ir.load_json(inp["families"]):
        fam_size[fam["family_id"].upper()] = len(fam.get("members", [])) + len(fam.get("review", []))
    by_key = {}
    for r in gen:
        by_key.setdefault(r["key"].upper(), r)

    def ok(k):
        r = by_key.get(k.upper())
        return (r is not None and r["status"] != "SKIP" and pset(k) not in ex_sets and k.upper() not in ex_keys
                and r["asset_id"].upper() not in ex_keys)

    def t(r):
        return txt.get(r["asset_id"].upper(), "")

    out = {s: [] for _n, _q, sub in LAYERS for s, _m in sub}
    for r in missed:                                      # перекраска вне семейства (скан V1): сторона - зерном
        a, b = r["a"], r["b"]
        k = a if int(order("side|%s|%s" % (a, b))[:2], 16) % 2 == 0 else b
        if ok(k):
            out["detector_recolor"].append((k, by_key[k.upper()], "пара %s ~ %s" % (a, b)))
    rows = [r for r in gen if ok(r["key"])]
    for r in rows:
        k, bl = r["key"], r["blockers"].split()
        if r["relation"] in ("recolor", "mirror") and r["key"] != r["asset_id"] and r["action"] == "DERIVE":
            out["family_derived"].append((k, r, "%s от %s" % (r["relation"], r["asset_id"])))
        if r["action"] in ("GENERATE", "GENERATE_WITH") and (
                r["relation"] == "alternate_view" or any(b.split(":")[0] in ("family_review", "in_review")
                                                         for b in bl)):
            out["family_open"].append((k, r, "relation %s, %s" % (r["relation"] or "-", " ".join(bl))))
        if r["action"] == "GENERATE" and r["kind"] == "один" and "part_fragment_suspect" in bl:
            out["part_suspect"].append((k, r, r.get("fragment_why", "")))
        if r["action"] == "GENERATE" and r["kind"] == "один" and PART_RX.search(t(r)) and not MODULAR_RX.search(t(r)):
            out["part_words"].append((k, r, PART_RX.search(t(r)).group(0)))
        if r["action"] == "GENERATE" and r["kind"] == "составной":
            out["composite"].append((k, r, "составной заказ"))
        if r["action"] == "GENERATE" and r["kind"] == "один" and MODULAR_RX.search(t(r)) and not PART_RX.search(t(r)):
            out["modular_words"].append((k, r, MODULAR_RX.search(t(r)).group(0)))
        cw = why.get(k.upper(), "")
        if r["asset_class"] == "object_or_relief" or "class_check" in bl:
            out["object_or_relief"].append((k, r, cw or "class_check"))
        if r["asset_class"] == "structural" and cw.startswith("рельеф"):
            out["relief"].append((k, r, cw))
        if r["asset_class"] == "structural" and cw.startswith("стена"):
            out["wall"].append((k, r, cw))
        if r["asset_class"] == "floor_like":
            out["floor"].append((k, r, cw or "floor_like"))
        if (r["action"] == "GENERATE" and r["kind"] == "один" and r["relation"] in ("canonical", "")
                and set(b.split(":")[0] for b in bl) <= {"identity"} and r["asset_class"] == "object"
                and fam_size.get(r["asset_id"].upper(), 1) <= 1 and r["identity_status"] == "AGENT_PROPOSED"
                and verd.get(r["asset_id"].upper()) == "agree" and not PART_RX.search(t(r))
                and not MODULAR_RX.search(t(r))):
            out["standalone"].append((k, r, "обычный одиночный"))
    out["mcd_state"] = []
    if state_index is not None:                           # лениво, по порядку зерна: читать все наборы долго
        for r in sorted((r for r in rows if r["kind"] == "один" and r["action"] in ("GENERATE", "DERIVE")),
                        key=lambda r: order("mcd|" + r["key"].upper())):
            ln = state_index.of(r["key"])
            if ln:
                out["mcd_state"].append((r["key"], r, "; ".join("%s записи с кадром %d" % w for w in ln[:3])))
            if len(out["mcd_state"]) >= 60:
                break
    return out


def select(pool):
    """Слои по порядку, подслои по порядку, внутри - зерно; ключ один раз; набор PCK один раз на весь holdout."""
    pick, short, used_sets, used_keys = [], {}, set(), set()
    for layer, _q, sub in LAYERS:
        for name, n in sub:
            cand = sorted(pool.get(name, []), key=lambda x: order(name + "|" + x[0].upper()))
            got = 0
            for k, r, note in cand:
                if got >= n:
                    break
                if k.upper() in used_keys or pset(k) in used_sets:
                    continue
                used_keys.add(k.upper())
                used_sets.add(pset(k))
                got += 1
                pick.append({"asset_id": k, "layer": layer, "sub": name, "family_asset": r["asset_id"],
                             "rank": int(r["rank"]), "kind": r["kind"], "action": r["action"],
                             "places": int(r["places"] or 0), "why_selected": note})
            if got < n:
                short[name] = "%d из %d (кандидатов %d)" % (got, n, len(cand))
    pick.sort(key=lambda x: order("card|" + x["asset_id"].upper()))
    return pick, short


def digest(items):
    return hashlib.sha256("\n".join(x["asset_id"] for x in items).encode()).hexdigest()


def do_select(out=OUT):
    if os.path.exists(p(out, "holdout.json")):
        raise SystemExit("holdout уже отобран: перевыбор запрещён")
    d = load_freeze(out)
    if code_changed(d):
        raise SystemExit("код изменён после заморозки: %s" % ", ".join(code_changed(d)))
    inp = d["inputs"]
    gen = ir.read_tsv(inp["generation"])
    ex_sets, ex_keys = exclusions(inp)
    pool = pools(inp, gen, ex_sets, ex_keys, StateIndex())
    items, short = select(pool)
    data = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"], "seed": SEED,
            "n": len(items), "pool": {k: len(v) for k, v in pool.items()}, "short": short,
            "excluded_sets": sorted(ex_sets), "excluded_keys_n": len(ex_keys), "sha256": digest(items),
            "items": items, "rule": "список заморожен до ответов и эталона; слой в карточку не идёт"}
    ir.dump_json(p(out, "holdout.json"), data)
    print("отобрано %d (sha256 %s): %s" % (len(items), data["sha256"][:12], dict(Counter(x["layer"] for x in items))))
    print("недобор:", short or "нет")
    print("пулы:", data["pool"])
    return data


def load_holdout(out=OUT):
    h = ir.load_json(p(out, "holdout.json"))
    if digest(h["items"]) != h["sha256"]:
        raise SystemExit("holdout.json изменён после заморозки")
    return h


# ---------------------------------------------------------------- relations

def do_relations(out=OUT):
    lock = p(out, "relations.lock.json")
    if os.path.exists(lock):
        raise SystemExit("родство уже посчитано и заморожено: %s" % lock)
    d, h = load_freeze(out), load_holdout(out)
    if code_changed(d):
        raise SystemExit("код изменён после заморозки: %s" % ", ".join(code_changed(d)))
    # discover читает живые items.json и touch.tsv - они обязаны совпадать со снимком
    for k in ("items", "touch"):
        if file_sha(d["inputs_source"][k]) != d["input_sha256"][k]:
            raise SystemExit("живой %s отличается от снимка - детектор посчитал бы не на тех данных" % k)
    import relation_probe as rp
    keys = [x["asset_id"] for x in h["items"]]
    rp.discover(rp.Ctx(), keys, p(out, "relations"))
    path = p(p(out, "relations"), "relations.json")
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"],
                        "holdout_sha256": h["sha256"], "relations_sha256": file_sha(path),
                        "path": path.replace(os.sep, "/")})
    print("родство заморожено: %s" % file_sha(path)[:12])


def load_relations(out=OUT):
    lk = ir.load_json(p(out, "relations.lock.json"))
    if file_sha(lk["path"]) != lk["relations_sha256"]:
        raise SystemExit("relations.json изменён после заморозки")
    return ir.load_json(lk["path"])["relations"]


# ---------------------------------------------------------------- карточки

def cards_builder(inp):
    import identity_card as ic
    C = ic.Cards()
    gen = {r["key"].upper(): r for r in ir.read_tsv(inp["generation"])}
    return ic, C, gen


def build_cards(out, items, inp):
    """Картинки карточек holdout в out/img; кадр не из asset_identity - строка подставляется из generation.tsv."""
    ic, C, gen = cards_builder(inp)
    os.makedirs(p(out, "img"), exist_ok=True)
    cards = []
    for n, x in enumerate(items, 1):
        a = x["asset_id"]
        if a not in C.rows:
            g = gen[a.upper()]
            C.rows[a] = {"asset_id": a, "rank": g["rank"], "asset_class": g["asset_class"], "status": "",
                         "identity": "", "proposed": ""}
        t0 = time.time()
        c = C.card(a, out, n)
        cards.append(c)
        print("%-26s панелей %d, %.0f с" % (a, len(c["panels"]), time.time() - t0), flush=True)
    return ic, cards


PAGE = ir.PAGE.replace("IDENTITY_ROUTING_V3 - диагностика: те же 28 предметов, ответ по двум осям",
                       "ROUTING_RULES_V4_R1 holdout: 40 новых предметов, ответ - только смысл и название")


def do_cards(out=OUT):
    d, h = load_freeze(out), load_holdout(out)
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("ответы уже есть - карточки не перестраиваются")
    ic, cards = build_cards(out, h["items"], d["inputs"])
    data = [{k: v for k, v in c.items()} for c in cards]
    spec = {"semantic_kind": ir.SPEC["semantic_kind"]}
    page = (PAGE_V.replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__MISS__", json.dumps(ic.MISSING)).replace("__SEM__", json.dumps(ir.SEMANTIC))
            .replace("__DEFS__", json.dumps(spec, ensure_ascii=False))
            .replace("__KEY__", "routing-holdout-v4r1-" + h["sha256"][:8]))
    with open(p(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    ir.dump_json(p(out, "cards.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "holdout_sha256": h["sha256"], "img_sha256": ir.img_digest(p(out, "img")),
                                        "assets": [c["asset"] for c in cards],
                                        "cards": [{k: v for k, v in c.items()} for c in cards]})
    rel = os.path.relpath(os.path.abspath(out), os.path.abspath(os.path.join("art", "objects", "generation")))
    print("карточек %d; страница: http://localhost:8778/%s/index.html" % (len(cards), rel.replace(os.sep, "/")))


PAGE_V = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Смысл предметов</title>
<style>
:root{--bg:#1b1b1f;--card:#26262c;--fg:#e8e8ea;--mut:#9a9aa3;--acc:#f2c14e;--on:#3a6fa8;--hyp:#5a4a2a}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px;max-width:1200px}
h1{font-size:18px;margin:0 0 4px}h2{font-size:16px;margin:0 0 8px}.mut{color:var(--mut)}
.card{background:var(--card);border-radius:8px;padding:14px;margin:16px 0}
.p{margin:10px 0}.p .t{color:var(--acc);font-weight:600;font-size:13px;margin-bottom:4px}
.p img{max-width:100%;border-radius:4px;image-rendering:pixelated}
pre{white-space:pre-wrap;background:#1f1f24;padding:8px;border-radius:4px;font-size:12px;margin:4px 0}
.hyp{background:#1f1f24;border-left:4px solid var(--hyp);border-radius:4px;padding:6px 8px;margin:4px 0}
.hyp .k{font-size:11px;letter-spacing:.06em;color:#c9a35a;font-weight:700}
button{background:#33333b;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px 10px;cursor:pointer}
button.on{background:var(--on)}button.m.on{background:#7a5ab8}
.btns{display:flex;gap:4px;flex-wrap:wrap;margin:6px 0}
.q{color:var(--acc);font-weight:600;margin-top:8px}
dl{margin:4px 0 0}dt{font-weight:600;margin-top:4px}dd{margin:0 0 0 12px;color:var(--mut)}
input[type=text]{width:100%;box-sizing:border-box;background:#1f1f24;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:5px;margin:4px 0}
textarea{width:100%;height:140px;background:#1f1f24;color:var(--fg);box-sizing:border-box}
details{background:#222228;border-radius:6px;padding:8px 10px;margin:8px 0}
</style></head><body>
<h1>Holdout маршрута: 40 новых предметов - только смысл и название</h1>
<div class="mut">Два ответа на каждый предмет: <b>A</b> - что это вообще (смысл) и final_identity по-английски
(что это или чего это кусок). Как его рисовать, здесь не спрашивается - маршрут считают правила. Описание прежнее,
ответы моделей и статус в базе - непроверенные гипотезы. Не ясно - UNSURE и какого контекста не хватило, не угадывать.
TSV внизу - прислать целиком.</div>
<details><summary>определения A</summary><div id="defs"></div></details>
<div id="cards"></div>
<h2>TSV</h2><textarea id="tsv" readonly></textarea>
<script>
const DATA = __DATA__, MISS = __MISS__, SEM = __SEM__, DEFS = __DEFS__, KEY = "__KEY__";
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} tsv(); }
const clean = s => (s || "").replace(/[\\t\\n]/g, " ");
const esc = t => String(t).replace(/[&<>"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));
function tsv(){
  const L = [["asset_id", "final_identity", "semantic_kind", "missing_context", "note"].join("\\t")];
  for (const c of DATA) { const s = st[c.asset] || {};
    L.push([c.asset, clean(s.i), s.a || "", Object.keys(s.m || {}).filter(k => s.m[k]).join(","), clean(s.n)].join("\\t")); }
  document.getElementById("tsv").value = L.join("\\n");
}
let dh = `<dl>`; for (const [k, v] of Object.entries(DEFS.semantic_kind)) dh += `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`;
document.getElementById("defs").innerHTML = dh + "</dl>";
const root = document.getElementById("cards");
for (const c of DATA) {
  const s = st[c.asset] = st[c.asset] || {}; s.m = s.m || {};
  const el = document.createElement("div"); el.className = "card";
  let h = `<h2>${c.n}. ${esc(c.asset)}</h2>`;
  for (const [t, f] of c.panels) h += `<div class="p"><div class="t">${esc(t)}</div><img src="img/${f}"></div>`;
  h += `<div class="p"><div class="t">7. гипотезы - НЕ проверены, могут быть неверны</div>`;
  h += `<div class="hyp"><div class="k">UNVERIFIED OLD DESCRIPTION</div>${esc(c.prompt || "-")}</div>`;
  const ab = ["A", "B"];
  c.answers.forEach((a, i) => { h += `<div class="hyp"><div class="k">MODEL HYPOTHESIS ${ab[i] || i + 1}</div>${esc(a)}</div>`; });
  h += `<div class="t" style="margin-top:8px">факты из данных игры</div><pre>${esc(c.facts)}</pre>`;
  if (c.notes.length) h += `<div class="mut">${c.notes.map(esc).join("<br>")}</div>`;
  h += `</div>`;
  el.innerHTML = h;
  el.insertAdjacentHTML("beforeend", `<div class="q">A. что это (SEMANTIC_KIND)</div>`);
  const cb = document.createElement("div"); cb.className = "btns";
  for (const v of SEM) { const b = document.createElement("button"); b.textContent = v; b.dataset.v = v;
    if (s.a === v) b.classList.add("on");
    b.onclick = () => { s.a = s.a === v ? "" : v; cb.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s.a)); save(); };
    cb.appendChild(b); }
  el.appendChild(cb);
  const i = document.createElement("input"); i.type = "text"; i.placeholder = "final_identity, in English: what it is, or what it is a part of";
  i.value = s.i || ""; i.oninput = () => { s.i = i.value; save(); };
  el.insertAdjacentHTML("beforeend", `<div class="q">что это (final_identity)</div>`); el.appendChild(i);
  el.insertAdjacentHTML("beforeend", `<div class="mut">UNSURE - какого контекста не хватило:</div>`);
  const mb = document.createElement("div"); mb.className = "btns";
  for (const v of MISS) { const b = document.createElement("button"); b.textContent = v; b.className = "m";
    if (s.m[v]) b.classList.add("on"); b.onclick = () => { s.m[v] = !s.m[v]; b.classList.toggle("on", s.m[v]); save(); };
    mb.appendChild(b); }
  el.appendChild(mb);
  const n = document.createElement("input"); n.type = "text"; n.placeholder = "заметка (по-русски можно)";
  n.value = s.n || ""; n.oninput = () => { s.n = n.value; save(); }; el.appendChild(n);
  root.appendChild(el);
}
tsv();
</script></body></html>"""


# ---------------------------------------------------------------- пакет эталона

FAMILY_LINE = re.compile(r"^- (same object in other tilesets/colours|possible other sides of it):")


def candidates(out, h, inp, rels):
    """Кандидаты в родню каждого предмета из всех источников; источник в пакет не идёт."""
    import relation_probe as rp
    fams = ir.load_json(inp["families"])
    co = {}
    for fam in fams:
        ks = [k for part in ("members", "review") for m in fam.get(part, []) for k in m.get("keys", [])]
        for k in ks:
            co.setdefault(k.upper(), set()).update(x for x in ks if x.upper() != k.upper())
    si = StateIndex()
    ctx = rp.Ctx()
    items = ir.load_json(inp["items"])
    shapes = []
    for it in items:
        if it["kind"] == "составной":
            continue
        a = ctx.rgba(it["src"][0])
        if a is not None:
            m, _c = rp.codes(a)
            if m.any():
                shapes.append((it["src"][0], m))
    res = {}
    for x in h["items"]:
        k = x["asset_id"]
        c = set(r["relative"] for r in rels.get(k, []))
        c |= co.get(k.upper(), set())
        s = pset(k)
        for what, fr in si.of(k):
            c.add("%s:%d" % (s, fr))
        recs = si.links(s)
        f = int(k.split(":")[1])
        for tgt, ln in recs.items():                       # и обратно: этот кадр - основа чужого состояния
            if any(fr == f for _w, fr in ln):
                c.add("%s:%d" % (s, tgt))
        A = ctx.rgba(k)
        if A is not None:
            ma, _ = rp.codes(A)
            sims = []
            for k2, m2 in shapes:
                if k2.upper() == k.upper():
                    continue
                u = (ma | m2).sum()
                if u:
                    sims.append(((ma & m2).sum() / u, k2))
            sims.sort(reverse=True)
            c |= {k2 for iou, k2 in sims[:4] if iou >= 0.90}
        c.discard(k)
        res[k] = sorted(c, key=lambda z: order("cand|" + k + "|" + z))[:10]
    return res, ctx


def pair_sheet(ctx, a, b, path):
    """A | B | маски силуэтов (A - красный, B - зелёный, общее - жёлтый), x4 на тёмном. Без вывода цвета."""
    from PIL import Image
    import numpy as np
    A, B = ctx.rgba(a), ctx.rgba(b)
    if A is None or B is None:
        return False
    k, bg = 4, (24, 24, 28)

    def big(x):
        im = Image.new("RGB", (x.shape[1], x.shape[0]), bg)
        im.paste(Image.fromarray(x, "RGBA"), (0, 0), Image.fromarray(x, "RGBA"))
        return im.resize((im.width * k, im.height * k), Image.NEAREST)

    h, w = max(A.shape[0], B.shape[0]), max(A.shape[1], B.shape[1])
    m = np.zeros((h, w, 3), np.uint8)
    m[:A.shape[0], :A.shape[1], 0] = (A[..., 3] > 0) * 220
    m[:B.shape[0], :B.shape[1], 1] = (B[..., 3] > 0) * 220
    ims = [big(A), big(B), Image.fromarray(m, "RGB").resize((w * k, h * k), Image.NEAREST)]
    out = Image.new("RGB", (sum(i.width for i in ims) + 12, max(i.height for i in ims)), (14, 14, 16))
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + 6
    out.save(path)
    return True


def do_dossier(out=OUT):
    d, h = load_freeze(out), load_holdout(out)
    rels = load_relations(out)
    cj = ir.load_json(p(out, "cards.json"))
    pack = p(out, "reference_pack")
    os.makedirs(p(pack, "img"), exist_ok=True)
    cand, ctx = candidates(out, h, d["inputs"], rels)
    entries, pairs = [], []
    for c in cj["cards"]:
        a = c["asset"]
        panels = []
        for t, f in c["panels"]:
            if f.split("_", 1)[1].startswith("family"):
                continue
            shutil.copyfile(p(p(out, "img"), f), p(p(pack, "img"), f))
            panels.append([t, "img/" + f])
        facts = "\n".join(line for line in c["facts"].split("\n") if not FAMILY_LINE.match(line))
        sheets = []
        for b in cand.get(a, []):
            fn = "pair_%02d_%s__%s.png" % (c["n"], a.replace(":", "-"), b.replace(":", "-"))
            if pair_sheet(ctx, a, b, p(p(pack, "img"), fn)):
                sheets.append([b, "img/" + fn])
            pairs.append([a, b])
        entries.append({"n": c["n"], "asset_id": a, "panels": panels, "facts": facts, "notes": c["notes"],
                        "candidate_relatives": cand.get(a, []), "pair_sheets": sheets})
    ir.dump_json(p(pack, "dossier.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                           "holdout_sha256": h["sha256"], "items": entries,
                                           "spec_v3": ir.SPEC, "ref_relations": REF_RELATIONS})
    with open(p(out, "reference.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(REF_HEAD) + "\n" + "".join(e["asset_id"] + "\t" * (len(REF_HEAD) - 1) + "\n"
                                                     for e in entries))
    with open(p(out, "reference_pairs.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(PAIR_HEAD) + "\n" + "".join("%s\t%s\t\t\t\n" % (a, b) for a, b in pairs))
    print("пакет эталона: %d предметов, пар %d -> %s" % (len(entries), len(pairs), pack))


# ---------------------------------------------------------------- эталон и отчёт

def check_reference(ref, refp, keys):
    bad = []
    for a in keys:
        r = ref.get(a)
        if not r:
            bad.append("%s: нет строки эталона" % a)
            continue
        if (r.get("ref_semantic_kind") or "open") not in ir.SEMANTIC[:-1] + ["open"]:
            bad.append("%s: ref_semantic_kind '%s'" % (a, r.get("ref_semantic_kind")))
        if (r.get("ref_route") or "open") not in REF_ROUTES + ["open"]:
            bad.append("%s: ref_route '%s'" % (a, r.get("ref_route")))
        if (r.get("ref_relation") or "OPEN") not in REF_RELATIONS:
            bad.append("%s: ref_relation '%s'" % (a, r.get("ref_relation")))
    for r in refp:
        if (r.get("ref_pair_relation") or "OPEN") not in REF_RELATIONS:
            bad.append("%s~%s: ref_pair_relation '%s'" % (r["asset_id"], r["relative"], r.get("ref_pair_relation")))
        if (r.get("direction") or "open") not in ("asset_derived", "relative_derived", "none", "open"):
            bad.append("%s~%s: direction '%s'" % (r["asset_id"], r["relative"], r.get("direction")))
    return bad


def do_lockref(out=OUT):
    lock = p(out, "reference.lock.json")
    if os.path.exists(lock):
        raise SystemExit("эталон уже заморожен: %s" % lock)
    h = load_holdout(out)
    ref = {r["asset_id"]: r for r in ir.read_tsv(p(out, "reference.tsv"))}
    refp = ir.read_tsv(p(out, "reference_pairs.tsv"))
    bad = check_reference(ref, refp, [x["asset_id"] for x in h["items"]])
    if bad:
        raise SystemExit("эталон с ошибками: " + "; ".join(bad))
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "holdout_sha256": h["sha256"],
                        "reference_sha256": file_sha(p(out, "reference.tsv")),
                        "reference_pairs_sha256": file_sha(p(out, "reference_pairs.tsv")),
                        "answers_present_at_lock": os.path.exists(p(out, "answers_vitali.tsv"))})
    print("эталон заморожен")


def load_reference(out=OUT):
    lk = ir.load_json(p(out, "reference.lock.json"))
    if (file_sha(p(out, "reference.tsv")) != lk["reference_sha256"] or
            file_sha(p(out, "reference_pairs.tsv")) != lk["reference_pairs_sha256"]):
        raise SystemExit("эталон изменён после заморозки")
    return ({r["asset_id"]: r for r in ir.read_tsv(p(out, "reference.tsv"))},
            ir.read_tsv(p(out, "reference_pairs.tsv")), lk)


def rate(k, n):
    return round(k / n, 3) if n else None


def routing_metrics(rows):
    """rows: rule_unit, ref_route ('open' - не закрыт)."""
    closed = [r for r in rows if r["ref_route"] != "open"]
    decided = [r for r in closed if r["rule_unit"] != "REVIEW"]
    ok = sum(r["rule_unit"] == r["ref_route"] for r in decided)
    alone = [r for r in rows if r["ref_route"] == "STANDALONE_RENDER"]
    over = sum(r["rule_unit"] != "STANDALONE_RENDER" for r in alone)
    return {"n": len(rows), "ref_closed": len(closed), "decided": len(decided), "correct": ok,
            "routing_accuracy": rate(ok, len(decided)), "routing_coverage": rate(len(decided), len(closed)),
            "dangerous_false_standalone": sum(r["rule_unit"] == "STANDALONE_RENDER" and
                                              r["ref_route"] in ir.DANGEROUS_REF for r in rows),
            "ref_standalone": len(alone), "overconservative": over, "overconservative_rate": rate(over, len(alone)),
            "overconservative_of_all": rate(over, len(rows)),
            "review": sum(r["rule_unit"] == "REVIEW" for r in rows)}


def relation_metrics(rels, refp, keys):
    """Утверждения детектора против эталона пар. Пары, где родство закрыто эталоном, - для полноты."""
    ref = {(r["asset_id"].upper(), r["relative"].upper()): r for r in refp}
    claims = []
    for k in keys:
        for c in rels.get(k, []):
            r = ref.get((k.upper(), c["relative"].upper()))
            rel = (r or {}).get("ref_pair_relation") or "OPEN"
            st = "open" if rel == "OPEN" else ("ok" if GROUP.get(rel) == CLAIM_GROUP[c["kind"]] else "wrong")
            exact = rel in CLAIM_EXACT[c["kind"]]
            dr = (r or {}).get("direction") or "open"
            dir_ok = None
            if st == "ok" and c["side"] in ("derived", "base") and dr in ("asset_derived", "relative_derived"):
                dir_ok = (c["side"] == "derived") == (dr == "asset_derived")
            claims.append({"asset_id": k, "relative": c["relative"], "kind": c["kind"], "level": c["level"],
                           "side": c["side"], "ref": rel, "direction": dr, "status": st, "exact": exact,
                           "direction_ok": dir_ok, "judged": r is not None})
    closed = [c for c in claims if c["status"] != "open"]
    ok = [c for c in closed if c["status"] == "ok"]
    claimed = {(c["asset_id"].upper(), c["relative"].upper(), CLAIM_GROUP[c["kind"]]) for c in claims}
    pos = [r for r in refp if r["asset_id"] in keys and GROUP.get(r.get("ref_pair_relation") or "")]
    found = [r for r in pos if (r["asset_id"].upper(), r["relative"].upper(), GROUP[r["ref_pair_relation"]])
             in claimed]
    by = {}
    for grp in sorted({(c["kind"], c["level"]) for c in claims}):
        cs = [c for c in closed if (c["kind"], c["level"]) == grp]
        by["%s %s" % grp] = {"claims": sum((c["kind"], c["level"]) == grp for c in claims), "closed": len(cs),
                             "ok": sum(c["status"] == "ok" for c in cs)}
    return {"claims": len(claims), "closed": len(closed), "ok": len(ok), "open": len(claims) - len(closed),
            "unjudged": sum(not c["judged"] for c in claims),
            "relation_precision": rate(len(ok), len(closed)),
            "exact_kind": sum(c["exact"] for c in ok), "direction_ok": sum(c["direction_ok"] is True for c in ok),
            "direction_wrong": sum(c["direction_ok"] is False for c in ok),
            "recall_pos": len(pos), "recall_found": len(found), "relation_recall": rate(len(found), len(pos)),
            "missed": [[r["asset_id"], r["relative"], r["ref_pair_relation"]] for r in pos if r not in found],
            "by_kind": by, "rows": claims}


def gate_checks(tot, relm, g):
    def ge(v, lim):
        return None if v is None else v >= lim

    def le(v, lim):
        return None if v is None else v <= lim

    prec = relm["relation_precision"] if relm["closed"] >= g["relation_precision_min_n"] else None
    return {"DANGEROUS_FALSE_STANDALONE = 0": tot["dangerous_false_standalone"] <= g["dangerous_false_standalone_max"],
            "routing_accuracy >= %.2f" % g["routing_accuracy_min"]: ge(tot["routing_accuracy"], g["routing_accuracy_min"]),
            "routing_coverage >= %.2f" % g["routing_coverage_min"]: ge(tot["routing_coverage"], g["routing_coverage_min"]),
            "overconservative_rate <= %.2f" % g["overconservative_rate_max"]:
                le(tot["overconservative_rate"], g["overconservative_rate_max"]),
            "verified_relation_precision >= %.2f (закрытых >= %d)" % (g["relation_precision_min"],
                                                                     g["relation_precision_min_n"]):
                ge(prec, g["relation_precision_min"])}


def verdict(checks):
    v = list(checks.values())
    return False if False in v else (None if None in v else True)


def do_report(out=OUT):
    d, h = load_freeze(out), load_holdout(out)
    ch = code_changed(d)
    if ch:
        raise SystemExit("код изменён после заморозки: %s - отчёт по замороженным правилам невозможен" % ", ".join(ch))
    rels = load_relations(out)
    ref, refp, lk = load_reference(out)
    ans_p = p(out, "answers_vitali.tsv")
    if not os.path.exists(ans_p):
        raise SystemExit("нет %s" % ans_p)
    ans = {r["asset_id"]: r for r in ir.read_tsv(ans_p)}
    keys = [x["asset_id"] for x in h["items"]]
    layer = {x["asset_id"]: x for x in h["items"]}
    bad = ["%s: нет ответа" % a for a in keys if a not in ans]
    bad += ["%s: semantic_kind '%s'" % (a, ans[a].get("semantic_kind")) for a in keys
            if a in ans and ans[a].get("semantic_kind") not in ir.SEMANTIC]
    bad += check_reference(ref, refp, keys)
    inp = dict(d["inputs"])
    inp["relations"] = load_json_path(out)
    meta = rr.metadata(inp)
    meta_v4 = meta[:6] + (None,)
    umap = d["routing"]["relation_unit"]
    rows = []
    for a in keys:
        sk = ans.get(a, {}).get("semantic_kind", "")
        u, rule, why = rr.route(a, sk, meta, unit_map=umap)
        u4, rule4, _ = rr.route(a, sk, meta_v4)
        r = ref.get(a, {})
        rows.append({"asset_id": a, "layer": layer[a]["layer"], "sub": layer[a]["sub"], "semantic_kind": sk,
                     "ref_semantic_kind": r.get("ref_semantic_kind") or "open", "rule_unit": u, "rule": rule,
                     "why": why, "ref_route": r.get("ref_route") or "open", "v4_unit": u4, "v4_rule": rule4,
                     "ref_relation": r.get("ref_relation") or "OPEN", "ref_relation_to": r.get("ref_relation_to", ""),
                     "final_identity": ans.get(a, {}).get("final_identity", ""),
                     "truth_identity": r.get("truth_identity", ""),
                     "missing_context": (ans.get(a, {}).get("missing_context") or "").strip()})
    tot = routing_metrics(rows)
    v4 = routing_metrics([dict(r, rule_unit=r["v4_unit"]) for r in rows])
    relm = relation_metrics(rels, refp, keys)
    sem = [r for r in rows if r["semantic_kind"] != "UNSURE" and r["ref_semantic_kind"] != "open"]
    sem_acc = rate(sum(r["semantic_kind"] == r["ref_semantic_kind"] for r in sem), len(sem))
    layers = {n: routing_metrics([r for r in rows if r["layer"] == n]) for n, _q, _s in LAYERS}
    checks = gate_checks(tot, relm, d["gates"])
    passed = verdict(checks)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"], "holdout_sha256": h["sha256"],
           "reference_locked": lk["created"], "answers_present_at_ref_lock": lk["answers_present_at_lock"],
           "passed": passed, "checks": checks, "total": tot, "v4_without_relations": v4,
           "relations": {k: v for k, v in relm.items() if k != "rows"}, "relation_claims": relm["rows"],
           "semantic_accuracy": sem_acc, "semantic_n": len(sem), "layers": layers,
           "rules_fired": dict(Counter(r["rule"] for r in rows)), "invalid": bad, "rows": rows}
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res, d)
    return res


def load_json_path(out):
    return ir.load_json(p(out, "relations.lock.json"))["path"]


def write_md(out, res, d):
    word = {True: "PASS", False: "**FAIL**", None: "не решено"}
    yes = {True: "да", False: "**нет**", None: "нет данных"}
    t, rm = res["total"], res["relations"]
    L = ["# ROUTING_RULES_V4_R1 - слепой holdout: %s" % word[res["passed"]], "",
         "снимок %s, holdout %s; ось A - Vitali, эталон - независимый (заморожен %s%s)." % (
             res["freeze_sha256"][:12], res["holdout_sha256"][:12], res["reference_locked"],
             ", ответы уже были" if res["answers_present_at_ref_lock"] else ", до ответов"), "",
         "## Ворота", "", "| ворота | значение | пройдено |", "|---|---|---|"]
    vals = [str(t["dangerous_false_standalone"]),
            "%s (%d из %d)" % (t["routing_accuracy"], t["correct"], t["decided"]),
            "%s (%d из %d)" % (t["routing_coverage"], t["decided"], t["ref_closed"]),
            "%s (%d из %d одиночных по эталону; от всех 40: %s)" % (t["overconservative_rate"], t["overconservative"],
                                                                    t["ref_standalone"], t["overconservative_of_all"]),
            "%s (%d из %d закрытых; утверждений %d, OPEN %d, без строки эталона %d)" % (
                rm["relation_precision"], rm["ok"], rm["closed"], rm["claims"], rm["open"], rm["unjudged"])]
    for (k, v), val in zip(res["checks"].items(), vals):
        L.append("| %s | %s | %s |" % (k, val, yes[v]))
    L += ["", "| ещё (не ворота) | значение |", "|---|---|",
          "| relation recall (пары с родством по эталону, найденные детектором) | %s (%d из %d) |" % (
              rm["relation_recall"], rm["recall_found"], rm["recall_pos"]),
          "| верных утверждений с точным видом / направление верно / неверно | %d / %d / %d |" % (
              rm["exact_kind"], rm["direction_ok"], rm["direction_wrong"]),
          "| точность оси A у Vitali | %s (из %d) |" % (res["semantic_accuracy"], res["semantic_n"]),
          "| REVIEW | %d |" % t["review"],
          "| V4 без родства и R8a на тех же ответах: опасных / точность / охват | %d / %s / %s |" % (
              res["v4_without_relations"]["dangerous_false_standalone"], res["v4_without_relations"]["routing_accuracy"],
              res["v4_without_relations"]["routing_coverage"]),
          "| сработали правила | %s |" % ", ".join("%s %d" % kv for kv in sorted(res["rules_fired"].items())), "",
          "## По видам утверждений детектора", "", "| вид | утверждений | закрыто эталоном | верно |", "|---|---|---|---|"]
    for k, v in rm["by_kind"].items():
        L.append("| %s | %d | %d | %d |" % (k, v["claims"], v["closed"], v["ok"]))
    L += ["", "## По слоям отбора (диагностика)", "",
          "| слой | n | опасных | точность | охват | сверхосторожно | REVIEW |", "|---|---|---|---|---|---|---|"]
    for n, m in res["layers"].items():
        L.append("| %s | %d | %d | %s | %s | %d из %d | %d |" % (n, m["n"], m["dangerous_false_standalone"],
                                                              m["routing_accuracy"], m["routing_coverage"],
                                                              m["overconservative"], m["ref_standalone"], m["review"]))
    L += ["", "## По предметам", "",
          "| предмет | слой | A Vitali / эталон | правило | V4_R1 | эталон | V4 | родство эталона | улика |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        mark = ("**ОПАСНО**" if r["rule_unit"] == "STANDALONE_RENDER" and r["ref_route"] in ir.DANGEROUS_REF else
                "" if r["rule_unit"] in ("REVIEW",) or r["ref_route"] == "open" else
                "да" if r["rule_unit"] == r["ref_route"] else "**нет**")
        L.append("| %s | %s/%s | %s / %s | %s | %s %s | %s | %s | %s %s | %s |" % (
            r["asset_id"], r["layer"], r["sub"], r["semantic_kind"], r["ref_semantic_kind"], r["rule"],
            r["rule_unit"], mark, r["ref_route"], r["v4_unit"], r["ref_relation"], r["ref_relation_to"], r["why"]))
    if res["invalid"]:
        L += ["", "Ошибки в ответах или эталоне: " + "; ".join(res["invalid"])]
    with open(p(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


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
        print("родство цело")
    if os.path.exists(p(out, "reference.lock.json")):
        load_reference(out)
        print("эталон цел")
    print("ответов: %s" % ("ЕСТЬ" if os.path.exists(p(out, "answers_vitali.tsv")) else "нет"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["freeze", "select", "relations", "cards", "dossier", "lockref", "report", "check"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.chdir(ROOT)
    {"freeze": freeze, "select": do_select, "relations": do_relations, "cards": do_cards, "dossier": do_dossier,
     "lockref": do_lockref, "report": do_report, "check": do_check}[a.cmd](a.out)


if __name__ == "__main__":
    main()
