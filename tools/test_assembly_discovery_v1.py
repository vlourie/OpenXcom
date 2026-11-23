#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка assembly_discovery_v1 на синтетике, без установки игры (V5_PREP, специалист 02.10).

  - машина 3x2 на трёх картах: каждая пара кусков - AO STRONG, и дальняя (сдвиг 2,1), которую P3L (сдвиг ±1) не
    видит; контроль - P3L-окно ±1 дальнюю пару не содержит
  - стул всегда у стола, стол часто один: одностороннее - довода нет (остаётся ATTACHMENT_CANDIDATE V4)
  - шахматка двух полов: сосед на нескольких сдвигах - узор, не сборка
  - машина на одной карте: AOs CANDIDATE при порядке номеров; контроль - разные наборы без порядка - довода нет
  - взаимная сборка без касания вокселей - AOc CANDIDATE, не STRONG
  - дверной проём в западной стене на двух картах - AW STRONG; логотип из двух полов - AF STRONG
"""
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import assembly_discovery_v1 as asm                              # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


FULL = np.ones((12, 16, 16), bool)
EMPTY_FACE = np.zeros((12, 16, 16), bool)
EMPTY_FACE[:, 6:10, 6:10] = True                              # столб в середине клетки: граней не касается
WEST = np.zeros((12, 16, 16), bool)
WEST[:, :, 0] = True
FLOOR = np.zeros((12, 16, 16), bool)
FLOOR[0] = True


class FakePlaces:
    def __init__(self):
        self.blocks = []                                       # [(блок, сетка)]

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
        self.inf = {}

    def info(self, k):
        return self.inf.get(k.upper(), {"rec": False})

    def mcd(self, k, tt, vox, armor=10):
        self.inf[k.upper()] = {"rec": True, "tile_type": tt, "vox": vox,
                               "phys": {"armor": armor, "flammable": 0, "fuel": 0, "footstep": 0}}


def car(g, x, y, keys):
    for i, k in enumerate(keys):
        g.setdefault((x + i % 3, y + i // 3, 0), []).append((3, k))


def edges_of(ctx, a):
    return {(e["target"], e["rule"], e["level"]) for e in asm.discover(asm.Assembly(ctx), a)}


def test_car():
    ctx = FakeCtx()
    keys = ["CAR:%d" % i for i in range(6)]
    for k in keys:
        ctx.mcd(k, 3, FULL)
    for blk in ("B1", "B2", "B3"):
        g = {}
        car(g, 2, 2, keys)
        ctx.places.put(blk, g)
    es = edges_of(ctx, "CAR:0")
    check("машина: все 5 кусков - AO STRONG (%d)" % len(es),
          {t for t, r, l in es if r == "AO" and l == "STRONG"} == set(keys[1:]))
    check("машина: дальний кусок CAR:5 на сдвиге (2,1) найден", ("CAR:5", "AO", "STRONG") in es)
    check("контроль: сдвиг (2,1) вне окна P3L (±1)", (2, 1, 0) not in
          [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)])


def test_one_sided():
    ctx = FakeCtx()
    ctx.mcd("FURN:1", 3, FULL)
    ctx.mcd("FURN:2", 3, FULL)
    for i in range(3):
        ctx.places.put("C%d" % i, {(1, 1, 0): [(3, "FURN:1")], (2, 1, 0): [(3, "FURN:2")]})
    for i in range(6):
        ctx.places.put("T%d" % i, {(1, 1, 0): [(3, "FURN:1")]})
    check("одностороннее (стул у стола, стол часто один): довода нет",
          not edges_of(ctx, "FURN:2") and not edges_of(ctx, "FURN:1"))
    ctx2 = FakeCtx()
    ctx2.mcd("FURN:1", 3, FULL)
    ctx2.mcd("FURN:2", 3, FULL)
    for i in range(3):
        ctx2.places.put("C%d" % i, {(1, 1, 0): [(3, "FURN:1")], (2, 1, 0): [(3, "FURN:2")]})
    check("контроль: без одиночных столов та же пара - AO STRONG", ("FURN:1", "AO", "STRONG") in edges_of(ctx2, "FURN:2"))


def test_checker():
    ctx = FakeCtx()
    ctx.mcd("FL:1", 0, FLOOR)
    ctx.mcd("FL:2", 0, FLOOR)
    for blk in ("B1", "B2", "B3"):
        g = {}
        for x in range(8):
            for y in range(8):
                g[(x, y, 0)] = [(0, "FL:%d" % (1 + (x + y) % 2))]
        ctx.places.put(blk, g)
    check("шахматка полов: узор, не сборка", not edges_of(ctx, "FL:1"))


def test_single():
    ctx = FakeCtx()
    keys = ["VAN:%d" % i for i in range(3)]
    for k in keys:
        ctx.mcd(k, 3, FULL)
    g = {}
    for i, k in enumerate(keys):
        g[(4 + i, 4, 0)] = [(3, k)]
    ctx.places.put("ONE", g)
    es = edges_of(ctx, "VAN:0")
    check("одно место: AOs CANDIDATE при порядке номеров", ("VAN:1", "AOs", "CANDIDATE") in es and
          not any(l == "STRONG" for _t, _r, l in es))
    ctx2 = FakeCtx()
    ctx2.mcd("AAA:0", 3, FULL)
    ctx2.mcd("BBB:7", 3, FULL)
    ctx2.places.put("ONE", {(4, 4, 0): [(3, "AAA:0")], (5, 4, 0): [(3, "BBB:7")]})
    check("контроль: одно место, разные наборы - довода нет", not edges_of(ctx2, "AAA:0"))


def test_no_contact():
    ctx = FakeCtx()
    ctx.mcd("POD:1", 3, EMPTY_FACE)
    ctx.mcd("POD:2", 3, EMPTY_FACE)
    for blk in ("B1", "B2"):
        ctx.places.put(blk, {(1, 1, 0): [(3, "POD:1")], (2, 1, 0): [(3, "POD:2")]})
    es = edges_of(ctx, "POD:1")
    check("взаимно без касания вокселей - AOc CANDIDATE", es == {("POD:2", "AOc", "CANDIDATE")})


def test_wall_floor():
    ctx = FakeCtx()
    for k in ("DOOR:3", "DOOR:4", "DOOR:5"):
        ctx.mcd(k, 1, WEST)
    ctx.mcd("WALL:0", 1, WEST)
    for blk in ("B1", "B2"):
        g = defaultdict(list)
        for y in range(0, 10):
            g[(3, y, 0)].append((1, "WALL:0"))
        g[(3, 4, 0)] = [(1, "DOOR:3")]
        g[(3, 5, 0)] = [(1, "DOOR:4")]
        g[(3, 6, 0)] = [(1, "DOOR:5")]
        ctx.places.put(blk, dict(g))
    es = edges_of(ctx, "DOOR:3")
    check("проём в западной стене: AW STRONG до DOOR:4 и DOOR:5", ("DOOR:4", "AW", "STRONG") in es and
          ("DOOR:5", "AW", "STRONG") in es)
    check("стена-основа на нескольких сдвигах - не партнёр проёма", not any(t == "WALL:0" for t, _r, _l in es))
    ctx = FakeCtx()
    for k in ("LOGO:1", "LOGO:2", "CARPET:0"):
        ctx.mcd(k, 0, FLOOR)
    for blk in ("B1", "B2", "B3"):
        g = {(x, y, 0): [(0, "CARPET:0")] for x in range(6) for y in range(6)}
        g[(2, 2, 0)] = [(0, "LOGO:1")]
        g[(3, 2, 0)] = [(0, "LOGO:2")]
        ctx.places.put(blk, g)
    es = edges_of(ctx, "LOGO:1")
    check("логотип из двух полов: AF STRONG", ("LOGO:2", "AF", "STRONG") in es)
    check("ковёр вокруг - не партнёр", not any(t == "CARPET:0" for t, _r, _l in es))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_car()
    test_one_sided()
    test_checker()
    test_single()
    test_no_contact()
    test_wall_floor()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
