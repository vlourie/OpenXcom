#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/routing_holdout.py на синтетике: метрики маршрута, точность родства по эталону пар,
ворота «не решено» при малом числе закрытых пар, порядок заморозки (freeze до select, без повтора).

    py -3.13 tools/test_routing_holdout.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import routing_holdout as rh  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def row(u, ref):
    return {"rule_unit": u, "ref_route": ref}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = [row("STANDALONE_RENDER", "STANDALONE_RENDER"), row("STANDALONE_RENDER", "COMPOSITE_PART"),
            row("REVIEW", "STANDALONE_RENDER"), row("DERIVED", "DERIVED"), row("EXCLUDE", "open"),
            row("DERIVED", "STANDALONE_RENDER")]
    m = rh.routing_metrics(rows)
    check("опасный одиночный считается", m["dangerous_false_standalone"] == 1)
    check("точность: open и REVIEW вне знаменателя", (m["correct"], m["decided"]) == (2, 4))
    check("охват: решено / закрыто", (m["decided"], m["ref_closed"]) == (4, 5))
    check("сверхосторожно: доля среди одиночных по эталону, REVIEW тоже", (m["overconservative"],
                                                                           m["ref_standalone"]) == (2, 3))

    rels = {"A:1": [{"kind": "RECOLOR_OF", "level": "STRONG", "relative": "B:1", "side": "derived"},
                    {"kind": "RECOLOR_WITH_LOCAL_EDIT", "level": "CANDIDATE", "relative": "C:1", "side": "derived"},
                    {"kind": "FIXED_NEIGHBOUR", "level": "CANDIDATE", "relative": "D:2", "side": "part?"},
                    {"kind": "RECOLOR_OF", "level": "CANDIDATE", "relative": "E:1", "side": "base"}],
            "F:1": [{"kind": "RECOLOR_OF", "level": "STRONG", "relative": "G:1", "side": "base"}]}
    refp = [{"asset_id": "A:1", "relative": "B:1", "ref_pair_relation": "RECOLOR_OF", "direction": "asset_derived"},
            {"asset_id": "A:1", "relative": "C:1", "ref_pair_relation": "STATE_VARIANT_OF",
             "direction": "relative_derived"},
            {"asset_id": "A:1", "relative": "D:2", "ref_pair_relation": "NONE", "direction": "none"},
            {"asset_id": "A:1", "relative": "E:1", "ref_pair_relation": "OPEN", "direction": "open"},
            {"asset_id": "F:1", "relative": "X:9", "ref_pair_relation": "DERIVED_FROM", "direction": "asset_derived"}]
    r = rh.relation_metrics(rels, refp, ["A:1", "F:1"])
    check("утверждений 5, одно без строки эталона", (r["claims"], r["unjudged"]) == (5, 1))
    check("OPEN и пропущенное вне точности", (r["closed"], r["open"]) == (3, 2))
    check("группа производного: LOCAL_EDIT против STATE_VARIANT_OF - верно; сосед против NONE - неверно",
          r["ok"] == 2)
    check("точный вид отдельно: LOCAL_EDIT != STATE_VARIANT_OF", r["exact_kind"] == 1)
    check("направление: A:1 derived и эталон asset_derived - да; C:1 derived против relative_derived - нет",
          (r["direction_ok"], r["direction_wrong"]) == (1, 1))
    check("полнота: найдено 2 из 3 пар с родством", (r["recall_found"], r["recall_pos"]) == (2, 3))

    g = dict(rh.GATES)
    tot = {"dangerous_false_standalone": 0, "routing_accuracy": 0.95, "routing_coverage": 0.8,
           "overconservative_rate": 0.1}
    ch = rh.gate_checks(tot, r, g)
    check("закрытых пар меньше 5 - точность родства не решена", list(ch.values())[-1] is None)
    check("вердикт при нерешённых воротах - не решено", rh.verdict(ch) is None)
    r2 = dict(r, closed=6, relation_precision=1.0)
    check("закрытых 6 и точность 1.0 - пройдено", rh.verdict(rh.gate_checks(tot, r2, g)) is True)
    check("опасный один - провал", rh.verdict(rh.gate_checks(dict(tot, dangerous_false_standalone=1), r2, g))
          is False)

    pool = {s: [] for _n, _q, sub in rh.LAYERS for s, _m in sub}
    pool["standalone"] = [("S%d:%d" % (i % 3, i), {"asset_id": "S%d:%d" % (i % 3, i), "rank": i, "kind": "один",
                                                 "action": "GENERATE", "places": 1}, "") for i in range(9)]
    items, short = rh.select(pool)
    check("один предмет на набор PCK", len(items) == 3 and len({rh.pset(x["asset_id"]) for x in items}) == 3)
    check("недобор назван", "standalone" in short)

    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in.tsv")
        with open(src, "w", encoding="utf-8") as f:
            f.write("x\n")
        out = os.path.join(d, "out")
        rh.freeze(out, inputs={"generation": src}, code=[])
        try:
            rh.freeze(out, inputs={"generation": src}, code=[])
            check("повторная заморозка - отказ", False)
        except SystemExit:
            check("повторная заморозка - отказ", True)
        check("снимок читается", rh.load_freeze(out)["seed"] == rh.SEED)
        with open(os.path.join(out, "inputs", "in.tsv"), "w", encoding="utf-8") as f:
            f.write("y\n")
        try:
            rh.load_freeze(out)
            check("снимок входа изменён - отказ", False)
        except SystemExit:
            check("снимок входа изменён - отказ", True)
        out2 = os.path.join(d, "out2")
        os.makedirs(out2)
        open(os.path.join(out2, "holdout.json"), "w").close()
        try:
            rh.freeze(out2, inputs={"generation": src}, code=[])
            check("заморозка после отбора - отказ", False)
        except SystemExit:
            check("заморозка после отбора - отказ", True)

    print("итог: %s" % ("все проверки прошли" if not FAILS else "провалено %d" % len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
