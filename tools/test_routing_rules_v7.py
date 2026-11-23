#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/routing_rules_v7.py на синтетике, у каждого изменения - контроль:
ANIMATION_FAMILY_COPY - кадры разных петель MCD, петли делят побайтно равный кадр (контроль: петли без общего
кадра, одна петля, кадр вне петли - не копия); перекраска и вариант между такими кадрами -> COPY STRONG, группа
animation, против эталона ANIMATION_FRAME_OF - ok (контроль: без петель остаётся перекраской - wrong);
R7t - OBJECT, мест >= 2, доля вплотную >= 0.75 -> REVIEW вместо R8 (контроль: одно место, доля ниже порога,
OBJECT_PART, выключено - как R2); CANDIDATE маршрут не меняет (контроль: та же связь STRONG - меняет); точность
родства разведена по STRONG и CANDIDATE.

    py -3.13 tools/test_routing_rules_v7.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import routing_rules_v7 as v7  # noqa: E402

v6 = v7.v6
FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def meta(rels=None):
    return ({}, {}, set(), set(), set(), {}, rels or {})


NONE = ("", "")


def rec(rel, level="STRONG", kind="RECOLOR_OF", verified=False):
    return {"kind": kind, "level": level, "relative": rel, "side": "derived", "verified": verified}


def link(state, base, via, level="STRONG"):
    return {"state": state, "base": base, "via": via, "level": level, "root": base, "why": "",
            "kind": {"die": "STATE_VARIANT_OF", "alt": "STATE_VARIANT_OF", "anim": "ANIMATION_FRAME_OF"}[via]}


def view(links, groups=None):
    idx = v6.ms.index({"S": links})
    return {k: v6.mcd_view(v, groups or {}, lambda k: None, "anim_only") for k, v in idx.items()}


