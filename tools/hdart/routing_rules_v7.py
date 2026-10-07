#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ROUTING_RULES_V7_PREP - правила V7 поверх V6_PREP_R2 и диагностический пересчёт на тех же 50 (специалист 02.10). CPU.

Слепые итоги V5 и пересчёты V6-prep / R2 не трогаются: V7 - отдельный модуль, holdout V5 только читается, код
V6 (routing_rules_v6.py) не меняется и вызывается как есть. Пять изменений специалиста:

1. Онтология v2 (ONTOLOGY_V2, SEM_DEFS_V2): лестницы, ступени, обшивка корпуса/машины, солнечные панели и иные
   встроенные поверхности конструкции - STRUCTURAL_SURFACE; OBJECT_PART - часть дискретного предмета, машины,
   мебели, механизма или существа, не встроенная поверхность. Правила маршрута это не меняет: меняется эталон.
   Эталон по онтологии v2 (probes/reference-ontology-v2/reference_v2.tsv) размечен независимым слепым судьёй по
   кадрам на границе поверхность / часть; старый слепой результат не пересчитывается как официальный PASS.
2. SAME_FRAME_ADJACENCY (PROVISIONAL): A = OBJECT, кадр стоит вплотную к своей копии не меньше чем в ADJ_MIN
   (0.75) мест на картах -> REVIEW (R7t) вместо одиночного заказа. Только улика: ни COMPOSITE_PART, ни
   STRUCTURAL_MODULAR не утверждает. Порог найден на тех же 50 (4 кадра) - временный.
   Доля мест: max(вплотную по x, по y) / мест, из inputs/touch.tsv снимка holdout (нижняя граница доли).
3. Разрушение по MCD - авторитетно: die STRONG (как R2: одна-две основы, не общий обломок, не одна петля
   анимации) - сильная связь состояния; визуальное суждение эталона её не отменяет
   (REFERENCE_CONFLICT_WITH_AUTHORITATIVE_MCD в reference_pairs_v2.tsv). Правила - как в R2.
4. Сила связи разведена. Маршрут меняет только STRONG-связь; CANDIDATE - REVIEW или улика (в коде V6 уже так:
   R4v, R7o, R7r дают REVIEW, R4 зеркало - только сильное зеркало семейства; держит тест). Точность родства -
   отдельно: relation_precision_strong (жёсткий порог >= 0.95) и relation_precision_candidate (только диагностика).
5. ANIMATION_FAMILY_COPY раньше перекраски: кадры X и Y в РАЗНЫХ петлях анимации MCD, и в петлях есть пара
   побайтно равных кадров (RGBA в палитре World) - петля скопирована между наборами. Перекраска и вариант
   цвета между такими кадрами заменяются связью ANIMATION_FAMILY_COPY (STRONG, группа animation). Маршрут она не
   меняет (направление не доказано), в pair_pick перекраской не считается.

6. HANDOFF (специалист 02.10, до заморозки): маршрут EXCLUDE остаётся (словарь и эталоны не ломаются), но у каждого
   EXCLUDE обязан быть второй результат handoff_target: STRUCTURAL_SURFACE -> STRUCTURAL_PIPELINE, TERRAIN_RELIEF ->
   TERRAIN_PIPELINE, NOT_OBJECT -> NONE (с причиной effect / decal / non-renderable / unknown). EXCLUDE без цели -
   ERROR_UNASSIGNED, ворота handoff_unassigned = 0. Конвейеры стен и рельефа ещё не построены: handoff_status
   NOT_IMPLEMENTED - downstream blocker, routing holdout он не валит. Манифест передачи - handoff.tsv.

Ворота V7 к заморозке (GATES, специалист 02.10): опасных 0; точность маршрута >= 0.90; охват >= 0.70; точность
родства STRONG >= 0.95 при >= 10 закрытых (меньше - INSUFFICIENT_SAMPLE, не PASS); handoff_unassigned = 0; опасных 0
в каждом слое с закрытым эталоном. Сверхосторожность (0.15) - только диагностика, как и всё в DIAG_DEFS. PASS V7 -
готовность routing layer, не downstream STRUCTURAL_PIPELINE. GOVTDECOR:33 честно спорный - не для настройки.

    py -3.13 tools/hdart/routing_rules_v7.py recount      -> routing-rules-v7-prep/recount.md / .json
"""
import argparse
import csv
import hashlib
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402
import mcd_state as ms                 # noqa: E402
import routing_holdout as rh           # noqa: E402
import routing_rules as rr             # noqa: E402
import routing_rules_v6 as v6          # noqa: E402

OUT = os.path.join(ir.PROBES, "routing-rules-v7-prep")
HOLDOUT = v6.HOLDOUT
REF_V2 = os.path.join(ir.PROBES, "reference-ontology-v2")
CODE = ("tools/hdart/routing_rules_v7.py", "tools/hdart/routing_rules_v6.py")
ADJ_MIN = 0.75
CONTESTED = ("GOVTDECOR:33",)
TARGETS = {"dangerous_false_standalone_max": 0, "routing_accuracy_min": 0.90, "routing_coverage_min": 0.70,
           "relation_precision_strong_min": 0.95}
SEM_DEFS_V2 = {
    "STRUCTURAL_SURFACE": "стена, пол, крыша, дверь, лестница, ступени, архитектурная панель, обшивка корпуса/машины, "
                          "солнечная панель или иная встроенная поверхность, которая является частью конструкции и не "
                          "является самостоятельным предметом",
    "OBJECT_PART": "часть дискретного предмета, машины, мебели, механизма или существа, которая не является "
                   "встроенной поверхностью/обшивкой конструкции"}
COPY = "ANIMATION_FAMILY_COPY"
CLAIM_GROUP = dict(v6.CLAIM_GROUP, **{COPY: "animation"})
CLAIM_EXACT = dict(v6.CLAIM_EXACT, **{COPY: ("ANIMATION_FRAME_OF",)})
COLOR_KINDS = v6.RECOLOR + v6.VARIANT
V7_OPTS = dict(v6.R2_OPTS, adjacency=True, adj_min=ADJ_MIN)


# ---------------------------------------------------------------- 2. SAME_FRAME_ADJACENCY

def touch_share(path):
    """Ключ (заглавными) -> (мест, доля мест вплотную к своей копии)."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        next(rd)
        for r in rd:
            n, x, y = int(r[1]), int(r[2]), int(r[3])
            out[r[0].upper()] = (n, round(max(x, y) / n, 3) if n else 0.0)
    return out


