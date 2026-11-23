#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка relation_holdout_v4 на синтетике, без установки игры: то, что замораживается вместе с V4.

  - отбор: квоты подслоёв, добор внутри слоя, один кадр на набор PCK, перенос недобора слоя в другие слои по кругу;
    контроль - без переноса (как V7) холдаут короче
  - безопасность: только творческий кадр; закрытая производная пара без довода - опасно, с доводом - нет; входящее
    ребро MCD - опасно и с доводом; исходящее - нет; составной без довода - опасно; открытый подтип - вне ворот
  - ворота: ровно шесть ворот V4 (те же пороги) плюс handoff; NO_DATA даёт INCONCLUSIVE, провал - FAIL
  - пул пар: утверждения все, побайтовые не больше EXACT_CAP, рёбра MCD все, независимых не меньше CAND_MIN_INDEP,
    повтор кадра в двух источниках - одна пара с двумя причинами, сам кадр не пара
  - кадры разработки: обе стороны пар истины v2, слепое зеркало, контроль, утверждения V4
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import relation_discovery_v2 as v2                              # noqa: E402
import relation_discovery_v4 as v4                              # noqa: E402
import relation_holdout_v4 as hv                                # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def row(k):
    return {"asset_id": k, "rank": "1", "kind": "один", "action": "GENERATE", "places": "3"}


def pool_of(spec):
    """{подслой: [ключ]} -> пул в формате h7.pools."""
    return {name: [(k, row(k), "синтетика") for k in ks] for name, ks in spec.items()}


def test_select():
    layers = (("A", 4, (("a1", 2), ("a2", 2))), ("B", 3, (("b1", 3),)), ("C", 3, (("c1", 3),)))
    pool = pool_of({"a1": ["SA%d:0" % i for i in range(5)], "a2": ["SB0:0"],
                    "b1": ["SC%d:0" % i for i in range(3)], "c1": ["SD%d:0" % i for i in range(6)]})
    items, short, moved = hv.select(pool, layers, 10)
    by = {}
    for x in items:
        by.setdefault(x["sub"], []).append(x)
    check("отбор: добор внутри слоя (a2 один - a1 три)", len(by["a1"]) == 3 and len(by["a2"]) == 1)
    check("отбор: недобор подслоя записан", "a2" in short)
    check("отбор: квоты полных слоёв", len(by["b1"]) == 3 and len(by["c1"]) == 3)
    sets = [hv.pset(x["asset_id"]) for x in items]
    check("отбор: один кадр на набор PCK", len(sets) == len(set(sets)))
    # слой B пуст наполовину: 3 из 3 нужно, есть 1 - два кадра переносятся в слои по кругу
    pool2 = pool_of({"a1": ["SA%d:0" % i for i in range(6)], "a2": ["SB%d:0" % i for i in range(4)],
                     "b1": ["SC0:0"], "c1": ["SD%d:0" % i for i in range(6)]})
    items2, short2, moved2 = hv.select(pool2, layers, 10)
    check("отбор: перенос недобора слоя - всего 10", len(items2) == 10)
    check("отбор: недобор слоя B записан", "B" in short2)
    check("отбор: перенос по кругу A и C по одному", moved2 == {"A": 1, "C": 1})
    check("отбор: перенос помечен", sum("перенос недобора" in x["why_selected"] for x in items2) == 2)
    # контроль: без переноса (как V7) холдаут короче
    import routing_holdout_v7 as h7
    old = h7.LAYERS
    try:
        h7.LAYERS = layers
        ctl, _s = h7.select(pool2)
    finally:
        h7.LAYERS = old
    check("отбор, контроль: без переноса (V7) кадров 8", len(ctl) == 8)
    # порядок заполнения: редкий слой C первым забирает свой набор, иначе его берёт богатый слой A
    pool4 = pool_of({"a1": ["SZ:0", "SA1:0", "SA2:0", "SA3:0"], "a2": [], "b1": ["SC%d:0" % i for i in range(3)],
                     "c1": ["SZ:1"]})
    first, _s, _m = hv.select(pool4, layers, 10, fill=("C", "A", "B"))
    plain, _s, _m = hv.select(pool4, layers, 10)
    check("отбор: редкий слой первым - его набор не уходит богатому (контроль: порядок LAYERS - уходит)",
          [x["asset_id"] for x in first if x["sub"] == "c1"] == ["SZ:1"]
          and not any(x["sub"] == "c1" for x in plain))
    check("отбор: FILL_ORDER - все слои ровно один раз",
          sorted(hv.FILL_ORDER) == sorted(n for n, _q, _s in hv.LAYERS))
    # одинаковый набор в двух подслоях - второй не берётся
    pool3 = pool_of({"a1": ["SX:0", "SX:1"], "a2": ["SX:2", "SY:0"], "b1": [], "c1": []})
    items3, _s3, _m3 = hv.select(pool3, layers, 10)
    check("отбор: набор SX один раз на холдаут", sum(hv.pset(x["asset_id"]) == "SX" for x in items3) == 1)


