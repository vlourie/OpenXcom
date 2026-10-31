#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ROUTING_RULES_V5 - заморозка и слепой holdout на 50 новых предметах (специалист 01.10, передал Vitali в чате). CPU.

Диагностика V5 на тех же 40 (recount_fr2: опасных 0, родство 24/24, точность 0.88, охват 0.781) - не приёмка: правила
писались после ответов и эталона тех 40. Здесь всё замораживается ДО отбора новых предметов, и после ответов ничего
не меняется - «независимо от красоты результата больше ничего не подстраивать». Замороженные V4_R1 (routing_holdout.py
и его папка) не трогаются: отсюда только читаются их функции.

Что заморожено (FREEZE.json): правила V5 и их порядок (routing_rules_v5.route_v5 с FAMILY_RELATION_V2), поиск
перекрасок RELATION_DISCOVERY_V1, файл прямых пар family_relation_v2.tsv, связи MCD с правилом частоты
MCD_DOMINANCE_RULE = PROVISIONAL (origin FORESTRED:4 diagnostic, requires_blind_validation), онтология оси A V5,
ворота и определения, слои, копии входов и sha256 кода.

Порядок (каждый шаг отказывается, если предыдущего нет или свой уже сделан):
    freeze     снимок (FREEZE.json, inputs/)
    select     50 предметов по слоям: 12 родство (прямые пары FR2, legacy, зеркало, открытое семейство), 10 состояние
               по MCD (die / alt / анимация / CANDIDATE / правило частоты), 10 кусок / составной / модуль, 8 поверхность
               и рельеф, 10 обычных одиночных. Исключены наборы PCK разработки V3 / V4 / V5 (всё, что было на карточках,
               пары V1, контроли, разобранные случаи), всё с решением человека; один предмет на набор
    relations  замороженный детектор (relation_probe.discover) на 50 - relations/relations.json и замок
    cards      страница для Vitali: только ось A (онтология V5) и final_identity; маршрут он не выбирает
    dossier    пакет независимого эталона: картинки без панели семейства, факты без меток родства; в кандидатах родни
               ВСЕ утверждения правил (детектор, FR2, MCD любого уровня) плюс похожие, вперемешку и без источника
               (у V4_R1 предел 10 кандидатов потерял 5 утверждений - здесь утверждения в пакет идут всегда)
    lockref    заморозить эталон до ответов Vitali
    report     маршрут V5 из оси A + замороженных метаданных, ворота, счётчики MCD и правила частоты
    check      все хэши целы

    py -3.13 tools/hdart/routing_holdout_v5.py freeze|select|relations|cards|dossier|lockref|report|check