def main():
    # ---------------- 5. ANIMATION_FAMILY_COPY
    groups = {"A:14": "A:14", "A:15": "A:14", "A:21": "A:14", "B:1": "B:1", "B:2": "B:1", "B:5": "B:1",
              "C:1": "C:1", "C:2": "C:1"}
    members = v7.loops(groups)
    pix = {"A:14": "a14", "A:15": "same", "A:21": "a21", "B:1": "b1", "B:2": "same", "B:5": "b5",
           "C:1": "c1", "C:2": "c2"}
    sig = pix.get
    check("копия петли: A:21 ~ B:5 (A:15 == B:2)", v7.anim_copy(groups, members, sig, "A:21", "B:5")[0])
    check("контроль: петли без общего кадра - не копия", not v7.anim_copy(groups, members, sig, "A:21", "C:2")[0])
    check("контроль: одна петля - не копия (это same_anim V6)", not v7.anim_copy(groups, members, sig, "A:21", "A:15")[0])
    check("контроль: кадр вне петли - не копия", not v7.anim_copy(groups, members, sig, "A:21", "D:1")[0])
    rels = {"A:21": [rec("B:5", "CANDIDATE"), rec("C:2", "CANDIDATE"),
                     {"kind": "FIXED_NEIGHBOUR", "level": "CANDIDATE", "relative": "B:5", "side": "part?"}]}
    conv, lst = v7.convert_rels(rels, groups, members, sig)
    kinds = {(c["relative"], c["kind"]): c for c in conv["A:21"]}
    check("перекраска копии петли -> ANIMATION_FAMILY_COPY STRONG",
          ("B:5", v7.COPY) in kinds and kinds[("B:5", v7.COPY)]["level"] == "STRONG" and len(lst) == 1)
    check("контроль: перекраска без копии петли остаётся", ("C:2", "RECOLOR_OF") in kinds)
    check("улика FIXED_NEIGHBOUR не трогается", ("B:5", "FIXED_NEIGHBOUR") in kinds)
    check("исходные rels не изменены", rels["A:21"][0]["kind"] == "RECOLOR_OF")
    var = {"A:21": [{"kind": "STYLE_VARIANT_OF", "level": "CANDIDATE", "relative": "B:5", "side": "open"}]}
    raw, _, cv = v7.claims_v7(["A:21"], {"A:21": [rec("B:5", "CANDIDATE")]}, {}, {}, var, groups, members, sig)
    check("утверждения: перекраска и вариант копии петли - одно ANIMATION_FAMILY_COPY",
          [x[2] for x in raw] == [v7.COPY] and len(cv) == 1)
    ref = [{"asset_id": "A:21", "relative": "B:5", "ref_pair_relation": "ANIMATION_FRAME_OF"}]
    check("COPY против эталона ANIMATION_FRAME_OF - ok", v7.score(raw, ref)[0]["status"] == "ok")
    raw0, _, _ = v7.claims_v7(["A:21"], {"A:21": [rec("B:5", "CANDIDATE")]}, {}, {}, {}, {}, {}, sig)
    check("контроль: без петель - перекраска, против ANIMATION_FRAME_OF wrong",
          raw0[0][2] == "RECOLOR_OF" and v7.score(raw0, ref)[0]["status"] == "wrong")

    # ---------------- 2. SAME_FRAME_ADJACENCY
    def rt(sk, adj, **o):
        return v7.route_v7("P:1", sk, meta(), [], NONE, [], None, o, adj)

    check("контроль: OBJECT без связей - R8 STANDALONE", rt("OBJECT", {})[:2] == ("STANDALONE_RENDER", "R8"))
    u, rule, why, _, _ = rt("OBJECT", {"P:1": (4, 1.0)})
    check("R7t: 4 места, все вплотную -> REVIEW PROVISIONAL", (u, rule) == ("REVIEW", "R7t") and "PROVISIONAL" in why)
    check("R7t: доля ровно 0.75 -> REVIEW", rt("OBJECT", {"P:1": (4, 0.75)})[1] == "R7t")
    check("контроль: доля 0.5 - R8", rt("OBJECT", {"P:1": (4, 0.5)})[1] == "R8")
    check("контроль: одно место - R8", rt("OBJECT", {"P:1": (1, 1.0)})[1] == "R8")
    check("контроль: выключено (R2) - R8", rt("OBJECT", {"P:1": (4, 1.0)}, adjacency=False)[1] == "R8")
    check("контроль: OBJECT_PART - R8a, не R7t", rt("OBJECT_PART", {"P:1": (4, 1.0)})[1] == "R8a")
    check("R7t не утверждает модуль: маршрут только REVIEW",
          all(rt("OBJECT", {"P:1": (n, s)})[0] in ("REVIEW", "STANDALONE_RENDER")
              for n in (2, 3, 8) for s in (0.75, 0.9, 1.0)))

    # ---------------- 4. CANDIDATE маршрут не меняет
    def rr(rels=None, mv=None, variants=None):
        return v7.route_v7("P:1", "OBJECT", meta(rels), mv or [], NONE, variants or [], None, {}, {})

    base = rr()[:2]
    for kind in v6.RECOLOR:
        check("CANDIDATE %s - маршрут как без связи" % kind,
              rr({"P:1": [rec("Q:1", "CANDIDATE", kind)]})[:2] == base)
    check("контроль: подтверждённая человеком перекраска - DERIVED R0v",
          rr({"P:1": [rec("Q:1", "STRONG", verified=True)]})[:2] == ("DERIVED", "R0v"))
    mv = view([link("P:1", "Q:1", "die", "CANDIDATE")])
    u = rr(mv=mv.get("P:1"))
    check("CANDIDATE die - REVIEW (R7m), не STATE_VARIANT", u[:2] == ("REVIEW", "R7m"))
    mv = view([link("P:1", "Q:1", "die")])
    check("контроль: STRONG die - STATE_VARIANT R3m", rr(mv=mv.get("P:1"))[:2] == ("STATE_VARIANT", "R3m"))
    var = [{"kind": "MATERIAL_VARIANT_OF", "level": "CANDIDATE", "relative": "Q:1", "side": "derived"}]
    check("CANDIDATE вариант - REVIEW R4v", rr(variants=var)[:2] == ("REVIEW", "R4v"))
    for lvl in ("CANDIDATE", "WEAK", "STRONG"):
        for kind in v6.RECOLOR:
            u = rr({"P:1": [rec("Q:1", lvl, kind)]})
            check("перекраска %s %s без подтверждения не даёт DERIVED" % (lvl, kind), u[0] != "DERIVED")

    # ---------------- 4. точность родства раздельно
    cl = [{"level": "STRONG", "status": "ok", "judged": True}, {"level": "STRONG", "status": "ok", "judged": True},
          {"level": "CANDIDATE", "status": "wrong", "judged": True}, {"level": "CANDIDATE", "status": "open",
                                                                     "judged": False}]
    ps = v7.precision_split(cl)
    check("STRONG 1.0, CANDIDATE 0.0, всё 0.667", (ps["strong"]["relation_precision"],
                                                  ps["candidate"]["relation_precision"],
                                                  ps["all"]["relation_precision"]) == (1.0, 0.0, 0.667))
    t = v7.targets({"dangerous_false_standalone": 0, "routing_accuracy": 0.95, "routing_coverage": 0.7}, ps)
    check("цели: CANDIDATE 0.0 порог не валит", all(t.values()))
    ps["strong"]["relation_precision"] = 0.94
    check("контроль: STRONG 0.94 порог валит", not v7.targets(
        {"dangerous_false_standalone": 0, "routing_accuracy": 0.95, "routing_coverage": 0.7}, ps)[
        "точность родства STRONG >= 0.95"])
    # ---------------- 6. HANDOFF и ворота V7
    check("поверхность -> STRUCTURAL_PIPELINE, NOT_IMPLEMENTED",
          v7.handoff("EXCLUDE", "STRUCTURAL_SURFACE") == ("STRUCTURAL_PIPELINE", "NOT_IMPLEMENTED", "STRUCTURAL_SURFACE"))
    check("рельеф -> TERRAIN_PIPELINE", v7.handoff("EXCLUDE", "TERRAIN_RELIEF")[0] == "TERRAIN_PIPELINE")
    check("не предмет -> NONE с причиной effect",
          v7.handoff("EXCLUDE", "NOT_OBJECT", "smoke puff effect") == ("NONE", "NO_RENDER", "effect"))
    check("не предмет без описания -> NONE, причина unknown", v7.handoff("EXCLUDE", "NOT_OBJECT")[2] == "unknown")
    check("EXCLUDE при OBJECT - ERROR_UNASSIGNED", v7.handoff("EXCLUDE", "OBJECT")[:2] == ("", "ERROR_UNASSIGNED"))
    check("контроль: не EXCLUDE - пусто", v7.handoff("STANDALONE_RENDER", "OBJECT") == ("", "", ""))
    for sk, rule in (("TERRAIN_RELIEF", "R1"), ("NOT_OBJECT", "R2")):
        u = v7.route_v7("P:1", sk, meta(), [], NONE, [], None, {}, {})
        check("route_v7 %s -> EXCLUDE %s, цель есть" % (sk, rule),
              u[:2] == ("EXCLUDE", rule) and v7.handoff(u[0], u[3])[0] != "")
    u = v7.route_v7("P:1", "OBJECT", meta(), [], ("STRONG", "стена"), [], None, {}, {})
    check("OBJECT с сильной уликой стены (R2_OPTS) - R7s REVIEW, не EXCLUDE без цели", u[:2] == ("REVIEW", "R7s"))

    def row(u, ref, layer="L", sk="OBJECT", ht="", hs=""):
        return {"asset_id": "X", "rule_unit": u, "rule": "-", "ref_route": ref, "layer": layer, "semantic_kind": sk,
                "ref_semantic_kind": sk, "handoff_target": ht, "handoff_status": hs}
    good = [row("STANDALONE_RENDER", "STANDALONE_RENDER")] * 9 + [
        row("EXCLUDE", "EXCLUDE", ht="STRUCTURAL_PIPELINE", hs="NOT_IMPLEMENTED")]
    sp = {"strong": {"closed": 12, "ok": 12, "relation_precision": 1.0}}
    ck = v7.gate_checks(v7.metrics(good), sp, good)
    check("всё в порядке - PASS (конвейер не построен - не валит)", v7.verdict(ck) == "PASS")
    bad = good[:-1] + [row("EXCLUDE", "EXCLUDE")]
    check("контроль: EXCLUDE без цели - FAIL", v7.verdict(v7.gate_checks(v7.metrics(bad), sp, bad)) == "FAIL")
    few = {"strong": {"closed": 9, "ok": 9, "relation_precision": 1.0}}
    check("STRONG 9 из 9 закрытых - INSUFFICIENT_SAMPLE, не PASS",
          v7.verdict(v7.gate_checks(v7.metrics(good), few, good)) == "INSUFFICIENT_SAMPLE")
    lay = good + [row("STANDALONE_RENDER", "DERIVED", layer="M")]
    ck = v7.gate_checks(v7.metrics(lay), sp, lay)
    check("опасный в одном слое - FAIL обоих ворот опасных", ck["опасных = 0"] is False and
          ck["опасных = 0 в каждом слое"] is False)
    over = [row("REVIEW", "STANDALONE_RENDER")] * 2 + good
    ck = v7.gate_checks(v7.metrics(over), sp, over)
    check("сверхосторожность 2/11 не ворота: охват 10/12 - PASS", v7.verdict(ck) == "PASS")
    check("онтология v2: лестница и обшивка - в STRUCTURAL_SURFACE",
          "лестница" in v7.SEM_DEFS_V2["STRUCTURAL_SURFACE"] and "обшивка корпуса/машины" in
          v7.SEM_DEFS_V2["STRUCTURAL_SURFACE"])
    print("\nпровалов: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