def claims(edges):
    C = v4.V4Claims()
    for e in edges:
        C.add(e)
    return C.finalize()


def test_danger():
    rel_der = ("RELATED", {"RECOLOR_PEER"}, set())
    rel_comp = ("RELATED", {"COMPOSITE"}, set())
    rel_open = ("RELATED", set(), {"RECOLOR_PEER", "DERIVED"})
    none = ("NONE", {"NONE"}, set())
    C0 = claims([])
    C1 = claims([v2.edge("RECOLOR_PEER", "A:1", "B:1", "STRONG", "V8", "R8", "")])
    check("опасность: не творческий - нет", hv.danger("A:1", False, C0, [("B:1", rel_der)], []) == ([], []))
    w, _o = hv.danger("A:1", True, C0, [("B:1", rel_der)], [])
    check("опасность: перекраска без довода - опасно", len(w) == 1)
    w, _o = hv.danger("A:1", True, C1, [("B:1", rel_der)], [])
    check("опасность: перекраска с доводом - нет", w == [])
    fin = [{"relative": "B:1", "dir": "IN"}]
    w, _o = hv.danger("A:1", True, C1, [("B:1", rel_der)], fin)
    check("опасность: входящее ребро MCD - опасно и с доводом", len(w) == 1 and "asset_derived" in w[0])
    fout = [{"relative": "B:1", "dir": "OUT"}]
    w, _o = hv.danger("A:1", True, C0, [("B:1", rel_der)], fout)
    check("опасность: исходящее ребро MCD - нет", w == [])
    w, _o = hv.danger("A:1", True, C0, [("B:1", rel_comp)], [])
    check("опасность: составной без довода - опасно", len(w) == 1)
    Cc = claims([v2.edge("COMPOSITE_PART", "A:1", "B:1", "CANDIDATE", "V8", "P", "")])
    w, _o = hv.danger("A:1", True, Cc, [("B:1", rel_comp)], [])
    check("опасность: составной с доводом-кандидатом - нет", w == [])
    w, o = hv.danger("A:1", True, C0, [("B:1", rel_open)], [])
    check("опасность: открытый подтип - вне ворот, в отдельный счёт", w == [] and len(o) == 1)
    w, o = hv.danger("A:1", True, C0, [("B:1", none)], [])
    check("опасность: NONE - нет", w == [] and o == [])


def test_gates():
    check("ворота: шесть ворот V4 с теми же порогами",
          {k: hv.GATES[k] for k in hv.GATE_FROM_V4} == {k: v4.GATES[v] for k, v in hv.GATE_FROM_V4.items()}
          and set(hv.GATE_FROM_V4.values()) == set(v4.GATES))
    check("ворота: ровно семь (шесть + handoff), без CI, подтипа зеркала и модуля",
          sorted(hv.GATES) == sorted(list(hv.GATE_FROM_V4) + ["handoff_unassigned"]))
    ok = {"dangerous_creative_standalone": (0, 80), "relation_existence_precision": (1.0, 50),
          "derived_recolor_discovery": (0.8, 20), "state_discovery": (0.75, 8), "true_composite_recall": (0.7, 10),
          "automatic_action_precision": (0.96, 40), "handoff_unassigned": (0, 80)}
    check("ворота: все прошли - PASS", hv.gate_rows(ok)[1] == "PASS")
    check("ворота: пустой знаменатель - INCONCLUSIVE",
          hv.gate_rows(dict(ok, state_discovery=(None, 0)))[1] == "INCONCLUSIVE")
    check("ворота: опасный 1 - FAIL", hv.gate_rows(dict(ok, dangerous_creative_standalone=(1, 80)))[1] == "FAIL")
    check("ворота: провал и NO_DATA - FAIL",
          hv.gate_rows(dict(ok, state_discovery=(None, 0), true_composite_recall=(0.69, 13)))[1] == "FAIL")
    check("ворота: handoff 1 - FAIL", hv.gate_rows(dict(ok, handoff_unassigned=(1, 80)))[1] == "FAIL")


