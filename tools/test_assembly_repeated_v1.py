#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка assembly_repeated_v1 на синтетике, без установки игры (ASSEMBLY_EVIDENCE_V2_PREP, специалист 02.10).

  - корабль 4x1 на двух картах: кусок борта HULL:5 дважды в следе якоря HULL:0 - доводы HULL:5 ~ HULL:0 и
    HULL:5 ~ HULL:9 (единственная деталь); найдены и от якоря, и от детали; CANDIDATE, детектор ASMR
  - пол HULL:20 под каждой клеткой корабля: довода нет (пол - поверхность)
  - забор A B A B: якорь не единственный в своём следе - довода нет
  - корабль на одной карте (даже в двух местах): довода нет (след не повторяется на картах)
  - кусок из другого набора: довода нет
  - кусок только на одном сдвиге (обычная деталь): довода RC нет
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import assembly_repeated_v1 as rc                               # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class FakePlaces:
    def __init__(self):
        self.blocks = []

    def put(self, blk, cells):
        self.blocks.append((blk, cells))

    def of(self, k):
        out = []
        for blk, g in self.blocks:
            for pos, lst in g.items():
                for la, kk in lst:
                    if kk == k.upper():
                        out.append(("T", blk, g, pos, la))
        return out


class FakeCtx:
    def __init__(self):
        self.places = FakePlaces()


def ship(x0=2, y0=2, piece="HULL:5", floor="HULL:20"):
    """Корабль 4x1: нос HULL:0, два одинаковых куска борта, корма HULL:9; под каждой клеткой пол."""
    row = ["HULL:0", piece, piece, "HULL:9"]
    return {(x0 + i, y0, 0): [(0, floor), (3, k)] for i, k in enumerate(row)}


def targets(ctx, a):
    return {e["target"] if e["source"] == a else e["source"]: e for e in rc.discover(rc.Footprints(ctx), a)}


# ---------------------------------------------------------------- корабль
c = FakeCtx()
c.places.put("M1", ship())
c.places.put("M2", ship(5, 7))
t = targets(c, "HULL:5")
check("корабль: HULL:5 ~ HULL:0 (якорь)", "HULL:0" in t and t["HULL:0"]["scores"]["partner_role"] == "anchor")
check("корабль: HULL:5 ~ HULL:9 (единственная деталь)",
      "HULL:9" in t and t["HULL:9"]["scores"]["partner_role"] == "unique_member")
e = t.get("HULL:0")
check("довод: ASMR, CANDIDATE, COMPOSITE_PART, кусок на двух сдвигах",
      bool(e) and e["detector"] == "ASMR" and e["level"] == "CANDIDATE" and e["type"] == "COMPOSITE_PART"
      and len(e["scores"]["repeated_nodes"]) == 2)
check("от якоря найден тот же довод", "HULL:5" in targets(c, "HULL:0"))
check("от детали найден тот же довод", "HULL:5" in targets(c, "HULL:9"))
check("пол HULL:20 под кораблём: довода нет ни с какой стороны",
      "HULL:20" not in t and not targets(c, "HULL:20"))
check("деталь на одном сдвиге не считается повторяющимся куском", "HULL:0" not in targets(c, "HULL:9"))

# ---------------------------------------------------------------- одна карта
c = FakeCtx()
g = ship()
g.update(ship(2, 9))
c.places.put("M1", g)
check("корабль дважды на одной карте: довода нет", not targets(c, "HULL:5"))

# ---------------------------------------------------------------- забор
c = FakeCtx()
for blk in ("F1", "F2", "F3"):
    c.places.put(blk, {(x, 0, 0): [(3, "FEN:%d" % (x % 2))] for x in range(7)})
check("забор A B A B: якорь не единственный - довода нет", not targets(c, "FEN:0") and not targets(c, "FEN:1"))

# ---------------------------------------------------------------- другой набор
c = FakeCtx()
c.places.put("M1", ship(piece="PLATE:5"))
c.places.put("M2", ship(5, 7, piece="PLATE:5"))
check("кусок из другого набора: довода нет", not targets(c, "PLATE:5"))

print("\n%s: %d провалов" % ("FAIL" if FAILS else "OK", len(FAILS)))
sys.exit(1 if FAILS else 0)
