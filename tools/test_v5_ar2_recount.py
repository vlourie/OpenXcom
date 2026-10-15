#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка v5_ar2_recount на синтетике, без установки игры (специалист 02.10: AR2 в V5).

  - контроль: V5AR2Claims без доводов AR2 = замороженный rd5.V5Claims (с AR1 и без него)
  - контроль: замороженный класс rd5 довод AR2 не принимает - нужен свой класс
  - AR2: группа derived, существование STRONG, тип открыт «AR2: подтип на ревью», не авто, кадр связан (v4.bound)
  - AR2 вместе с R4 или AR1 - тоже открыт; AR2 при другом сильном детекторе типа не перебивает его
  - edges_ar2 убирает только доводы AR1; keep_on_asset трогает только доводы своего кадра
  - спецификация сериализуется в JSON без потерь
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import relation_discovery_v2 as v2                               # noqa: E402
import relation_discovery_v4 as v4                               # noqa: E402
import relation_discovery_v5 as rd5                              # noqa: E402
import relation_taxonomy as tx                                   # noqa: E402
import test_relation_discovery_v5 as t5                          # noqa: E402
import v5_ar2_recount as rc                                      # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


E = v2.edge
AR1_EDGE = E("ALIGNED_RECOLOR", "K:15", "AV:53", "CANDIDATE", "AR1", "AR1", "x")
AR2_EDGE = E("ALIGNED_RECOLOR", "K:15", "AV:53", "STRONG", "AR2", "AR2", "x")


def build(cls, edges):
    C = cls()
    for e in edges:
        C.add(e)
    return C.finalize()


def test_control():
    for name, edges in (("доводы V4", t5.V4_EDGES), ("доводы V4 + AR1", t5.V4_EDGES + [AR1_EDGE])):
        check("контроль: без AR2 класс пересчёта = замороженный V5Claims (%s)" % name,
              t5.norm(build(rc.V5AR2Claims, edges)) == t5.norm(build(rd5.V5Claims, edges)))
    try:
        build(rd5.V5Claims, [AR2_EDGE])
        ok = False
    except KeyError:
        ok = True
    check("контроль: замороженный класс V5 довод AR2 не принимает", ok)


def test_ar2():
    C = build(rc.V5AR2Claims, [AR2_EDGE])
    c = C.pair("K:15", "AV:53")[0]
    check("AR2: группа derived, STRONG, тип ALIGNED_RECOLOR", c["group"] == "derived" and c["existence"] == rc.STRONG
          and c["type"] == "ALIGNED_RECOLOR")
    check("AR2: тип открыт, «AR2: подтип на ревью», не авто", c["type_level"] == rc.T_OPEN and
          "AR2: подтип на ревью" in c["type_open_why"] and not tx.auto_claim(c))
    check("AR2: кадр связан (не creative)", v4.bound(C, "K:15") and v4.bound(C, "AV:53"))
    for other in (E("LOCAL_EDIT_VARIANT", "K:15", "AV:53", "STRONG", "R4", "R4ds", "x"),
                  E("ALIGNED_RECOLOR", "K:15", "AV:53", "STRONG", "AR1", "AR1s", "x")):
        c = build(rc.V5AR2Claims, [AR2_EDGE, other]).pair("K:15", "AV:53")[0]
        check("AR2 вместе с %s: тип открыт, не авто" % other["detector"], c["type_level"] == rc.T_OPEN and
              not tx.auto_claim(c))
    rec = E("RECOLOR_PEER", "K:15", "AV:53", "STRONG", "RECOLOR", "R1", "x")
    c = build(rc.V5AR2Claims, [AR2_EDGE, rec]).pair("K:15", "AV:53")[0]
    c0 = build(rd5.V5Claims, [rec]).pair("K:15", "AV:53")[0]
    check("AR2 при сильном RECOLOR: тип и уровень как без AR2", (c["type"], c["type_level"]) ==
          (c0["type"], c0["type_level"]))


def test_helpers():
    f5 = {"edges": [AR1_EDGE, t5.V4_EDGES[0]]}
    es, n = rc.edges_ar2(f5, {"edges": [AR2_EDGE]})
    check("edges_ar2: AR1 убран, ASM/прочие на месте, AR2 добавлен", n == 1 and
          [e["detector"] for e in es] == ["PLACE4", "AR2"])
    C = build(rc.V5AR2Claims, [AR2_EDGE, E("COMPOSITE_PART", "K:15", "Z:1", "CANDIDATE", "ASM", "AOc", "x"),
                               E("COMPOSITE_PART", "Z:1", "Z:2", "STRONG", "ASM", "AO", "x")])
    C2, removed = rc.keep_on_asset(C, "K:15", {tx.pk("K:15", "AV:53")})
    check("keep_on_asset: снят только чужой довод кадра", removed == [["K:15", "Z:1"]] and
          len(C2.claims) == 2 and C2.pair("Z:1", "Z:2") and C2.pair("K:15", "AV:53") and
          not C2.pair("K:15", "Z:1") and len(C.claims) == 3)
    rel = rc.closed_related([("a", [("X:1", "Y:1", "RELATED"), ("X:2", "Y:2", "NONE")]),
                             ("b", [("Y:1", "X:1", "RELATED")])])
    check("closed_related: только RELATED, источники собраны", rel == {tx.pk("X:1", "Y:1"): ["a", "b"]})


def test_spec():
    s = rc.spec()
    check("спецификация сериализуется без потерь", json.loads(json.dumps(s, ensure_ascii=False)) == s)
    check("порог в спецификации 0.70", s["aligned_recolor_v2"]["AR_BORDER"] == 0.70)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_control()
    test_ar2()
    test_helpers()
    test_spec()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
