#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка assembly_group_v1 на синтетике, без установки игры (V6_PREP, специалист 02.10).

  - общий ствол под разными кронами: крона ~ ствол - довод AG (одна сторона), хотя ствола в ядре кроны хватает,
    а кроны в ядре ствола нет (взаимность ASM V1 рвётся); ветка - общий третий кадр
  - машина 3x2 на трёх картах: все пары кусков - AG, одна группа из шести кадров
  - стул всегда у стола, полы разные: третьего общего кадра нет - довода нет (одностороннее соседство)
  - забор A B A B: сосед на нескольких сдвигах с обеих сторон - узор, довода нет, хотя пол общий
  - крона в другом наборе - довода нет (SAME_SET); с SAME_SET = False - есть (контроль условия)
  - дерево на одной карте - довода нет (повтор)
  - довод всегда CANDIDATE, детектор ASMG, тип COMPOSITE_PART; выборка мест не больше GRP_CAP
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import assembly_group_v1 as ag                                  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class FakePlaces:
    def __init__(self):
        self.blocks = []

    def put(self, blk, cells):
        """cells: {(x, y, z): [(слой, кадр)]}"""
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


def targets(ctx, a):
    return {e["target"]: e for e in ag.discover(ag.Groups(ctx), a)}


def tree(ctx, blk, crown, trunk="TREE:1", branch="TREE:5", floor="GRASS:0"):
    g = {(4, 4, 0): [(0, floor), (3, trunk)], (4, 4, 1): [(3, crown)], (5, 4, 1): [(3, branch)]}
    ctx.places.put(blk, g)


# ---------------------------------------------------------------- общий ствол
c = FakeCtx()
for i, crown in enumerate(["TREE:2", "TREE:2", "TREE:3", "TREE:3", "TREE:4", "TREE:4"]):
    tree(c, "B%d" % i, crown)
G = ag.Groups(c)
core_t = G.core("TREE:1", 3)
check("ствол: кроны TREE:2 нет в ядре ствола (2 места из 6 < 0.5)", "TREE:2" not in core_t["frames"])
check("ствол: ветка в ядре ствола", "TREE:5" in core_t["frames"])
t = targets(c, "TREE:2")
check("общий ствол: крона TREE:2 ~ ствол - довод AG", "TREE:1" in t)
e = t.get("TREE:1")
check("довод: детектор ASMG, CANDIDATE, COMPOSITE_PART",
      bool(e) and e["detector"] == "ASMG" and e["level"] == "CANDIDATE" and e["type"] == "COMPOSITE_PART")
check("довод: одна сторона (a), общий третий кадр - ветка",
      bool(e) and e["scores"]["side"] == "a" and "TREE:5" in e["scores"]["shared"])
check("довод: сдвиг ствола от кроны (0, 0, -1)", bool(e) and e["scores"]["offset"] == [0, 0, -1])
t1 = targets(c, "TREE:1")
check("со стороны ствола тот же довод (a в ядре b)", "TREE:2" in t1 and t1["TREE:2"]["scores"]["side"] == "b")

# ---------------------------------------------------------------- машина 3x2
c = FakeCtx()
parts = ["CAR:%d" % i for i in range(6)]
for blk in ("M1", "M2", "M3"):
    g = {}
    for i, k in enumerate(parts):
        g[(2 + i % 3, 2 + i // 3, 0)] = [(0, "ROAD:%d" % (ord(blk[1]) % 2)), (3, k)]
    c.places.put(blk, g)
G = ag.Groups(c)
es = []
for k in parts:
    es += ag.discover(G, k)
pairs = {frozenset((x["source"], x["target"])) for x in es}
check("машина: все 15 пар кусков - AG", len(pairs) == 15)
check("машина: одна группа из шести", ag.groups(es) == [sorted(parts)])
check("машина: дальняя пара CAR:0 ~ CAR:5 (сдвиг 2, 1) - обе стороны",
      any({x["source"], x["target"]} == {"CAR:0", "CAR:5"} and x["scores"]["side"] == "обе" for x in es))

# ---------------------------------------------------------------- стул у стола
c = FakeCtx()
for i in range(4):
    c.places.put("S%d" % i, {(3, 3, 0): [(0, "FLOOR%d:0" % i), (3, "FURN:0")],
                             (4, 3, 0): [(0, "FLOOR%d:0" % i), (3, "FURN:1")]})
for i in range(4, 10):
    c.places.put("S%d" % i, {(3, 3, 0): [(0, "FLOOR%d:0" % i), (3, "FURN:0")]})
check("стул всегда у стола, полы разные: довода нет", "FURN:0" not in targets(c, "FURN:1"))
check("стол один чаще: со стороны стола довода тоже нет", "FURN:1" not in targets(c, "FURN:0"))

# ---------------------------------------------------------------- забор A B A B
c = FakeCtx()
for blk in ("F1", "F2", "F3"):
    g = {}
    for x in range(6):
        g[(x, 0, 0)] = [(0, "PAVE:0"), (3, "FEN:%d" % (x % 2))]
    c.places.put(blk, g)
G = ag.Groups(c)
check("забор: сосед в ядре на нескольких сдвигах", len(ag.offsets(G.core("FEN:0", 3), "FEN:1")) > 1)
check("забор: узор - довода нет, хотя пол общий", "FEN:1" not in targets(c, "FEN:0"))

# ---------------------------------------------------------------- чужой набор
c = FakeCtx()
for i, crown in enumerate(["CROWN:2", "CROWN:2", "TREE:3", "TREE:3"]):
    tree(c, "C%d" % i, crown)
check("крона в другом наборе: довода нет", "TREE:1" not in targets(c, "CROWN:2"))
ag.SAME_SET = False
try:
    check("контроль: без условия набора довод есть", "TREE:1" in targets(c, "CROWN:2"))
finally:
    ag.SAME_SET = True

# ---------------------------------------------------------------- одно место
c = FakeCtx()
tree(c, "U0", "TREE:2")
check("дерево на одной карте: довода нет", not targets(c, "TREE:2"))

# ---------------------------------------------------------------- выборка
pl = list(range(1000))
s = ag.sample(pl)
check("выборка: не больше GRP_CAP, равномерно", len(s) == ag.GRP_CAP and s[0] == 0 and s[-1] > 990)
check("выборка: меньше GRP_CAP - все места", ag.sample(pl[:10]) == pl[:10])

print("\n%s: %d провалов" % ("FAIL" if FAILS else "OK", len(FAILS)))
sys.exit(1 if FAILS else 0)
