#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка relation_discovery_v3 на синтетике, без установки игры и без видеокарты.

  - граф доводов: у пары два довода разных групп (составной и разрушенный вид) - оба живы; контроль - граф V2
    второе ребро на ту же пару не кладёт. Один и тот же довод от двух детекторов хранится один раз с двумя опорами
  - существование и тип: спор гипотез вывода (перекраска против петли анимации) - существование STRONG, тип
    TYPE_OPEN у обоих, кадр не рисуется сам и роль в ось B не идёт; точная копия с петлёй не спорит
  - MIRRORED_RECOLOR_V1: отражённая перекраска - только кандидат и TYPE_OPEN; цвета, перемешанные внутри силуэта, и
    другой рисунок того же отражённого силуэта - не срабатывают; совместимость MCD по вокселям, отражённым по
    диагонали
  - PLACEMENT_STRUCTURE_V2: две расстановки и две улики вне карты - STRONG; без улик - CANDIDATE; стул у стола
    (односторонне) - ничего; много мест - карта решает сама; след без общего узора - не STRONG
  - модуль: стык по оси с кадрами того же класса MCD и касанием вокселей - кандидат; один постоянный сосед - нет
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
sys.path.insert(0, HERE)
import relation_discovery_v2 as v2                              # noqa: E402
import relation_discovery_v3 as v3                              # noqa: E402
from test_relation_discovery_v2 import FakePlaces, frame, recolor   # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def box(full=True):
    v = np.zeros((12, 16, 16), bool)
    if full:
        v[:6] = True
    return v


class FakeCtx:
    def __init__(self, frames=None, infos=None, grids=None, mcd_ok=False):
        self.f = {k.upper(): v for k, v in (frames or {}).items()}
        self.ix = v2.Index({k: list(v2.digests(v)) for k, v in self.f.items()})
        self.infos = {k.upper(): v for k, v in (infos or {}).items()}
        self.places = FakePlaces(grids or [])
        self.mcd_ok = mcd_ok
        keys = sorted(self.f)
        self.masks = v3.Masks(keys, np.stack([np.packbits((self.f[k][..., 3] > 0).ravel()) for k in keys]),
                              (40, 32)) if keys else None

    def rgba(self, k):
        return self.f.get(k.upper())

    def mcd_compatible(self, a, b):
        return self.mcd_ok

    def info(self, k):
        return self.infos.get(k.upper(), {"rec": False})

    mcd_mirror_compatible = v3.Ctx.mcd_mirror_compatible


def info(tile=3, armor=20, vox=None):
    return {"rec": True, "tile_type": tile, "vox": box() if vox is None else vox,
            "phys": {"armor": armor, "flammable": 255, "fuel": 0, "footstep": 1}}


def test_graph():
    C = v3.Claims()
    C.add(v2.edge("COMPOSITE_PART", "T:84", "T:82", "STRONG", "PLACE", "P3x", ""))
    C.add(v2.edge("DESTROYED_VARIANT_OF", "T:84", "T:82", "STRONG", "MCD", "M-die", ""))
    C.add(v2.edge("DESTROYED_VARIANT_OF", "T:84", "T:82", "STRONG", "V8", "R3m", ""))
    C.finalize()
    cs = C.pair("T:84", "T:82")
    check("graph: составной и разрушенный вид на одной паре - два довода", sorted(c["group"] for c in cs) == ["composite", "state"])
    st = [c for c in cs if c["group"] == "state"][0]
    check("graph: один довод от двух детекторов хранится один раз, опор две",
          len(st["support"]) == 2 and st["support"][0]["detector"] == "V8")
    check("graph: составной со state не спорит - оба TYPE_STRONG", all(c["type_level"] == v3.T_STRONG for c in cs))
    g = v2.Graph()
    g.add(v2.edge("DESTROYED_VARIANT_OF", "T:84", "T:82", "STRONG", "MCD", "M-die", ""))
    check("graph: контроль - граф V2 второе ребро на пару не кладёт",
          not g.add(v2.edge("COMPOSITE_PART", "T:84", "T:82", "STRONG", "PLACE", "P1", "")))


