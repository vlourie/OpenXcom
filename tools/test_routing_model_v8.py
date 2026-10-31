#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/routing_model_v8.py на синтетике, у каждого изменения - контроль:
факты MCD в обе стороны - входящий die виден, досье пишет «нет» только без исходящих И входящих (контроль: своя
запись пуста, досье V7 сказало бы «нет»); дверь НЛО - Frame[7] открытое состояние, 1-6 фазы (контроль: та же петля без
флага двери - фаза петли); ось C - набор рёбер: кусок составного и разрушаемый сразу (контроль: V7 даёт одну роль);
STRUCTURAL_SURFACE -> STRUCTURAL_PIPELINE при любой связи (контроль: V7 даёт EXCLUDE и связь теряет); улика без
связи - не CANONICAL; D1 PROVISIONAL (контроль: выключен - ANIMATION_FAMILY) и его счётчики; L1 NOT_ACTIVE; опасный -
только одиночный творческий заказ, прежняя строгая мера отдельно; ворота: опасный при обеих осях A, конвейер при оси A
эталона, end_to_end и semantic не в вердикте; сверка с маршрутом V7 (контроль: потерянное ребро ловится); эталон в
осях V8 (uninformed по R-171); утверждение по входящему ребру - fact_only; онтология V8; раскладка байтов MCD.
Перед заморозкой: доказанная перекраска - ребро RECOLOR_PEER без основы и группа рисования (контроль: потерянное ребро
ловится сверкой с V7; подтверждённая основа - DERIVED_FROM R0v), счётчики RECOLOR_PEER; граф - одно ребро на
отношение и обратное чтение relations_in (контроль: ребро одно и без строки производного кадра); B_SAFETY и E2E_SAFETY.

    py -3.13 tools/test_routing_model_v8.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import routing_model_v8 as v8  # noqa: E402
