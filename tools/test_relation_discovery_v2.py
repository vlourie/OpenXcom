#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка relation_discovery_v2 на синтетике, без установки игры и без видеокарты.

  - точная копия и зеркало по хэшу пикселей; цвет под нулевой альфой не входит в хэш (R-043)
  - тёмная перекраска (два оттенка сведены в один) - RECOLOR_OF в одну сторону, от производного к основе;
    контроль - V1 (функция в обе стороны) её не видит (R-166)
  - перекраска без подтверждения MCD и порядка номеров - CANDIDATE, а не STRONG
  - безопасность V2: основа с исходящим die одиночно рисоваться может (IDT_SNOWCULTIVAT:12), производный - нет;
    контроль - замороженное правило V8 считает основу опасной
  - составной только при взаимной встрече: стул у стола (стол стоит и без стула) - не составной
  - граф: одна связь - одно ребро, первое по порядку сохраняется
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import relation_discovery_v2 as rd   # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def frame(seed, colors=8):
    rng = np.random.default_rng(seed)
    a = np.zeros((40, 32, 4), np.uint8)
    a[8:36, 4:20, 3] = 255
    pal = rng.integers(20, 235, (colors, 3), dtype=np.uint8)
    idx = rng.integers(0, colors, (40, 32))
    idx[8:36, 4:20] = np.repeat(np.arange(colors), 28 * 16 // colors + 1)[:28 * 16].reshape(28, 16)
    a[..., :3] = pal[idx]
    a[a[..., 3] == 0, :3] = 0
    return a


def recolor(a, mapping):
    """Новый цвет - функция старого по индексу цвета (порядок уникальных цветов)."""
    b = a.copy()
    cols = [tuple(c) for c in np.unique(a[a[..., 3] > 0][:, :3], axis=0)]
    for i, c in enumerate(cols):
        m = (a[..., :3] == c).all(-1) & (a[..., 3] > 0)
        b[m, :3] = mapping(i, c)
    return b


class FakeCtx:
    def __init__(self, frames, mcd_ok=False):
        self.f = {k.upper(): v for k, v in frames.items()}
        self.ix = rd.Index({k: list(rd.digests(v)) for k, v in self.f.items()})
        self.mcd_ok = mcd_ok

    def rgba(self, k):
        return self.f.get(k.upper())

    def mcd_compatible(self, a, b):
        return self.mcd_ok


def test_exact():
    a = frame(1)
    b = a.copy()
    b[0, 0, :3] = 77                       # под нулевой альфой - не рисуется
    m = np.ascontiguousarray(a[:, ::-1])
    ctx = FakeCtx({"S:0": a, "T:5": b, "U:1": m})
    check("exact: копия с другим цветом под нулевой альфой найдена", "T:5" in ctx.ix.exact("S:0"))
    check("exact: зеркало - EXACT_MIRROR, не копия", "U:1" in ctx.ix.mirror("S:0") and "U:1" not in ctx.ix.exact("S:0"))
    es = rd.exact_edges(ctx.ix, "S:0")
    check("exact: рёбра STRONG и симметричные",
          {e["type"] for e in es} == {"EXACT_COPY_PEER", "EXACT_MIRROR_PEER"} and all(e["level"] == "STRONG" for e in es))
    check("exact: пустой кадр не индексируется", rd.digests(np.zeros((40, 32, 4), np.uint8)) is None)


def test_recolor():
    import relation_probe as rp
    a = frame(2, colors=10)
    dark = recolor(a, lambda i, c: (5 + 3 * (i // 2), 5, 5))      # пары оттенков сведены в один - функция в одну сторону
    ctx = FakeCtx({"BASE:3": a, "DARK:3": dark}, mcd_ok=True)
    e = rd.recolor_pair(ctx, "DARK:3", "BASE:3")
    check("recolor: тёмная перекраска найдена", e is not None and e["type"] == "RECOLOR_OF")
    check("recolor: направление от производного к основе", e is not None and e["source"] == "DARK:3" and e["target"] == "BASE:3")
    check("recolor: MCD совместим и основа информативна - STRONG", e is not None and e["level"] == "STRONG")
    ma, ca = rp.codes(a)
    _mb, cb = rp.codes(dark)
    f_ab, f_ba = rp.func_map(ca[ma], cb[ma])[0], rp.func_map(cb[ma], ca[ma])[0]
    check("recolor: контроль - V1 (функция в обе стороны) её не видит", not (f_ab >= rp.FUNC and f_ba >= rp.FUNC))
    ctx2 = FakeCtx({"BASE:3": a, "DARK:3": dark}, mcd_ok=False)
    e2 = rd.recolor_pair(ctx2, "DARK:3", "BASE:3")
    check("recolor: без MCD и без порядка номеров - CANDIDATE", e2 is not None and e2["level"] == "CANDIDATE")
    other = a.copy()
    body = other[8:36, 4:20, :3].reshape(-1, 3)
    other[8:36, 4:20, :3] = body[np.random.default_rng(5).permutation(len(body))].reshape(28, 16, 3)
    ctx3 = FakeCtx({"BASE:3": a, "OTHER:3": other}, mcd_ok=True)
    check("recolor: другой рисунок того же силуэта - нет ребра", rd.recolor_pair(ctx3, "OTHER:3", "BASE:3") is None)


def row(a, ref_groups, ref_pipe="OBJECT_PIPELINE"):
    return {"asset_id": a, "ref_pipeline": ref_pipe, "ref_role_groups": ref_groups, "ref_role_status": "judged",
            "creative": True}


def test_safety():
    import routing_model_v8 as v8
    g = rd.Graph()
    g.add(rd.edge("DESTROYED_VARIANT_OF", "X:13", "X:12", "STRONG", "MCD", "M-die", ""))
    pairs = [{"relative": "X:13", "ref_pair_relation": "STATE_VARIANT_OF", "direction": "open"}]
    fs = [{"relative": "X:13", "dir": "OUT", "via": "die"}]
    base = row("X:12", ["state"])
    check("safety: основа с исходящим die - не опасна", rd.danger_v2(base, True, g, pairs, fs) == [])
    check("safety: контроль - замороженное правило V8 считает её опасной", v8.dangerous_creative_standalone(base))
    der = row("X:13", ["state"])
    fs_in = [{"relative": "X:12", "dir": "IN", "via": "die"}]
    check("safety: производный (die чужой записи) одиночно - опасен",
          bool(rd.danger_v2(der, True, g, [{"relative": "X:12", "ref_pair_relation": "STATE_VARIANT_OF",
                                            "direction": "open"}], fs_in)))
    sym = [{"relative": "Y:1", "ref_pair_relation": "RECOLOR_OF", "direction": "open"}]
    check("safety: симметричная пара без группы - опасна", bool(rd.danger_v2(row("Z:1", ["derived"]), True, rd.Graph(), sym, [])))
    gp = rd.Graph()
    gp.add(rd.edge("EXACT_COPY_PEER", "Z:1", "Y:1", "STRONG", "EXACT", "X1", ""))
    check("safety: та же пара в группе рисования - не опасна", rd.danger_v2(row("Z:1", ["derived"]), True, gp, sym, []) == [])
    check("safety: точная копия связывает кадр - не одиночный заказ", rd.bound(gp, "Z:1") and rd.bound(gp, "Y:1"))
    check("safety: основа только с входящим ребром не связана", not rd.bound(g, "X:12") and rd.bound(g, "X:13"))


class FakePlaces:
    def __init__(self, grids):
        self.grids = grids

    def of(self, k):
        out = []
        for bi, grid in enumerate(self.grids):
            for pos, ks in grid.items():
                for layer, kk in ks:
                    if kk == k.upper():
                        out.append(("T", "B%d" % bi, grid, pos, layer))
        return out


def test_composite():
    grids = []
    for i in range(4):                     # кровать из двух кусков: всегда вместе, на одном сдвиге
        grids.append({(1, 1, 0): [(3, "BED:1")], (2, 1, 0): [(3, "BED:2")]})
    for i in range(4):                     # стол без стула и стол со стулом
        g = {(5, 5, 0): [(3, "TABLE:0")]}
        if i < 2:
            g[(6, 5, 0)] = [(3, "CHAIR:0")]
        grids.append(g)
    grids.append({(1, 1, 0): [(3, "CHAIR:0")], (2, 1, 0): [(3, "TABLE:0")]})
    ctx = FakeCtx({})
    ctx.places = FakePlaces(grids)
    es = rd.composite_edges(ctx, "BED:1")
    check("composite: два куска всегда вместе - COMPOSITE_PART STRONG",
          len(es) == 1 and es[0]["target"] == "BED:2" and es[0]["level"] == "STRONG")
    check("composite: стул у стола (стол стоит и без стула) - не составной", rd.composite_edges(ctx, "CHAIR:0") == [])


def test_graph():
    g = rd.Graph()
    first = rd.edge("ANIMATION_FAMILY", "A:2", "A:1", "STRONG", "MCD", "M-anim", "")
    check("graph: первое ребро кладётся", g.add(first))
    check("graph: второе ребро на ту же пару - нет", not g.add(rd.edge("EXACT_COPY_PEER", "A:1", "A:2", "STRONG", "EXACT", "X1", "")))
    check("graph: пара держит первое", g.between("A:1", "A:2")["type"] == "ANIMATION_FAMILY")
    check("graph: группы с обеих сторон", rd.groups_of(g, "A:1") == ["animation"] == rd.groups_of(g, "A:2"))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_exact()
    test_recolor()
    test_safety()
    test_composite()
    test_graph()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