def adjacency_hit(a, sk, adj, lim=ADJ_MIN):
    n, share = adj.get(a.upper(), (0, 0.0))
    return sk == "OBJECT" and n >= 2 and share >= lim, n, share


# ---------------------------------------------------------------- 5. ANIMATION_FAMILY_COPY

def loops(groups):
    """Основа петли -> список кадров петли (по anim_groups V6)."""
    out = {}
    for k, b in groups.items():
        out.setdefault(b, []).append(k)
    return out


class Pixels:
    """Подпись кадра - sha1 RGBA в палитре World (побайтное равенство кадров одной палитры)."""

    def __init__(self, ctx):
        self.ctx, self.cache = ctx, {}

    def sig(self, key):
        k = key.upper()
        if k not in self.cache:
            try:
                im = self.ctx.rgba(k)
            except (Exception, SystemExit):     # noqa: BLE001
                im = None
            self.cache[k] = None if im is None else hashlib.sha1(
                str(im.shape).encode() + im.tobytes()).hexdigest()
        return self.cache[k]


def anim_copy(groups, members, sig, a, b):
    """(да, почему): a и b в разных петлях MCD, и петли делят побайтно равный кадр."""
    ga, gb = groups.get(a.upper()), groups.get(b.upper())
    if ga is None or gb is None or ga == gb:
        return False, ""
    sb = {}
    for k in members.get(gb, []):
        s = sig(k)
        if s:
            sb.setdefault(s, k)
    for k in members.get(ga, []):
        s = sig(k)
        if s and s in sb:
            return True, "петля %s и петля %s делят кадр: %s == %s" % (ga, gb, k, sb[s])
    return False, ""


def convert_rels(rels, groups, members, sig):
    """Копия rels: перекраска/вариант между кадрами скопированной петли -> ANIMATION_FAMILY_COPY STRONG."""
    out, conv = {}, []
    for k, lst in (rels or {}).items():
        new = []
        for c in lst:
            if c["kind"] in COLOR_KINDS:
                ok, why = anim_copy(groups, members, sig, k, c["relative"])
                if ok:
                    c = dict(c, kind=COPY, level="STRONG", was=c["kind"], copy_why=why)
                    conv.append([k, c["relative"], c["was"], why])
            new.append(c)
        out[k] = new
    return out, conv


def claims_v7(keys, rels, mlinks, fr2, variants, groups, members, sig):
    """Утверждения V6 (claims_v6), затем перекраска/вариант скопированной петли -> ANIMATION_FAMILY_COPY."""
    raw, dropped = v6.claims_v6(keys, rels, mlinks, fr2, variants, groups)
    out, seen, conv = [], set(), []
    for k, rel_to, kind, level, side, src in raw:
        if kind in COLOR_KINDS:
            ok, why = anim_copy(groups, members, sig, k, rel_to)
            if ok:
                conv.append([k, rel_to, kind, src, why])
                kind, level, side, src = COPY, "STRONG", "open", "anim_copy"
        key = (k.upper(), rel_to.upper(), CLAIM_GROUP[kind])
        if key in seen:
            continue
        seen.add(key)
        out.append((k, rel_to, kind, level, side, src))
    return out, dropped, conv


def score(raw, refp):
    ref = {(r["asset_id"].upper(), r["relative"].upper()): r for r in refp}
    out = []
    for k, rel_to, kind, level, side, src in raw:
        r = ref.get((k.upper(), rel_to.upper()))
        rel = (r or {}).get("ref_pair_relation") or "OPEN"
        st = "open" if rel == "OPEN" else ("ok" if v6.REF_GROUP.get(rel) == CLAIM_GROUP[kind] else "wrong")
        out.append({"asset_id": k, "relative": rel_to, "kind": kind, "level": level, "side": side, "source": src,
                    "ref": rel, "direction": (r or {}).get("direction") or "open", "status": st,
                    "exact": rel in CLAIM_EXACT[kind], "judged": r is not None})
    return out


def precision_split(claims):
    """4. Общая точность, STRONG (жёсткий порог) и CANDIDATE (диагностика) раздельно."""
    strong = [c for c in claims if c["level"] == "STRONG"]
    cand = [c for c in claims if c["level"] != "STRONG"]
    return {"all": v6.precision(claims), "strong": v6.precision(strong), "candidate": v6.precision(cand)}


# ---------------------------------------------------------------- маршрут

def route_v7(a, sk, meta, mlinks, surf, variants, unit_map, opts, adj):
    """Маршрут R2 (route_v6 с R2_OPTS) и 2: одиночный заказ R8 при доле мест вплотную к копии -> REVIEW R7t."""
    o = dict(V7_OPTS, **(opts or {}))
    vo = {k: v for k, v in o.items() if k in v6.DEFAULT_OPTS}
    u, rule, why, kind, pick = v6.route_v6(a, sk, meta, mlinks, surf, variants, unit_map, vo)
    if o["adjacency"] and rule == "R8":
        hit, n, share = adjacency_hit(a, sk, adj, o["adj_min"])
        if hit:
            return ("REVIEW", "R7t", "PROVISIONAL: вплотную к своей копии %.2f мест (%d) - может быть модулем или "
                    "составным, одиночный заказ не доказан" % (share, n), kind, False)
    return u, rule, why, kind, pick