import routing_rules_v7 as v7  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def rec(frames, die=0, alt=0, ufo=0, door=0):
    fr = list(frames) * (8 // len(frames)) if len(frames) < 8 else list(frames)
    return {"n": 0, "frames": fr[:8], "ufo": ufo, "door": door, "die": die, "alt": alt, "type": 3}


def mcd(*recs):
    rs = [dict(r, n=i) for i, r in enumerate(recs)]
    return v8.Mcd(recs={"S": rs})


def meta(gen=None, blockers=""):
    g = dict(gen or {})
    if blockers:
        g = {k: dict(v, blockers=blockers) for k, v in g.items()}
    return (g, {}, set(), set(), set(), {}, {})


def pr(a, view=(), surf=("", ""), gen=None, blockers=""):
    if blockers and not gen:
        gen = {a: {}}
    return {"surf": {a: surf}, "adj": {}, "origin": set(), "meta7": meta(gen, blockers), "view": {a: list(view)},
            "variants7": {a: []}}


def link(state, base, via="die", v6k="die_ok"):
    return {"state": state, "base": base, "via": via, "kind": "STATE_VARIANT_OF", "level": "STRONG", "why": "",
            "root": base, "side": "derived", "relative": base, "v6": v6k, "v6_why": ""}


def row(pipe, roles, ref_pipe, groups=(), status="judged", d1=""):
    roles = sorted(roles)
    return {"asset_id": "S:1", "pipeline_target": pipe, "relation_roles": roles,
            "relation_groups": sorted({v8.ROLE_GROUP[t] for t in roles}),
            "creative": pipe == "OBJECT_PIPELINE" and roles == ["CANONICAL"], "edges": [], "d1": d1,
            "ref_pipeline": ref_pipe, "ref_role_groups": sorted(groups), "ref_role_status": status,
            "semantic_kind": "OBJECT", "ref_semantic_kind": "OBJECT"}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    blank = rec([0])
    # -- факты в обе стороны
    m = mcd(blank, rec([1], die=2), rec([2]))
    fs = v8.facts(m, "S:2")
    check("входящий die: кадр 2 - разрушенный вид записи с кадром 1",
          [(x["dir"], x["via"], x["relative"], x["meaning"]) for x in fs] == [("IN", "die", "S:1", "DESTROYED_STATE")])
    check("контроль: своя запись пуста - досье V7 ребра не показывало", not v8.shown_in_v7(fs, "S:1"))
    d = "\n".join(v8.dossier_lines(m, "S:2"))
    check("досье V8 называет входящее ребро и окрестность", "Die_MCD записи с кадром S:1" in d and
          "окрестность" in d and "связей нет ни" not in d)
    check("у основы то же ребро исходящее", [(x["dir"], x["relative"]) for x in v8.facts(m, "S:1")] == [("OUT", "S:2")])
    check("«нет» - только без исходящих и входящих", "связей нет ни" in v8.dossier_lines(mcd(blank, rec([1])), "S:1")[0])
    # -- дверь НЛО
    door = mcd(blank, rec([1, 2, 3, 4, 5, 6, 7, 8], ufo=1))
    f8, f4 = v8.facts(door, "S:8"), v8.facts(door, "S:4")
    check("дверь НЛО: Frame[7] - открытое неподвижное состояние",
          [(x["dir"], x["meaning"], x["pos"]) for x in f8] == [("IN", "DOOR_OPEN_STATE", [7])])
    check("дверь НЛО: Frame[3] - фаза открывания", [x["meaning"] for x in f4] == ["DOOR_PHASE"])
    loop = mcd(blank, rec([1, 2, 3, 4, 5, 6, 7, 8]))
    check("контроль: та же петля без флага двери - фаза петли",
          [x["meaning"] for x in v8.facts(loop, "S:8")] == ["ANIMATION_PHASE"])
    check("распашная дверь: alt записи с флагом Door - открытая дверь",
          [x["meaning"] for x in v8.facts(mcd(blank, rec([1], alt=2, door=1), rec([2])), "S:2")] == ["DOOR_STATE"])
    check("alt двери НЛО движок не читает - не DOOR_STATE",
          [x["meaning"] for x in v8.facts(mcd(blank, rec([1], alt=2, ufo=1), rec([2])), "S:2")] == ["ALT_STATE"])
    # -- ось B
    for roles in (["COMPOSITE_PART"], ["DESTROYED_VARIANT_OF"], ["CANONICAL"], []):
        check("STRUCTURAL_SURFACE + %s -> STRUCTURAL_PIPELINE" % ("+".join(roles) or "без связи"),
              v8.pipeline_of("STRUCTURAL_SURFACE", "", roles)[0] == "STRUCTURAL_PIPELINE")
    check("OBJECT_PART без целого -> REVIEW", v8.pipeline_of("OBJECT_PART", "", ["CANONICAL"])[0] == "REVIEW")
    check("OBJECT_PART только с уликами -> REVIEW", v8.pipeline_of("OBJECT_PART", "", [])[0] == "REVIEW")
    check("контроль: OBJECT_PART составного -> OBJECT_PIPELINE",
          v8.pipeline_of("OBJECT_PART", "", ["COMPOSITE_PART"])[0] == "OBJECT_PIPELINE")
    check("OBJECT с уликой поверхности -> REVIEW", v8.pipeline_of("OBJECT", "STRONG", ["CANONICAL"])[0] == "REVIEW")
    check("TERRAIN_RELIEF / NOT_OBJECT / UNSURE", [v8.pipeline_of(k, "", [])[0] for k in
                                                   ("TERRAIN_RELIEF", "NOT_OBJECT", "UNSURE")] ==
          ["TERRAIN_PIPELINE", "NONE", "REVIEW"])
    # -- ось C: набор рёбер
    a = "S:2"
    p = pr(a, [link(a, "S:1")])
    r = v8.decide(a, "STRUCTURAL_SURFACE", p, None, fs)
    check("поверхность с die: STRUCTURAL_PIPELINE + DESTROYED_VARIANT_OF S:1",
          (r["pipeline_target"], r["relation_roles"], r["edges"][0]["target"]) ==
          ("STRUCTURAL_PIPELINE", ["DESTROYED_VARIANT_OF"], "S:1"))
    u = v7.route_v7(a, "STRUCTURAL_SURFACE", p["meta7"], p["view"][a], ("", ""), [], None, {}, {})
    check("контроль: V7 даёт той же поверхности EXCLUDE (правило S, связь потеряна)", (u[0], u[1]) == ("EXCLUDE", "S"))
    pc = pr(a, [link(a, "S:1")], gen={a: {"kind": "составной"}})
    r = v8.decide(a, "OBJECT_PART", pc, None, fs)
    check("кусок составного и разрушаемый: оба ребра, без старшинства",
          r["relation_roles"] == ["COMPOSITE_PART", "DESTROYED_VARIANT_OF"] and r["pipeline_target"] == "OBJECT_PIPELINE"
          and not r["creative"])
    u = v7.route_v7(a, "OBJECT", pc["meta7"], pc["view"][a], ("", ""), [], None, {}, {})
    check("контроль: V7 даёт одну роль - составной (R5), разрушенный вид теряется", (u[0], u[1]) ==
          ("COMPOSITE_PART", "R5"))
    check("сверка с V7: составной V7 есть в наборе", v8.consistency(a, pc, None, fs) == [])
    keep = v8.relations
    v8.relations = lambda *x, **k: ([e for e in keep(*x, **k)[0] if e["relation_type"] != "COMPOSITE_PART"], [])
    try:
        check("контроль сверки: потерянное ребро составного ловится", v8.consistency(a, pc, None, fs) != [])
    finally:
        v8.relations = keep
    pe = pr("S:5", blockers="part_fragment_suspect")
    r = v8.decide("S:5", "OBJECT", pe, None, [])
    check("улика без связи: рёбер нет, улика R7p, не одиночный заказ",
          (r["relation_roles"], [x["rule"] for x in r["open_evidence"]], r["creative"]) == ([], ["R7p"], False))
    r = v8.decide("S:5", "OBJECT", pr("S:5"), None, [])
    check("контроль: без улики - CANONICAL, одиночный творческий", (r["relation_roles"], r["creative"]) ==
          (["CANONICAL"], True))
    def prc(level="STRONG", side="base", verified=False, a="S:5", b="T:5"):
        q = pr(a)
        q["meta7"] = q["meta7"][:6] + ({a: [{"kind": "RECOLOR_OF", "level": level, "relative": b, "side": side,
                                             "verified": verified}]},)
        return q
    pp = prc()
    r = v8.decide("S:5", "OBJECT", pp, None, [])
    check("RECOLOR_PEER: доказанная перекраска (бывший pair_pick) - ребро STRONG без основы, не одиночный заказ",
          (r["relation_roles"], [(e["target"], e["confidence"], e["rule"]) for e in r["edges"]], r["creative"],
           r["pipeline_target"]) == (["RECOLOR_PEER"], [("T:5", "STRONG", "RP")], False, "OBJECT_PIPELINE"))
    check("RECOLOR_PEER: группа рисования и якорь", (r["render_group_id"], r["render_anchor"]) == ("rg:S:5+T:5", "S:5"))
    check("сверка с V7: pair_pick V7 <=> набор {RECOLOR_PEER}", v8.consistency("S:5", pp, None, []) == [])
    keep = v8.relations
    v8.relations = lambda *x, **k: ([e for e in keep(*x, **k)[0] if e["relation_type"] != "RECOLOR_PEER"] or
                                    [{"relation_type": "CANONICAL", "target": "", "rule": "R8"}], [])
    try:
        check("контроль сверки: потерянное ребро RECOLOR_PEER ловится (как pair_pick в V8 до заморозки)",
              v8.consistency("S:5", pp, None, []) != [])
    finally:
        v8.relations = keep
    check("контроль: перекраска с основой у S:5, подтверждённой человеком, - ребро у второго кадра, S:5 CANONICAL",
          v8.decide("S:5", "OBJECT", prc(verified=True), None, [])["relation_roles"] == ["CANONICAL"])
    r = v8.decide("S:5", "OBJECT", prc(side="derived", verified=True), None, [])
    check("контроль: подтверждённая основа T:5 - DERIVED_FROM VERIFIED (R0v), не RECOLOR_PEER",
          [(e["relation_type"], e["confidence"], e["rule"]) for e in r["edges"]] ==
          [("DERIVED_FROM", "VERIFIED", "R0v")] and not r["render_group_id"])
    check("контроль: перекраска-кандидат - не ребро", "RECOLOR_PEER" not in
          v8.decide("S:5", "OBJECT", prc(level="CANDIDATE"), None, [])["relation_roles"])
    check("OBJECT_PART только с RECOLOR_PEER -> REVIEW (пара перекраски - не целое)",
          v8.pipeline_of("OBJECT_PART", "", ["RECOLOR_PEER"])[0] == "REVIEW")
    peer = [{"relation_type": "RECOLOR_PEER", "target": "A:5"}]
    check("якорь - набор оригинальных данных игры, затем ключ",
          v8.render_group("X:5", peer, {"X"})[1] == "X:5" and v8.render_group("X:5", peer)[1] == "A:5")
    check("сверка с V7: R8 <=> {CANONICAL}", v8.consistency("S:5", pr("S:5"), None, []) == [] and
          v8.consistency("S:5", pe, None, []) == [])
    # -- D1 (PROVISIONAL), L1 (NOT_ACTIVE)
    pd = pr("S:8", [link("S:8", "S:1", via="anim", v6k="anim")])
    r = v8.decide("S:8", "STRUCTURAL_SURFACE", pd, None, f8)
    e = r["edges"]
    check("D1: открытая дверь НЛО - STATE_VARIANT_OF S:1 PROVISIONAL вместо ребра анимации",
          [(x["relation_type"], x["target"], x["confidence"], x["rule"]) for x in e] ==
          [("STATE_VARIANT_OF", "S:1", "PROVISIONAL", "D1")])
    r0 = v8.decide("S:8", "STRUCTURAL_SURFACE", pd, None, f8, {"door": False})
    check("контроль D1 выкл: ANIMATION_FAMILY (R3a)", [(x["relation_type"], x["rule"]) for x in r0["edges"]] ==
          [("ANIMATION_FAMILY", "R3a")])
    r = v8.decide("S:8", "OBJECT", pr("S:8"), None, f8)
    check("D1 без ребра V7: добавляет состояние, не одиночный творческий",
          (r["relation_roles"], r["creative"]) == (["STATE_VARIANT_OF"], False))
    r4 = v8.decide("S:4", "STRUCTURAL_SURFACE", pr("S:4", [link("S:4", "S:1", via="anim", v6k="anim")]), None, f4)
    check("фаза двери остаётся ANIMATION_FAMILY", r4["relation_roles"] == ["ANIMATION_FAMILY"])
    r = v8.decide("S:1", "OBJECT", pr("S:1"), None, v8.facts(loop, "S:1"))
    check("L1 NOT_ACTIVE: голова своей петли - CANONICAL", (r["relation_roles"], r["creative"]) == (["CANONICAL"], True))
    rd = dict(row("OBJECT_PIPELINE", ["STATE_VARIANT_OF"], "OBJECT_PIPELINE", {"state"}),
              edges=[{"rule": "D1", "target": "S:1"}])
    pair = [{"relative": "S:1", "ref_pair_relation": "STATE_VARIANT_OF"}]
    check("D1 correct: судимый эталон state", v8.d1_outcome(rd, []) == "correct")
    check("D1 correct: пара эталона STATE_VARIANT_OF", v8.d1_outcome(dict(rd, ref_role_status="open",
                                                                         ref_role_groups=[]), pair) == "correct")
    check("D1 wrong: судимый эталон без state", v8.d1_outcome(dict(rd, ref_role_groups=["animation"]), []) == "wrong")
    check("D1 unresolved: эталон связь не судил", v8.d1_outcome(dict(rd, ref_role_status="uninformed",
                                                                     ref_role_groups=[]), []) == "unresolved")
    check("контроль: без D1 - не считается", v8.d1_outcome(dict(rd, edges=[{"rule": "R3a", "target": "S:1"}]), [])
          == "")
    mm = v8.metrics([dict(rd, d1="correct"), dict(rd, d1="wrong"), dict(rd, d1="unresolved"), rd])
    check("счётчики D1: 3 / 1 / 1 / 1", (mm["D1_triggered"], mm["D1_correct"], mm["D1_wrong"], mm["D1_unresolved"])
          == (3, 1, 1, 1))
    # -- RECOLOR_PEER: счётчики holdout
    rr = dict(row("OBJECT_PIPELINE", ["RECOLOR_PEER"], "OBJECT_PIPELINE", {"derived"}),
              edges=[{"relation_type": "RECOLOR_PEER", "target": "T:5"}])
    rpo = v8.rp_outcomes
    check("RECOLOR_PEER correct: пара эталона RECOLOR_OF, направление не сверяется",
          rpo(rr, [{"relative": "T:5", "ref_pair_relation": "RECOLOR_OF"}]) == ["correct"])
    check("RECOLOR_PEER wrong: пара эталона NONE", rpo(rr, [{"relative": "T:5", "ref_pair_relation": "NONE"}]) ==
          ["wrong"])
    check("RECOLOR_PEER: без пары - по судимой связи кадра", rpo(rr, []) == ["correct"] and
          rpo(dict(rr, ref_role_groups=["composite"]), []) == ["wrong"])
    check("RECOLOR_PEER unresolved: эталон не судил", rpo(dict(rr, ref_role_status="uninformed"), []) == ["unresolved"])
    check("контроль: без ребра RECOLOR_PEER - не считается", rpo(dict(rr, edges=[]), []) == [])
    mm = v8.metrics([dict(rr, rp=["correct"], render_group_id="rg:S:1+T:5"),
                     dict(rr, rp=["wrong", "unresolved"], render_group_id="rg:S:1+T:5"), rd])
    check("счётчики RECOLOR_PEER: 3 / 1 / 1 / 1, группа одна",
          (mm["RECOLOR_PEER_triggered"], mm["RECOLOR_PEER_correct"], mm["RECOLOR_PEER_wrong"],
           mm["RECOLOR_PEER_unresolved"], mm["render_groups"]) == (3, 1, 1, 1, 1))
    check("пара перекраски при эталоне derived - не опасный творческий; контроль: CANONICAL - опасный",
          not v8.dangerous_creative_standalone(rr) and
          v8.dangerous_creative_standalone(row("OBJECT_PIPELINE", ["CANONICAL"], "OBJECT_PIPELINE", {"derived"})))
    # -- граф: одно направленное ребро, обратное чтение
    md = mcd(blank, rec([1], die=2), rec([2]))
    base = dict(link("S:2", "S:1"), side="base", relative="S:2")
    pg = {"view": {"S:1": [base], "S:2": [link("S:2", "S:1")]}}
    r22 = dict(v8.decide("S:2", "OBJECT", pr("S:2", [link("S:2", "S:1")]), None, v8.facts(md, "S:2")))
    g = v8.build_graph([r22, {"asset_id": "S:1", "edges": []}], pg, md)
    check("граф: разрушенный вид хранится одним ребром S:2 -> S:1, хотя виден с обеих сторон",
          list(g.edges) == [("S:2", "DESTROYED_VARIANT_OF", "S:1")])
    check("relations_out(S:2): DESTROYED_VARIANT_OF S:1",
          [(e["relation_type"], e["target"]) for e in g.relations_out("S:2")] == [("DESTROYED_VARIANT_OF", "S:1")])
    check("relations_in(S:1): HAS_DESTROYED_VARIANT S:2 - обратное чтение того же ребра",
          [(e["relation_type"], e["target"], e["inverse_of"]) for e in g.relations_in("S:1")] ==
          [("HAS_DESTROYED_VARIANT", "S:2", "DESTROYED_VARIANT_OF")] and g.relations_out("S:1") == [] and
          g.relations_in("S:2") == [])
    g1 = v8.build_graph([{"asset_id": "S:1", "edges": []}], pg, md)
    check("контроль: строки S:2 нет - ребро всё равно одно, из MCD основы", list(g1.edges) == list(g.edges))
    g2 = v8.Graph()
    for s, t in (("S:5", "T:5"), ("T:5", "S:5")):
        g2.add({"relation_type": "RECOLOR_PEER", "source": s, "target": t, "confidence": "STRONG", "rule": "RP",
                "evidence": ""})
    check("RECOLOR_PEER с двух сторон - одно ребро, читается с обеих, обратного чтения нет",
          len(g2.edges) == 1 and [e["target"] for e in g2.relations_out("T:5")] == ["S:5"] and
          [e["target"] for e in g2.relations_out("S:5")] == ["T:5"] and g2.relations_in("S:5") == [])
    g2.add({"relation_type": "CANONICAL", "source": "S:5", "target": "", "confidence": "STRONG", "rule": "R8",
            "evidence": ""})
    check("CANONICAL в граф не попадает", len(g2.edges) == 1)
    # -- опасный: только одиночный творческий заказ
    ds = v8.dangerous_creative_standalone
    check("одиночный творческий при эталоне STRUCTURAL - опасный",
          ds(row("OBJECT_PIPELINE", ["CANONICAL"], "STRUCTURAL_PIPELINE")))
    check("одиночный творческий при судимом составном - опасный",
          ds(row("OBJECT_PIPELINE", ["CANONICAL"], "OBJECT_PIPELINE", {"composite"})))
    check("кусок составного при эталоне STRUCTURAL - не опасный, но wrong_pipeline",
          not ds(row("OBJECT_PIPELINE", ["COMPOSITE_PART"], "STRUCTURAL_PIPELINE")) and
          v8.wrong_pipeline(row("OBJECT_PIPELINE", ["COMPOSITE_PART"], "STRUCTURAL_PIPELINE")))
    check("контроль: одиночный при судимом canonical - не опасный",
          not ds(row("OBJECT_PIPELINE", ["CANONICAL"], "OBJECT_PIPELINE", {"canonical"})))
    check("контроль: эталон не информирован (R-171) - связь не судится",
          not ds(row("OBJECT_PIPELINE", ["CANONICAL"], "OBJECT_PIPELINE", {"derived"}, "uninformed")))
    check("контроль: CANONICAL в STRUCTURAL - не творческий заказ",
          not ds(row("STRUCTURAL_PIPELINE", ["CANONICAL"], "OBJECT_PIPELINE", {"composite"})))
    mm = v8.metrics([row("OBJECT_PIPELINE", ["COMPOSITE_PART"], "STRUCTURAL_PIPELINE"),
                     row("OBJECT_PIPELINE", ["CANONICAL"], "OBJECT_PIPELINE", {"composite"}),
                     row("REVIEW", [], "STRUCTURAL_PIPELINE")])
    check("метрика: опасных творческих 1, строгих неверных 1 (OBJECT при не-OBJECT 1)",
          (mm["dangerous_creative_standalone"], mm["wrong_pipeline_classification"],
           mm["wrong_object_for_non_object"]) == (1, 1, 1))
    # -- связь набором против эталона
    mm = v8.metrics([row("OBJECT_PIPELINE", ["COMPOSITE_PART", "DESTROYED_VARIANT_OF"], "OBJECT_PIPELINE", {"state"})])
    by = mm["relation_by_type"]
    check("набор: пересечение 1, точно 0, state точность 1, composite точность 0",
          (mm["role_overlap"], mm["role_exact"], by["state"]["precision"], by["composite"]["precision"],
           mm["multi_relation"]) == (1.0, 0.0, 1.0, 0.0, 1))
    # -- ворота
    good = {"dangerous_creative_standalone": 0, "pipeline_accuracy": 0.96, "pipeline_coverage": 0.8,
            "semantic_axis_accuracy": 0.9}
    ps = {"strong": {"closed": 12, "relation_precision": 0.96}}
    check("все ворота - PASS", v8.verdict(v8.gate_checks(good, good, ps)) == "PASS")
    check("STRONG закрытых 9 - INSUFFICIENT_SAMPLE", v8.verdict(v8.gate_checks(
        good, good, {"strong": {"closed": 9, "relation_precision": 1.0}})) == "INSUFFICIENT_SAMPLE")
    ce = v8.gate_checks(dict(good, dangerous_creative_standalone=1), good, ps)
    cb = v8.gate_checks(good, dict(good, dangerous_creative_standalone=1), ps)
    check("E2E_SAFETY: опасный при оси A специалиста - FAIL, B_SAFETY цел",
          v8.verdict(ce) == "FAIL" and [k for k, v in ce.items() if v is False][0].startswith("E2E_SAFETY"))
    check("B_SAFETY: опасный при оси A эталона - FAIL, E2E_SAFETY цел",
          v8.verdict(cb) == "FAIL" and [k for k, v in cb.items() if v is False][0].startswith("B_SAFETY"))
    check("порядок ворот: B_SAFETY, E2E_SAFETY первыми (по нему пишется recount.md)",
          [k.split(":")[0] for k in list(ce)[:2]] == ["B_SAFETY", "E2E_SAFETY"])
    check("pipeline_logic 0.94 - FAIL", v8.verdict(v8.gate_checks(good, dict(good, pipeline_accuracy=0.94), ps)) == "FAIL")
    check("контроль: end_to_end 0.5 и semantic 0.6 вердикт не меняют",
          v8.verdict(v8.gate_checks(dict(good, pipeline_accuracy=0.5, semantic_axis_accuracy=0.6), good, ps)) == "PASS")
    check("semantic 0.84 - ворота карточки не пройдены", v8.semantic_check({"semantic_axis_accuracy": 0.84}) is False
          and v8.semantic_check({"semantic_axis_accuracy": 0.85}) is True)
    # -- эталон в осях V8
    base = {"ref_semantic_kind": "STRUCTURAL_SURFACE", "ref_route": "EXCLUDE", "ref_relation": "STATE_VARIANT_OF"}
    check("EXCLUDE с ref_relation STATE_VARIANT_OF - связь state судима",
          v8.ref_axes(base, [], []) == ("STRUCTURAL_PIPELINE", {"state"}, "judged"))
    check("EXCLUDE без связи - not_judged", v8.ref_axes(dict(base, ref_relation="OPEN"), [], [])[2] == "not_judged")
    check("входящее ребро, которого досье не показывало - uninformed",
          v8.ref_axes({"ref_semantic_kind": "OBJECT", "ref_route": "STANDALONE_RENDER"}, [], fs)[2] == "uninformed")
    # -- утверждения: факт отдельно от смысла
    refp = [{"asset_id": "S:2", "relative": "S:1", "ref_pair_relation": "NONE", "direction": "none"}]
    raw = [("S:2", "S:1", "STATE_VARIANT_OF", "STRONG", "derived", "mcd_die")]
    check("входящий die, эталон NONE - fact_only, не wrong", v8.claims_v8(raw, {"S:2": fs}, refp)[0]["status"] ==
          "fact_only")
    c = v8.claims_v8([("S:1", "S:2", "STATE_VARIANT_OF", "STRONG", "base", "mcd_die")], {"S:1": v8.facts(m, "S:1")},
                     [dict(refp[0], asset_id="S:1", relative="S:2")])[0]
    check("контроль: исходящее ребро судится - wrong", c["status"] == "wrong")
    check("пара, снятая специалистом - excluded",
          v8.claims_v8(raw, {"S:2": fs}, refp, exclude=(("S:2", "S:1"),))[0]["status"] == "excluded")
    # -- выход рёбер
    t = os.path.join(tempfile.mkdtemp(), "edges.tsv")
    v8.write_edges(t, [dict(v8.decide(a, "OBJECT_PART", pc, None, fs), asset_id=a),
                       dict(v8.decide("S:5", "OBJECT", pe, None, []), asset_id="S:5")])
    lines = open(t, encoding="utf-8-sig").read().splitlines()
    check("relation_edges.tsv: два ребра кадра и строка улики",
          len(lines) == 4 and lines[0].split("\t") == v8.EDGE_HEAD and
          [x.split("\t")[-1] for x in lines[1:]] == ["own", "own", "evidence"])
    v8.write_edges(t, [dict(r22, relations_in=[]), dict(v8.decide("S:5", "OBJECT", pp, None, []),
                                                        relations_in=g.relations_in("S:1"), asset_id="S:1")])
    views = [x.split("\t")[-1] for x in open(t, encoding="utf-8-sig").read().splitlines()[1:]]
    check("relation_edges.tsv: обратное чтение и группа рисования отдельными видами",
          sorted(views) == ["inverse", "own", "own", "render"])
    # -- онтология V8 и MCD
    o = v8.ONTOLOGY_V8
    ex = " ".join(o["STRUCTURAL_SURFACE"]["examples"] + o["OBJECT_PART"]["examples"])
    check("онтология: определения, проверка удалением, примеры без кадров",
          "оболочк" in o["STRUCTURAL_SURFACE"]["def"] and "объёмн" in o["OBJECT_PART"]["def"] and "дыра" in o["test"]
          and ":" not in ex and "секция фюзеляжа" in o["OBJECT_PART"]["examples"] and
          "обшивка" in o["STRUCTURAL_SURFACE"]["examples"])
    b = bytearray(62)
    b[0:8] = bytes([5] * 8)
    b[30], b[35], b[44], b[46], b[53] = 1, 0, 7, 9, 1
    x = v8.parse_mcd(bytes(b))[0]
    check("байты MCD: UFO_Door 30, Die 44, Alt 46, Tile_Type 53",
          (x["frames"][0], x["ufo"], x["die"], x["alt"], x["type"]) == (5, 1, 7, 9, 1))
    check("роли и группы согласованы", set(v8.ROLES) == set(v8.ROLE_GROUP))
    print("\nпровалов: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
