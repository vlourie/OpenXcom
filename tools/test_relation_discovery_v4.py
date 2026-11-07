#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка relation_discovery_v4 на синтетике, без установки игры и без видеокарты.

  - политика: MR1 из V3 - RELATED_STRONG, подтип MIRRORED_RECOLOR_CANDIDATE (TYPE_OPEN), кадр не рисуется сам, роль
    в ось B не идёт; вариант typed - TYPE_STRONG; R4 - существование до STRONG, тип всегда открыт; примыкание - только
    улика; составной V3 (PLACE) снимается; анимация и перекраска по-прежнему сосуществуют
  - PLACEMENT_STRUCTURE_V3: доля по слою (кусок в двух слоях) находит составной, контроль - V3 по всем местам нет;
    стул у стола - ATTACHMENT_CANDIDATE с обеих сторон, не составной; связки 2 и 3 клетки - P5r, STRONG только с двумя
    уликами вне карты
  - R4: почти тот же силуэт с функцией цвета - R4b; перемешанный контроль и другой рисунок - нет; наборы-перекраски -
    существование STRONG и R4c; местная правка - R4d; точная копия - не R4
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
sys.path.insert(0, HERE)
import relation_discovery_v2 as v2                              # noqa: E402
import relation_discovery_v3 as v3                              # noqa: E402
import relation_discovery_v4 as v4                              # noqa: E402
from test_relation_discovery_v2 import frame, recolor           # noqa: E402
from test_relation_discovery_v3 import FakeCtx, info            # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def claims(cls, edges):
    C = cls()
    for e in edges:
        e2 = v4.convert_v3(e)
        if e2:
            C.add(e2)
    return C.finalize()


def test_policy():
    mr = v2.edge("MIRRORED_RECOLOR", "M:1", "N:2", "CANDIDATE", "MIRROR", "MR1", "")
    C = claims(v4.V4Claims, [mr])
    c = C.pair("M:1", "N:2")[0]
    check("policy: MR1 - RELATED_STRONG", c["existence"] == v4.STRONG)
    check("policy: MR1 - TYPE_OPEN, MIRRORED_RECOLOR_CANDIDATE",
          c["type_level"] == v4.T_OPEN and "MIRRORED_RECOLOR_CANDIDATE" in c["type_open_why"])
    check("policy: MR1 - кадр не рисуется сам, роль в ось B не идёт",
          v4.bound(C, "M:1") and v4.bound(C, "N:2") and v4.pipe_roles(C, "M:1") == ["CANONICAL"])
    Ct = claims(v4.V4ClaimsTyped, [mr])
    ct = Ct.pair("M:1", "N:2")[0]
    check("policy typed: MR1 - TYPE_STRONG, роль пары перекраски",
          ct["type_level"] == v4.T_STRONG and v4.pipe_roles(Ct, "M:1") == ["RECOLOR_PEER"])
    nr = v2.edge("NEAR_RECOLOR", "M:1", "K:2", "CANDIDATE", "MIRROR", "NR1", "")
    check("policy: NEAR_RECOLOR - диагностика, кандидат", claims(v4.V4Claims, [nr]).pair("M:1", "K:2")[0]["existence"] == v4.CAND)
    r4 = v2.edge("NEAR_SILHOUETTE_RECOLOR", "R:1", "Q:1", "STRONG", "R4", "R4bs", "")
    c4 = claims(v4.V4ClaimsTyped, [r4]).pair("R:1", "Q:1")[0]
    check("policy: R4 STRONG - существование STRONG, тип открыт даже в typed",
          c4["existence"] == v4.STRONG and c4["type_level"] == v4.T_OPEN)
    at = v2.edge("ATTACHMENT_CANDIDATE", "CH:0", "TB:0", "CANDIDATE", "PLACE4", "A1", "")
    Ca = claims(v4.V4Claims, [at])
    ca = Ca.pair("CH:0", "TB:0")[0]
    check("policy: примыкание - не составной, улика, кадр не связан",
          ca["group"] == "attachment" and ca["existence"] == v4.CAND and not v4.bound(Ca, "CH:0") and
          v3.has_evidence(Ca, "CH:0"))
    pl = v2.edge("COMPOSITE_PART", "P:1", "P:2", "STRONG", "PLACE", "P3x", "")
    check("policy: составной V3 (PLACE) снимается", not claims(v4.V4Claims, [pl]).claims)
    Cr = claims(v4.V4Claims, [v2.edge("RECOLOR_PEER", "S:21", "S:14", "STRONG", "RECOLOR", "C2", ""),
                              v2.edge("ANIMATION_FAMILY", "S:14", "S:21", "STRONG", "MCD", "M-anim", "")])
    cs = Cr.pair("S:21", "S:14")
    check("policy: анимация и перекраска сосуществуют (TaxClaims), перекраска - не производство",
          all(c["type_level"] == v4.T_STRONG for c in cs) and
          [c["production"] for c in cs if c["group"] == "derived"] == [False])


