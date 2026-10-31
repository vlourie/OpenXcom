#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/routing_rules_v5.py на синтетике: состояние по MCD не идёт одиночным (контроль без MCD -
одиночный, как NUKE2:2 в holdout V4_R1); FIXED_NEIGHBOUR сам даёт только REVIEW и не входит в точность родства;
улика поверхности: OBJECT_PART и NOT_OBJECT дают один маршрут, OBJECT при улике не одиночный; part_fragment_suspect
у поверхности не вопрос, у куска вещи - вопрос; признаки поверхности по записи MCD.

    py -3.13 tools/test_routing_rules_v5.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import routing_rules_v5 as v5  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def meta(gen=None, rels=None):
    return (gen or {}, {}, set(), set(), set(), {}, rels or {})


NB = {"kind": "FIXED_NEIGHBOUR", "level": "CANDIDATE", "side": "part?", "relative": "S:9"}
STATE = {"S:2": [{"side": "derived", "level": "STRONG", "via": "die", "base": "S:3", "root": "S:3",
                  "relative": "S:3", "kind": "STATE_VARIANT_OF", "why": ""}]}
NONE = ("", "")
WALL = ("STRONG", "запись стены (Tile_Type 2)")
BLOCK = ("CANDIDATE", "Big_Wall 1, Stop_LOS")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    u = v5.route_v5("S:2", "OBJECT", meta(), STATE, NONE)
    check("состояние по MCD - STATE_VARIANT R3m", u[:2] == ("STATE_VARIANT", "R3m"))
    check("контроль: без MCD тот же кадр одиночный",
          v5.route_v5("S:2", "OBJECT", meta(), STATE, NONE, use_mcd=False)[0] == "STANDALONE_RENDER")
    cand = {"S:2": [dict(STATE["S:2"][0], level="CANDIDATE")]}
    check("состояние CANDIDATE - REVIEW R7m", v5.route_v5("S:2", "OBJECT", meta(), cand, NONE)[:2] == ("REVIEW", "R7m"))
    check("TERRAIN_RELIEF - EXCLUDE раньше MCD", v5.route_v5("S:2", "TERRAIN_RELIEF", meta(), STATE, NONE)[0] == "EXCLUDE")

    for sk in ("OBJECT", "OBJECT_PART", "NOT_OBJECT", "UNSURE"):
        for sv in (NONE, WALL, BLOCK):
            u = v5.route_v5("S:1", sk, meta(rels={"S:1": [NB]}), {}, sv)[0]
            check("FIXED_NEIGHBOUR сам: %s, улика %s -> %s (не кусок, не родство)" % (sk, sv[0] or "-", u),
                  u in ("REVIEW", "EXCLUDE"))
    check("FIXED_NEIGHBOUR - улика R7n у вещи",
          v5.route_v5("S:1", "OBJECT", meta(rels={"S:1": [NB]}), {}, NONE)[:2] == ("REVIEW", "R7n"))
    check("контроль: без соседа та же вещь одиночная",
          v5.route_v5("S:1", "OBJECT", meta(), {}, NONE)[0] == "STANDALONE_RENDER")
    rows = v5.claim_rows({"S:1": [NB]}, {}, [{"asset_id": "S:1", "relative": "S:9",
                                               "ref_pair_relation": "NONE", "direction": "none"}], ["S:1"])
    check("FIXED_NEIGHBOUR не входит в точность родства", rows == [])
    rows = v5.claim_rows({}, STATE, [{"asset_id": "S:2", "relative": "S:3", "ref_pair_relation": "STATE_VARIANT_OF",
                                      "direction": "asset_derived"}], ["S:2"])
    check("утверждение MCD засчитано по эталону с направлением", len(rows) == 1 and rows[0]["status"] == "ok"
          and rows[0]["direction_ok"] is True and rows[0]["exact"])

    for sv in (WALL, BLOCK):
        a = v5.route_v5("S:1", "OBJECT_PART", meta(), {}, sv)
        b = v5.route_v5("S:1", "NOT_OBJECT", meta(), {}, sv)
        check("поверхность %s: OBJECT_PART и NOT_OBJECT - один маршрут (%s)" % (sv[0], a[0]),
              a[:2] == b[:2] == ("EXCLUDE", "S") and a[3] == "STRUCTURAL_SURFACE")
        check("поверхность %s: OBJECT - не одиночный" % sv[0],
              v5.route_v5("S:1", "OBJECT", meta(), {}, sv)[:2] == ("REVIEW", "R7s"))
    check("NOT_OBJECT без улики - R2", v5.route_v5("S:1", "NOT_OBJECT", meta(), {}, NONE)[:2] == ("EXCLUDE", "R2"))
    gen = {"S:1": {"blockers": "part_fragment_suspect"}}
    check("part_fragment_suspect у поверхности не вопрос",
          v5.route_v5("S:1", "OBJECT_PART", meta(gen), {}, WALL)[:2] == ("EXCLUDE", "S"))
    check("part_fragment_suspect у куска вещи - вопрос R7",
          v5.route_v5("S:1", "OBJECT_PART", meta(gen), {}, NONE)[:2] == ("REVIEW", "R7"))
    check("составной у поверхности - кусок R5, а не EXCLUDE",
          v5.route_v5("S:1", "OBJECT_PART", meta({"S:1": {"kind": "составной"}}), {}, WALL)[0] == "COMPOSITE_PART")

    # FAMILY_RELATION_V2: перекраска - только прямым ребром; цепочка A~B~C ребра A~C не даёт
    fam = lambda rel: ({}, {"S:1": rel}, set(), set(), set(), {}, {})     # noqa: E731
    e = lambda st, side, rel: {"status": st, "side": side, "relative": rel, "relation": "RECOLOR_OF",   # noqa: E731
                               "confidence": "CANDIDATE"}
    fr2 = {"S:1": [e("VERIFIED_DIRECT", "derived", "S:0")]}
    check("FR2 прямое ребро, производная сторона - DERIVED R4d",
          v5.route_v5("S:1", "OBJECT", fam("recolor"), {}, NONE, fr2=fr2)[:2] == ("DERIVED", "R4d"))
    check("FR2 DIRECT_NEW вне семейства - DERIVED R4d",
          v5.route_v5("S:1", "OBJECT", meta(), {}, NONE,
                      fr2={"S:1": [e("DIRECT_NEW", "derived", "T:1")]})[:2] == ("DERIVED", "R4d"))
    check("FR2 основа пары - не производная (одиночный)",
          v5.route_v5("S:1", "OBJECT", meta(), {}, NONE,
                      fr2={"S:1": [e("DIRECT_NEW", "base", "T:1")]})[0] == "STANDALONE_RENDER")
    check("recolor семейства без прямого ребра - REVIEW R4l (LEGACY_RELATION)",
          v5.route_v5("S:1", "OBJECT", fam("recolor"), {}, NONE,
                      fr2={"S:1": [e("LEGACY_RELATION", "derived", "S:0")]})[:2] == ("REVIEW", "R4l"))
    check("контроль: без fr2 тот же recolor - DERIVED R4",
          v5.route_v5("S:1", "OBJECT", fam("recolor"), {}, NONE)[:2] == ("DERIVED", "R4"))
    check("зеркало семейства с fr2 - DERIVED R4",
          v5.route_v5("S:1", "OBJECT", fam("mirror"), {}, NONE, fr2={})[:2] == ("DERIVED", "R4"))
    chain = {"S:1": [e("DIRECT_NEW", "base", "S:2")], "S:2": [e("DIRECT_NEW", "derived", "S:1"),
                                                            e("DIRECT_NEW", "base", "S:3")],
             "S:3": [e("DIRECT_NEW", "derived", "S:2")]}
    rows = v5.claim_rows({}, {}, [], ["S:1", "S:3"], chain)
    check("цепочка S:1~S:2~S:3 не даёт утверждения S:1~S:3",
          {(r["asset_id"], r["relative"]) for r in rows} == {("S:1", "S:2"), ("S:3", "S:2")})
    det = {"S:1": [{"kind": "RECOLOR_OF", "level": "STRONG", "side": "derived", "relative": "S:0"}]}
    check("ребро FR2 той же пары, что детектор, не повторяется",
          len(v5.claim_rows(det, {}, [], ["S:1"], fr2)) == 1)
    anim = {"S:5": [{"side": "derived", "level": "STRONG", "via": "anim", "base": "S:4", "root": "S:4",
                     "relative": "S:4", "kind": "ANIMATION_FRAME_OF", "why": ""}]}
    check("кадр анимации - ANIMATION_FAMILY R3a, не STATE_VARIANT",
          v5.route_v5("S:5", "OBJECT", meta(), anim, NONE)[:2] == ("ANIMATION_FAMILY", "R3a"))
    check("анимация не точный STATE_VARIANT_OF в эталоне", v5.CLAIM_EXACT["ANIMATION_FRAME_OF"] == ())

    class St:
        def __init__(self, r):
            self.r = r

        def record(self, s, f):
            return self.r

    def r(tt=3, bw=0, los=0, door=0):
        x = [0] * 62
        x[53], x[33], x[31], x[35] = tt, bw, los, door
        return x
    ev = lambda rec: v5.surface_evidence(St(rec), "S:1")[0]     # noqa: E731
    check("запись стены - STRONG", ev(r(tt=1)) == "STRONG" and ev(r(tt=2)) == "STRONG")
    check("Big_Wall 5 + Stop_LOS - STRONG, без Stop_LOS - нет", ev(r(bw=5, los=1)) == "STRONG" and ev(r(bw=5)) == "")
    check("дверь - STRONG", ev(r(door=1)) == "STRONG")
    check("Big_Wall 1 + Stop_LOS - CANDIDATE, без Stop_LOS - нет", ev(r(bw=1, los=1)) == "CANDIDATE" and ev(r(bw=1)) == "")
    check("записи нет - нет улики", ev(None) == "")
    print("\nпровалов: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
