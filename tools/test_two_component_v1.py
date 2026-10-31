#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка two_component_v1 на синтетике, без установки игры (ASSEMBLY_EVIDENCE_V2_PREP, специалист 02.10).

  - скамья из двух кадров на трёх картах: довод TC, сдвиг (1, 0, 0), CANDIDATE, детектор ASM2
  - стул всегда у стола, стол часто один: довода нет (зависимость односторонняя)
  - одно место: довода нет (SINGLE_PLACEMENT); две копии на одной карте: довода нет (карт меньше TC_BLOCKS)
  - забор A B A B: сосед на нескольких сдвигах - довода нет
  - пол + предмет всегда вместе: в доводы не идёт, только в диагностику (fo_diag)
  - другой набор: довода нет
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import two_component_v1 as tc                                   # noqa: E402

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


def targets(ctx, a, diag=False):
    return {e["target"]: e for e in tc.discover(tc.Windows(ctx), a, diag=diag)}


# ---------------------------------------------------------------- скамья
c = FakeCtx()
for i in range(3):
    c.places.put("B%d" % i, {(2, 2, 0): [(0, "GRASS:%d" % i), (3, "BENCH:0")],
                             (3, 2, 0): [(0, "GRASS:%d" % i), (3, "BENCH:1")]})
t = targets(c, "BENCH:0")
e = t.get("BENCH:1")
check("скамья: довод TC", bool(e))
check("скамья: ASM2, CANDIDATE, COMPOSITE_PART",
      bool(e) and e["detector"] == "ASM2" and e["level"] == "CANDIDATE" and e["type"] == "COMPOSITE_PART")
check("скамья: сдвиг (1, 0, 0), зависимость 1.0 с обеих сторон, карт 3",
      bool(e) and e["scores"]["offset"] == [1, 0, 0] and e["scores"]["dep"] == 1.0 and e["scores"]["blocks"] == 3)
check("скамья: со стороны второго куска тот же довод", "BENCH:0" in targets(c, "BENCH:1"))

# ---------------------------------------------------------------- стул у стола
c = FakeCtx()
for i in range(3):
    c.places.put("S%d" % i, {(3, 3, 0): [(3, "FURN:0")], (4, 3, 0): [(3, "FURN:1")]})
for i in range(3, 10):
    c.places.put("S%d" % i, {(3, 3, 0): [(3, "FURN:0")]})
check("стул всегда у стола, стол часто один: довода нет", "FURN:0" not in targets(c, "FURN:1"))
w = tc.Windows(c)
f = tc.features(w, "FURN:1", 3, "FURN:0", 3)
check("контроль: со стороны стула зависимость 1.0, со стороны стола 0.3",
      f["dep_a"] == 1.0 and abs(f["dep_b"] - 0.3) < 1e-9)

# ---------------------------------------------------------------- одно место / одна карта
c = FakeCtx()
c.places.put("U0", {(2, 2, 0): [(3, "PAIR:0")], (3, 2, 0): [(3, "PAIR:1")]})
check("одно место: довода нет (SINGLE_PLACEMENT)", not targets(c, "PAIR:0"))
c = FakeCtx()
c.places.put("U0", {(2, 2, 0): [(3, "PAIR:0")], (3, 2, 0): [(3, "PAIR:1")],
                    (12, 2, 0): [(3, "PAIR:0")], (13, 2, 0): [(3, "PAIR:1")]})
check("две копии на одной карте: довода нет (карт меньше TC_BLOCKS)", not targets(c, "PAIR:0"))
c.places.put("U1", {(2, 2, 0): [(3, "PAIR:0")], (3, 2, 0): [(3, "PAIR:1")]})
check("контроль: та же пара ещё на одной карте - довод есть", "PAIR:1" in targets(c, "PAIR:0"))

# ---------------------------------------------------------------- забор
c = FakeCtx()
for blk in ("F1", "F2", "F3"):
    c.places.put(blk, {(x, 0, 0): [(3, "FEN:%d" % (x % 2))] for x in range(8)})
check("забор A B A B: довода нет", "FEN:1" not in targets(c, "FEN:0"))

# ---------------------------------------------------------------- пол + предмет
c = FakeCtx()
for i in range(3):
    c.places.put("P%d" % i, {(2, 2, 0): [(0, "MACH:0"), (3, "MACH:1")], (3, 2, 0): [(0, "TILE:0")],
                             (1, 2, 0): [(0, "TILE:0")]})
check("пол + предмет всегда вместе: в доводы не идёт", "MACH:0" not in targets(c, "MACH:1"))
d = targets(c, "MACH:1", diag=True)
check("пол + предмет: только диагностика TC-FO-DIAG", "MACH:0" in d and d["MACH:0"]["rule"] == "TC-FO-DIAG")

# ---------------------------------------------------------------- другой набор
c = FakeCtx()
for i in range(3):
    c.places.put("X%d" % i, {(2, 2, 0): [(3, "AAA:0")], (3, 2, 0): [(3, "BBB:0")]})
check("другой набор: довода нет", not targets(c, "AAA:0"))

print("\n%s: %d провалов" % ("FAIL" if FAILS else "OK", len(FAILS)))
sys.exit(1 if FAILS else 0)