# ---------------------------------------------------------------- HANDOFF (специалист 02.10, до заморозки)

HANDOFF = {"STRUCTURAL_SURFACE": "STRUCTURAL_PIPELINE", "TERRAIN_RELIEF": "TERRAIN_PIPELINE", "NOT_OBJECT": "NONE"}
HANDOFF_IMPLEMENTED = {"STRUCTURAL_PIPELINE": False, "TERRAIN_PIPELINE": False}     # downstream, не routing
NONE_REASON = (("effect", r"\b(effect|smoke|fire|flame|spark|explosion|blast|glow|light beam|steam)\b"),
               ("decal", r"\b(decal|stain|blood|mark|graffiti|puddle|scorch|crack)\b"),
               ("non-renderable", r"\b(blank|empty|placeholder|service|invisible|transparent|marker|debug)\b"))


def handoff(unit, kind, identity=""):
    """Второй результат маршрута EXCLUDE: куда кадр передаётся. EXCLUDE без цели - ошибка, кадр не пропадает тихо.
    (target, status, reason); не EXCLUDE - пустые строки."""
    import re
    if unit != "EXCLUDE":
        return "", "", ""
    t = HANDOFF.get(kind)
    if t is None:
        return "", "ERROR_UNASSIGNED", "EXCLUDE при оси %s - цели нет" % (kind or "-")
    if t == "NONE":
        why = next((n for n, rx in NONE_REASON if re.search(rx, identity or "", re.I)), "unknown")
        return t, "NO_RENDER", why
    return t, ("IMPLEMENTED" if HANDOFF_IMPLEMENTED.get(t) else "NOT_IMPLEMENTED"), kind


def handoff_counts(rows):
    ex = [r for r in rows if r["rule_unit"] == "EXCLUDE"]
    return {"excluded_total": len(ex),
            "handoff_structural": sum(r["handoff_target"] == "STRUCTURAL_PIPELINE" for r in ex),
            "handoff_terrain": sum(r["handoff_target"] == "TERRAIN_PIPELINE" for r in ex),
            "handoff_none": sum(r["handoff_target"] == "NONE" for r in ex),
            "handoff_unassigned": sum(not r["handoff_target"] for r in ex),
            "handoff_target_not_implemented": sum(r["handoff_status"] == "NOT_IMPLEMENTED" for r in ex),
            "handoff_queue_object_class": sum(r.get("queue_class") == "object" for r in ex
                                              if r["handoff_target"] in ("STRUCTURAL_PIPELINE", "TERRAIN_PIPELINE"))}


# ---------------------------------------------------------------- ворота и диагностика V7 (замораживаются)

GATES = {"dangerous_false_standalone_max": 0, "routing_accuracy_min": 0.90, "routing_coverage_min": 0.70,
         "relation_precision_strong_min": 0.95, "relation_strong_closed_min": 10, "handoff_unassigned_max": 0,
         "dangerous_per_layer_max": 0}
GATE_DEFS = {
    "dangerous_false_standalone": "маршрут STANDALONE_RENDER при закрытом ref_route из DANGEROUS (COMPOSITE_PART, "
                                  "STRUCTURAL_MODULAR, STATE_VARIANT, DERIVED, EXCLUDE, ANIMATION_FAMILY); все кадры",
    "routing_accuracy": "верно / решено: закрытый ref_route, маршрут не REVIEW",
    "routing_coverage": "решено (не REVIEW) / закрытых ref_route",
    "relation_precision_strong": "утверждения уровня STRONG (MCD STRONG, FR2 прямые строгие, детектор STRONG, "
                                 "ANIMATION_FAMILY_COPY): верно / закрытых эталоном пар; закрытых меньше %d - "
                                 "INSUFFICIENT_SAMPLE, не PASS" % GATES["relation_strong_closed_min"],
    "handoff_unassigned": "EXCLUDE без handoff_target; обязан быть 0 (инвариант)",
    "dangerous_per_layer": "опасные по каждому слою отбора, где есть закрытый ref_route; рядом - STANDALONE при "
                           "ref_route open (не опасные по определению, но и не доказанные)",
    "verdict": "FAIL - любая ворота нет; INSUFFICIENT_SAMPLE - остальные да, а STRONG закрытых мало; PASS - все да. "
               "PASS означает готовность routing layer, не downstream STRUCTURAL_PIPELINE / TERRAIN_PIPELINE"}
DIAG_DEFS = {
    "overconservative_rate": "из ref_route STANDALONE_RENDER - доля ушедших в другой маршрут или REVIEW (не ворота)",
    "unnecessary_review": "REVIEW при закрытом ref_route: число и доля от закрытых; отдельно при ref_route "
                          "STANDALONE_RENDER - число и доля от одиночных по эталону",
    "relation_precision_candidate": "утверждения не STRONG - только диагностика",
    "semantic_axis_accuracy": "ось A ответов против ref_semantic_kind (онтология v2), UNSURE и open вне знаменателя",
    "structural_surface_accuracy": "кадры с ref_semantic_kind STRUCTURAL_SURFACE: ось A ответа = STRUCTURAL_SURFACE "
                                   "(semantic) и маршрут = ref_route среди решённых (route)",
    "r7t": "triggered - сработал R7t; helped - ref_route закрыт и опасен (без R7t был бы опасный одиночный); "
           "unnecessary - ref_route STANDALONE_RENDER (одиночный был верен, проверка лишняя); unresolved - ref_route "
           "open; hurt - потеря охвата от R7t в долях и сменила ли она ворота охвата (coverage_gate_flipped)",
    "mcd": "точность утверждений mcd_anim и mcd_die отдельно",
    "animation_family_copy": "точность утверждений anim_copy",
    "handoff": "excluded_total, handoff_structural / terrain / none / unassigned, handoff_target_not_implemented, "
               "handoff_queue_object_class (передано в конвейер, а очередь держит кадр предметом)"}