def test_existence_type():
    C = v3.Claims()
    C.add(v2.edge("RECOLOR_PEER", "S:21", "S:14", "STRONG", "RECOLOR", "C2", ""))
    C.add(v2.edge("ANIMATION_FAMILY", "S:14", "S:21", "STRONG", "MCD", "M-anim", ""))
    C.add(v2.edge("EXACT_COPY_PEER", "A:1", "A:2", "STRONG", "EXACT", "X1", ""))
    C.add(v2.edge("ANIMATION_FAMILY", "A:2", "A:1", "STRONG", "MCD", "M-anim", ""))
    C.add(v2.edge("DESTROYED_VARIANT_OF", "D:2", "D:1", "STRONG", "MCD", "M-die", ""))
    C.finalize()
    cs = C.pair("S:21", "S:14")
    check("type: спор перекраски и анимации - существование STRONG у обоих",
          all(c["existence"] == v3.STRONG for c in cs) and len(cs) == 2)
    check("type: спор - TYPE_OPEN у обоих", all(c["type_level"] == v3.T_OPEN for c in cs))
    check("type: RELATED_STRONG + TYPE_OPEN - кадр не рисуется сам (обе стороны)",
          v3.bound(C, "S:21") and v3.bound(C, "S:14"))
    check("type: открытый тип не идёт ролью в ось B", v3.pipe_roles(C, "S:21") == ["CANONICAL"])
    check("type: точная копия с петлёй не спорит", all(c["type_level"] == v3.T_STRONG for c in C.pair("A:1", "A:2")))
    check("type: основа разрушенного вида без спора - рисуется сама", not v3.bound(C, "D:1") and v3.bound(C, "D:2"))
    check("type: группы auto у спорной пары - canonical, strong - обе гипотезы",
          v3.groups_of(C, "S:21", "auto") == ["canonical"] and v3.groups_of(C, "S:21", "strong") == ["animation", "derived"])


def test_mirror():
    a = frame(11, colors=10)
    a[8:36, 4:20, 3] = 255
    a[8:20, 20:26, 3] = 255                           # несимметричный силуэт
    a[a[..., 3] == 0, :3] = 0
    m = np.ascontiguousarray(a[:, ::-1])
    mr = recolor(m, lambda i, c: (20 + 20 * i, 40, 200 - 15 * i))
    other = m.copy()
    body = other[other[..., 3] > 0][:, :3]
    other[other[..., 3] > 0, :3] = body[np.random.default_rng(3).permutation(len(body))]
    ctx = FakeCtx({"A:1": a, "B:9": mr, "C:4": other},
                  infos={"A:1": info(), "B:9": info(vox=box().transpose(0, 2, 1))})
    es = v3.mirror_near_edges(ctx, "A:1")
    hit = [e for e in es if e["target"] == "B:9"]
    check("mirror: отражённая перекраска найдена", len(hit) == 1 and hit[0]["type"] == "MIRRORED_RECOLOR")
    check("mirror: только CANDIDATE", all(e["level"] == "CANDIDATE" for e in es))
    check("mirror: другой рисунок того же отражённого силуэта - нет", not [e for e in es if e["target"] == "C:4"])
    sc, _w = v3.recolor_test(ctx, "A:1", "B:9", True, B=v3.permuted(ctx, "B:9", 7))
    check("mirror: перемешанный контроль - не срабатывает", sc is None)
    check("mirror: MCD совместим по вокселям, отражённым по диагонали", hit and hit[0]["scores"]["mcd"])
    C = v3.Claims()
    for e in es:
        C.add(e)
    C.finalize()
    check("mirror: довод - RELATED_CANDIDATE и TYPE_OPEN",
          all(c["existence"] == v3.CAND and c["type_level"] == v3.T_OPEN for c in C.claims.values()))
    check("mirror: кадр не рисуется сам - уходит на ревью", v3.has_evidence(C, "A:1"))


def test_contact():
    va = np.zeros((12, 16, 16), bool)
    va[:4, :, 15] = True
    vb = np.zeros((12, 16, 16), bool)
    vb[:4, :, 0] = True
    check("contact: грани по x касаются", v3.contact(va, vb, (1, 0, 0)) == 1.0)
    check("contact: с другой стороны грани пусты", v3.contact(va, vb, (-1, 0, 0)) == 0.0)
    check("contact: диагональный сдвиг - грани нет", v3.contact(va, vb, (1, 1, 0)) is None)