def test_pairs():
    claimed = {"C%d:0" % i for i in range(12)}
    exact = {"E%d:0" % i for i in range(5)}
    byte = exact | {"F0:0", "F1:0"}
    prs, must = hv.item_pairs("A:0", claimed, exact, {"M:0", "C0:0"}, byte,
                              [("neighbour", ["A:1", "A:2", "A:0"]), ("coplace", ["A:1", "P:0", "Q:0"]),
                               ("similar", ["S:0", "S:1"]), ("similar_mirror", [])])
    bs = [b for b, _w in prs]
    why = dict(prs)
    check("пары: все утверждения", claimed <= set(bs))
    check("пары: побайтовых не больше EXACT_CAP", len(set(bs) & byte) == hv.EXACT_CAP)
    check("пары: побайтовые - сначала утверждённые", set(bs) & byte <= exact)
    check("пары: ребро MCD есть, повтор утверждения - одна пара с двумя причинами",
          "M:0" in bs and bs.count("C0:0") == 1 and why["C0:0"] == ["claim", "mcd"])
    check("пары: обязательных 12 + 3 + 1", must == 16)
    check("пары: независимых не меньше CAND_MIN_INDEP при большом must", len(bs) - must == hv.CAND_MIN_INDEP)
    check("пары: сам кадр не пара", "A:0" not in bs)
    check("пары: повтор в двух источниках - две причины", why.get("A:1") == ["neighbour", "coplace"])
    prs2, must2 = hv.item_pairs("A:0", set(), set(), set(), set(),
                                [("neighbour", ["A:%d" % i for i in range(1, 9)]), ("coplace", ["P:0"]),
                                 ("similar", ["S:%d" % i for i in range(9)]), ("similar_mirror", ["R:0"])])
    check("пары: без обязательных - до CAND_TOTAL по кругу", must2 == 0 and len(prs2) == hv.CAND_TOTAL
          and {"P:0", "R:0"} <= {b for b, _w in prs2})


def test_dev_frames():
    tmp = tempfile.mkdtemp()
    old = dict(hv.DEV)
    try:
        def dump(name, data):
            path = os.path.join(tmp, name)
            with open(path, "w", encoding="utf-8-sig") as f:
                json.dump(data, f)
            return path
        hv.DEV.update({"mirror_blind": dump("m.json", {"items": [{"a": "m1:0", "b": "M2:0"}]}),
                       "taxonomy_key": dump("t.json", {"items": [{"a": "T1:0", "b": "T2:0"}]}),
                       "v3_controls": dump("c3.json", {"pairs": [{"asset_id": "K1:0", "relative": "K2:0"}]}),
                       "v4_controls": dump("c4.json", {"pairs": [{"asset_id": "L1:0", "relative": "L2:0"}]}),
                       "v4_relations": dump("r4.json", {"keys": ["H:0"], "edges": [{"source": "H:0",
                                                                                 "target": "G:5"}]})})
        ks = hv.dev_frames({"pairs": [{"a": "X:1", "b": "Y:2"}]})
        check("разработка: обе стороны пар истины v2", {"X:1", "Y:2"} <= ks)
        check("разработка: слепое зеркало, первый пакет, контроль V3 и V4",
              {"M1:0", "M2:0", "T1:0", "T2:0", "K1:0", "K2:0", "L1:0", "L2:0"} <= ks)
        check("разработка: 60 и их родня из утверждений V4", {"H:0", "G:5"} <= ks)
    finally:
        hv.DEV.clear()
        hv.DEV.update(old)
        shutil.rmtree(tmp, ignore_errors=True)


def test_freeze_body():
    check("снимок: MR - существование STRONG, подтип кандидат, TYPE_OPEN",
          hv.POLICY["mirrored_recolor"]["existence"] == "STRONG"
          and hv.POLICY["mirrored_recolor"]["type_level"] == "TYPE_OPEN")
    check("снимок: пороги V4 целиком", hv.POLICY["thresholds"] == v4.THRESHOLDS)
    check("снимок: слои 18/12/14/12/8/16 = 80, подслои сходятся",
          [q for _n, q, _s in hv.LAYERS] == [18, 12, 14, 12, 8, 16] and
          all(sum(m for _s, m in sub) == q for _n, q, sub in hv.LAYERS) and
          sum(q for _n, q, _s in hv.LAYERS) == hv.N_TOTAL == 80)
    check("снимок: зерно своё, не V8", hv.h7.SEED == hv.SEED != hv.h8.SEED)
    check("снимок: код V4, таксономии, истины v2 и этого модуля в хэшах",
          all(c in hv.CODE for c in ("tools/hdart/relation_discovery_v4.py", "tools/hdart/relation_taxonomy.py",
                                     "tools/hdart/relation_truth_v2.py", "tools/hdart/relation_holdout_v4.py",
                                     "tools/test_relation_holdout_v4.py")))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_select()
    test_danger()
    test_gates()
    test_pairs()
    test_dev_frames()
    test_freeze_body()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