def metrics(rows):
    return v6.metrics(rows)


def strong_gate(ps, g=GATES):
    s = ps["strong"]
    if s["closed"] < g["relation_strong_closed_min"]:
        return None
    return s["relation_precision"] >= g["relation_precision_strong_min"]


def gate_checks(tot, ps, rows, g=GATES):
    def ge(v, lim):
        return None if v is None else v >= lim
    lay = {}
    for r in rows:
        lay.setdefault(r.get("layer", "-"), []).append(r)
    per = {n: metrics(rs)["dangerous_false_standalone"] for n, rs in lay.items()
           if any(r["ref_route"] != "open" for r in rs)}
    return {"опасных = 0": tot["dangerous_false_standalone"] <= g["dangerous_false_standalone_max"],
            "точность маршрута >= %.2f" % g["routing_accuracy_min"]: ge(tot["routing_accuracy"], g["routing_accuracy_min"]),
            "охват >= %.2f" % g["routing_coverage_min"]: ge(tot["routing_coverage"], g["routing_coverage_min"]),
            "родство STRONG >= %.2f при >= %d закрытых" % (g["relation_precision_strong_min"],
                                                         g["relation_strong_closed_min"]): strong_gate(ps, g),
            "handoff_unassigned = 0": handoff_counts(rows)["handoff_unassigned"] <= g["handoff_unassigned_max"],
            "опасных = 0 в каждом слое": all(v <= g["dangerous_per_layer_max"] for v in per.values())}


def verdict(checks):
    v = list(checks.values())
    if False in v:
        return "FAIL"
    strong = [x for k, x in checks.items() if k.startswith("родство STRONG")]
    if strong and strong[0] is None and None not in [x for k, x in checks.items() if not k.startswith("родство")]:
        return "INSUFFICIENT_SAMPLE"
    return "PASS" if None not in v else "NOT_DECIDED"


def diagnostics(rows, claims, rows_no_r7t=None):
    rate = v6.rh.rate
    closed = [r for r in rows if r["ref_route"] != "open"]
    alone = [r for r in rows if r["ref_route"] == "STANDALONE_RENDER"]
    rev_c = [r for r in closed if r["rule_unit"] == "REVIEW"]
    rev_a = [r for r in alone if r["rule_unit"] == "REVIEW"]
    sem = [r for r in rows if r["semantic_kind"] not in ("UNSURE", "") and r["ref_semantic_kind"] != "open"]
    ss = [r for r in rows if r["ref_semantic_kind"] == "STRUCTURAL_SURFACE"]
    ss_dec = [r for r in ss if r["ref_route"] != "open" and r["rule_unit"] != "REVIEW"]
    r7 = [r for r in rows if r["rule"] == "R7t"]
    tot = metrics(rows)
    out = {"overconservative_rate": tot["overconservative_rate"], "overconservative": tot["overconservative"],
           "ref_standalone": tot["ref_standalone"],
           "unnecessary_review": {"count": len(rev_c), "rate": rate(len(rev_c), len(closed)),
                                  "standalone_count": len(rev_a), "standalone_rate": rate(len(rev_a), len(alone))},
           "semantic_axis_accuracy": rate(sum(r["semantic_kind"] == r["ref_semantic_kind"] for r in sem), len(sem)),
           "semantic_n": len(sem),
           "structural_surface_accuracy": {
               "n": len(ss), "semantic": rate(sum(r["semantic_kind"] == "STRUCTURAL_SURFACE" for r in ss), len(ss)),
               "route": rate(sum(r["rule_unit"] == r["ref_route"] for r in ss_dec), len(ss_dec)),
               "route_decided": len(ss_dec)},
           "r7t": {"triggered": len(r7),
                   "helped": sum(r["ref_route"] in v6.DANGEROUS for r in r7),
                   "unnecessary": sum(r["ref_route"] == "STANDALONE_RENDER" for r in r7),
                   "unresolved": sum(r["ref_route"] == "open" for r in r7),
                   "assets": [[r["asset_id"], r["ref_route"]] for r in r7]},
           "mcd": {"animation": v6.precision([c for c in claims if c["source"] == "mcd_anim"]),
                   "die": v6.precision([c for c in claims if c["source"] == "mcd_die"])},
           "animation_family_copy": v6.precision([c for c in claims if c["source"] == "anim_copy"]),
           "handoff": handoff_counts(rows)}
    if rows_no_r7t is not None:
        t0 = metrics(rows_no_r7t)
        lim = GATES["routing_coverage_min"]
        out["r7t"]["hurt"] = {"coverage_without": t0["routing_coverage"], "coverage_with": tot["routing_coverage"],
                              "coverage_cost": None if t0["routing_coverage"] is None or tot["routing_coverage"] is None
                              else round(t0["routing_coverage"] - tot["routing_coverage"], 3),
                              "coverage_gate_flipped": bool(t0["routing_coverage"] is not None and
                                                            t0["routing_coverage"] >= lim and
                                                            (tot["routing_coverage"] or 0) < lim)}
    return out


def targets(tot, ps):
    t = TARGETS

    def ge(v, lim):
        return None if v is None else v >= lim
    return {"опасных = 0": tot["dangerous_false_standalone"] <= t["dangerous_false_standalone_max"],
            "точность маршрута >= 0.90": ge(tot["routing_accuracy"], t["routing_accuracy_min"]),
            "охват >= 0.70": ge(tot["routing_coverage"], t["routing_coverage_min"]),
            "точность родства STRONG >= 0.95": ge(ps["strong"]["relation_precision"],
                                                   t["relation_precision_strong_min"])}


