#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ROUTING_RULES_V7 - заморозка и слепой holdout на 60 новых предметах (специалист 02.10, передал Vitali в чате). CPU.

Диагностика V7 на тех же 50 (routing-rules-v7-prep) - не приёмка: правила V7 и эталон v2 сделаны после ответов по
тем 50. Здесь V7 замораживается ДО отбора новых предметов, и после заморозки ничего не меняется до конца holdout -
ни правила, ни пороги, ни онтология. Замороженные V3 / V4_R1 / V5 и их папки только читаются.

Что заморожено (FREEZE.json): правила V7 и порядок всех правил (routing_rules_v7.route_v7 поверх V6_PREP_R2),
онтология v2 целиком (не истина архитектуры, а договорённость на этот holdout), R7t SAME_FRAME_ADJACENCY с порогом
0.75 как PROVISIONAL (requires_blind_validation), ANIMATION_FAMILY_COPY, FAMILY_RELATION_V2, правила MCD и статус
временных правил, определения STRONG / CANDIDATE, HANDOFF (EXCLUDE -> STRUCTURAL_PIPELINE / TERRAIN_PIPELINE / NONE),
ворота V7 и диагностика, слои отбора, копии входов и sha256 кода. PASS V7 - готовность routing layer, а не
downstream STRUCTURAL_PIPELINE.

Порядок (каждый шаг отказывается, если предыдущего нет или свой уже сделан):
    pools      до заморозки: только размеры пулов отбора на живых входах (содержимое не печатается)
    freeze     снимок (FREEZE.json, inputs/)
    select     60 предметов автоматически по слоям, зерно SEED: 12 родство / перекраска / вариант материала, 10 состояние
               по MCD, 10 кусок / составной / модуль, 10 поверхность конструкции (лестница, дверь, обшивка корпуса,
               крыша, панель, стена, кузов машины), 8 рельеф / исключаемое, 10 обычных одиночных. Исключены наборы
               разработки V3-V7 (всё, что было на карточках, holdout V4_R1 и V5 с роднёй), всё с решением человека;
               один предмет на набор PCK
    relations  замороженные детекторы на 60: relation_probe.discover и выходы детекторов маршрута V7 (связи MCD,
               улика поверхности, варианты цвета, подписи петель анимации, наборы оригинала) - и замок
    cards      страница: только ось A (онтология v2), final_identity и missing_context; маршрут не выбирается
    dossier    пакет независимого эталона: определения v2, картинки без панели семейства, в кандидатах родни все
               утверждения правил (любого уровня) плюс похожие, вперемешку и без источника
    lockref    заморозить эталон до ответов
    report     маршрут V7 из оси A и замороженных выходов детекторов, handoff, ворота V7, вердикт, диагностика
    check      все хэши целы

    py -3.13 tools/hdart/routing_holdout_v7.py pools|freeze|select|relations|cards|dossier|lockref|report|check
