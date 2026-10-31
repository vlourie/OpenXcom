#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка relation_discovery_v5 на синтетике, без установки игры (V5_PREP, специалист 02.10).

  - V5Claims без новых доводов даёт те же доводы, что замороженный V4Claims (контрольный опыт)
  - AR1 - группа derived, всегда TYPE_OPEN, никогда не автоматическое действие; вместе с R4 - тоже открыт
  - ASM STRONG - составной TYPE_STRONG (как P3L); ASM CANDIDATE - кандидат
  - категория пары: тип клетки обоих кадров, разный или без MCD - OTHER
  - спецификация сериализуется в JSON без потерь (заморозка сравнивает её с кодом)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import relation_discovery_v2 as v2                               # noqa: E402
import relation_discovery_v4 as v4                               # noqa: E402
import relation_discovery_v5 as v5                               # noqa: E402
import relation_taxonomy as tx                                   # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


E = v2.edge
V4_EDGES = [E("COMPOSITE_PART", "A:1", "A:2", "STRONG", "PLACE4", "P3L", "x"),
            E("NEAR_SILHOUETTE_RECOLOR", "A:1", "B:1", "CANDIDATE", "R4", "R4b", "x"),
            E("LOCAL_EDIT_VARIANT", "A:3", "B:3", "STRONG", "R4", "R4ds", "x"),
            E("ATTACHMENT_CANDIDATE", "A:4", "A:5", "CANDIDATE", "PLACE4", "A1", "x"),
            E("MIRRORED_RECOLOR", "A:6", "C:6", "STRONG", "MR4", "MR1s", "x"),
            E("RECOLOR_PEER", "A:7", "D:7", "STRONG", "RECOLOR", "R1", "x")]


def build(cls, edges):
    C = cls()
    for e in edges:
        C.add(e)
    return C.finalize()


def norm(C):
    return sorted(json.dumps({k: c[k] for k in ("pair", "group", "type", "existence", "type_level", "type_open_why",
                                                 "exact", "production")}, sort_keys=True, ensure_ascii=False)
                  for c in C.claims.values())


def test_control():
    check("контроль: V5Claims без новых доводов = V4Claims", norm(build(v5.V5Claims, V4_EDGES)) ==
          norm(build(v4.V4Claims, V4_EDGES)))
    other = V4_EDGES[:-1] + [E("RECOLOR_PEER", "A:7", "D:7", "CANDIDATE", "RECOLOR", "R1", "x")]
    check("контроль чувствителен: другой уровень даёт другие доводы", norm(build(v5.V5Claims, other)) !=
          norm(build(v4.V4Claims, V4_EDGES)))


def test_ar1():
    C = build(v5.V5Claims, [E("ALIGNED_RECOLOR", "K:15", "AV:53", "STRONG", "AR1", "AR1s", "x")])
    c = C.pair("K:15", "AV:53")[0]
    check("AR1: группа derived, существование STRONG", c["group"] == "derived" and c["existence"] == v5.STRONG)
    check("AR1: тип открыт, не авто", c["type_level"] == v4.T_OPEN and not tx.auto_claim(c) and
          "AR1: подтип на ревью" in c["type_open_why"])
    C = build(v5.V5Claims, [E("ALIGNED_RECOLOR", "K:15", "AV:53", "STRONG", "AR1", "AR1s", "x"),
                            E("LOCAL_EDIT_VARIANT", "K:15", "AV:53", "STRONG", "R4", "R4ds", "x")])
    c = C.pair("K:15", "AV:53")[0]
    check("AR1 вместе с R4: тип открыт", c["type_level"] == v4.T_OPEN and not tx.auto_claim(c))
    C = build(v5.V5Claims, [E("ALIGNED_RECOLOR", "K:15", "AV:53", "CANDIDATE", "AR1", "AR1", "x")])
    check("AR1 CANDIDATE: кадр под доводом (has_evidence), не связан", C.pair("K:15", "AV:53")[0]["existence"] ==
          v5.CAND)


def test_asm():
    C = build(v5.V5Claims, [E("COMPOSITE_PART", "CAR:0", "CAR:5", "STRONG", "ASM", "AO", "x")])
    c = C.pair("CAR:0", "CAR:5")[0]
    check("ASM STRONG: составной, TYPE_STRONG, авто", c["group"] == "composite" and c["type_level"] == v4.T_STRONG
          and tx.auto_claim(c))
    C = build(v5.V5Claims, [E("COMPOSITE_PART", "CAR:0", "CAR:5", "CANDIDATE", "ASM", "AOc", "x")])
    c = C.pair("CAR:0", "CAR:5")[0]
    check("ASM CANDIDATE: не авто", not tx.auto_claim(c) and c["existence"] == v5.CAND)


class FakeCtx:
    def __init__(self, inf):
        self.inf = inf

    def info(self, k):
        return self.inf.get(k, {"rec": False})


def test_category():
    ctx = FakeCtx({"A": {"rec": True, "tile_type": 3}, "B": {"rec": True, "tile_type": 3},
                   "W1": {"rec": True, "tile_type": 1}, "W2": {"rec": True, "tile_type": 2},
                   "F": {"rec": True, "tile_type": 0}})
    check("категория: предмет", v5.category(ctx, "A", "B") == "OBJECT")
    check("категория: западная и северная стена - WALL", v5.category(ctx, "W1", "W2") == "WALL")
    check("категория: разные - OTHER", v5.category(ctx, "A", "F") == "OTHER")
    check("категория: без MCD - OTHER", v5.category(ctx, "A", "X") == "OTHER")


def test_spec():
    s = v5.spec()
    j = json.loads(json.dumps(s, ensure_ascii=False))
    check("спецификация сериализуется", json.dumps(j, sort_keys=True) == json.dumps(
        json.loads(json.dumps(v5.spec(), ensure_ascii=False)), sort_keys=True))
    check("в спецификации оба детектора и цели", "aligned_recolor_v1" in j and "assembly_discovery_v1" in j and
          j["targets"]["true_composite_recall"] == 0.70 and j["targets"]["dangerous_creative_standalone"] == 0)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_control()
    test_ar1()
    test_asm()
    test_category()
    test_spec()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