# ---------------------------------------------------------------- эталон v2

def load_ref_v2(d=REF_V2):
    """reference_v2.tsv / reference_pairs_v2.tsv: эталон V5 с поправками онтологии v2 и MCD (колонка v2_change)."""
    ref = {r["asset_id"]: r for r in ir.read_tsv(os.path.join(d, "reference_v2.tsv"))}
    refp = ir.read_tsv(os.path.join(d, "reference_pairs_v2.tsv"))
    ja = os.path.join(d, "blind", "answers.tsv")
    judge = {r["asset_id"]: r for r in ir.read_tsv(ja)} if os.path.exists(ja) else {}
    return ref, refp, judge


# ---------------------------------------------------------------- детекторы, подготовка, строки маршрута

def detect(ctx, inp, keys, rels):
    """Выходы детекторов, которые маршрут V7 читает помимо оси A и снимка входов, - JSON: связи MCD по наборам кадров
    и их родни (by_set), улика поверхности MCD, варианты цвета (find_variants), подписи кадров петель анимации
    (ANIMATION_FAMILY_COPY), наборы оригинала (R0p). Holdout V7 замораживает их до ответов; пересчёт V7_PREP
    считает заново тем же кодом."""
    import map_mockup as mm
    import obj_struct as os_
    import routing_rules_v5 as v5
    sets = {k.split(":")[0] for k in keys} | {c["relative"].split(":")[0] for k in keys for c in rels.get(k, [])}
    by_set = ms.build(sets, ctx.world, cells=ms.placements(inp["census_frames"]))
    st = os_.Struct(ctx.world)
    set_list, cache = v6.all_sets(ctx.world), {}
    px = Pixels(ctx)
    members = loops(v6.anim_groups(by_set))
    origin = {n[:-4].upper() for dd in v6.ORIGIN_DIRS if os.path.isdir(os.path.join(mm.INSTALL, dd))
              for n in os.listdir(os.path.join(mm.INSTALL, dd)) if n.upper().endswith(".PCK")}
    return {"by_set": by_set, "surf": {a: list(v5.surface_evidence(st, a)) for a in keys},
            "variants": {a: v6.find_variants(ctx, a, set_list, cache) for a in keys},
            "sigs": {k.upper(): px.sig(k) for g in members.values() for k in g},
            "origin_sets": sorted(origin)}


def prepare(det, inp, keys):
    """Из выходов детекторов и снимка входов - всё для маршрута и утверждений (5. ANIMATION_FAMILY_COPY применена)."""
    groups = v6.anim_groups(det["by_set"])
    members = loops(groups)
    sigs = det["sigs"]

    def sig(k):
        return sigs.get(k.upper())
    meta = list(rr.metadata(inp))
    meta_rels, conv_route = convert_rels(meta[6], groups, members, sig)
    variants = det["variants"]
    idx = ms.index(det["by_set"])
    return {"meta": tuple(meta), "meta7": tuple(meta[:6]) + (meta_rels,), "conv_route": conv_route,
            "groups": groups, "members": members, "sig": sig, "by_set": det["by_set"], "surf": det["surf"],
            "variants": variants,
            # 5. вариант цвета между кадрами скопированной петли - не вариант (в маршрут не идёт, в утверждениях COPY)
            "variants7": {a: [v for v in vs if not anim_copy(groups, members, sig, a, v["relative"])[0]]
                          for a, vs in variants.items()},
            "view": {a: v6.mcd_view(idx.get(a.upper(), []), groups, None, "anim_only") for a in keys},
            "adj": touch_share(inp["touch"]), "origin": set(det["origin_sets"]),
            "qcls": {g["key"].upper(): (g["asset_class"], g["action"]) for g in ir.read_tsv(inp["generation"])}}


def build_rows(pr, keys, layer, ans, ref, umap, judge=None, axis="answers", meta_=None, var=None, **opts):
    """Строки маршрута V7 (с handoff) для кадров keys: ось A из ans (или судьи), эталон ref."""
    o = dict(V7_OPTS, origin_sets=pr["origin"], **opts)
    meta_ = pr["meta7"] if meta_ is None else meta_
    var = pr["variants7"] if var is None else var
    adj, rows = pr["adj"], []
    for a in keys:
        sk = ans.get(a, {}).get("semantic_kind", "")
        if axis == "judge" and a in (judge or {}) and judge[a]["semantic_kind"] != "UNSURE":
            sk = judge[a]["semantic_kind"]
        u, rule, why, kind, pick = route_v7(a, sk, meta_, pr["view"][a], pr["surf"][a], var[a], umap, o, adj)
        r = ref.get(a, {})
        n, share = adj.get(a.upper(), (0, 0.0))
        ht, hs, hr = handoff(u, kind, ans.get(a, {}).get("final_identity", ""))
        q = pr["qcls"].get(a.upper(), ("", ""))
        rows.append({"asset_id": a, "layer": layer[a]["layer"], "sub": layer[a]["sub"], "semantic_kind": sk,
                     "semantic_v6": kind, "surface": pr["surf"][a][0], "rule_unit": u, "rule": rule, "why": why,
                     "pair_pick": pick, "ref_route": r.get("ref_route") or "open",
                     "ref_semantic_kind": r.get("ref_semantic_kind") or "open",
                     "ref_change": r.get("v2_change", ""), "adj_places": n, "adj_share": share,
                     "handoff_target": ht, "handoff_status": hs, "handoff_reason": hr,
                     "queue_class": q[0], "queue_action": q[1]})
    return rows