def test_placement():
    grids = [{(1, 1, 0): [(3, "BED:1")], (2, 1, 0): [(3, "BED:2")]} for _ in range(2)]
    infos = {"BED:1": info(), "BED:2": info()}
    ctx = FakeCtx(infos=infos, grids=grids)
    es = v3.placement_structure(ctx, "BED:1")
    check("placement: две расстановки и улики вне карты - STRONG P3x",
          len(es) == 1 and es[0]["level"] == "STRONG" and es[0]["rule"] == "P3x")
    ctx2 = FakeCtx(infos={"BED:1": info(armor=10), "BEDX:7": info(armor=50, vox=np.zeros((12, 16, 16), bool))},
                   grids=[{(1, 1, 0): [(3, "BED:1")], (2, 1, 0): [(3, "BEDX:7")]} for _ in range(2)])
    es2 = v3.placement_structure(ctx2, "BED:1")
    check("placement: только карта на двух местах - CANDIDATE", len(es2) == 1 and es2[0]["level"] == "CANDIDATE")
    many = [{(1, 1, 0): [(3, "Q:1")], (2, 1, 0): [(3, "Z:7")]} for _ in range(6)]
    ctx3 = FakeCtx(infos={"Q:1": info(armor=1), "Z:7": info(armor=2)}, grids=many)
    es3 = v3.placement_structure(ctx3, "Q:1")
    check("placement: шесть мест в шести блоках - карта решает сама (P3)", len(es3) == 1 and es3[0]["rule"] == "P3")
    chair = [{(5, 5, 0): [(3, "TABLE:0")], (6, 5, 0): [(3, "CHAIR:0")]} for _ in range(2)] + \
        [{(5, 5, 0): [(3, "TABLE:0")]} for _ in range(4)]
    ctx4 = FakeCtx(infos={"TABLE:0": info(), "CHAIR:0": info()}, grids=chair)
    check("placement: стул у стола (стол стоит и без стула) - ничего", v3.placement_structure(ctx4, "CHAIR:0") == [])
    loose = []
    for i in range(6):
        g = {(1, 1, 0): [(3, "P:1")], (2, 1, 0): [(3, "P:2")]}
        if i < 4:
            g[(1, 2, 0)] = [(3, "P:3")]
        loose.append(g)
    ctx5 = FakeCtx(infos={k: info(armor=i) for i, k in enumerate(("P:1", "P:2", "P:3"))}, grids=loose)
    es5 = {e["target"]: e for e in v3.placement_structure(ctx5, "P:1")}
    check("placement: третий кусок не всегда рядом - не во взаимном следе", "P:3" not in es5 and "P:2" in es5)


def test_module():
    run = []
    for i in range(5):
        run.append({(1, 1, 0): [(1, "W:1")], (1, 2, 0): [(1, "W:2")], (1, 0, 0): [(1, "W:3")]})
    wall = np.zeros((12, 16, 16), bool)
    wall[:, :, 0] = True
    infos = {k: info(tile=1, vox=wall) for k in ("W:1", "W:2", "W:3")}
    ctx = FakeCtx(infos=infos, grids=run)
    m = v3.module_structure(ctx, "W:1")
    check("module: стена в ряду с разными соседями того же класса - кандидат", m is not None and m["level"] == "CANDIDATE")
    one = [{(1, 1, 0): [(1, "W:1")], (1, 2, 0): [(1, "W:2")]} for _ in range(5)]
    check("module: один постоянный сосед - узор составного, не модуль",
          v3.module_structure(FakeCtx(infos=infos, grids=one), "W:1") is None)
    other = {"W:1": info(tile=1, vox=wall), "W:2": info(tile=1, armor=99, vox=wall), "W:3": info(tile=1, armor=99, vox=wall)}
    check("module: соседи другого класса MCD - нет", v3.module_structure(FakeCtx(infos=other, grids=run), "W:1") is None)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_graph()
    test_existence_type()
    test_mirror()
    test_contact()
    test_placement()
    test_module()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