"""
import argparse
import hashlib
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
import routing_rules as rr             # noqa: E402
import routing_rules_v5 as v5          # noqa: E402

ROOT = ir.ROOT
ENC = ir.ENC
OUT = os.path.join(ir.PROBES, "routing-holdout-v5")
SEED = "routing-holdout-v5-2026-10-01"
N_TOTAL = 50
INPUTS = dict(rh.INPUTS, family_relation_v2=fr2m.TSV,
              mcd_state=os.path.join(ms.OUT, "mcd_state_relations.json"), census_frames=ms.CENSUS)
CODE = ["tools/hdart/routing_rules_v5.py", "tools/hdart/mcd_state.py", "tools/hdart/family_relation_v2.py",
        "tools/hdart/families_recolor_diff.py", "tools/hdart/obj_struct.py", "tools/hdart/relation_probe.py",
        "tools/hdart/routing_rules.py", "tools/hdart/identity_routing.py", "tools/hdart/obj_families.py",
        "tools/hdart/routing_holdout.py", "tools/hdart/routing_holdout_v5.py", "tools/hdart/map_mockup.py"]

LAYERS = (("relation", 12, (("fr2_new", 3), ("fr2_verified", 3), ("legacy_recolor", 2), ("family_mirror", 2),
                            ("family_open", 2))),
          ("mcd_state", 10, (("mcd_die", 3), ("mcd_alt", 2), ("mcd_anim", 2), ("mcd_dominance", 1),
                             ("mcd_candidate", 2))),
          ("part", 10, (("part_suspect", 3), ("part_words", 2), ("composite", 3), ("modular_words", 2))),
          ("surface", 8, (("wall", 2), ("floor", 2), ("relief", 2), ("object_or_relief", 1), ("surface_mcd", 1))),
          ("standalone", 10, (("standalone", 10),)))

SEMANTIC = list(v5.SEMANTIC_V5)
SEM_DEFS = {
    "OBJECT": ir.SPEC["semantic_kind"]["OBJECT"],
    "OBJECT_PART": "часть вещи, машины, мебели или существа: кусок корпуса машины, хвост вертолёта, изголовье "
                   "кровати на две клетки (не стена и не обшивка постройки)",
    "STRUCTURAL_SURFACE": "поверхность постройки или корабля: стена, пол, крыша, обшивка, архитектурная панель, дверь",
    "TERRAIN_RELIEF": ir.SPEC["semantic_kind"]["TERRAIN_RELIEF"],
    "NOT_OBJECT": "не вещь и не поверхность: эффект, служебный или пустой кадр",
    "UNSURE": ir.SPEC["semantic_kind"]["UNSURE"]}
REF_ROUTES = list(rh.REF_ROUTES) + ["ANIMATION_FAMILY"]
DANGEROUS = tuple(ir.DANGEROUS_REF) + ("ANIMATION_FAMILY",)
REF_RELATIONS = [x for x in rh.REF_RELATIONS if x != "OPEN"] + ["ANIMATION_FRAME_OF", "OPEN"]
GROUP = dict(rh.GROUP, ANIMATION_FRAME_OF="animation")
CLAIM_GROUP = {"RECOLOR_OF": "derived", "RECOLOR_WITH_LOCAL_EDIT": "derived", "STATE_VARIANT_OF": "derived",
               "ANIMATION_FRAME_OF": "animation"}
CLAIM_EXACT = {"RECOLOR_OF": ("RECOLOR_OF",), "RECOLOR_WITH_LOCAL_EDIT": ("DERIVED_FROM",),
               "STATE_VARIANT_OF": ("STATE_VARIANT_OF",), "ANIMATION_FRAME_OF": ("ANIMATION_FRAME_OF",)}

ROUTING = {
    "version": "V5",
    "precedence": ["R1", "R2", "R0v", "R3m", "R3a", "R3", "R4d", "R4", "R4l", "R5", "R6", "R7", "R7r", "R7m", "S",
                   "R7n", "R7s", "R8a", "R8", "R9"],
    "rules": v5.__doc__.split("Правила V5 по порядку")[1].split("Пересчёт на 40")[0].strip(),
    "relation_unit": rr.RELATION_UNIT_HOLDOUT,
    "open_blockers": list(rr.OPEN_BLOCKERS),
    "evidence_only": list(v5.EVIDENCE_ONLY),
    "family_relation": "FAMILY_RELATION_V2: перекраска даёт DERIVED только прямым строгим ребром (VERIFIED_DIRECT / "
                       "DIRECT_NEW), кадр - производная сторона; без замыкания по цепочке. recolor рабочего семейства "
                       "без прямого подтверждения - REVIEW (LEGACY_RELATION, не ложь). Зеркало семейства - как было",
    "animation": "кадр анимации (MCD Frame[1..7], STRONG) - ANIMATION_FAMILY: общий облик и опознание с основой, "
                 "возможно рендер по фазам под общей структурой; не смешивается с разрушенным видом",
}
FAMILY_RELATION = {"version": "FAMILY_RELATION_V2", "doc": fr2m.__doc__.strip(),
                   "direct_statuses": list(fr2m.DIRECT), "families_json_unchanged": True}
MCD = {"version": "MCD_STATE_RELATIONS", "doc": ms.__doc__.strip(), "shared_debris_min": ms.SHARED_DEBRIS_MIN,
       "dominant_min": ms.DOMINANT_MIN, "dominant_ratio": ms.DOMINANT_RATIO,
       "MCD_DOMINANCE_RULE": ms.MCD_DOMINANCE_RULE}
ONTOLOGY = {"semantic_kind": SEM_DEFS, "surface_from_answer": "OBJECT_PART / NOT_OBJECT + улика поверхности MCD -> "
            "STRUCTURAL_SURFACE (routing_rules_v5.semantic_v5); STRUCTURAL_SURFACE в ответе - как есть"}
GATES = dict(rh.GATES)
DEFINITIONS = {
    "dangerous_false_standalone": "маршрут V5 STANDALONE_RENDER при ref_route %s; все 50" % "/".join(DANGEROUS),
    "routing_accuracy": "верно / решено: предметы с закрытым ref_route (не open), где V5 дал конкретный маршрут "
                        "(не REVIEW)",
    "routing_coverage": "решено V5 (не REVIEW) / предметов с закрытым ref_route",
    "overconservative_rate": "из предметов с ref_route STANDALONE_RENDER - доля, ушедших в любой другой маршрут или "
                             "REVIEW; число от всех 50 печатается рядом, не ворота",
    "relation_precision": "утверждения правил на 50 (пара предмет - родственник, обе стороны): перекраска детектора "
                          "(без FIXED_NEIGHBOUR - он улика), прямые рёбра FR2, связи MCD STRONG. Закрытые эталоном пар "
                          "(не OPEN и строка есть): верно - эталон назвал родство той же группы (производное: "
                          "RECOLOR_OF / DERIVED_FROM / STATE_VARIANT_OF; анимация: ANIMATION_FRAME_OF), неверно - NONE "
                          "или другая группа. Меньше relation_precision_min_n закрытых - ворота не решены. Точный вид и "
                          "направление - отдельной строкой, не ворота",
    "mcd_state_claims": "не ворота: утверждения MCD STRONG отдельно - correct / wrong / unresolved (OPEN или нет "
                        "строки эталона); MCD relation precision = correct / (correct + wrong) - диагностика",
    "dominance_rule": "не ворота: MCD_DOMINANCE_RULE (PROVISIONAL) - triggered: связи holdout, понижённые правилом; "
                      "по эталону пар helped (эталон не STATE_VARIANT_OF - ложное состояние снято), hurt (эталон "
                      "STATE_VARIANT_OF - верное состояние потеряно), unresolved; плюс смена маршрута с правилом и без",
    "semantic_accuracy": "только метрика: ось A Vitali против ref_semantic_kind в онтологии V5 (UNSURE и open вне "
                         "знаменателя)",
    "layers": "все метрики и по слоям отбора; слои - диагностика, не ворота",
}
ANS_HEAD = rh.ANS_HEAD
REF_HEAD = rh.REF_HEAD
PAIR_HEAD = rh.PAIR_HEAD
BODY = ("routing", "family_relation", "relation_discovery", "mcd", "ontology", "gates", "definitions", "seed",
        "layers", "inputs_source", "inputs", "input_sha256", "code_sha256")
file_sha = rh.file_sha
pset = rh.pset


def p(out, name):
    return os.path.join(out, name)


def order(key):
    return hashlib.sha256((SEED + "|" + key).encode()).hexdigest()


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
    body = {"routing": ROUTING, "family_relation": FAMILY_RELATION, "relation_discovery": rh.RELATION_DISCOVERY,
            "mcd": MCD, "ontology": ONTOLOGY, "gates": GATES, "definitions": DEFINITIONS, "seed": SEED,
            "layers": [[n, q, [list(s) for s in sub]] for n, q, sub in LAYERS],
            "inputs_source": {k: v.replace(os.sep, "/") for k, v in inputs.items()},
            "inputs": snap, "input_sha256": {k: file_sha(v) for k, v in snap.items()},
            "code_sha256": {c: file_sha(c) for c in code}}
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                decided="специалист 01.10, передал Vitali в чате: V5 архитектуру утверждаю; FAMILY_RELATION_V2 из "
                        "прямых строгих пар без транзитивных слияний, families.json не менять, пересчитать 40 только "
                        "диагностически, больше ничего не подстраивать, заморозить V5, blind holdout на ~50 новых",
                rule="после отбора holdout ничего из этого не меняется")
    ir.dump_json(p(out, "FREEZE.json"), data)
    print("V5 заморожен (sha256 %s): входов %d, файлов кода %d" % (data["sha256"][:12], len(snap), len(code)))
    return data


def load_freeze(out=OUT):
    d = ir.load_json(p(out, "FREEZE.json"))
    if ir.sha({k: d[k] for k in BODY}) != d["sha256"]:
        raise SystemExit("FREEZE.json изменён после заморозки: хэш не сходится")
    bad = [k for k, v in d["inputs"].items() if file_sha(v) != d["input_sha256"][k]]
    if bad:
        raise SystemExit("снимок входов изменён: %s" % ", ".join(bad))
    return d


def code_changed(d):
    return [c for c, h in d["code_sha256"].items() if not os.path.exists(c) or file_sha(c) != h]


def live_same(d, names=("items", "touch")):
    """Детектор и FR2.load читают живые items.json и touch.tsv - они обязаны совпадать со снимком."""
    bad = [k for k in names if file_sha(d["inputs_source"][k]) != d["input_sha256"][k]]
    if bad:
        raise SystemExit("живые %s отличаются от снимка - посчитали бы не на тех данных" % ", ".join(bad))


# ---------------------------------------------------------------- select

def pools(inp, gen, ex_sets, ex_keys, struct=None):
    """Кандидаты подслоёв: {подслой: [(ключ, строка, заметка)]}. Отбор по замороженным метаданным."""
    txt, why, verd = rh.texts(inp), rh.class_why(inp), rh.verdicts(inp)
    fam_size = Counter()
    for fam in ir.load_json(inp["families"]):
        fam_size[fam["family_id"].upper()] = len(fam.get("members", [])) + len(fam.get("review", []))
    fr2 = fr2m.load(inp["family_relation_v2"])
    mcd = ms.index(ir.load_json(inp["mcd_state"])["relations"])
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
    rows = [r for r in gen if ok(r["key"])]
    for r in rows:
        k, bl = r["key"], r["blockers"].split()
        es = fr2.get(k.upper(), [])
        der = [e for e in es if e["side"] == "derived"]
        dn = [e for e in der if e["status"] == "DIRECT_NEW"]
        dv = [e for e in der if e["status"] == "VERIFIED_DIRECT"]
        if dn:
            out["fr2_new"].append((k, r, "FR2 DIRECT_NEW от %s" % dn[0]["relative"]))
        if dv:
            out["fr2_verified"].append((k, r, "FR2 VERIFIED_DIRECT от %s" % dv[0]["relative"]))
        if r["relation"] == "recolor" and not dn and not dv and any(e["status"] == "LEGACY_RELATION" for e in der):
            out["legacy_recolor"].append((k, r, "recolor семейства без прямого подтверждения"))
        if r["relation"] == "mirror" and r["key"] != r["asset_id"] and r["action"] == "DERIVE":
            out["family_mirror"].append((k, r, "mirror от %s" % r["asset_id"]))
        if r["action"] in ("GENERATE", "GENERATE_WITH") and (
                r["relation"] == "alternate_view" or any(b.split(":")[0] in ("family_review", "in_review")
                                                         for b in bl)):
            out["family_open"].append((k, r, "relation %s, %s" % (r["relation"] or "-", " ".join(bl))))
        for x in mcd.get(k.upper(), []):
            if x["side"] != "derived":
                continue
            if x["level"] == "STRONG":
                sub = {"die": "mcd_die", "alt": "mcd_alt", "anim": "mcd_anim"}[x["via"]]
            else:
                sub = "mcd_dominance" if x.get("dominance") else "mcd_candidate"
            out[sub].append((k, r, "MCD %s %s %s" % (x["via"], x["level"], x["base"])))
        if r["action"] == "GENERATE" and r["kind"] == "один" and "part_fragment_suspect" in bl:
            out["part_suspect"].append((k, r, r.get("fragment_why", "")))
        if (r["action"] == "GENERATE" and r["kind"] == "один" and rh.PART_RX.search(t(r))
                and not rh.MODULAR_RX.search(t(r))):
            out["part_words"].append((k, r, rh.PART_RX.search(t(r)).group(0)))
        if r["action"] == "GENERATE" and r["kind"] == "составной":
            out["composite"].append((k, r, "составной заказ"))
        if (r["action"] == "GENERATE" and r["kind"] == "один" and rh.MODULAR_RX.search(t(r))
                and not rh.PART_RX.search(t(r))):
            out["modular_words"].append((k, r, rh.MODULAR_RX.search(t(r)).group(0)))
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
                and verd.get(r["asset_id"].upper()) == "agree" and not rh.PART_RX.search(t(r))
                and not rh.MODULAR_RX.search(t(r)) and not es and not mcd.get(k.upper())):
            out["standalone"].append((k, r, "обычный одиночный"))
    if struct is not None:              # вещь по классу очереди, а MCD говорит «стена / пол» - лениво, по зерну
        for r in sorted((r for r in rows if r["action"] == "GENERATE" and r["kind"] == "один"
                         and r["asset_class"] == "object"), key=lambda r: order("surf|" + r["key"].upper())):
            lv, w = v5.surface_evidence(struct, r["key"])
            if lv == "STRONG":
                out["surface_mcd"].append((r["key"], r, w))
            if len(out["surface_mcd"]) >= 40:
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


def do_select(out=OUT):
    if os.path.exists(p(out, "holdout.json")):
        raise SystemExit("holdout уже отобран: перевыбор запрещён")
    d = load_freeze(out)
    if code_changed(d):
        raise SystemExit("код изменён после заморозки: %s" % ", ".join(code_changed(d)))
    live_same(d, ("items",))
    inp = d["inputs"]
    gen = ir.read_tsv(inp["generation"])
    ex_sets, ex_keys = rh.exclusions(inp)
    v4 = rh.OUT                             # V4_R1 и V5-prep: наборы 40 и их родни - разработка V5
    for x in rh.load_holdout(v4)["items"]:
        ex_sets.add(pset(x["asset_id"]))
        ex_keys.add(x["asset_id"].upper())
    for k, rs in rh.load_relations(v4).items():
        ex_sets |= {pset(r["relative"]) for r in rs}
    v4keys = [x["asset_id"].upper() for x in rh.load_holdout(v4)["items"]]
    fr2 = fr2m.load(inp["family_relation_v2"])           # V5 писался по прямым парам и связям MCD этих 40
    mcd = ms.index(ir.load_json(inp["mcd_state"])["relations"])
    for k in v4keys:
        ex_sets |= {pset(e["relative"]) for e in fr2.get(k, [])}
        ex_sets |= {pset(x["relative"]) for x in mcd.get(k, [])}
    ex_sets.add(ms.MCD_DOMINANCE_RULE["origin"].split(":")[0].upper())
    import map_mockup as mm
    import obj_struct as os_
    pool = pools(inp, gen, ex_sets, ex_keys, os_.Struct(mm.World()))
    items, short = select(pool)
    data = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"], "seed": SEED,
            "n": len(items), "pool": {k: len(v) for k, v in pool.items()}, "short": short,
            "excluded_sets": sorted(ex_sets), "excluded_keys_n": len(ex_keys), "sha256": rh.digest(items),
            "items": items, "rule": "список заморожен до ответов и эталона; слой в карточку не идёт"}
    ir.dump_json(p(out, "holdout.json"), data)
    print("отобрано %d (sha256 %s): %s" % (len(items), data["sha256"][:12], dict(Counter(x["layer"] for x in items))))
    print("недобор:", short or "нет")
    print("пулы:", data["pool"])
    return data


def load_holdout(out=OUT):
    return rh.load_holdout(out)


# ---------------------------------------------------------------- relations

def do_relations(out=OUT):
    lock = p(out, "relations.lock.json")
    if os.path.exists(lock):
        raise SystemExit("родство уже посчитано и заморожено: %s" % lock)
    d, h = load_freeze(out), load_holdout(out)
    if code_changed(d):
        raise SystemExit("код изменён после заморозки: %s" % ", ".join(code_changed(d)))
    live_same(d)
    import relation_probe as rp
    keys = [x["asset_id"] for x in h["items"]]
    rp.discover(rp.Ctx(), keys, p(out, "relations"))
    path = p(p(out, "relations"), "relations.json")
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"],
                        "holdout_sha256": h["sha256"], "relations_sha256": file_sha(path),
                        "path": path.replace(os.sep, "/")})
    print("родство заморожено: %s" % file_sha(path)[:12])


load_relations = rh.load_relations


# ---------------------------------------------------------------- карточки

def do_cards(out=OUT):
    d, h = load_freeze(out), load_holdout(out)
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("ответы уже есть - карточки не перестраиваются")
    ic, cards = rh.build_cards(out, h["items"], d["inputs"])
    data = [{k: v for k, v in c.items()} for c in cards]
    title = "Holdout маршрута: 40 новых предметов"
    if title not in rh.PAGE_V:
        raise SystemExit("заголовок страницы V4_R1 не найден - страница сказала бы «40»")
    page = (rh.PAGE_V.replace(title, "Holdout маршрута V5: %d новых предметов" % len(cards))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__MISS__", json.dumps(ic.MISSING)).replace("__SEM__", json.dumps(SEMANTIC))
            .replace("__DEFS__", json.dumps({"semantic_kind": SEM_DEFS}, ensure_ascii=False))
            .replace("__KEY__", "routing-holdout-v5-" + h["sha256"][:8]))
    with open(p(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    ir.dump_json(p(out, "cards.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "holdout_sha256": h["sha256"], "img_sha256": ir.img_digest(p(out, "img")),
                                        "assets": [c["asset"] for c in cards], "cards": data})
    rel = os.path.relpath(os.path.abspath(out), os.path.abspath(os.path.join("art", "objects", "generation")))
    print("карточек %d; страница: http://localhost:8778/%s/index.html" % (len(cards), rel.replace(os.sep, "/")))


# ---------------------------------------------------------------- утверждения правил

def mcd_index(inp, keys, rels, dominant=True):
    import map_mockup as mm
    sets = {pset(k) for k in keys} | {pset(c["relative"]) for k in keys for c in rels.get(k, [])}
    return ms.index(ms.build(sets, mm.World(), cells=ms.placements(inp["census_frames"]), dominant=dominant))


def rule_claims(rels, mcd, fr2, keys, with_candidates=False):
    """Пары-утверждения правил: (ключ, родственник, вид, уровень, сторона, источник). FIXED_NEIGHBOUR - нет."""
    raw, seen = [], set()
    for k in keys:
        for c in rels.get(k, []):
            if c["kind"] not in v5.EVIDENCE_ONLY:
                raw.append((k, c["relative"], c["kind"], c["level"], c["side"], "detector"))
                seen.add((k.upper(), c["relative"].upper(), c["kind"]))
        for x in mcd.get(k.upper(), []):
            if x["level"] == "STRONG" or with_candidates:
                raw.append((k, x["relative"], x["kind"], x["level"], x["side"], "mcd_" + x["via"]))
        for e in fr2.get(k.upper(), []):
            if e["status"] in fr2m.DIRECT and (k.upper(), e["relative"].upper(), e["relation"]) not in seen:
                seen.add((k.upper(), e["relative"].upper(), e["relation"]))
                raw.append((k, e["relative"], e["relation"], e["confidence"], e["side"], "fr2_" + e["status"]))
    return raw


def score_claims(raw, refp):
    ref = {(r["asset_id"].upper(), r["relative"].upper()): r for r in refp}
    out = []
    for k, rel_to, kind, level, side, src in raw:
        r = ref.get((k.upper(), rel_to.upper()))
        rel = (r or {}).get("ref_pair_relation") or "OPEN"
        st = "open" if rel == "OPEN" else ("ok" if GROUP.get(rel) == CLAIM_GROUP[kind] else "wrong")
        dr = (r or {}).get("direction") or "open"
        dir_ok = None
        if st == "ok" and side in ("derived", "base") and dr in ("asset_derived", "relative_derived"):
            dir_ok = (side == "derived") == (dr == "asset_derived")
        out.append({"asset_id": k, "relative": rel_to, "kind": kind, "level": level, "side": side, "source": src,
                    "ref": rel, "direction": dr, "status": st, "exact": rel in CLAIM_EXACT[kind],
                    "direction_ok": dir_ok, "judged": r is not None})
    return out


def precision(claims):
    closed = [c for c in claims if c["status"] != "open"]
    ok = [c for c in closed if c["status"] == "ok"]
    return {"claims": len(claims), "closed": len(closed), "ok": len(ok), "wrong": len(closed) - len(ok),
            "open": len(claims) - len(closed), "unjudged": sum(not c["judged"] for c in claims),
            "relation_precision": rh.rate(len(ok), len(closed)), "exact_kind": sum(c["exact"] for c in ok),
            "direction_ok": sum(c["direction_ok"] is True for c in ok),
            "direction_wrong": sum(c["direction_ok"] is False for c in ok)}


# ---------------------------------------------------------------- пакет эталона

def do_dossier(out=OUT):
    d, h = load_freeze(out), load_holdout(out)
    live_same(d)
    rels = load_relations(out)
    cj = ir.load_json(p(out, "cards.json"))
    pack = p(out, "reference_pack")
    if os.path.exists(p(out, "reference.lock.json")):
        raise SystemExit("эталон уже заморожен - пакет не перестраивается")
    os.makedirs(p(pack, "img"), exist_ok=True)
    inp = d["inputs"]
    keys = [x["asset_id"] for x in h["items"]]
    fr2 = fr2m.load(inp["family_relation_v2"])
    mcd = mcd_index(inp, keys, rels)
    raw = rule_claims(rels, mcd, fr2, keys, with_candidates=True)
    must = {}
    for k, rel_to, *_ in raw:
        must.setdefault(k, set()).add(rel_to)
    for k in keys:
        for e in fr2.get(k.upper(), []):
            must.setdefault(k, set()).add(e["relative"])      # и LEGACY_RELATION: эталону знать полезно
        for c in rels.get(k, []):
            must.setdefault(k, set()).add(c["relative"])      # и FIXED_NEIGHBOUR: улика, эталон её закрывает
    cand, ctx = rh.candidates(out, h, inp, rels)
    entries, pairs = [], []
    for c in cj["cards"]:
        a = c["asset"]
        m = sorted({x for x in must.get(a, set()) if x.upper() != a.upper()})
        rest = [x for x in cand.get(a, []) if x not in m]
        allc = sorted(m + rest[:max(0, 12 - len(m))], key=lambda z: order("cand|" + a + "|" + z))
        panels = []
        for t, f in c["panels"]:
            if f.split("_", 1)[1].startswith("family"):
                continue
            shutil.copyfile(p(p(out, "img"), f), p(p(pack, "img"), f))
            panels.append([t, "img/" + f])
        facts = "\n".join(line for line in c["facts"].split("\n") if not rh.FAMILY_LINE.match(line))
        sheets = []
        for b in allc:
            fn = "pair_%02d_%s__%s.png" % (c["n"], a.replace(":", "-"), b.replace(":", "-"))
            if rh.pair_sheet(ctx, a, b, p(p(pack, "img"), fn)):
                sheets.append([b, "img/" + fn])
            pairs.append([a, b])
        entries.append({"n": c["n"], "asset_id": a, "panels": panels, "facts": facts, "notes": c["notes"],
                        "candidate_relatives": allc, "pair_sheets": sheets})
    missing = [(k, x) for k, xs in must.items() for x in xs if [k, x] not in pairs and x.upper() != k.upper()]
    if missing:
        raise SystemExit("утверждения не попали в пакет: %s" % missing[:5])
    spec = {"semantic_kind": SEM_DEFS, "ref_routes": REF_ROUTES, "render_unit": dict(
        ir.SPEC["render_unit"], ANIMATION_FAMILY="кадр анимации другого кадра (фаза петли): общий облик и опознание "
                                                 "с основой; не разрушенный вид и не перекраска"),
            "precedence": ir.SPEC["precedence"], "ref_relations": REF_RELATIONS,
            "ref_relation_note": "ANIMATION_FRAME_OF - фаза анимации; STATE_VARIANT_OF - другое состояние той же вещи "
                                 "(разрушенная, открытая); недоказанное - OPEN, сходство истиной не делается"}
    ir.dump_json(p(pack, "dossier.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                           "holdout_sha256": h["sha256"], "items": entries, "spec_v5": spec})
    with open(p(out, "reference.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(REF_HEAD) + "\n" + "".join(e["asset_id"] + "\t" * (len(REF_HEAD) - 1) + "\n"
                                                     for e in entries))
    with open(p(out, "reference_pairs.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(PAIR_HEAD) + "\n" + "".join("%s\t%s\t\t\t\n" % (a, b) for a, b in pairs))
    print("пакет эталона: %d предметов, пар %d (утверждений правил в них %d) -> %s" % (
        len(entries), len(pairs), sum(len(v) for v in must.values()), pack))


# ---------------------------------------------------------------- эталон и отчёт

def check_reference(ref, refp, keys):
    bad = []
    for a in keys:
        r = ref.get(a)
        if not r:
            bad.append("%s: нет строки эталона" % a)
            continue
        if (r.get("ref_semantic_kind") or "open") not in SEMANTIC[:-1] + ["open"]:
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


load_reference = rh.load_reference


def metrics(rows):
    m = rh.routing_metrics(rows)
    m["dangerous_false_standalone"] = sum(r["rule_unit"] == "STANDALONE_RENDER" and r["ref_route"] in DANGEROUS
                                          for r in rows)
    return m


def dominance(rows, rows_nodom, mcd, keys, refp):
    ref = {(r["asset_id"].upper(), r["relative"].upper()): r.get("ref_pair_relation") or "OPEN" for r in refp}
    links = [(k, x) for k in keys for x in mcd.get(k.upper(), []) if x.get("dominance")]
    trig = [{"asset_id": k, "relative": x["relative"], "side": x["side"], "why": x["why"],
             "ref": ref.get((k.upper(), x["relative"].upper()), "OPEN")} for k, x in links]
    for t in trig:
        t["effect"] = ("unresolved" if t["ref"] == "OPEN" else "hurt" if t["ref"] == "STATE_VARIANT_OF" else "helped")
    old = {r["asset_id"]: r for r in rows_nodom}
    changed = [[r["asset_id"], old[r["asset_id"]]["rule_unit"], r["rule_unit"], r["ref_route"]] for r in rows
               if old[r["asset_id"]]["rule_unit"] != r["rule_unit"]]
    return {"triggered": len(trig), "helped": sum(t["effect"] == "helped" for t in trig),
            "hurt": sum(t["effect"] == "hurt" for t in trig), "unresolved": sum(t["effect"] == "unresolved" for t in trig),
            "links": trig, "route_changed": changed,
            "route_helped": [c[0] for c in changed if c[3] != "open" and c[2] == c[3] and c[1] != c[3]],
            "route_hurt": [c[0] for c in changed if c[3] != "open" and c[1] == c[3] and c[2] != c[3]]}


def do_report(out=OUT):
    d, h = load_freeze(out), load_holdout(out)
    ch = code_changed(d)
    if ch:
        raise SystemExit("код изменён после заморозки: %s - отчёт по замороженным правилам невозможен" % ", ".join(ch))
    live_same(d)
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
            if a in ans and ans[a].get("semantic_kind") not in SEMANTIC]
    bad += check_reference(ref, refp, keys)
    inp = dict(d["inputs"])
    inp["relations"] = rh.load_json_path(out)
    meta = rr.metadata(inp)
    umap = d["routing"]["relation_unit"]
    fr2 = fr2m.load(inp["family_relation_v2"])
    mcd, mcd_nodom = mcd_index(inp, keys, rels), mcd_index(inp, keys, rels, dominant=False)
    import map_mockup as mm
    import obj_struct as os_
    st = os_.Struct(mm.World())
    surf = {a: v5.surface_evidence(st, a) for a in keys}

    def build(mcd_idx, fr):
        rows = []
        for a in keys:
            sk = ans.get(a, {}).get("semantic_kind", "")
            u, rule, why, kind = v5.route_v5(a, sk, meta, mcd_idx, surf[a], umap, fr2=fr)
            r = ref.get(a, {})
            rows.append({"asset_id": a, "layer": layer[a]["layer"], "sub": layer[a]["sub"], "semantic_kind": sk,
                         "semantic_v5": kind, "surface": surf[a][0], "ref_semantic_kind": r.get("ref_semantic_kind")
                         or "open", "rule_unit": u, "rule": rule, "why": why, "ref_route": r.get("ref_route") or "open",
                         "ref_relation": r.get("ref_relation") or "OPEN", "ref_relation_to": r.get("ref_relation_to", ""),
                         "final_identity": ans.get(a, {}).get("final_identity", ""),
                         "truth_identity": r.get("truth_identity", "")})
        return rows

    rows = build(mcd, fr2)
    tot = metrics(rows)
    claims = score_claims(rule_claims(rels, mcd, fr2, keys), refp)
    relm = precision(claims)
    mcd_c = [c for c in claims if c["source"].startswith("mcd_")]
    mcd_cand = score_claims([x for x in rule_claims({}, mcd, {}, keys, with_candidates=True)
                             if x[3] != "STRONG"], refp)
    checks = rh.gate_checks(tot, relm, d["gates"])
    sem = [r for r in rows if r["semantic_v5"] != "UNSURE" and r["ref_semantic_kind"] != "open"]
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"], "holdout_sha256": h["sha256"],
           "reference_locked": lk["created"], "answers_present_at_ref_lock": lk["answers_present_at_lock"],
           "passed": rh.verdict(checks), "checks": checks, "total": tot,
           "relations": relm, "by_source": {s: precision([c for c in claims if c["source"] == s])
                                            for s in sorted({c["source"] for c in claims})},
           "mcd_state_claims": {"correct": sum(c["status"] == "ok" for c in mcd_c),
                                "wrong": sum(c["status"] == "wrong" for c in mcd_c),
                                "unresolved": sum(c["status"] == "open" for c in mcd_c),
                                "mcd_relation_precision": precision(mcd_c)["relation_precision"]},
           "mcd_candidate_links": precision(mcd_cand),
           "dominance_rule": dict(dominance(rows, build(mcd_nodom, fr2), mcd, keys, refp),
                                  status=ms.MCD_DOMINANCE_RULE["status"]),
           "sensitivity": {"V5 без FR2 (прежний R4)": metrics(build(mcd, None)),
                           "V5 без правила частоты MCD": metrics(build(mcd_nodom, fr2))},
           "semantic_accuracy": rh.rate(sum(r["semantic_v5"] == r["ref_semantic_kind"] for r in sem), len(sem)),
           "semantic_n": len(sem), "rules_fired": dict(Counter(r["rule"] for r in rows)),
           "layers": {n: metrics([r for r in rows if r["layer"] == n]) for n, _q, _s in LAYERS},
           "invalid": bad, "claims": claims, "rows": rows}
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    return res


def write_md(out, res):
    word = {True: "PASS", False: "**FAIL**", None: "не решено"}
    yes = {True: "да", False: "**нет**", None: "нет данных"}
    t, rm = res["total"], res["relations"]
    L = ["# ROUTING_RULES_V5 - слепой holdout: %s" % word[res["passed"]], "",
         "снимок %s, holdout %s; ось A - Vitali, эталон - независимый (заморожен %s%s)." % (
             res["freeze_sha256"][:12], res["holdout_sha256"][:12], res["reference_locked"],
             ", ответы уже были" if res["answers_present_at_ref_lock"] else ", до ответов"), "",
         "## Ворота", "", "| ворота | значение | пройдено |", "|---|---|---|"]
    vals = [str(t["dangerous_false_standalone"]),
            "%s (%d из %d)" % (t["routing_accuracy"], t["correct"], t["decided"]),
            "%s (%d из %d)" % (t["routing_coverage"], t["decided"], t["ref_closed"]),
            "%s (%d из %d одиночных по эталону; от всех: %s)" % (t["overconservative_rate"], t["overconservative"],
                                                                 t["ref_standalone"], t["overconservative_of_all"]),
            "%s (%d из %d закрытых; утверждений %d, OPEN %d, без строки эталона %d)" % (
                rm["relation_precision"], rm["ok"], rm["closed"], rm["claims"], rm["open"], rm["unjudged"])]
    for (k, v), val in zip(res["checks"].items(), vals):
        L.append("| %s | %s | %s |" % (k, val, yes[v]))
    mc, dm = res["mcd_state_claims"], res["dominance_rule"]
    L += ["", "## MCD и правило частоты (не ворота)", "",
          "mcd_state_claims: correct %d, wrong %d, unresolved %d; MCD relation precision %s." % (
              mc["correct"], mc["wrong"], mc["unresolved"], mc["mcd_relation_precision"]),
          "MCD CANDIDATE (в REVIEW, не утверждения): закрыто %d, из них родство подтверждено %d." % (
              res["mcd_candidate_links"]["closed"], res["mcd_candidate_links"]["ok"]),
          "MCD_DOMINANCE_RULE (%s): triggered %d, helped %d, hurt %d, unresolved %d; маршрут сменился у %d "
          "(помогло %s, навредило %s)." % (dm["status"], dm["triggered"], dm["helped"], dm["hurt"], dm["unresolved"],
                                           len(dm["route_changed"]), ", ".join(dm["route_helped"]) or "-",
                                           ", ".join(dm["route_hurt"]) or "-"), "",
          "## Утверждения по источникам", "", "| источник | утверждений | закрыто | верно | точность |",
          "|---|---|---|---|---|"]
    for s, x in res["by_source"].items():
        L.append("| %s | %d | %d | %d | %s |" % (s, x["claims"], x["closed"], x["ok"], x["relation_precision"]))
    L += ["", "| ещё (не ворота) | значение |", "|---|---|",
          "| верных с точным видом / направление верно / неверно | %d / %d / %d |" % (
              rm["exact_kind"], rm["direction_ok"], rm["direction_wrong"]),
          "| ось A Vitali против эталона (V5) | %s (из %d) |" % (res["semantic_accuracy"], res["semantic_n"]),
          "| REVIEW | %d |" % t["review"],
          "| сработали правила | %s |" % ", ".join("%s %d" % kv for kv in sorted(res["rules_fired"].items())), "",
          "## Чувствительность (не итог)", "", "| вариант | опасных | точность | охват |", "|---|---|---|---|"]
    for k, s in res["sensitivity"].items():
        L.append("| %s | %d | %s | %s |" % (k, s["dangerous_false_standalone"], s["routing_accuracy"],
                                            s["routing_coverage"]))
    L += ["", "## По слоям отбора (диагностика)", "",
          "| слой | n | опасных | точность | охват | сверхосторожно | REVIEW |", "|---|---|---|---|---|---|---|"]
    for n, m in res["layers"].items():
        L.append("| %s | %d | %d | %s | %s | %d из %d | %d |" % (n, m["n"], m["dangerous_false_standalone"],
                                                              m["routing_accuracy"], m["routing_coverage"],
                                                              m["overconservative"], m["ref_standalone"], m["review"]))
    L += ["", "## По предметам", "",
          "| предмет | слой | A Vitali / V5 / эталон | правило | V5 | эталон | родство эталона | улика |",
          "|---|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        mark = ("**ОПАСНО**" if r["rule_unit"] == "STANDALONE_RENDER" and r["ref_route"] in DANGEROUS else
                "" if r["rule_unit"] == "REVIEW" or r["ref_route"] == "open" else
                "да" if r["rule_unit"] == r["ref_route"] else "**нет**")
        L.append("| %s | %s/%s | %s / %s / %s | %s | %s %s | %s | %s %s | %s |" % (
            r["asset_id"], r["layer"], r["sub"], r["semantic_kind"], r["semantic_v5"], r["ref_semantic_kind"],
            r["rule"], r["rule_unit"], mark, r["ref_route"], r["ref_relation"], r["ref_relation_to"], r["why"]))
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