def claims_of(pr, keys, rels, fr2):
    """Утверждения V7 на кадрах keys: (raw, dropped, conv)."""
    return claims_v7(keys, rels, pr["view"], fr2, pr["variants"], pr["groups"], pr["members"], pr["sig"])


# ---------------------------------------------------------------- пересчёт

def recount(out=OUT, hold=HOLDOUT, ref_dir=REF_V2):
    import family_relation_v2 as fr2m
    import relation_probe as rp
    import routing_holdout_v5 as h5
    import routing_rules_v5 as v5
    before = v5.dir_sha(hold)
    d, h = h5.load_freeze(hold), h5.load_holdout(hold)
    v5_code_changed = h5.code_changed(d)
    h5.live_same(d)
    ref5, refp5, _ = h5.load_reference(hold)
    ref2, refp2, judge = load_ref_v2(ref_dir)
    rels = h5.load_relations(hold)
    ans = {r["asset_id"]: r for r in ir.read_tsv(os.path.join(hold, "answers_vitali.tsv"))}
    keys = [x["asset_id"] for x in h["items"]]
    layer = {x["asset_id"]: x for x in h["items"]}
    inp = dict(d["inputs"])
    inp["relations"] = rh.load_json_path(hold)
    umap = d["routing"]["relation_unit"]
    fr2 = fr2m.load(inp["family_relation_v2"])
    pr = prepare(detect(rp.Ctx(), inp, keys, rels), inp, keys)
    conv_route, by_set = pr["conv_route"], pr["by_set"]

    def build(ref=ref2, axis="answers", **opts):
        return build_rows(pr, keys, layer, ans, ref, umap, judge, axis, **opts)

    def without(rows, drop=CONTESTED):
        return [r for r in rows if r["asset_id"] not in drop]

    rows = build()
    tot = metrics(rows)
    raw, dropped, conv = claims_of(pr, keys, rels, fr2)
    claims = score(raw, refp2)
    ps = precision_split(claims)
    r2_rows = build(adjacency=False, meta_=pr["meta"], var=pr["variants"])
    raw6, _ = v6.claims_v6(keys, rels, pr["view"], fr2, pr["variants"], pr["groups"])
    routing = {
        "V7, эталон v2": tot,
        "V7, эталон v2, без GOVTDECOR:33": metrics(without(rows)),
        "V7, эталон V5 (исходный)": metrics(build(ref=ref5)),
        "R2 (без 2 и 5), эталон v2": metrics(r2_rows),
        "R2 (без 2 и 5), эталон v2, без GOVTDECOR:33": metrics(without(r2_rows)),
        "V7 без R7t (только 5), эталон v2": metrics(build(adjacency=False)),
        "V7, R7t порог 0.5": metrics(build(adj_min=0.5)),
        "V7, R7t порог 1.0": metrics(build(adj_min=1.0)),
        "V7, ось A судьи v2 (потолок правил)": metrics(build(axis="judge")),
    }
    relation = {
        "V7, эталон v2": ps,
        "V7, эталон V5 (исходный)": precision_split(score(raw, refp5)),
        "без ANIMATION_FAMILY_COPY (как R2), эталон v2": precision_split(v6.score(raw6, refp2)),
        "без ANIMATION_FAMILY_COPY (как R2), эталон V5": precision_split(v6.score(raw6, refp5)),
    }
    chain = mcd_chains(by_set, keys)
    rows_no_r7t = build(adjacency=False)
    checks = gate_checks(tot, ps, rows)
    after = v5.dir_sha(hold)
    r7t = [[r["asset_id"], r["adj_places"], r["adj_share"], r["ref_route"]] for r in rows if r["rule"] == "R7t"]
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "ROUTING_RULES_V7_PREP", "diagnostic_only": True,
           "not_blind": "правила V7 написаны после ответов и эталона этих 50 - PASS не заявляется, V7 не заморожен",
           "holdout": hold.replace(os.sep, "/"), "holdout_freeze_sha256": d["sha256"],
           "holdout_untouched": before == after, "holdout_files": len(before), "v5_code_changed": v5_code_changed,
           "code_sha256": {c: rh.file_sha(c) for c in CODE}, "reference_v2": ref_dir.replace(os.sep, "/"),
           "ontology_v2": SEM_DEFS_V2, "adj_min": ADJ_MIN, "contested": list(CONTESTED),
           "targets": targets(tot, ps), "targets_without_contested": targets(metrics(without(rows)), ps),
           "checks": checks, "verdict_if_blind": verdict(checks), "gates": GATES, "gate_defs": GATE_DEFS,
           "diag_defs": DIAG_DEFS, "diagnostics": diagnostics(rows, claims, rows_no_r7t),
           "total": tot, "relations": ps, "routing": routing, "relation": relation,
           "r7t": r7t, "anim_copy_route": conv_route, "anim_copy_claims": conv, "dropped": dropped,
           "mcd_chains": chain, "rules_fired": dict(Counter(r["rule"] for r in rows)),
           "outcomes": dict(Counter(v6.outcome(r) for r in rows)),
           "changed_vs_r2": [[r["asset_id"], q["rule_unit"], q["rule"], r["rule_unit"], r["rule"], r["ref_route"], r["why"]]
                             for r, q in zip(rows, r2_rows) if (r["rule_unit"], r["rule"]) != (q["rule_unit"], q["rule"])],
           "ref_changes": [[a, ref5[a]["ref_semantic_kind"], ref5[a]["ref_route"], ref2[a]["ref_semantic_kind"],
                            ref2[a]["ref_route"], ref2[a].get("v2_change", "")] for a in keys
                           if ref2[a].get("v2_change")],
           "pair_changes": [[p["asset_id"], p["relative"], p["ref_pair_relation"], p.get("v2_change", "")]
                            for p in refp2 if p.get("v2_change")],
           "pair_pick": [r["asset_id"] for r in rows if r["pair_pick"]], "claims": claims, "rows": rows}
    os.makedirs(out, exist_ok=True)
    ir.dump_json(os.path.join(out, "recount.json"), res)
    write_handoff(os.path.join(out, "handoff.tsv"), rows)
    write_md(out, res)
    if not res["holdout_untouched"]:
        raise SystemExit("папка holdout изменилась во время пересчёта - так быть не должно")
    return res