def test_placement():
    grids = []
    for i in range(6):                         # кусок в слое 2 всегда с соседом
        grids.append({(1, 1, 0): [(2, "NC:3")], (2, 1, 0): [(2, "NC:4")]})
    for i in range(4):                         # тот же кадр в слое 3 - другая роль, соседа нет
        grids.append({(5, 5, 0): [(3, "NC:3")]})
    ctx = FakeCtx(grids=grids)
    es = v4.placement_v3(ctx, "NC:3")
    comp = [e for e in es if e["type"] == "COMPOSITE_PART" and e["target"] == "NC:4"]
    check("placement: доля по слою - составной найден (P3L)", len(comp) == 1 and comp[0]["rule"] == "P3L")
    check("placement: контроль - V3 по всем местам (6 из 10) его не видит", v3.placement_structure(ctx, "NC:3") == [])
    chair = [{(5, 5, 0): [(3, "TB:0")], (6, 5, 0): [(3, "CH:0")]} for _ in range(5)] + \
        [{(5, 5, 0): [(3, "TB:0")]} for _ in range(5)]
    ctx2 = FakeCtx(grids=chair)
    e_ch = v4.placement_v3(ctx2, "CH:0")
    e_tb = v4.placement_v3(ctx2, "TB:0")
    check("placement: стул у стола - ATTACHMENT A1 со стороны стула",
          [(e["type"], e["rule"], e["source"], e["target"]) for e in e_ch] == [("ATTACHMENT_CANDIDATE", "A1", "CH:0", "TB:0")])
    check("placement: со стороны стола - A1r, то же направление",
          [(e["type"], e["rule"], e["source"], e["target"]) for e in e_tb] == [("ATTACHMENT_CANDIDATE", "A1r", "CH:0", "TB:0")])
    check("placement: пара контроля (only) - примыкание без A1r",
          [e["rule"] for e in v4.placement_v3(ctx2, "TB:0", only="CH:0")] == [] and
          [e["rule"] for e in v4.placement_v3(ctx2, "CH:0", only="TB:0")] == ["A1"])
    runs = []
    for i in range(4):                         # связка 2 клетки рядом со связкой 3 клеток, сдвиг x+1
        runs.append({(1, 0, 0): [(3, "NK:3")], (1, 1, 0): [(3, "NK:3")],
                     (2, 0, 0): [(3, "NK:4")], (2, 1, 0): [(3, "NK:4")], (2, 2, 0): [(3, "NK:4")]})
    ctx3 = FakeCtx(grids=runs)
    e3 = [e for e in v4.placement_v3(ctx3, "NK:3") if e["target"] == "NK:4"]
    check("placement: связки - P5rc без второй улики (только порядок номеров)",
          [(e["rule"], e["level"]) for e in e3] == [("P5rc", "CANDIDATE")])
    ctx4 = FakeCtx(grids=runs, infos={"NK:3": info(), "NK:4": info()})
    e4 = [e for e in v4.placement_v3(ctx4, "NK:3") if e["target"] == "NK:4"]
    check("placement: связки и две улики вне карты - P5r STRONG", [(e["rule"], e["level"]) for e in e4] == [("P5r", "STRONG")])
    check("placement: контроль - по клеткам взаимности нет (V3 молчит)", v3.placement_structure(ctx3, "NK:3") == [])


def trim(a, col=19):
    b = a.copy()
    b[:, col, 3] = 0
    b[b[..., 3] == 0, :3] = 0
    return b


def test_r4():
    a = frame(1)
    near = trim(recolor(a, lambda i, c: (255 - c[0], c[2], c[1])))
    o = frame(99)                                # другой рисунок: свои цвета, разложенные по силуэту иначе
    m = o[..., 3] > 0
    o[m] = o[m][np.random.default_rng(3).permutation(int(m.sum()))]
    other = trim(o)
    ctx = FakeCtx({"S:0": a, "T:5": near, "U:5": other, "V:0": a.copy()})
    si = v4.SetIndex(ctx)
    es = v4.r4_pair(ctx, si, "S:0", "T:5")
    check("r4: почти тот же силуэт и функция цвета - R4b кандидат",
          [(e["rule"], e["level"]) for e in es] == [("R4b", "CANDIDATE")])
    check("r4: перемешанный контроль - молчит", v4.r4_pair(ctx, si, "S:0", "T:5", B=v3.permuted(ctx, "T:5", 7)) == [])
    check("r4: другой рисунок того же силуэта - молчит", v4.r4_pair(ctx, si, "S:0", "U:5") == [])
    check("r4: точная копия - не R4", v4.r4_pair(ctx, si, "S:0", "V:0") == [])
    fr = {}
    for n in range(9):
        x = frame(10 + n)
        fr["A:%d" % n] = x
        fr["B:%d" % n] = recolor(x, lambda i, c: (c[1], c[2], c[0]))
    fr["B:0"] = trim(fr["B:0"])
    ctx2 = FakeCtx(fr)
    si2 = v4.SetIndex(ctx2)
    es2 = {e["rule"]: e for e in v4.r4_pair(ctx2, si2, "A:0", "B:0")}
    check("r4: наборы-перекраски - существование STRONG (R4bs) и соответствие наборов (R4cs)",
          sorted(es2) == ["R4bs", "R4cs"] and all(e["level"] == "STRONG" for e in es2.values()))
    C = claims(v4.V4Claims, list(es2.values()))
    check("r4: STRONG по наборам - тип всё равно открыт", all(c["type_level"] == v4.T_OPEN for c in C.claims.values()))
    ed = recolor(a, lambda i, c: (c[1], c[0], c[2]))
    ed[8:10, 4:20, :3] = ed[30, 10, :3]          # местная правка: часть одной области цветом другой (не функция ни туда, ни обратно)
    ctx3 = FakeCtx({"S:0": a, "W:3": ed})
    si3 = v4.SetIndex(ctx3)
    e3 = v4.r4_pair(ctx3, si3, "S:0", "W:3")
    sc = v4.r4_scores(a, ed, False)
    check("r4: местная правка - R4d (функция %.3f, границ %.2f)" % (sc["fmax"], sc["topology"]),
          [e["rule"] for e in e3] == ["R4d"])
    check("r4: местная правка, перемешанный контроль - молчит",
          v4.r4_pair(ctx3, si3, "S:0", "W:3", B=v3.permuted(ctx3, "W:3", 7)) == [])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_policy()
    test_placement()
    test_r4()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
