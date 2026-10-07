#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ROUTING_MODEL_V8 - маршрут из трёх независимых осей и диагностический пересчёт тех же 60 (специалист 02.10). CPU.

V7 остаётся FAIL: report.md holdout V7 не переписывается, этот модуль его только читает. Код V3-V7 и папки holdout
не меняются - V8 вызывает подготовку V7 как есть и раскладывает связи по осям. V8_PREP (probes/routing-model-v8-prep)
- прежний пересчёт с одной ролью на кадр, остаётся как был; пересчёт до заморозки (probes/routing-model-v8-prefreeze)
тоже остаётся как был; проверка реализации перед заморозкой - probes/routing-model-v8-freeze-check.

Одно поле route смешивало две вещи: куда кадр идёт (конвейер) и как он связан с другим кадром. В V8 они разные:

    A. semantic_kind   онтология v2: OBJECT, OBJECT_PART, STRUCTURAL_SURFACE, TERRAIN_RELIEF, NOT_OBJECT, UNSURE;
                       граница OBJECT_PART / STRUCTURAL_SURFACE - ONTOLOGY_V8 (убрали деталь: дыра в оболочке или
                       исчез объёмный узел)
    B. pipeline_target OBJECT_PIPELINE, STRUCTURAL_PIPELINE, TERRAIN_PIPELINE, NONE, REVIEW - только от оси A
                       (и улики поверхности MCD у OBJECT); связь конвейер не меняет: STRUCTURAL_SURFACE ->
                       STRUCTURAL_PIPELINE при любой связи (решение специалиста)
    C. relations       НАБОР рёбер (relation_type, source, target, confidence, evidence) без порядка старшинства:
                       COMPOSITE_PART + DESTROYED_VARIANT_OF X у одного кадра не спорят. Типы: CANONICAL,
                       COMPOSITE_PART, STRUCTURAL_MODULAR, STATE_VARIANT_OF, DESTROYED_VARIANT_OF, ANIMATION_FAMILY,
                       ANIMATION_FAMILY_COPY, RECOLOR_PEER, MATERIAL_VARIANT_OF, DERIVED_FROM. Рёбра собирают те же
                       условия, что правила V6/V7 (relations), но каждое само по себе; улика без доказанной связи -
                       open_evidence (кадр не CANONICAL и не получает одиночный заказ). Считается для КАЖДОГО кадра,
                       и для поверхности тоже (в V7 правило S отрезало связь)

Факт и смысл разделены. relation_fact - ребро MCD, прочитанное из записей (Frame[0..7], Die_MCD, Alt_MCD, UFO_Door,
Door; раскладка - struct MCD в src/Mod/MapDataSet.cpp), в обе стороны: исходящие (die / alt / кадры анимации своей
записи) и входящие (used_as_die_by / used_as_alt_by / used_as_animation_frame_by). Факт не судится. relation_semantics
- что ребро значит (разрушенный вид, второе состояние, фаза, псевдоним, необычное повторное использование); его решает
человек, правило только предлагает. Досье эталона показывает факты в обе стороны и окрестность в один шаг (R-171).

Правило V8 поверх родства V7 (найдено на споре слепого V7):
  D1 (дверь, PROVISIONAL - нужна слепая проверка): кадр Frame[7] записи UFO_Door - открытое неподвижное состояние
     (Tile::animate держит кадры 0 и 7, Tile::openDoor), alt записи Door - открытая дверь (setMapData(altMCD)); это
     STATE_VARIANT_OF, а не фаза петли. Кадры 1-6 двери НЛО - фазы перехода (ANIMATION_FAMILY). Фаза и состояние в
     один класс не сливаются. На holdout считаются D1_triggered / correct / wrong / unresolved.
  L1 (голова петли - член семейства анимации) - NOT_ACTIVE, отложенная гипотеза (специалист 02.10): на 60 не
     сработал ни разу, ничего не исправляет.

Перед заморозкой (специалист 02.10, единственная архитектурная поправка): доказанная перекраска STRONG (pair_pick
V6/V7) - явное ребро RECOLOR_PEER, симметричное, без основы (RECOLOR_PEER != DERIVED_FROM); для дедупликации -
техническая группа render_group_id / render_anchor (якорь - что рисуем первым, не истинный оригинал). Связь хранится
одним направленным ребром (Graph: source :22 DESTROYED_VARIANT_OF target :21), у основы - обратное чтение
relations_in (HAS_DESTROYED_VARIANT :22), не второе отношение и не второй довод.

Ворота V8 (GATES_V8, специалист 02.10): B_SAFETY и E2E_SAFETY - dangerous_creative_standalone = 0 при оси A эталона
и при оси A специалиста (одиночный творческий заказ там, где эталону нужен составной, конвейер поверхности или
рельефа, вывод, состояние, анимация или NONE); pipeline_logic_accuracy >= 0.95 и pipeline_logic_coverage >= 0.70 - правила B
при оси A эталона; strong_relation_precision >= 0.95 при >= 10 закрытых. Отдельно, не в вердикте маршрута:
semantic_axis_accuracy >= 0.85 (ворота карточки и оператора), end_to_end_pipeline_accuracy (без ворот),
wrong_pipeline_classification (прежняя строгая мера), точность и полнота связей по видам. Пересчёт на 60 V7 -
диагностика: V8 написан после ответов и эталона, PASS задним числом не заявляется.

    py -3.13 tools/hdart/routing_model_v8.py recount          -> probes/routing-model-v8-freeze-check/recount.md / .json
    py -3.13 tools/hdart/routing_model_v8.py facts CAVEBROWN:33 USOEXT2:8
    py -3.13 tools/hdart/routing_model_v8.py dossier CAVEBROWN:33