def mcd_chains(by_set, keys):
    """3. Цепочки разрушения у кадров 50: die-связь, у состояния которой есть свой die. Уровень - как у mcd_state."""
    links = [x for lst in by_set.values() for x in lst if x["via"] == "die"]
    bases = {x["base"].upper() for x in links}
    ks = {k.upper() for k in keys}
    out = []
    for x in links:
        if x["state"].upper() in bases and (x["state"].upper() in ks or x["base"].upper() in ks):
            out.append([x["base"], x["state"], x["level"], x.get("why", "")])
    return out


# ---------------------------------------------------------------- отчёт

HANDOFF_HEAD = ["asset_id", "route", "rule", "semantic_kind", "handoff_target", "handoff_status", "handoff_reason",
                "queue_class", "queue_action"]


def write_handoff(path, rows):
    """Манифест передачи: каждый EXCLUDE со своей целью - ни один кадр не пропадает из HD молча."""
    ex = [r for r in rows if r["rule_unit"] == "EXCLUDE"]
    with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("\t".join(HANDOFF_HEAD) + "\n")
        for r in ex:
            f.write("\t".join(str(x) for x in (r["asset_id"], r["rule_unit"], r["rule"], r["semantic_v6"],
                                                r["handoff_target"] or "UNASSIGNED", r["handoff_status"],
                                                r["handoff_reason"], r.get("queue_class", ""),
                                                r.get("queue_action", ""))) + "\n")
    return len(ex)


def diag_md(dg):
    ur, ss, r7, h = dg["unnecessary_review"], dg["structural_surface_accuracy"], dg["r7t"], dg["handoff"]
    hurt = r7.get("hurt") or {}
    pr = dg["mcd"]

    def p_(x):
        return "%s (%d/%d)" % (x["relation_precision"], x["ok"], x["closed"])
    return ["## Диагностика (не ворота)", "",
            "| показатель | значение |", "|---|---|",
            "| сверхосторожно | %s (%d/%d) |" % (dg["overconservative_rate"], dg["overconservative"], dg["ref_standalone"]),
            "| лишний REVIEW: всего / одиночные | %d (%s) / %d (%s) |" % (ur["count"], ur["rate"], ur["standalone_count"],
                                                                     ur["standalone_rate"]),
            "| ось A против эталона | %s (из %d) |" % (dg["semantic_axis_accuracy"], dg["semantic_n"]),
            "| поверхности: ось A / маршрут | %s / %s (поверхностей %d, решено %d) |" % (
                ss["semantic"], ss["route"], ss["n"], ss["route_decided"]),
            "| R7t: сработал / помог / лишний / не решено | %d / %d / %d / %d |" % (
                r7["triggered"], r7["helped"], r7["unnecessary"], r7["unresolved"]),
            "| R7t: охват без него / с ним / ворота охвата сменились | %s / %s / %s |" % (
                hurt.get("coverage_without"), hurt.get("coverage_with"),
                "да" if hurt.get("coverage_gate_flipped") else "нет"),
            "| MCD анимация / разрушение | %s / %s |" % (p_(pr["animation"]), p_(pr["die"])),
            "| ANIMATION_FAMILY_COPY | %s |" % p_(dg["animation_family_copy"]),
            "| EXCLUDE: всего / стены / рельеф / NONE / без цели | %d / %d / %d / %d / %d |" % (
                h["excluded_total"], h["handoff_structural"], h["handoff_terrain"], h["handoff_none"],
                h["handoff_unassigned"]),
            "| передано в ещё не построенный конвейер | %d |" % h["handoff_target_not_implemented"],
            "| из них очередь держит предметом | %d |" % h["handoff_queue_object_class"], ""]