"""
import argparse
import json
import os
import re
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
import routing_rules as rr             # noqa: E402
import routing_rules_v6 as v6          # noqa: E402
import routing_rules_v7 as v7          # noqa: E402

ROOT = ir.ROOT
ENC = ir.ENC
OUT = os.path.join(ir.PROBES, "routing-holdout-v7")
SEED = "routing-holdout-v7-2026-10-02"
N_TOTAL = 60
INPUTS = dict(h5.INPUTS)
CODE = ["tools/hdart/routing_rules_v7.py", "tools/hdart/routing_rules_v6.py",
        "tools/hdart/routing_holdout_v7.py"] + list(h5.CODE)

LAYERS = (("relation", 12, (("fr2_new", 3), ("fr2_verified", 2), ("legacy_recolor", 2), ("material_variant", 2),
                            ("family_mirror", 2), ("family_open", 1))),
          ("mcd_state", 10, (("mcd_die", 3), ("mcd_alt", 2), ("mcd_anim", 2), ("mcd_dominance", 1),
                             ("mcd_candidate", 2))),
          ("part", 10, (("part_suspect", 3), ("part_words", 2), ("composite", 3), ("modular_words", 2))),
          ("structural", 10, (("stairs", 2), ("door", 1), ("hull", 2), ("roof", 1), ("panel", 1), ("wall", 2),
                              ("vehicle_body", 1))),
          ("terrain", 8, (("floor", 2), ("relief", 3), ("object_or_relief", 2), ("surface_mcd", 1))),
          ("standalone", 10, (("standalone", 10),)))
# поверхности конструкции - по тексту гипотез опознания (rh.texts: предложения моделей и прежнее описание), стена -
# ещё и по классу очереди (structural, «стена» в class_why); слова не правило маршрута, только способ найти кандидатов
STRUCT_RX = {
    "stairs": re.compile(r"\b(stairs?|staircase|stairway|steps|ladder)\b", re.I),
    "door": re.compile(r"\b(door|doors|doorway|gate|hatch|airlock)\b", re.I),
    "hull": re.compile(r"\b(hull|plating|fuselage|bulkhead|armou?red plat\w*)\b", re.I),
    "roof": re.compile(r"\b(roof|rooftop|roofing|shingles?)\b", re.I),
    "panel": re.compile(r"\b(solar|photovoltaic|control panel|wall panel|tech\w* panel|console panel|vent panel)\b",
                        re.I),
    "wall": re.compile(r"\b(wall|walls)\b", re.I),
    "vehicle_body": re.compile(r"\b(car|truck|van|bus|vehicle|lorry|jeep|wagon)\b[^.]{0,30}\b(body|side|hood|bonnet|"
                               r"bumper|chassis|door|panel)\b|\bbodywork\b", re.I)}
LAZY_FOUND, LAZY_SCAN = 40, 600        # ленивые пулы (вариант цвета, улика MCD): сколько найти / просмотреть по зерну

SEMANTIC = list(h5.SEMANTIC)
SEM_DEFS = dict(h5.SEM_DEFS, **v7.SEM_DEFS_V2)          # онтология v2 целиком
REF_ROUTES = list(h5.REF_ROUTES)
REF_RELATIONS = list(h5.REF_RELATIONS)

ROUTING = {
    "version": "V7",
    "precedence": ["R1", "R2", "S", "R5", "R6", "R7s", "R8a", "R7p", "R0v", "R0p->R7o", "R3a", "R3m", "R3", "R4",
                   "R4v", "R7", "R7r", "R7m", "R7a", "R7n", "R8", "R8->R7t", "R9"],
    "rules_v6": v6.__doc__.split("Правила V6 по порядку")[1].split("Пересчёт на 50")[0].strip(),
    "profile_r2": v6.__doc__.split("V6_PREP_R2 (специалист 02.10")[1].split("py -3.13")[0].strip(),
    "v7": v7.__doc__.split("Пять изменений специалиста:")[1].split("Ворота V7 к заморозке")[0].strip(),
    "opts": {k: (sorted(v) if isinstance(v, set) else v) for k, v in v7.V7_OPTS.items()},
    "origin_sets": "наборы TERRAIN оригинальных данных (%s) - замораживаются выходом детектора" % ", ".join(
        d.replace(os.sep, "/") for d in v6.ORIGIN_DIRS),
    "relation_unit": rr.RELATION_UNIT_HOLDOUT,
    "evidence_only": list(v6.EVIDENCE_ONLY)}
R7T = {"rule": "SAME_FRAME_ADJACENCY", "status": "PROVISIONAL", "requires_blind_validation": True,
       "adj_min": v7.ADJ_MIN, "min_places": 2, "only": "A = OBJECT и маршрут R8 -> REVIEW R7t; модуль и составной не "
       "утверждаются", "share": "max(вплотную по x, по y) / мест из inputs/touch.tsv снимка (нижняя граница)",
       "origin": "найден на 4 кадрах тех же 50 V5 - временный"}
ANIMATION_COPY = {"relation": v7.COPY, "level": "STRONG", "group": "animation", "exact": "ANIMATION_FRAME_OF",
                  "rule": "кадры в разных петлях анимации MCD, петли делят побайтно равный кадр (sha1 RGBA в палитре "
                          "World) -> перекраска и вариант цвета этой пары заменяются ANIMATION_FAMILY_COPY; маршрут "
                          "не меняет, в pair_pick перекраской не считается"}
FAMILY_RELATION = {"version": "FAMILY_RELATION_V2", "doc": fr2m.__doc__.strip(),
                   "direct_statuses": list(fr2m.DIRECT), "families_json_unchanged": True}
MCD = {"version": "MCD_STATE_RELATIONS + V6_PREP_R2", "doc": ms.__doc__.strip(),
       "shared_debris_min": ms.SHARED_DEBRIS_MIN, "dominant_min": ms.DOMINANT_MIN,
       "dominant_ratio": ms.DOMINANT_RATIO, "MCD_DOMINANCE_RULE": ms.MCD_DOMINANCE_RULE,
       "die": "авторитетно (V7 п.3): связь die STRONG mcd_state (одна-две основы, не общий обломок, не чаще основы) и "
              "не одна петля анимации; иначе REVIEW R7m; визуальное суждение эталона её не отменяет",
       "provisional": {"MCD_DOMINANCE_RULE": ms.MCD_DOMINANCE_RULE.get("status"), "R7t": "PROVISIONAL"}}
STRENGTH = {"STRONG": "маршрут меняет только STRONG-связь: MCD STRONG (anim, die с подтверждением), прямые строгие "
                      "рёбра FR2, связь детектора уровня STRONG, ANIMATION_FAMILY_COPY",
            "CANDIDATE": "всё остальное (варианты цвета find_variants, MCD CANDIDATE, перекраска CANDIDATE) - REVIEW "
                         "или улика, маршрута не даёт; точность - только диагностика"}
HANDOFF = {"map": v7.HANDOFF, "implemented": v7.HANDOFF_IMPLEMENTED,
           "none_reasons": [n for n, _rx in v7.NONE_REASON] + ["unknown"],
           "rule": "у каждого EXCLUDE обязан быть handoff_target; без цели - ERROR_UNASSIGNED (ворота). Конвейер не "
                   "построен - handoff_status NOT_IMPLEMENTED: downstream blocker, routing holdout он не валит"}
ONTOLOGY = {"version": "ONTOLOGY_V2", "semantic_kind": SEM_DEFS,
            "note": "заморожена на этот holdout; не истина архитектуры. LIGHTNIN_GR:15 не правится, GOVTDECOR:33 не "
                    "используется для настройки"}
BODY = ("routing", "r7t", "animation_copy", "family_relation", "relation_discovery", "mcd", "strength", "handoff",
        "ontology", "gates", "gate_defs", "diag_defs", "seed", "n_total", "layers", "struct_rx", "inputs_source",
        "inputs", "input_sha256", "code_sha256")
file_sha = rh.file_sha
pset = rh.pset


def p(out, name):
    return os.path.join(out, name)


def order(key):
    import hashlib
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
    body = {"routing": ROUTING, "r7t": R7T, "animation_copy": ANIMATION_COPY, "family_relation": FAMILY_RELATION,
            "relation_discovery": rh.RELATION_DISCOVERY, "mcd": MCD, "strength": STRENGTH, "handoff": HANDOFF,
            "ontology": ONTOLOGY, "gates": v7.GATES, "gate_defs": v7.GATE_DEFS, "diag_defs": v7.DIAG_DEFS,
            "seed": SEED, "n_total": N_TOTAL, "layers": [[n, q, [list(s) for s in sub]] for n, q, sub in LAYERS],
            "struct_rx": {k: rx.pattern for k, rx in STRUCT_RX.items()},
            "inputs_source": {k: v.replace(os.sep, "/") for k, v in inputs.items()},
            "inputs": snap, "input_sha256": {k: file_sha(v) for k, v in snap.items()},
            "code_sha256": {c: file_sha(c) for c in code}}
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                decided="специалист 02.10, передал Vitali в чате: handoff layer до заморозки (EXCLUDE остаётся, "
                        "handoff_target обязателен), overconservative - диагностика, ворота V7 как в GATES; freeze V7 -> "
                        "автоматически 60 новых -> lock detector outputs -> blind reference -> semantic-A answers -> "
                        "report без изменений правил. Acceptance V7 означает готовность routing layer, а не "
                        "готовность downstream STRUCTURAL_PIPELINE",
                rule="после заморозки ничего из этого не меняется до конца holdout")
    ir.dump_json(p(out, "FREEZE.json"), data)
    print("V7 заморожен (sha256 %s): входов %d, файлов кода %d" % (data["sha256"][:12], len(snap), len(code)))
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


def guard(d):
    ch = code_changed(d)
    if ch:
        raise SystemExit("код изменён после заморозки: %s" % ", ".join(ch))


live_same = h5.live_same


# ---------------------------------------------------------------- select

def exclusions(inp):
    """Наборы и ключи разработки V3-V7: rh.exclusions (всё, что было на карточках, пары V1, разобранные случаи,
    решения человека), holdout V4_R1 и V5 с роднёй (детектор, FR2, MCD, пары эталона), начало правила частоты."""
    ex_sets, ex_keys = rh.exclusions(inp)
    fr2 = fr2m.load(inp["family_relation_v2"])
    mcd = ms.index(ir.load_json(inp["mcd_state"])["relations"])
    for out in (rh.OUT, h5.OUT):
        ks = [x["asset_id"] for x in rh.load_holdout(out)["items"]]
        ex_keys |= {k.upper() for k in ks}
        ex_sets |= {pset(k) for k in ks}
        for k, rs in rh.load_relations(out).items():
            ex_sets |= {pset(r["relative"]) for r in rs}
        for k in ks:
            ex_sets |= {pset(e["relative"]) for e in fr2.get(k.upper(), [])}
            ex_sets |= {pset(x["relative"]) for x in mcd.get(k.upper(), [])}
        rp_ = p(out, "reference_pairs.tsv")
        if os.path.exists(rp_):
            ex_sets |= {pset(r["relative"]) for r in ir.read_tsv(rp_)}
    for r in ir.read_tsv(os.path.join(v7.REF_V2, "reference_pairs_v2.tsv")):
        ex_sets |= {pset(r["asset_id"]), pset(r["relative"])}
    ex_sets.add(ms.MCD_DOMINANCE_RULE["origin"].split(":")[0].upper())
    return ex_sets, ex_keys


def pools(inp, gen, ex_sets, ex_keys):
    """Кандидаты подслоёв {подслой: [(ключ, строка, заметка)]}: подслои V5 (h5.pools, без ленивого surface_mcd) плюс
    вариант цвета, поверхности конструкции по словам и улика поверхности MCD - ленивые по зерну V7."""
    import obj_struct as os_
    import relation_probe as rp
    import routing_rules_v5 as v5
    base = h5.pools(inp, gen, ex_sets, ex_keys, None)
    out = {s: list(base.get(s, [])) for _n, _q, sub in LAYERS for s, _m in sub}
    txt, why = rh.texts(inp), rh.class_why(inp)
    by_key = {}
    for r in gen:
        by_key.setdefault(r["key"].upper(), r)

    def ok(k):
        r = by_key.get(k.upper())
        return (r is not None and r["status"] != "SKIP" and pset(k) not in ex_sets and k.upper() not in ex_keys
                and r["asset_id"].upper() not in ex_keys)
    rows = [r for r in gen if ok(r["key"])]
    for r in rows:
        t = txt.get(r["asset_id"].upper(), "") or txt.get(r["key"].upper(), "")
        for name, rx in STRUCT_RX.items():
            m = rx.search(t)
            if m and not (name == "wall" and r["asset_class"] not in ("structural", "object")):
                out[name].append((r["key"], r, "слово «%s»" % m.group(0)))
        if r["asset_class"] == "structural" and why.get(r["key"].upper(), "").startswith("стена"):
            out["wall"].append((r["key"], r, why[r["key"].upper()]))
    # обычный одиночный V7: условия V5 без уверенности агентов в опознании (AGENT_PROPOSED и verdict agree) - на
    # живых входах их держали 5 кадров; опознание даёт ответ человека, а не очередь
    fam_size = Counter()
    for fam in ir.load_json(inp["families"]):
        fam_size[fam["family_id"].upper()] = len(fam.get("members", [])) + len(fam.get("review", []))
    fr2 = fr2m.load(inp["family_relation_v2"])
    mcd = ms.index(ir.load_json(inp["mcd_state"])["relations"])
    out["standalone"] = []
    for r in rows:
        t = txt.get(r["asset_id"].upper(), "")
        if (r["action"] == "GENERATE" and r["kind"] == "один" and r["relation"] in ("canonical", "")
                and set(b.split(":")[0] for b in r["blockers"].split()) <= {"identity"}
                and r["asset_class"] == "object" and fam_size.get(r["asset_id"].upper(), 1) <= 1
                and not rh.PART_RX.search(t) and not rh.MODULAR_RX.search(t)
                and not fr2.get(r["key"].upper()) and not mcd.get(r["key"].upper())):
            out["standalone"].append((r["key"], r, "обычный одиночный"))
    single = sorted((r for r in rows if r["action"] == "GENERATE" and r["kind"] == "один"),
                    key=lambda r: order("lazy|" + r["key"].upper()))
    ctx = rp.Ctx()
    st = os_.Struct(ctx.world)
    set_list, cache = v6.all_sets(ctx.world), {}
    for r in single[:LAZY_SCAN]:
        if len(out["material_variant"]) < LAZY_FOUND:
            vs = [v for v in v6.find_variants(ctx, r["key"], set_list, cache) if v["kind"] in v6.VARIANT]
            if vs:
                out["material_variant"].append((r["key"], r, "%s %s" % (vs[0]["kind"], vs[0]["relative"])))
        if len(out["surface_mcd"]) < LAZY_FOUND and r["asset_class"] == "object":
            lv, w = v5.surface_evidence(st, r["key"])
            if lv == "STRONG":
                out["surface_mcd"].append((r["key"], r, w))
    return out


def select(pool):
    """Слои по порядку, подслои по порядку, внутри - зерно V7; ключ один раз; набор PCK один раз на весь holdout.
    Недобор подслоя добирается следующими подслоями того же слоя по кругу - состав по слоям держится, подслой нет."""
    pick, short, used_sets, used_keys = [], {}, set(), set()

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

    for layer, q, sub in LAYERS:
        left = {name: iter(cands(name)) for name, _n in sub}
        got = Counter()
        for name, n in sub:
            while got[name] < n and take(layer, name, left[name]):
                got[name] += 1
            if got[name] < n:
                short[name] = "%d из %d (кандидатов %d)" % (got[name], n, len(cands(name)))
        while sum(got.values()) < q:                 # добор недостачи слоя
            moved = False
            for name, _n in sub:
                if sum(got.values()) >= q:
                    break
                if take(layer, name, left[name], " (добор слоя)"):
                    got[name] += 1
                    moved = True
            if not moved:
                short[layer] = "слой %d из %d" % (sum(got.values()), q)
                break
    pick.sort(key=lambda x: order("card|" + x["asset_id"].upper()))
    return pick, short


def do_pools(out=OUT):
    """До заморозки: размеры пулов на живых входах - проверить, что слои вообще наполнимы. Содержимое не печатается."""
    if os.path.exists(p(out, "FREEZE.json")):
        raise SystemExit("уже заморожено - пулы смотрит select")
    inp = dict(INPUTS)
    gen = ir.read_tsv(inp["generation"])
    ex_sets, ex_keys = exclusions(inp)
    pool = pools(inp, gen, ex_sets, ex_keys)
    print("исключено наборов %d, ключей %d" % (len(ex_sets), len(ex_keys)))
    for layer, q, sub in LAYERS:
        print("%-11s %2d: %s" % (layer, q, ", ".join("%s %d/%d" % (s, len({x[0].upper() for x in pool[s]}), m)
                                                      for s, m in sub)))
    _items, short = select(pool)
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
    pool = pools(inp, gen, ex_sets, ex_keys)
    items, short = select(pool)
    data = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"], "seed": SEED,
            "n": len(items), "pool": {k: len(v) for k, v in pool.items()}, "short": short,
            "excluded_sets": sorted(ex_sets), "excluded_keys_n": len(ex_keys), "sha256": rh.digest(items),
            "items": items, "rule": "список заморожен до ответов и эталона; слой в карточку не идёт"}
    ir.dump_json(p(out, "holdout.json"), data)
    print("отобрано %d (sha256 %s): %s" % (len(items), data["sha256"][:12], dict(Counter(x["layer"] for x in items))))
    print("недобор:", short or "нет")
    return data


def load_holdout(out=OUT):
    return rh.load_holdout(out)


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


def load_relations(out=OUT):
    return rh.load_relations(out)


def load_detectors(out=OUT):
    lk = ir.load_json(p(out, "relations.lock.json"))
    if file_sha(lk["detectors_path"]) != lk["detectors_sha256"]:
        raise SystemExit("detectors.json изменён после заморозки")
    return ir.load_json(lk["detectors_path"])


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
    page = (rh.PAGE_V.replace(title, "Holdout маршрута V7: %d новых предметов" % len(cards))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__MISS__", json.dumps(ic.MISSING)).replace("__SEM__", json.dumps(SEMANTIC))
            .replace("__DEFS__", json.dumps({"semantic_kind": SEM_DEFS}, ensure_ascii=False))
            .replace("__KEY__", "routing-holdout-v7-" + h["sha256"][:8]))
    with open(p(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    ir.dump_json(p(out, "cards.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "holdout_sha256": h["sha256"], "img_sha256": ir.img_digest(p(out, "img")),
                                        "assets": [c["asset"] for c in cards], "cards": data})
    rel = os.path.relpath(os.path.abspath(out), os.path.abspath(os.path.join("art", "objects", "generation")))
    print("карточек %d; страница: http://localhost:8778/%s/index.html" % (len(cards), rel.replace(os.sep, "/")))


# ---------------------------------------------------------------- подготовка маршрута из замков

def prepared(out, d, h):
    inp = dict(d["inputs"])
    inp["relations"] = rh.load_json_path(out)
    keys = [x["asset_id"] for x in h["items"]]
    return inp, keys, v7.prepare(load_detectors(out), inp, keys)


# ---------------------------------------------------------------- пакет эталона

def do_dossier(out=OUT):
    d, h = load_freeze(out), load_holdout(out)
    live_same(d)
    if os.path.exists(p(out, "reference.lock.json")):
        raise SystemExit("эталон уже заморожен - пакет не перестраивается")
    rels = load_relations(out)
    inp, keys, pr = prepared(out, d, h)
    cj = ir.load_json(p(out, "cards.json"))
    pack = p(out, "reference_pack")
    os.makedirs(p(pack, "img"), exist_ok=True)
    fr2 = fr2m.load(inp["family_relation_v2"])
    raw, _dropped, _conv = v7.claims_of(pr, keys, rels, fr2)
    idx = ms.index(pr["by_set"])
    must = {}
    for k, rel_to, *_ in raw:
        must.setdefault(k, set()).add(rel_to)
    for k in keys:
        for e in fr2.get(k.upper(), []):
            must.setdefault(k, set()).add(e["relative"])          # и LEGACY_RELATION
        for c in rels.get(k, []):
            must.setdefault(k, set()).add(c["relative"])          # и FIXED_NEIGHBOUR
        for x in idx.get(k.upper(), []):
            must.setdefault(k, set()).add(x["relative"])          # MCD любого уровня
        for v in pr["variants"].get(k, []):
            must.setdefault(k, set()).add(v["relative"])          # варианты цвета (CANDIDATE)
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
    spec = {"semantic_kind": SEM_DEFS, "ontology": "ONTOLOGY_V2", "ref_routes": REF_ROUTES, "render_unit": dict(
        ir.SPEC["render_unit"], ANIMATION_FAMILY="кадр анимации другого кадра (фаза петли): общий облик и опознание "
                                                 "с основой; не разрушенный вид и не перекраска"),
            "precedence": ir.SPEC["precedence"], "ref_relations": REF_RELATIONS,
            "ref_relation_note": "ANIMATION_FRAME_OF - фаза анимации (в том числе петля, скопированная между "
                                 "наборами); STATE_VARIANT_OF - другое состояние той же вещи (разрушенная, открытая); "
                                 "недоказанное - OPEN, сходство истиной не делается"}
    ir.dump_json(p(pack, "dossier.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                           "holdout_sha256": h["sha256"], "items": entries, "spec_v7": spec})
    with open(p(out, "reference.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(rh.REF_HEAD) + "\n" + "".join(e["asset_id"] + "\t" * (len(rh.REF_HEAD) - 1) + "\n"
                                                        for e in entries))
    with open(p(out, "reference_pairs.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(rh.PAIR_HEAD) + "\n" + "".join("%s\t%s\t\t\t\n" % (a, b) for a, b in pairs))
    print("пакет эталона: %d предметов, пар %d (утверждений и связей правил в них %d) -> %s" % (
        len(entries), len(pairs), sum(len(v) for v in must.values()), pack))


# ---------------------------------------------------------------- эталон и отчёт

check_reference = h5.check_reference


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
    inp, keys, pr = prepared(out, d, h)
    layer = {x["asset_id"]: x for x in h["items"]}
    bad = ["%s: нет ответа" % a for a in keys if a not in ans]
    bad += ["%s: semantic_kind '%s'" % (a, ans[a].get("semantic_kind")) for a in keys
            if a in ans and ans[a].get("semantic_kind") not in SEMANTIC]
    bad += check_reference(ref, refp, keys)
    umap = d["routing"]["relation_unit"]
    fr2 = fr2m.load(inp["family_relation_v2"])
    rows = v7.build_rows(pr, keys, layer, ans, ref, umap)
    for r in rows:
        r["final_identity"] = ans.get(r["asset_id"], {}).get("final_identity", "")
        r["truth_identity"] = ref.get(r["asset_id"], {}).get("truth_identity", "")
        r["ref_relation"] = ref.get(r["asset_id"], {}).get("ref_relation") or "OPEN"
        r["ref_relation_to"] = ref.get(r["asset_id"], {}).get("ref_relation_to", "")
    tot = v7.metrics(rows)
    raw, dropped, conv = v7.claims_of(pr, keys, rels, fr2)
    claims = v7.score(raw, refp)
    ps = v7.precision_split(claims)
    rows_no_r7t = v7.build_rows(pr, keys, layer, ans, ref, umap, adjacency=False)
    checks = v7.gate_checks(tot, ps, rows, d["gates"])
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "freeze_sha256": d["sha256"], "holdout_sha256": h["sha256"],
           "reference_locked": lk["created"], "answers_present_at_ref_lock": lk["answers_present_at_lock"],
           "verdict": v7.verdict(checks), "checks": checks, "gates": d["gates"], "total": tot, "relations": ps,
           "diagnostics": v7.diagnostics(rows, claims, rows_no_r7t),
           "by_source": {s: v6.precision([c for c in claims if c["source"] == s])
                         for s in sorted({c["source"] for c in claims})},
           "layers": {n: v7.metrics([r for r in rows if r["layer"] == n]) for n, _q, _s in LAYERS},
           "layers_open_standalone": {n: sum(r["rule_unit"] == "STANDALONE_RENDER" and r["ref_route"] == "open"
                                             for r in rows if r["layer"] == n) for n, _q, _s in LAYERS},
           "sensitivity": {"V7 без R7t": v7.metrics(rows_no_r7t)},
           "rules_fired": dict(Counter(r["rule"] for r in rows)), "anim_copy_route": pr["conv_route"],
           "anim_copy_claims": conv, "dropped": dropped, "invalid": bad, "claims": claims, "rows": rows,
           "note": "PASS V7 - готовность routing layer, не downstream STRUCTURAL_PIPELINE / TERRAIN_PIPELINE"}
    ir.dump_json(p(out, "report.json"), res)
    v7.write_handoff(p(out, "handoff.tsv"), rows)
    write_md(out, res)
    return res


def write_md(out, res):
    yes = {True: "да", False: "**нет**", None: "нет данных"}
    t, ps = res["total"], res["relations"]

    def pr_(x):
        return "%s (%d/%d)" % (x["relation_precision"], x["ok"], x["closed"])
    L = ["# ROUTING_RULES_V7 - слепой holdout: %s" % res["verdict"], "",
         "снимок %s, holdout %s; ось A - ответы, эталон - независимый (заморожен %s%s)." % (
             res["freeze_sha256"][:12], res["holdout_sha256"][:12], res["reference_locked"],
             ", ответы уже были" if res["answers_present_at_ref_lock"] else ", до ответов"),
         res["note"] + ".", "", "## Ворота", "", "| ворота | значение | пройдено |", "|---|---|---|"]
    h = res["diagnostics"]["handoff"]
    vals = [str(t["dangerous_false_standalone"]),                       # порядок - как в v7.gate_checks
            "%s (%d/%d)" % (t["routing_accuracy"], t["correct"], t["decided"]),
            "%s (%d/%d)" % (t["routing_coverage"], t["decided"], t["ref_closed"]),
            "STRONG %s; CANDIDATE %s (диагностика)" % (pr_(ps["strong"]), pr_(ps["candidate"])),
            "%d из %d EXCLUDE" % (h["handoff_unassigned"], h["excluded_total"]),
            ", ".join("%s %d" % (n, m["dangerous_false_standalone"]) for n, m in res["layers"].items())]
    for (k, v), val in zip(res["checks"].items(), vals):
        L.append("| %s | %s | %s |" % (k, val, yes[v]))
    L += ["", "Вердикт: **%s**." % res["verdict"], ""]
    L += v7.diag_md(res["diagnostics"])
    L += ["Манифест передачи - handoff.tsv.", "", "## Утверждения по источникам", "",
          "| источник | утверждений | закрыто | верно | точность |", "|---|---|---|---|---|"]
    for s, x in res["by_source"].items():
        L.append("| %s | %d | %d | %d | %s |" % (s, x["claims"], x["closed"], x["ok"], x["relation_precision"]))
    L += ["", "## По слоям отбора", "",
          "| слой | n | опасных | точность | охват | сверхосторожно | REVIEW | одиночных при эталоне open |",
          "|---|---|---|---|---|---|---|---|"]
    for n, m in res["layers"].items():
        L.append("| %s | %d | %d | %s | %s | %d из %d | %d | %d |" % (
            n, m["n"], m["dangerous_false_standalone"], m["routing_accuracy"], m["routing_coverage"],
            m["overconservative"], m["ref_standalone"], m["review"], res["layers_open_standalone"][n]))
    s = res["sensitivity"]["V7 без R7t"]
    L += ["", "Чувствительность (не итог): V7 без R7t - опасных %d, точность %s, охват %s." % (
        s["dangerous_false_standalone"], s["routing_accuracy"], s["routing_coverage"]),
          "Сработали правила: %s." % ", ".join("%s %d" % kv for kv in sorted(res["rules_fired"].items())), "",
          "## По предметам", "",
          "| предмет | слой | A / вид V7 / эталон | правило | V7 | эталон | исход | handoff | почему |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        L.append("| %s | %s/%s | %s / %s / %s | %s | %s | %s | %s | %s | %s |" % (
            r["asset_id"], r["layer"], r["sub"], r["semantic_kind"], r["semantic_v6"], r["ref_semantic_kind"],
            r["rule"], r["rule_unit"], r["ref_route"], v6.outcome(r),
            ("%s %s" % (r["handoff_target"] or "UNASSIGNED", r["handoff_status"])) if r["rule_unit"] == "EXCLUDE"
            else "", r["why"]))
    if res["invalid"]:
        L += ["", "Ошибки в ответах или эталоне: " + "; ".join(res["invalid"])]
    with open(p(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:20]))


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
        load_detectors(out)
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