"""
import argparse
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402

OUT = os.path.join(ir.PROBES, "routing-model-v8-freeze-check")
HOLD_V7 = os.path.join(ir.PROBES, "routing-holdout-v7")
CODE = ("tools/hdart/routing_model_v8.py",)

SEMANTIC = ["OBJECT", "OBJECT_PART", "STRUCTURAL_SURFACE", "TERRAIN_RELIEF", "NOT_OBJECT", "UNSURE"]
PIPELINES = ["OBJECT_PIPELINE", "STRUCTURAL_PIPELINE", "TERRAIN_PIPELINE", "NONE", "REVIEW"]
PIPELINE_OF = {"OBJECT": "OBJECT_PIPELINE", "OBJECT_PART": "OBJECT_PIPELINE", "STRUCTURAL_SURFACE": "STRUCTURAL_PIPELINE",
               "TERRAIN_RELIEF": "TERRAIN_PIPELINE", "NOT_OBJECT": "NONE"}
ROLES = ["CANONICAL", "COMPOSITE_PART", "STRUCTURAL_MODULAR", "STATE_VARIANT_OF", "DESTROYED_VARIANT_OF",
         "ANIMATION_FAMILY", "ANIMATION_FAMILY_COPY", "RECOLOR_PEER", "MATERIAL_VARIANT_OF", "DERIVED_FROM"]
ROLE_GROUP = {"CANONICAL": "canonical", "COMPOSITE_PART": "composite", "STRUCTURAL_MODULAR": "modular",
              "STATE_VARIANT_OF": "state", "DESTROYED_VARIANT_OF": "state", "ANIMATION_FAMILY": "animation",
              "ANIMATION_FAMILY_COPY": "animation", "RECOLOR_PEER": "derived", "MATERIAL_VARIANT_OF": "derived",
              "DERIVED_FROM": "derived"}
GROUPS = ["canonical", "composite", "modular", "state", "animation", "derived"]
# граница OBJECT_PART / STRUCTURAL_SURFACE - геометрическая (специалист 02.10); примеры без кадров holdout
ONTOLOGY_V8 = {
    "STRUCTURAL_SURFACE": {"def": "встроенная оболочка или поверхность конструкции",
                           "examples": ["обшивка", "панель крыши", "панель стены", "полотно двери", "пол",
                                        "поверхность рампы", "лестница", "встроенная рампа"]},
    "OBJECT_PART": {"def": "дискретная объёмная часть машины или предмета",
                    "examples": ["секция фюзеляжа", "хвостовая секция", "секция крыла", "двигатель", "шасси",
                                 "бампер в сборе", "механический придаток"]},
    "test": "убрали деталь: осталась дыра в оболочке или поверхности - STRUCTURAL_SURFACE; исчез отдельный объёмный "
            "узел или секция - OBJECT_PART. «Часть корпуса машины» сама по себе не решает"}

GATES_V8 = {"dangerous_creative_standalone_max": 0, "pipeline_logic_accuracy_min": 0.95,
            "pipeline_logic_coverage_min": 0.70, "strong_relation_precision_min": 0.95, "strong_closed_min": 10}
SEMANTIC_GATE = {"semantic_axis_accuracy_min": 0.85}      # ворота карточки и оператора, не вердикт маршрута
GATE_DEFS = {
    "dangerous_creative_standalone": "одиночный творческий заказ (OBJECT_PIPELINE и единственное ребро CANONICAL), а "
                                     "эталону нужен другой конвейер (STRUCTURAL / TERRAIN / NONE) или у кадра по "
                                     "судимому эталону связь (составной, модуль, состояние, вывод, анимация). Двое "
                                     "ворот, обе 0: B_SAFETY - при оси A эталона (сам маршрут), E2E_SAFETY - при оси A "
                                     "специалиста (система для production)",
    "RECOLOR_PEER": "доказанная перекраска (STRONG, основа человеком не подтверждена) - симметричное ребро без основы. "
                    "correct - пара эталона RECOLOR_OF / DERIVED_FROM в любую сторону (или без пары судимый эталон "
                    "derived); wrong - пара эталона другого вида (или без пары судимый эталон без derived); "
                    "unresolved - эталон не судил. render_group_id / render_anchor - техническое: что рисуем первым "
                    "(набор оригинальных данных игры, затем меньший ключ), не основа",
    "graph": "отношение хранится одним направленным ребром (производный -> основа, симметричное - по упорядоченной "
             "паре); relations_in - обратное чтение того же ребра (HAS_DESTROYED_VARIANT и т.п.), не второе отношение",
    "wrong_pipeline_classification": "решённый конвейер не совпал с эталонным (прежняя строгая мера, точность, не "
                                     "безопасность); сюда же - сколько из них OBJECT_PIPELINE при эталонном не-OBJECT",
    "pipeline_logic_accuracy": "правила B при оси A эталона: верно / решено (эталонный конвейер закрыт, не REVIEW)",
    "pipeline_logic_coverage": "правила B при оси A эталона: решено / закрытых эталонных конвейеров",
    "end_to_end_pipeline_accuracy": "ось A специалиста -> правила -> B против эталона; без ворот",
    "semantic_axis_accuracy": "ось A ответов против ref_semantic_kind, UNSURE и open вне знаменателя; ворота карточки",
    "strong_relation_precision": "утверждения STRONG о смысле связи: верно / закрытых; факт MCD, который эталон не "
                                 "видел (только входящее ребро, R-171), и пары, снятые специалистом, не закрыты; "
                                 "закрытых меньше 10 - INSUFFICIENT_SAMPLE",
    "relation_by_type": "по группам связи (canonical, composite, modular, state, animation, derived), набор против "
                        "набора: точность - из кадров, где V8 дал ребро группы, доля, где группа есть в эталоне; "
                        "полнота - из кадров с группой в эталоне доля, где V8 её дал. Строки с неинформированным "
                        "эталоном (R-171) и без суждения о связи - вне. Эталон V7 размечен одной связью на кадр, "
                        "поэтому лишнее, но верное ребро здесь считается ошибкой - диагностика, не ворота",
    "D1": "triggered - D1 дал ребро; correct - судимый эталон кадра с группой state или пара эталона с этим кадром "
          "STATE_VARIANT_OF; wrong - судимый эталон без state и пара не STATE_VARIANT_OF; unresolved - эталон не "
          "судил связь"}

# MCD: struct MCD в src/Mod/MapDataSet.cpp - Frame[8] 0-7, UFO_Door 30, Door 35, Die_MCD 44, Alt_MCD 46, Tile_Type 53
MCD_RECORD = 62
F_UFO_DOOR, F_DOOR, F_DIE, F_ALT, F_TYPE = 30, 35, 44, 46, 53
UFO_OPEN_POS = 7                    # Tile::animate: дверь НЛО стоит на кадрах 0 (закрыта) и 7 (открыта)


# ---------------------------------------------------------------- relation_fact: рёбра MCD в обе стороны

def parse_mcd(data):
    """Записи MCD из байтов: n, frames (Frame[0..7]), ufo, door, die, alt, type."""
    return [{"n": i // MCD_RECORD, "frames": list(data[i:i + 8]), "ufo": data[i + F_UFO_DOOR],
             "door": data[i + F_DOOR], "die": data[i + F_DIE], "alt": data[i + F_ALT], "type": data[i + F_TYPE]}
            for i in range(0, len(data) - MCD_RECORD + 1, MCD_RECORD)]


class Mcd:
    """Записи MCD наборов установки (map_mockup.World), с кэшем; recs - готовые записи для синтетики."""

    def __init__(self, world=None, recs=None):
        self.world, self.cache = world, dict(recs or {})

    def records(self, s):
        s = s.upper()
        if s not in self.cache:
            path = self.world.files.find(os.path.join("TERRAIN", s + ".MCD")) if self.world else None
            self.cache[s] = parse_mcd(open(path, "rb").read()) if path else []
        return self.cache[s]


def door_of(r):
    return "ufo" if r["ufo"] else ("swing" if r["door"] else "")


def meaning(via, direction, door, pos):
    """Машинное прочтение ребра (не суждение): что кадр-цель значит по коду движка."""
    if via == "die":
        return "DESTROYED_STATE"
    if via == "alt":
        return "DOOR_STATE" if door == "swing" else "ALT_STATE"      # Tile::openDoor читает Alt_MCD только у Door
    if door == "ufo":
        return "DOOR_OPEN_STATE" if UFO_OPEN_POS in pos else "DOOR_PHASE"
    return "ANIMATION_PHASE"


def facts(mcd, key):
    """Рёбра MCD кадра в обе стороны: [{asset, relative, via, dir OUT|IN, record, rel_record, pos, door, meaning}].
    OUT - своя запись кадра (Frame[0] = кадр) ссылается на другой кадр; IN - чужая запись ссылается на этот кадр."""
    s, f = key.split(":")[0].upper(), int(key.split(":")[1])
    recs = mcd.records(s)
    out = []

    def frame(i):
        return recs[i]["frames"][0] if 0 < i < len(recs) else None

    def add(rel, via, d, rec, rrec, pos, door):
        out.append({"asset": "%s:%d" % (s, f), "relative": "%s:%d" % (s, rel), "via": via, "dir": d, "record": rec,
                    "rel_record": rrec, "pos": pos, "door": door, "meaning": meaning(via, d, door, pos)})

    for r in recs:
        f0 = r["frames"][0]
        for via in ("die", "alt"):
            g = frame(r[via])
            if g is None:
                continue
            if f0 == f and g != f:
                add(g, via, "OUT", r["n"], r[via], [], door_of(r))
            elif g == f and f0 != f:
                add(f0, via, "IN", r[via], r["n"], [], door_of(r))
        if f0 == f:
            for g in sorted(set(r["frames"][1:]) - {f}):
                add(g, "anim", "OUT", r["n"], r["n"], [i for i, x in enumerate(r["frames"]) if x == g], door_of(r))
        elif f in r["frames"][1:]:
            add(f0, "anim", "IN", r["n"], r["n"], [i for i, x in enumerate(r["frames"]) if x == f], door_of(r))
    return out


def neighbourhood(mcd, key):
    """Окрестность в один шаг: факты кадра и факты каждого его соседа по MCD."""
    own = facts(mcd, key)
    hop = {}
    for x in own:
        hop.setdefault(x["relative"], facts(mcd, x["relative"]))
    return own, hop


def shown_in_v7(fs, relative):
    """Было ли ребро в досье V5/V7: оно показывало только свою запись кадра (исходящие рёбра)."""
    return any(x["dir"] == "OUT" and x["relative"].upper() == relative.upper() for x in fs)


# досье пишет факт и то, что с ним делает движок; что это по смыслу (разрушенный вид, псевдоним, необычное повторное
# использование) - решает судья
TXT_OUT = {"die": "Die_MCD ->", "alt": "Alt_MCD ->", "anim": "среди кадров анимации -"}
TXT_IN = {"die": "Die_MCD записи с кадром", "alt": "Alt_MCD записи с кадром", "anim": "кадр анимации записи с кадром"}
TXT_MEANING = {"DESTROYED_STATE": "движок ставит цель на место записи при разрушении",
               "DOOR_STATE": "запись - дверь: движок ставит цель на её место при открывании",
               "ALT_STATE": "Alt_MCD у записи без флага Door - движок его не читает", "DOOR_OPEN_STATE": "дверь НЛО, Frame[7]: движок держит этот кадр "
               "открытой дверью", "DOOR_PHASE": "дверь НЛО, кадр перехода при открывании",
               "ANIMATION_PHASE": "кадр петли анимации"}


def fact_line(x):
    pos = " (позиция %s)" % ",".join(map(str, x["pos"])) if x["pos"] else ""
    if x["dir"] == "OUT":
        return "запись %d: %s %s%s - %s" % (x["record"], TXT_OUT[x["via"]], x["relative"], pos, TXT_MEANING[x["meaning"]])
    return "этот кадр - %s %s (запись %d)%s - %s" % (TXT_IN[x["via"]], x["relative"], x["rel_record"], pos,
                                                   TXT_MEANING[x["meaning"]])


def dossier_lines(mcd, key):
    """Строки досье эталона про MCD (R-171): исходящие, входящие, окрестность в один шаг. «нет» - только когда нет
    ни исходящих, ни входящих."""
    own, hop = neighbourhood(mcd, key)
    o = [x for x in own if x["dir"] == "OUT"]
    i = [x for x in own if x["dir"] == "IN"]
    if not own:
        return ["MCD: связей нет ни исходящих (die, alt, анимация своей записи), ни входящих (кадр не стоит в die, "
                "alt или петле чужой записи)"]
    L = ["MCD исходящие (своя запись):" + (" нет" if not o else "")] + ["  - " + fact_line(x) for x in o]
    L += ["MCD входящие (чужие записи ссылаются на этот кадр):" + (" нет" if not i else "")]
    L += ["  - " + fact_line(x) for x in i]
    L += ["MCD окрестность в один шаг:"]
    for rel, fs in sorted(hop.items()):
        rest = [x for x in fs if x["relative"].upper() != key.upper()]
        L.append("  %s: %s" % (rel, "; ".join(fact_line(x) for x in rest) if rest else "других связей нет"))
    return L


# ---------------------------------------------------------------- оси B и C

def role_of(rule, why, unit):
    """Роль V8 по правилу родства V7 (кадр прогнан как OBJECT без улики поверхности, правило S не срабатывает)."""
    if rule == "R5":
        return "COMPOSITE_PART"
    if rule == "R6":
        return "STRUCTURAL_MODULAR"
    if rule == "R0v":
        k = (why or "").split(" ")[0]
        return {"MATERIAL_VARIANT_OF": "MATERIAL_VARIANT_OF", "STYLE_VARIANT_OF": "MATERIAL_VARIANT_OF",
                "STATE_VARIANT_OF": "STATE_VARIANT_OF"}.get(k, "DERIVED_FROM")
    if rule in ("R0p", "R4") or (rule == "R4v" and unit == "DERIVED"):
        return "DERIVED_FROM"
    if rule == "R3a":
        return "ANIMATION_FAMILY"
    if rule == "R3m":
        return "DESTROYED_VARIANT_OF"
    if rule == "R3":
        return "STATE_VARIANT_OF"
    if rule == "R8":
        return "CANONICAL"
    return "OPEN"


def door_state(fs):
    """D1: факт открытого состояния двери (IN: кадр - Frame[7] двери НЛО или alt записи с флагом двери)."""
    for x in fs:
        if x["dir"] == "IN" and x["meaning"] in ("DOOR_OPEN_STATE", "DOOR_STATE"):
            return x
    return None


def relations(a, kind, pr, umap, fs, door=True):
    """Ось C: (рёбра, open_evidence). Каждое условие правил V6/V7 проверяется само по себе, без порядка старшинства:
    кадр может быть и куском составного, и разрушенным видом. Ребро - relation_type, source, target, confidence
    (STRONG | VERIFIED | PROVISIONAL), rule, evidence. Улика без доказанной связи - open_evidence: кадр не CANONICAL,
    но и связи не получает. CANONICAL - только когда нет ни рёбер, ни улик. Опции - V7_OPTS как есть."""
    import routing_rules_v6 as v6
    import routing_rules_v7 as v7
    o = dict(v7.V7_OPTS, origin_sets=pr["origin"])
    umap = umap or v6.rr.RELATION_UNIT_HOLDOUT              # как route_v6
    gen, fam_rel, fam_review, state, modular, cls, rels = pr["meta7"]
    mlinks, variants = pr["view"][a], pr["variants7"][a]
    g = gen.get(a, {})
    blockers = [b.split(":")[0] for b in (g.get("blockers") or "").split()]
    rel, fr = g.get("relation", ""), fam_rel.get(a, "canonical")
    rs = (rels or {}).get(a, [])
    rec = [r for r in rs if r["kind"] in v6.RECOLOR]
    E, ev = [], []

    def edge(t, target, conf, rule, why):
        E.append({"relation_type": t, "source": a, "target": target, "confidence": conf, "rule": rule,
                  "evidence": why})

    def evid(rule, why):
        ev.append({"rule": rule, "evidence": why})

    # структура
    if g.get("kind") == "составной" or cls.get(a) == "part_fragment":
        edge("COMPOSITE_PART", "", "STRONG", "R5", "kind %s, class %s" % (g.get("kind", "-"), cls.get(a, "-")))
    if a in modular or cls.get(a) == "structural_modular":
        edge("STRUCTURAL_MODULAR", "", "STRONG", "R6", "modular_objects / class_decisions")
    if "part_fragment_suspect" in blockers:
        evid("R7p", "part_fragment_suspect")
    # родство
    for r in rs:
        if r.get("verified") and r["kind"] in umap and r["side"] == "derived":
            edge(role_of("R0v", r["kind"], umap[r["kind"]]), r["relative"], "VERIFIED", "R0v",
                 "%s %s (основа подтверждена человеком)" % (r["kind"], r["relative"]))
    # RP (специалист 02.10): доказанная перекраска - симметричное ребро без основы (бывший pair_pick V6/V7);
    # перекраска с основой, подтверждённой человеком, - R0v выше, с основой у второго кадра - его ребро
    for r in rec:
        if r["level"] == "STRONG" and not (r.get("verified") and r["side"] != "open"):
            edge("RECOLOR_PEER", r["relative"], "STRONG", "RP", "%s %s: доказанная перекраска, связь симметрична, "
                 "основа не назначается" % (r["kind"], r["relative"]))
    src = []
    if o["origin_sets"] is not None and a.split(":")[0].upper() not in o["origin_sets"]:
        proven = [r for r in rec if r["level"] == "STRONG"] + list(variants)
        src = [r for r in proven if r["relative"].split(":")[0].upper() in o["origin_sets"]]
    der = [x for x in mlinks if x["side"] == "derived"]
    for x in der:
        if x["v6"] == "anim":
            edge("ANIMATION_FAMILY", x["base"], "STRONG", "R3a", "MCD anim %s, основа %s" % (x["base"], x["root"]))
        elif x["v6"] == "die_ok":
            edge("DESTROYED_VARIANT_OF", x["base"], "STRONG", "R3m", "MCD die %s, основа %s (%s)" % (
                x["base"], x["root"], x["v6_why"]))
    if a in state or cls.get(a) == "state_variant":
        edge("STATE_VARIANT_OF", "", "STRONG", "R3", "state_variants / class_decisions")
    if o["mirror_routes"] and (rel == "mirror" or fr == "mirror"):
        edge("DERIVED_FROM", "", "STRONG", "R4", "зеркало семейства")
    for v in variants:
        if o["variant_one_way_derived"] and v["side"] == "derived":
            edge("DERIVED_FROM", v["relative"], "STRONG", "R4v", "%s %s, функция в одну сторону" % (
                v["kind"], v["relative"]))
        else:
            evid("R4v", "%s %s - основа не доказана" % (v["kind"], v["relative"]))
    if src and o["origin_mode"] == "evidence":
        evid("R7o", "улика основы: %s %s - набор из оригинальных данных игры" % (src[0]["kind"], src[0]["relative"]))
    opened = [b for b in blockers if b in v6.OPEN_V6]
    if a in fam_review:
        opened.append("review семейства")
    if rel == "alternate_view" or fr == "alternate_view":
        opened.append("alternate_view")
    if opened:
        evid("R7", " ".join(opened))
    if o["recolor_candidate_review"]:
        for r in rec:
            if r["level"] != "STRONG":
                evid("R7r", "%s %s" % (r["kind"], r["relative"]))
    for x in der:
        if x["v6"] in ("candidate", "die_weak"):
            evid("R7m", "MCD %s %s: %s" % (x["via"], x["base"], x["v6_why"]))
    if o["alt_review"]:
        for x in mlinks:
            if x["v6"] == "alt":
                evid("R7a", "MCD alt %s" % x["relative"])
    for r in rs:
        if r["kind"] in v6.EVIDENCE_ONLY:
            evid("R7n", "%s %s" % (r["kind"], r["relative"]))
    # D1 (PROVISIONAL): открытое неподвижное состояние двери - не фаза; ребро анимации к той же цели меняет вид
    d = door_state(fs) if door else None
    if d:
        why = "%s: %s" % (d["relative"], TXT_MEANING[d["meaning"]])
        same = [e for e in E if e["relation_type"] == "ANIMATION_FAMILY" and e["target"].upper() == d["relative"].upper()]
        for e in same:
            e.update(relation_type="STATE_VARIANT_OF", confidence="PROVISIONAL", rule="D1", evidence=why)
        if not same and not any(e["relation_type"] in ("STATE_VARIANT_OF", "DESTROYED_VARIANT_OF") and
                                e["target"].upper() == d["relative"].upper() for e in E):
            edge("STATE_VARIANT_OF", d["relative"], "PROVISIONAL", "D1", why)
    # R7t в V7 стоит на месте R8, а перекраска (pair_pick) R8 не отменяла - смотреть и у пары перекраски
    if not ev and o["adjacency"] and all(e["relation_type"] == "RECOLOR_PEER" for e in E):
        hit, n, share = v7.adjacency_hit(a, kind, pr["adj"], o["adj_min"])
        if hit:
            evid("R7t", "PROVISIONAL: вплотную к своей копии %.2f мест (%d)" % (share, n))
    if not E and not ev:
        edge("CANONICAL", "", "STRONG", "R8", "нет структурной роли, доказанной основы и улик")
    return E, ev


def role_set(edges):
    return sorted({e["relation_type"] for e in edges})


def render_group(a, edges, origin=()):
    """Техническая группа рисования пары перекраски: (render_group_id, render_anchor) или ("", ""). Якорь - что рисуем
    первым, а не истинный оригинал: сначала кадр из набора оригинальных данных игры, затем меньший ключ. Связь
    RECOLOR_PEER при этом остаётся симметричной, DERIVED_FROM не появляется."""
    peers = {e["target"] for e in edges if e["relation_type"] == "RECOLOR_PEER"}
    if not peers:
        return "", ""
    members = sorted({a} | peers, key=str.upper)
    anchor = min(members, key=lambda k: (k.split(":")[0].upper() not in origin, k.upper()))
    return "rg:" + "+".join(members), anchor


# ---------------------------------------------------------------- граф: одно направленное ребро, обратное чтение

INVERSE = {"DESTROYED_VARIANT_OF": "HAS_DESTROYED_VARIANT", "STATE_VARIANT_OF": "HAS_STATE_VARIANT",
           "ANIMATION_FAMILY": "HAS_ANIMATION_FRAME", "DERIVED_FROM": "HAS_DERIVED",
           "MATERIAL_VARIANT_OF": "HAS_MATERIAL_VARIANT", "RECOLOR_PEER": "RECOLOR_PEER"}
SYMMETRIC = ("RECOLOR_PEER",)


class Graph:
    """Каждое отношение хранится один раз: направленное ребро от производного кадра к основе (симметричное - по
    упорядоченной паре). relations_out / relations_in читают его с двух сторон; обратное чтение - не второе
    отношение и не второй довод (специалист 02.10)."""

    def __init__(self):
        self.edges = {}

    @staticmethod
    def key(e):
        s, t = e["source"].upper(), e["target"].upper()
        if e["relation_type"] in SYMMETRIC:
            s, t = min(s, t), max(s, t)
        return s, e["relation_type"], t

    def add(self, e):
        if e["relation_type"] == "CANONICAL" or not e["target"]:
            return
        self.edges.setdefault(self.key(e), e)

    def relations_out(self, a):
        A = a.upper()
        out = [e for k, e in self.edges.items() if k[0] == A or (k[1] in SYMMETRIC and k[2] == A)]
        return [dict(e, source=a, target=e["target"] if e["source"].upper() == A else e["source"]) for e in out]

    def relations_in(self, a):
        A = a.upper()
        return [{"relation_type": INVERSE.get(k[1], "INVERSE_" + k[1]), "source": a, "target": e["source"],
                 "inverse_of": k[1], "confidence": e["confidence"], "rule": e["rule"], "evidence": e["evidence"]}
                for k, e in self.edges.items() if k[2] == A and k[1] not in SYMMETRIC]


def build_graph(rows, pr, mcd, door=True):
    """Граф из рёбер строк и связей MCD, где кадр строки - основа (side base в mcd_state.index): это рёбра соседа,
    прочитанные тем же правилом (anim, die_ok; D1 по фактам соседа)."""
    g = Graph()
    for r in rows:
        for e in r["edges"]:
            g.add(e)
        a = r["asset_id"]
        for x in pr["view"].get(a, []):
            if x["side"] != "base" or x["v6"] not in ("anim", "die_ok"):
                continue
            s = x["state"]
            t, conf, rule, why = ("ANIMATION_FAMILY", "STRONG", "R3a", "MCD anim %s, основа %s" % (a, x["root"])) \
                if x["v6"] == "anim" else ("DESTROYED_VARIANT_OF", "STRONG", "R3m", "MCD die %s, основа %s (%s)" % (
                    a, x["root"], x["v6_why"]))
            d = door_state(facts(mcd, s)) if door and mcd is not None else None
            if d and d["relative"].upper() == a.upper() and t == "ANIMATION_FAMILY":
                t, conf, rule, why = "STATE_VARIANT_OF", "PROVISIONAL", "D1", "%s: %s" % (a, TXT_MEANING[d["meaning"]])
            g.add({"relation_type": t, "source": s, "target": a, "confidence": conf, "rule": rule, "evidence": why})
    return g


def pipeline_of(kind, surf_level, roles):
    """Ось B. (конвейер, почему). Связь меняет конвейер только у OBJECT_PART без целого или основы."""
    if kind in ("", "UNSURE") or kind not in PIPELINE_OF:
        return "REVIEW", "ось A %s" % (kind or "-")
    if kind == "OBJECT" and surf_level:
        return "REVIEW", "OBJECT с уликой поверхности MCD (%s): вещь или поверхность?" % surf_level
    if kind == "OBJECT_PART" and not (set(roles) - {"CANONICAL", "RECOLOR_PEER"}):    # пара перекраски - не целое
        return "REVIEW", "OBJECT_PART без доказанного целого или основы"
    return PIPELINE_OF[kind], "ось A %s" % kind


def decide(a, sk, pr, umap, fs, opts=None):
    """Три оси для кадра a: ось A ответа sk, подготовка V7 pr (routing_rules_v7.prepare), факты MCD fs."""
    import routing_rules_v6 as v6
    o = dict({"door": True}, **(opts or {}))
    lvl, swhy = pr["surf"][a]
    kind = v6.semantic_v6(sk, lvl, "strong", False)
    E, ev = relations(a, kind, pr, umap, fs, o["door"])
    roles = role_set(E)
    pipe, pwhy = pipeline_of(kind, lvl, roles)
    gid, anchor = render_group(a, E, pr["origin"])
    return {"asset_id": a, "semantic_kind": sk, "semantic_eff": kind, "surface": lvl, "pipeline_target": pipe,
            "render_group_id": gid, "render_anchor": anchor,
            "pipeline_why": pwhy, "relation_roles": roles, "relation_groups": sorted({ROLE_GROUP[t] for t in roles}),
            "edges": E, "open_evidence": ev, "rules": sorted({e["rule"] for e in E} | {x["rule"] for x in ev}),
            "creative": pipe == "OBJECT_PIPELINE" and roles == ["CANONICAL"]}


def consistency(a, pr, umap, fs):
    """Сверка рёбер с маршрутом V7 (без D1): одна роль V7, если она не OPEN, обязана быть в наборе; R8 V7 <=> набор
    {CANONICAL}. Пустой список - сходится."""
    import routing_rules_v7 as v7
    E, ev = relations(a, "OBJECT", pr, umap, fs, door=False)
    roles = role_set(E)
    unit, rule, why, _k, _p = v7.route_v7(a, "OBJECT", pr["meta7"], pr["view"][a], ("", ""), pr["variants7"][a],
                                          umap, dict(origin_sets=pr["origin"]), pr["adj"])
    r7 = role_of(rule, why, unit)
    bad = []
    if r7 == "CANONICAL" and _p:
        r7 = "RECOLOR_PEER"                       # pair_pick V7 - то же отношение, теперь ребром
    if r7 != "OPEN" and r7 not in roles:
        bad.append("V7 %s (%s) нет в наборе %s" % (r7, rule, roles))
    # R8 V7 (одиночный заказ, с pair_pick или без) <=> без улик и набор {CANONICAL} или {RECOLOR_PEER}
    if (rule == "R8") != (not ev and roles in (["CANONICAL"], ["RECOLOR_PEER"])):
        bad.append("V7 %s, набор %s" % (rule, roles))
    if rule == "R8" and bool(_p) != (roles == ["RECOLOR_PEER"]):
        bad.append("V7 pair_pick %s, набор %s" % (_p, roles))
    return bad


# ---------------------------------------------------------------- эталон в осях V8 (из замороженного эталона V7)

REF_ROLE_OF_ROUTE = {"STANDALONE_RENDER": {"canonical"}, "COMPOSITE_PART": {"composite"},
                     "STRUCTURAL_MODULAR": {"modular"}, "STATE_VARIANT": {"state"}, "DERIVED": {"derived"},
                     "ANIMATION_FAMILY": {"animation"}}
REF_ROLE_OF_RELATION = {"STATE_VARIANT_OF": {"state"}, "DERIVED_FROM": {"derived"}, "RECOLOR_OF": {"derived"},
                        "STRUCTURAL_RELATION": {"composite", "modular"}, "ANIMATION_FRAME_OF": {"animation"}}


def ref_axes(r, pairs, fs):
    """(ref_pipeline, ref_role_groups | None, статус роли): детерминированное прочтение эталона V7, эталон не правится.
    Статус: judged | not_judged (EXCLUDE поглотил связь) | uninformed (у кадра входящее ребро MCD, которого досье
    не показывало, R-171) | open."""
    sk = r.get("ref_semantic_kind") or "open"
    pipe = PIPELINE_OF.get(sk, "open")
    if any(x["dir"] == "IN" and not shown_in_v7(fs, x["relative"]) for x in fs):
        return pipe, None, "uninformed"
    route, rel = r.get("ref_route") or "open", r.get("ref_relation") or "OPEN"
    if route == "EXCLUDE":
        g = REF_ROLE_OF_RELATION.get(rel)
        return pipe, g, "judged" if g else "not_judged"
    if route == "open":
        return pipe, None, "open"
    g = set(REF_ROLE_OF_ROUTE.get(route, set()))
    if route == "STANDALONE_RENDER" and any(p["ref_pair_relation"] == "ANIMATION_FRAME_OF" and
                                            p.get("direction") == "relative_derived" for p in pairs):
        g = {"animation"}                    # голова петли по эталону - член семейства анимации
    return pipe, g, "judged" if g else "open"


# ---------------------------------------------------------------- метрики и ворота

def rate(k, n):
    return round(k / n, 3) if n else None


NON_OBJECT = ("STRUCTURAL_PIPELINE", "TERRAIN_PIPELINE", "NONE")


def dangerous_creative_standalone(row):
    """Одиночный творческий заказ там, где эталону нужен другой конвейер или связь (GATE_DEFS)."""
    if not row["creative"]:
        return False
    if row["ref_pipeline"] in NON_OBJECT:
        return True
    g = row["ref_role_groups"]
    return bool(row["ref_role_status"] == "judged" and g and "canonical" not in g)


def wrong_pipeline(row):
    """Прежняя строгая мера: решённый конвейер не совпал с закрытым эталонным."""
    return row["ref_pipeline"] != "open" and row["pipeline_target"] not in ("REVIEW", row["ref_pipeline"])


def d1_outcome(row, pairs):
    """D1 на кадре: '' (не сработал) | correct | wrong | unresolved (GATE_DEFS["D1"])."""
    d1 = [e for e in row["edges"] if e["rule"] == "D1"]
    if not d1:
        return ""
    tgt = {e["target"].upper() for e in d1}
    pr_ = [p for p in pairs if p["relative"].upper() in tgt]
    if row["ref_role_status"] == "judged" and "state" in row["ref_role_groups"] or \
            any(p["ref_pair_relation"] == "STATE_VARIANT_OF" for p in pr_):
        return "correct"
    if row["ref_role_status"] == "judged" or any(p["ref_pair_relation"] not in ("", "OPEN") for p in pr_):
        return "wrong"
    return "unresolved"


RECOLOR_REF = ("RECOLOR_OF", "DERIVED_FROM", "RECOLOR_PEER")


def rp_outcomes(row, pairs):
    """RECOLOR_PEER по каждому ребру кадра: correct | wrong | unresolved (GATE_DEFS["RECOLOR_PEER"]). Направление
    эталона не сверяется: связь симметрична."""
    out = []
    for e in row["edges"]:
        if e["relation_type"] != "RECOLOR_PEER":
            continue
        p = [x for x in pairs if x["relative"].upper() == e["target"].upper()]
        if any(x["ref_pair_relation"] in RECOLOR_REF for x in p):
            out.append("correct")
        elif any(x["ref_pair_relation"] not in ("", "OPEN") for x in p):
            out.append("wrong")
        elif not p and row["ref_role_status"] == "judged":
            out.append("correct" if "derived" in row["ref_role_groups"] else "wrong")
        else:
            out.append("unresolved")
    return out


def metrics(rows):
    closed = [r for r in rows if r["ref_pipeline"] != "open"]
    dec = [r for r in closed if r["pipeline_target"] != "REVIEW"]
    ok = [r for r in dec if r["pipeline_target"] == r["ref_pipeline"]]
    wrong = [r for r in rows if wrong_pipeline(r)]
    dang = [r for r in rows if dangerous_creative_standalone(r)]
    sem = [r for r in rows if r["semantic_kind"] not in ("UNSURE", "") and r["ref_semantic_kind"] != "open"]
    judged = [r for r in rows if r["ref_role_status"] == "judged"]
    rdec = [r for r in judged if r["relation_groups"]]
    by = {}
    for g in GROUPS:
        pred = [r for r in rdec if g in r["relation_groups"]]
        ref = [r for r in judged if g in r["ref_role_groups"]]
        by[g] = {"precision": rate(sum(g in r["ref_role_groups"] for r in pred), len(pred)), "predicted": len(pred),
                 "recall": rate(sum(g in r["relation_groups"] for r in ref), len(ref)), "reference": len(ref)}
    d1 = Counter(r["d1"] for r in rows if r["d1"])
    rp = Counter(x for r in rows for x in r.get("rp", []))
    return {"n": len(rows), "pipeline_closed": len(closed), "pipeline_decided": len(dec), "pipeline_ok": len(ok),
            "pipeline_accuracy": rate(len(ok), len(dec)), "pipeline_coverage": rate(len(dec), len(closed)),
            "dangerous_creative_standalone": len(dang), "dangerous_assets": [r["asset_id"] for r in dang],
            "wrong_pipeline_classification": len(wrong), "wrong_assets": [r["asset_id"] for r in wrong],
            "wrong_object_for_non_object": sum(r["pipeline_target"] == "OBJECT_PIPELINE" and
                                               r["ref_pipeline"] in NON_OBJECT for r in wrong),
            "creative_render": sum(r["creative"] for r in rows),
            "semantic_axis_accuracy": rate(sum(r["semantic_kind"] == r["ref_semantic_kind"] for r in sem), len(sem)),
            "semantic_n": len(sem),
            "role_judged": len(judged), "role_decided": len(rdec),
            "role_overlap": rate(sum(bool(set(r["relation_groups"]) & set(r["ref_role_groups"])) for r in rdec),
                                 len(rdec)),
            "role_exact": rate(sum(set(r["relation_groups"]) == set(r["ref_role_groups"]) for r in rdec), len(rdec)),
            "role_coverage": rate(len(rdec), len(judged)),
            "multi_relation": sum(len(r["relation_roles"]) > 1 for r in rows),
            "role_status": dict(Counter(r["ref_role_status"] for r in rows)), "relation_by_type": by,
            "pipelines": dict(Counter(r["pipeline_target"] for r in rows)),
            "roles": dict(Counter(t for r in rows for t in r["relation_roles"])),
            "open_rows": sum(not r["relation_roles"] for r in rows),
            "D1_triggered": sum(d1.values()), "D1_correct": d1["correct"], "D1_wrong": d1["wrong"],
            "D1_unresolved": d1["unresolved"],
            "RECOLOR_PEER_triggered": sum(rp.values()), "RECOLOR_PEER_correct": rp["correct"],
            "RECOLOR_PEER_wrong": rp["wrong"], "RECOLOR_PEER_unresolved": rp["unresolved"],
            "render_groups": len({r["render_group_id"] for r in rows if r.get("render_group_id")})}


def precision(claims):
    ok = sum(c["status"] == "ok" for c in claims)
    bad = sum(c["status"] == "wrong" for c in claims)
    return {"relation_precision": rate(ok, ok + bad), "ok": ok, "closed": ok + bad, "claims": len(claims),
            "fact_only": sum(c["status"] == "fact_only" for c in claims),
            "excluded": sum(c["status"] == "excluded" for c in claims)}


def gate_checks(e2e, logic, ps, g=GATES_V8):
    """Ворота маршрута V8: опасный - при оси A специалиста (e2e) и при оси A эталона (logic); конвейер - logic."""
    def ge(v, lim):
        return None if v is None else v >= lim
    s = ps["strong"]
    strong = None if s["closed"] < g["strong_closed_min"] else s["relation_precision"] >= g["strong_relation_precision_min"]
    lim = g["dangerous_creative_standalone_max"]
    return {"B_SAFETY: dangerous_creative_standalone = 0 (ось A эталона)":
                logic["dangerous_creative_standalone"] <= lim,
            "E2E_SAFETY: dangerous_creative_standalone = 0 (ось A специалиста)":
                e2e["dangerous_creative_standalone"] <= lim,
            "pipeline_logic_accuracy >= %.2f" % g["pipeline_logic_accuracy_min"]:
                ge(logic["pipeline_accuracy"], g["pipeline_logic_accuracy_min"]),
            "pipeline_logic_coverage >= %.2f" % g["pipeline_logic_coverage_min"]:
                ge(logic["pipeline_coverage"], g["pipeline_logic_coverage_min"]),
            "strong_relation_precision >= %.2f при >= %d закрытых" % (g["strong_relation_precision_min"],
                                                                       g["strong_closed_min"]): strong}


def semantic_check(e2e, g=SEMANTIC_GATE):
    v = e2e["semantic_axis_accuracy"]
    return None if v is None else v >= g["semantic_axis_accuracy_min"]


def verdict(checks):
    v = list(checks.values())
    if False in v:
        return "FAIL"
    if None in v:
        return "INSUFFICIENT_SAMPLE"
    return "PASS"


# ---------------------------------------------------------------- утверждения: факт отдельно от смысла

def claims_v8(raw, fsets, refp, door=True, exclude=()):
    """Утверждения V7 (raw) в V8: D1 меняет смысл ребра двери на STATE_VARIANT_OF; ребро MCD, которого досье эталона
    не показывало (только входящее), - fact_only: факт установлен, смысл эталоном не судился (R-171); пары exclude -
    сняты специалистом. Остальное - как routing_rules_v7.score."""
    import routing_rules_v7 as v7
    conv, meta = [], []
    for k, rel_to, kind, level, side, src in raw:
        fs = fsets.get(k.upper(), [])
        link = [x for x in fs if x["relative"].upper() == rel_to.upper()]
        if door and src == "mcd_anim" and any(x["meaning"] in ("DOOR_OPEN_STATE", "DOOR_STATE") for x in link):
            kind = "STATE_VARIANT_OF"
        conv.append((k, rel_to, kind, level, side, src))
        meta.append(link)
    out = v7.score(conv, refp)
    for c, link in zip(out, meta):
        c["fact"] = ";".join(sorted({"%s %s %s" % (x["dir"], x["via"], x["meaning"]) for x in link}))
        c["shown_in_v7"] = shown_in_v7(link, c["relative"]) if link else None
        if (c["asset_id"].upper(), c["relative"].upper()) in {(a.upper(), b.upper()) for a, b in exclude}:
            c["status"] = "excluded"
        elif c["source"].startswith("mcd_") and link and not c["shown_in_v7"]:
            c["status"] = "fact_only"
    return out


def precision_split(claims):
    return {"all": precision(claims), "strong": precision([c for c in claims if c["level"] == "STRONG"]),
            "candidate": precision([c for c in claims if c["level"] != "STRONG"])}


# ---------------------------------------------------------------- пересчёт тех же 60

EXCLUDED_PAIRS = (("URBITS_WASTE:24", "URBITS_WASTE:11"),)     # специалист 02.10: эталон пары не для решения


def build(pr, keys, ans, ref, refp_by, fsets, umap, axis="answers", **opts):
    rows = []
    for a in keys:
        sk = ans.get(a, {}).get("semantic_kind", "")
        if axis == "ref":
            sk = ref.get(a, {}).get("ref_semantic_kind", "") if ref.get(a, {}).get("ref_semantic_kind") not in (
                None, "", "open") else sk
        row = decide(a, sk, pr, umap, fsets[a.upper()], opts)
        rp, rg, st = ref_axes(ref.get(a, {}), refp_by.get(a, []), fsets[a.upper()])
        row.update({"axis": axis, "ref_semantic_kind": ref.get(a, {}).get("ref_semantic_kind") or "open",
                    "ref_route": ref.get(a, {}).get("ref_route") or "open", "ref_pipeline": rp,
                    "ref_role_groups": sorted(rg) if rg else [], "ref_role_status": st})
        row["d1"] = d1_outcome(row, refp_by.get(a, []))
        row["rp"] = rp_outcomes(row, refp_by.get(a, []))
        rows.append(row)
    return rows


def recount(out=OUT, hold=HOLD_V7):
    import family_relation_v2 as fr2m
    import map_mockup as mm
    import routing_holdout as rh
    import routing_holdout_v7 as h7
    import routing_rules_v5 as v5
    import routing_rules_v7 as v7
    before = v5.dir_sha(hold)
    d, h = h7.load_freeze(hold), h7.load_holdout(hold)
    changed = h7.code_changed(d)
    if changed:
        raise SystemExit("замороженный код V7 изменён: %s" % ", ".join(changed))
    h7.live_same(d)
    ref, refp, lk = h7.load_reference(hold)
    ans = {r["asset_id"]: r for r in ir.read_tsv(os.path.join(hold, "answers_vitali.tsv"))}
    rep7 = ir.load_json(os.path.join(hold, "report.json"))
    rels = h7.load_relations(hold)
    inp, keys, pr = h7.prepared(hold, d, h)
    umap = d["routing"]["relation_unit"]
    fr2 = fr2m.load(inp["family_relation_v2"])
    mcd = Mcd(mm.World())
    fsets = {a.upper(): facts(mcd, a) for a in keys}
    refp_by = {}
    for p_ in refp:
        refp_by.setdefault(p_["asset_id"], []).append(p_)

    def run(**kw):
        return build(pr, keys, ans, ref, refp_by, fsets, umap, **kw)

    rows = run()                                   # end-to-end: ось A специалиста
    lrows = run(axis="ref")                        # logic: ось A эталона
    m, lm = metrics(rows), metrics(lrows)
    raw, _dropped, _conv = v7.claims_of(pr, keys, rels, fr2)
    claims = claims_v8(raw, fsets, refp, exclude=EXCLUDED_PAIRS)
    ps = precision_split(claims)
    checks = gate_checks(m, lm, ps)
    incons = {a: b for a in keys for b in [consistency(a, pr, umap, fsets[a.upper()])] if b}
    # чувствительность (не итог)
    sens = {"без D1, ось A специалиста": metrics(run(door=False)),
            "без D1, ось A эталона": metrics(run(axis="ref", door=False))}
    sens_rel = {"без D1": precision_split(claims_v8(raw, fsets, refp, door=False, exclude=EXCLUDED_PAIRS)),
                "эталон как есть (без R-171 и снятий, как в V7)": precision_split(v7.score(raw, refp))}
    # V7 в осях V8: EXCLUDE -> handoff_target, остальное - предметный конвейер; связь - одна роль V7
    r7 = {r["asset_id"]: r for r in rep7["rows"]}
    unit_role = {"STANDALONE_RENDER": ["CANONICAL"], "COMPOSITE_PART": ["COMPOSITE_PART"],
                 "STRUCTURAL_MODULAR": ["STRUCTURAL_MODULAR"], "STATE_VARIANT": ["STATE_VARIANT_OF"],
                 "DERIVED": ["DERIVED_FROM"], "ANIMATION_FAMILY": ["ANIMATION_FAMILY"]}
    v7_rows = []
    for r in rows:
        u = r7[r["asset_id"]]["rule_unit"]
        roles = unit_role.get(u, [])
        v7_rows.append(dict(r, pipeline_target=(r7[r["asset_id"]]["handoff_target"] or "REVIEW") if u == "EXCLUDE"
                            else ("REVIEW" if u == "REVIEW" else "OBJECT_PIPELINE"),
                            relation_roles=roles, relation_groups=sorted({ROLE_GROUP[t] for t in roles}),
                            creative=u == "STANDALONE_RENDER", d1="", rp=[], render_group_id=""))
    sens["V7 (замороженный маршрут, одна роль) в осях V8"] = metrics(v7_rows)
    # граф: одно ребро на отношение, обратное чтение у основы
    graph = build_graph(rows, pr, mcd)
    for r in rows:
        r["relations_out"], r["relations_in"] = graph.relations_out(r["asset_id"]), graph.relations_in(r["asset_id"])
    gstat = {"stored_edges": len(graph.edges),
             "row_edges": sum(e["relation_type"] != "CANONICAL" and bool(e["target"]) for r in rows for e in r["edges"]),
             "inverse_views": sum(len(r["relations_in"]) for r in rows),
             "inverse_by_type": dict(Counter(x["relation_type"] for r in rows for x in r["relations_in"]))}
    hop = {a: neighbourhood(mcd, a)[1] for a in keys}
    after = v5.dir_sha(hold)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "ROUTING_MODEL_V8_FREEZE_CHECK",
           "graph": gstat,
           "diagnostic_only": True,
           "not_blind": "V8 написан после ответов и эталона этих 60; V7 остаётся FAIL, его report.md не меняется; "
                        "V8_PREP и пересчёт до заморозки (prefreeze) задним числом не PASS",
           "holdout": hold.replace(os.sep, "/"), "holdout_untouched": before == after,
           "v7_freeze_sha256": d["sha256"], "v7_code_unchanged": not changed, "reference_locked": lk["created"],
           "v7_verdict": rep7["verdict"], "code_sha256": {c: rh.file_sha(c) for c in CODE},
           "gates": GATES_V8, "semantic_gate": SEMANTIC_GATE, "gate_defs": GATE_DEFS, "checks": checks,
           "semantic_check": semantic_check(m), "verdict_if_frozen": verdict(checks),
           "metrics_end_to_end": m, "metrics_logic": lm, "relations": ps,
           "by_source": {s: precision([c for c in claims if c["source"] == s])
                         for s in sorted({c["source"] for c in claims})},
           "consistency_with_v7": incons, "d1_rule": "PROVISIONAL", "l1_rule": "NOT_ACTIVE",
           "sensitivity": sens, "sensitivity_relations": sens_rel, "excluded_pairs": [list(x) for x in EXCLUDED_PAIRS],
           "ontology": ONTOLOGY_V8, "rules_fired": dict(Counter(x for r in rows for x in r["rules"])),
           "rows": rows, "rows_logic": lrows, "claims": claims, "facts": {a: fsets[a.upper()] for a in keys},
           "neighbourhood": hop}
    os.makedirs(out, exist_ok=True)
    ir.dump_json(os.path.join(out, "recount.json"), res)
    write_edges(os.path.join(out, "relation_edges.tsv"), rows)
    write_facts(os.path.join(out, "relation_facts.tsv"), keys, fsets, hop)
    write_dossier(os.path.join(out, "dossier_mcd.md"), keys, mcd)
    write_md(out, res)
    if not res["holdout_untouched"]:
        raise SystemExit("папка holdout V7 изменилась во время пересчёта - так быть не должно")
    return res


FACT_HEAD = ["asset_id", "hop_from", "relative", "via", "dir", "record", "rel_record", "pos", "door", "meaning",
             "shown_in_v7_dossier"]


EDGE_HEAD = ["asset_id", "relation_type", "source", "target", "confidence", "rule", "evidence", "view"]


def write_edges(path, rows):
    """Ось C набором, ось A специалиста. view: own - ребро кадра; inverse - обратное чтение ребра соседа
    (relations_in, не второе отношение); evidence - улика без связи; render - техническая группа рисования."""
    L = ["\t".join(EDGE_HEAD)]
    for r in rows:
        for e in r["edges"]:
            L.append("\t".join([r["asset_id"], e["relation_type"], e["source"], e["target"], e["confidence"],
                                e["rule"], e["evidence"], "own"]))
        for e in r.get("relations_in", []):
            L.append("\t".join([r["asset_id"], e["relation_type"], e["source"], e["target"], e["confidence"],
                                e["rule"], "обратное чтение %s: %s" % (e["inverse_of"], e["evidence"]), "inverse"]))
        for x in r["open_evidence"]:
            L.append("\t".join([r["asset_id"], "OPEN_EVIDENCE", r["asset_id"], "", "", x["rule"], x["evidence"],
                                "evidence"]))
        if r.get("render_group_id"):
            L.append("\t".join([r["asset_id"], "RENDER_GROUP", r["asset_id"], r["render_anchor"], "", "",
                                "%s: якорь - что рисуем первым, не основа" % r["render_group_id"], "render"]))
    with open(path, "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")


def write_facts(path, keys, fsets, hop):
    L = ["\t".join(FACT_HEAD)]
    for a in keys:
        own = fsets[a.upper()]
        for x in own:
            L.append("\t".join([a, "", x["relative"], x["via"], x["dir"], str(x["record"]), str(x["rel_record"]),
                                ",".join(map(str, x["pos"])), x["door"], x["meaning"],
                                "yes" if x["dir"] == "OUT" else "no"]))
        for rel, fs in sorted(hop[a].items()):
            for x in fs:
                L.append("\t".join([a, rel, x["relative"], x["via"], x["dir"], str(x["record"]), str(x["rel_record"]),
                                    ",".join(map(str, x["pos"])), x["door"], x["meaning"], "-"]))
    with open(path, "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")


def write_dossier(path, keys, mcd):
    L = ["# Досье MCD V8 (R-171): связи в обе стороны и окрестность в один шаг", "",
         "Образец блока «5. запись MCD» для следующего пакета эталона. Факт - из записей MCD установки; смысл решает "
         "судья: разрушенный вид / псевдоним / необычное повторное использование / OPEN.", ""]
    for a in keys:
        L += ["## " + a, ""] + ["    " + x for x in dossier_lines(mcd, a)] + [""]
    with open(path, "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")


def write_md(out, res):
    m, lm, ps, ck = res["metrics_end_to_end"], res["metrics_logic"], res["relations"], res["checks"]
    yes = {True: "да", False: "**нет**", None: "мало данных"}
    cv = list(ck.values())

    def pr_(x):
        return "%s (%d/%d)" % (x["relation_precision"], x["ok"], x["closed"])
    L = ["# ROUTING_MODEL_V8 перед заморозкой - проверка реализации на тех же 60 (диагностика)", "",
         "%s V7 остаётся **%s**, report.md holdout V7 не менялся (папка holdout не тронута: %s, код V7 тот же: %s). "
         "V8_PREP задним числом не PASS." % (res["created"], res["v7_verdict"], res["holdout_untouched"],
                                            res["v7_code_unchanged"]),
         "Это не слепой итог: V8 написан после ответов и эталона этих 60. Ось C - набор рёбер, D1 %s, L1 %s." % (
             res["d1_rule"], res["l1_rule"]), "",
         "| ворота V8 | значение | |", "|---|---|---|",
         "| B_SAFETY: dangerous_creative_standalone = 0, ось A эталона | %d %s | %s |" % (
             lm["dangerous_creative_standalone"], " ".join(lm["dangerous_assets"]), yes[cv[0]]),
         "| E2E_SAFETY: dangerous_creative_standalone = 0, ось A специалиста | %d %s | %s |" % (
             m["dangerous_creative_standalone"], " ".join(m["dangerous_assets"]), yes[cv[1]]),
         "| pipeline_logic_accuracy >= 0.95 | %s (%d/%d) | %s |" % (lm["pipeline_accuracy"], lm["pipeline_ok"],
                                                                  lm["pipeline_decided"], yes[cv[2]]),
         "| pipeline_logic_coverage >= 0.70 | %s (%d/%d) | %s |" % (lm["pipeline_coverage"], lm["pipeline_decided"],
                                                                  lm["pipeline_closed"], yes[cv[3]]),
         "| strong_relation_precision >= 0.95, >= 10 закрытых | %s | %s |" % (pr_(ps["strong"]), yes[cv[4]]),
         "", "Вердикт, если бы V8 был заморожен: **%s**. Заморозку и новый holdout решает специалист." % (
             res["verdict_if_frozen"]), "",
         "| вне вердикта маршрута | значение |", "|---|---|",
         "| semantic_axis_accuracy >= 0.85 (ворота карточки и оператора) | %s (n %d) - %s |" % (
             m["semantic_axis_accuracy"], m["semantic_n"], yes[res["semantic_check"]]),
         "| end_to_end_pipeline_accuracy (без ворот) | %s (%d/%d), охват %s |" % (
             m["pipeline_accuracy"], m["pipeline_ok"], m["pipeline_decided"], m["pipeline_coverage"]),
         "| wrong_pipeline_classification, ось A специалиста | %d (из них OBJECT при не-OBJECT эталоне %d): %s |" % (
             m["wrong_pipeline_classification"], m["wrong_object_for_non_object"], " ".join(m["wrong_assets"])),
         "| wrong_pipeline_classification, ось A эталона | %d %s |" % (lm["wrong_pipeline_classification"],
                                                                     " ".join(lm["wrong_assets"])),
         "| одиночных творческих заказов (специалист / эталон) | %d / %d |" % (m["creative_render"],
                                                                          lm["creative_render"]),
         "| relation_precision_candidate | %s |" % pr_(ps["candidate"]),
         "| D1: triggered / correct / wrong / unresolved | %d / %d / %d / %d |" % (
             m["D1_triggered"], m["D1_correct"], m["D1_wrong"], m["D1_unresolved"]),
         "| RECOLOR_PEER: triggered / correct / wrong / unresolved | %d / %d / %d / %d (групп рисования %d) |" % (
             m["RECOLOR_PEER_triggered"], m["RECOLOR_PEER_correct"], m["RECOLOR_PEER_wrong"],
             m["RECOLOR_PEER_unresolved"], m["render_groups"]),
         "| граф: хранимых рёбер / рёбер в строках / обратных чтений | %d / %d / %d (%s) |" % (
             res["graph"]["stored_edges"], res["graph"]["row_edges"], res["graph"]["inverse_views"],
             ", ".join("%s %d" % kv for kv in sorted(res["graph"]["inverse_by_type"].items())) or "-"),
         "| связь (группы): пересечение / точно / охват | %s / %s / %s (решено %d из %d судимых) |" % (
             m["role_overlap"], m["role_exact"], m["role_coverage"], m["role_decided"], m["role_judged"]),
         "| кадров с несколькими связями | %d |" % m["multi_relation"],
         "| кадров без связи (только улики) | %d |" % m["open_rows"],
         "| статус связи в эталоне | %s |" % ", ".join("%s %d" % kv for kv in sorted(m["role_status"].items())),
         "| факт MCD без суждения (R-171) / снято специалистом | %d / %d |" % (ps["all"]["fact_only"],
                                                                             ps["all"]["excluded"]),
         "| сверка рёбер с маршрутом V7 (без D1) | %s |" % ("сходится на всех 60" if not res["consistency_with_v7"]
                                                         else "расходится: %d" % len(res["consistency_with_v7"])),
         "| конвейеры (специалист) | %s |" % ", ".join("%s %d" % kv for kv in sorted(m["pipelines"].items())),
         "| рёбра по видам | %s |" % ", ".join("%s %d" % kv for kv in sorted(m["roles"].items())),
         "| сработавшие правила (рёбра и улики) | %s |" % ", ".join("%s %d" % kv for kv in
                                                                 sorted(res["rules_fired"].items())), "",
         "## Связь по видам (группы, набор против набора; диагностика)", "",
         "Эталон V7 размечен одной связью на кадр: лишнее, но верное ребро здесь считается ошибкой.", "",
         "| группа | точность | V8 дал | полнота | в эталоне |", "|---|---|---|---|---|"]
    for g, v in m["relation_by_type"].items():
        L.append("| %s | %s | %d | %s | %d |" % (g, v["precision"], v["predicted"], v["recall"], v["reference"]))
    L += ["", "## Утверждения по источникам", "", "| источник | точность | fact_only | снято |", "|---|---|---|---|"]
    for s, v in res["by_source"].items():
        L.append("| %s | %s | %d | %d |" % (s, pr_(v), v["fact_only"], v["excluded"]))
    L += ["", "## Чувствительность (не итог)", "",
          "| вариант | опасных творческих | конвейер точн. | охват | связь пересеч. |", "|---|---|---|---|---|"]
    for n, v in res["sensitivity"].items():
        L.append("| %s | %d %s | %s | %s | %s |" % (n, v["dangerous_creative_standalone"],
                                                   " ".join(v["dangerous_assets"]), v["pipeline_accuracy"],
                                                   v["pipeline_coverage"], v["role_overlap"]))
    for n, v in res["sensitivity_relations"].items():
        L.append("| STRONG, %s | | %s | | |" % (n, pr_(v["strong"])))
    for title, rows in (("ось A специалиста", res["rows"]), ("ось A эталона", res["rows_logic"])):
        wrong = [r for r in rows if wrong_pipeline(r)]
        L += ["", "## Неверный конвейер, %s (%d)" % (title, len(wrong)), ""]
        L += ["- %s: V8 %s (ось A %s), эталон %s (%s), связи %s%s" % (
            r["asset_id"], r["pipeline_target"], r["semantic_eff"], r["ref_pipeline"], r["ref_semantic_kind"],
            "+".join(r["relation_roles"]) or "нет (улики)",
            " - **опасный творческий**" if dangerous_creative_standalone(r) else "") for r in wrong]
        dang = [r for r in rows if dangerous_creative_standalone(r) and not wrong_pipeline(r)]
        if dang:
            L += ["", "Опасный творческий при верном конвейере, %s:" % title, ""]
            L += ["- %s: одиночный заказ (CANONICAL), эталон %s %s" % (
                r["asset_id"], r["ref_route"], "|".join(r["ref_role_groups"])) for r in dang]
    multi = [r for r in res["rows"] if len(r["relation_roles"]) > 1]
    L += ["", "## Кадры с несколькими связями (%d)" % len(multi), ""]
    L += ["- %s: %s; эталон %s (%s)" % (r["asset_id"], "; ".join(
        "%s %s [%s %s]" % (e["relation_type"], e["target"] or "-", e["rule"], e["confidence"]) for e in r["edges"]),
        "|".join(r["ref_role_groups"]) or "-", r["ref_role_status"]) for r in multi]
    rw = [r for r in res["rows"] if r["ref_role_status"] == "judged" and r["relation_groups"] and
          not set(r["relation_groups"]) & set(r["ref_role_groups"])]
    L += ["", "## Связь не пересекается с судимым эталоном (%d)" % len(rw), ""]
    L += ["- %s: V8 %s, эталон %s" % (r["asset_id"], "; ".join("%s [%s: %s]" % (e["relation_type"], e["rule"],
                                                                                 e["evidence"]) for e in r["edges"]),
                                     "|".join(r["ref_role_groups"])) for r in rw]
    peer = [r for r in res["rows"] if r["rp"]]
    L += ["", "## RECOLOR_PEER и группы рисования (%d)" % len(peer), "",
          "Связь симметрична, основа не назначается; якорь группы - что рисуем первым, не истинный оригинал.", ""]
    L += ["- %s: %s; группа %s, якорь %s; эталон %s (%s)" % (
        r["asset_id"], "; ".join("RECOLOR_PEER %s - %s" % (e["target"], o) for e, o in
                                 zip([e for e in r["edges"] if e["relation_type"] == "RECOLOR_PEER"], r["rp"])),
        r["render_group_id"], r["render_anchor"], "|".join(r["ref_role_groups"]) or "-", r["ref_role_status"])
        for r in peer]
    inv = [r for r in res["rows"] if r.get("relations_in")]
    L += ["", "## Обратное чтение (relations_in, %d кадров)" % len(inv), "",
          "Одно хранимое ребро соседа, прочитанное со стороны основы: не второе отношение и не второй довод.", ""]
    L += ["- %s: %s" % (r["asset_id"], "; ".join("%s %s [%s, ребро %s]" % (x["relation_type"], x["target"], x["rule"],
                                                                            x["inverse_of"]) for x in r["relations_in"]))
          for r in inv]
    d1 = [r for r in res["rows"] if r["d1"]]
    L += ["", "## D1 (PROVISIONAL)", ""]
    L += ["- %s: %s - %s" % (r["asset_id"], "; ".join(e["evidence"] for e in r["edges"] if e["rule"] == "D1"),
                             r["d1"]) for r in d1]
    if res["consistency_with_v7"]:
        L += ["", "## Расхождения с маршрутом V7", ""]
        L += ["- %s: %s" % (a, "; ".join(b)) for a, b in sorted(res["consistency_with_v7"].items())]
    bad = [c for c in res["claims"] if c["level"] == "STRONG" and c["status"] in ("wrong", "fact_only", "excluded")]
    L += ["", "## STRONG: неверные, только факт, снятые", ""]
    L += ["- %s ~ %s: %s, %s, эталон %s, факт MCD «%s»" % (c["asset_id"], c["relative"], c["kind"], c["status"],
                                                             c["ref"], c["fact"] or "-") for c in bad]
    L += ["", "Файлы: recount.json (строки обеих осей A, relations_out / relations_in), relation_edges.tsv (ось C "
          "набором: свои рёбра, обратные чтения, улики, группы рисования - столбец view), "
          "relation_facts.tsv (рёбра MCD 60 кадров и окрестность в один шаг), dossier_mcd.md (образец досье по R-171).",
          ""]
    with open(os.path.join(out, "recount.md"), "w", encoding=ir.ENC) as f:
        f.write("\n".join(L))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["recount", "facts", "dossier"])
    ap.add_argument("keys", nargs="*")
    a = ap.parse_args()
    os.chdir(ir.ROOT)
    if a.cmd == "recount":
        res = recount()
        print(open(os.path.join(OUT, "recount.md"), encoding=ir.ENC).read())
        return res
    import map_mockup as mm
    mcd = Mcd(mm.World())
    for k in a.keys:
        if a.cmd == "facts":
            for x in facts(mcd, k):
                print("%-20s %-3s %-4s %-20s rec %3d->%3d pos %-6s %-5s %s" % (
                    k, x["dir"], x["via"], x["relative"], x["record"], x["rel_record"], ",".join(map(str, x["pos"])),
                    x["door"], x["meaning"]))
        else:
            print("== " + k)
            print("\n".join(dossier_lines(mcd, k)))


if __name__ == "__main__":
    main()