def write_md(out, res):
    word = {True: "да", False: "**нет**", None: "нет данных"}

    def acc(x):
        return "%s (%d/%d)" % (x["routing_accuracy"], x["correct"], x["decided"])

    def pr(x):
        return "%s (%d/%d)" % (x["relation_precision"], x["ok"], x["closed"])

    t, ps, tg = res["total"], res["relations"], res["targets"]
    L = ["# ROUTING_RULES_V7_PREP - диагностический пересчёт на тех же 50", "",
         "Не слепо и не PASS: правила V7 написаны после ответов и эталона этих 50. Итоги V5, V6-prep и R2 стоят; "
         "holdout только читался (файлов %d, не изменились: %s), код V5 из FREEZE %s." % (
             res["holdout_files"], "да" if res["holdout_untouched"] else "**НЕТ**",
             "тот же" if not res["v5_code_changed"] else "**ИЗМЕНЁН**"),
         "Эталон - v2 (онтология v2 и MCD): `%s`." % res["reference_v2"], "",
         "## Цели (V7)", "", "| показатель | V7 | цель | достигнута | без GOVTDECOR:33 |", "|---|---|---|---|---|"]
    tw = res["routing"]["V7, эталон v2, без GOVTDECOR:33"]
    tgw = res["targets_without_contested"]
    L += ["| опасных одиночных | %d | 0 | %s | %d (%s) |" % (t["dangerous_false_standalone"], word[tg["опасных = 0"]],
                                                           tw["dangerous_false_standalone"], word[tgw["опасных = 0"]]),
          "| точность маршрута | %s | >= 0.90 | %s | %s (%s) |" % (acc(t), word[tg["точность маршрута >= 0.90"]], acc(tw),
                                                                  word[tgw["точность маршрута >= 0.90"]]),
          "| охват | %s (%d/%d) | >= 0.70 | %s | %s (%s) |" % (t["routing_coverage"], t["decided"], t["ref_closed"],
                                                              word[tg["охват >= 0.70"]], tw["routing_coverage"],
                                                              word[tgw["охват >= 0.70"]]),
          "| точность родства STRONG | %s | >= 0.95 | %s | |" % (pr(ps["strong"]),
                                                               word[tg["точность родства STRONG >= 0.95"]]),
          "| точность родства CANDIDATE | %s | диагностика | - | |" % pr(ps["candidate"]),
          "| точность родства вся | %s | - | - | |" % pr(ps["all"]),
          "| сверхосторожно | %s (%d/%d) | - | - | |" % (t["overconservative_rate"], t["overconservative"],
                                                       t["ref_standalone"]), "",
          "Исходы: %s. Правила: %s." % (", ".join("%s %d" % kv for kv in sorted(res["outcomes"].items())),
                                        ", ".join("%s %d" % kv for kv in sorted(res["rules_fired"].items()))), "",
          "## Ворота V7 к заморозке (как на слепом holdout; здесь не слепо)", "",
          "| ворота | пройдено |", "|---|---|"]
    L += ["| %s | %s |" % (k, word[v]) for k, v in res["checks"].items()]
    L += ["", "Вердикт по этим воротам: %s (диагностика, не приёмка)." % res["verdict_if_blind"], ""]
    L += diag_md(res["diagnostics"])
    L += ["Манифест передачи - handoff.tsv.", ""]
    L += [""]
    L += ["## Маршрут по профилям", "", "| профиль | опасных | точность | охват | сверхосторожно |", "|---|---|---|---|---|"]
    L += ["| %s | %d | %s | %s | %s |" % (k, x["dangerous_false_standalone"], acc(x), x["routing_coverage"],
                                         x["overconservative_rate"]) for k, x in res["routing"].items()]
    L += ["", "## Родство по профилям", "", "| профиль | STRONG | CANDIDATE | всё |", "|---|---|---|---|"]
    L += ["| %s | %s | %s | %s |" % (k, pr(x["strong"]), pr(x["candidate"]), pr(x["all"]))
          for k, x in res["relation"].items()]
    bad = [r for r in res["rows"] if v6.outcome(r) in ("ОПАСНО", "неверно")]
    L += ["", "## Ошибки маршрута (эталон v2)", "", "| кадр | A | правило | V7 | эталон | исход | почему |",
          "|---|---|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s | %s | %s |" % (r["asset_id"], r["semantic_kind"], r["rule"], r["rule_unit"],
                                                   r["ref_route"], v6.outcome(r), r["why"]) for r in bad] or \
        ["| нет | | | | | | |"]
    over = [r for r in res["rows"] if r["rule_unit"] == "REVIEW" and r["ref_route"] == "STANDALONE_RENDER"]
    L += ["", "Сверхосторожно (REVIEW при эталоне STANDALONE): %s." % (
        "; ".join("%s %s" % (r["asset_id"], r["rule"]) for r in over) or "нет")]
    L += ["", "## R7t SAME_FRAME_ADJACENCY (PROVISIONAL)", ""]
    L += ["- %s: мест %d, доля вплотную %.2f, эталон %s" % tuple(x) for x in res["r7t"]] or ["- не сработал"]
    L += ["", "## ANIMATION_FAMILY_COPY", ""]
    L += ["- %s ~ %s: было %s (%s), %s" % tuple(x) for x in res["anim_copy_claims"]] or ["- нет"]
    L += ["", "## Сменили маршрут против R2", "", "| кадр | R2 | V7 | эталон v2 | почему |", "|---|---|---|---|---|"]
    L += ["| %s | %s %s | %s %s | %s | %s |" % tuple(c) for c in res["changed_vs_r2"]] or ["| нет | | | | |"]
    L += ["", "## Поправки эталона v2", "", "| кадр | V5 | v2 | причина |", "|---|---|---|---|"]
    L += ["| %s | %s / %s | %s / %s | %s |" % tuple(c) for c in res["ref_changes"]] or ["| нет | | | |"]
    L += ["", "Пары: " + ("; ".join("%s ~ %s -> %s (%s)" % tuple(c) for c in res["pair_changes"]) or "нет")]
    L += ["", "## Цепочки разрушения MCD у кадров 50 (3)", ""]
    L += ["- %s -> %s: %s %s" % tuple(x) for x in res["mcd_chains"]] or ["- нет"]
    L += ["", "## По кадрам", "", "| кадр | A | правило | V7 | эталон v2 | исход |", "|---|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s | %s |" % (r["asset_id"], r["semantic_kind"], r["rule"], r["rule_unit"],
                                              r["ref_route"], v6.outcome(r)) for r in res["rows"]]
    with open(os.path.join(out, "recount.md"), "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("recount")
    c.add_argument("--out", default=OUT)
    c.add_argument("--ref", default=REF_V2, help="папка эталона v2 (reference_v2.tsv, reference_pairs_v2.tsv)")
    a = ap.parse_args()
    if a.cmd == "recount":
        res = recount(a.out, ref_dir=a.ref)
        print("V7: опасных %d, точность %s, охват %s, родство STRONG %s, CANDIDATE %s" % (
            res["total"]["dangerous_false_standalone"], res["total"]["routing_accuracy"],
            res["total"]["routing_coverage"], res["relations"]["strong"]["relation_precision"],
            res["relations"]["candidate"]["relation_precision"]))
        print("цели:", res["targets"])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
