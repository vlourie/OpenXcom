#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/routing_holdout_diag2.py на синтетике: ACTIONABLE_RELATION_TRUTH (DERIVED_FROM /
STATE_VARIANT_OF без направления - unresolved, RECOLOR_OF - при любом), срезы gate / all / STRONG, дополнение
только по своим парам, проверка формата дополнения, отказ поправки после ответов.

    py -3.13 tools/test_routing_holdout_diag2.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import routing_holdout_diag2 as r2  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def c(a, b, level, ref, direction, status):
    return {"asset_id": a, "relative": b, "level": level, "ref": ref, "direction": direction, "status": status}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    check("DERIVED_FROM без направления - unresolved",
          r2.actionable(c("A:1", "B:1", "STRONG", "DERIVED_FROM", "open", "ok"))["status"] == "open")
    check("DERIVED_FROM direction none - тоже unresolved",
          r2.actionable(c("A:1", "B:1", "STRONG", "DERIVED_FROM", "none", "ok"))["status"] == "open")
    check("DERIVED_FROM с направлением - засчитан",
          r2.actionable(c("A:1", "B:1", "STRONG", "DERIVED_FROM", "relative_derived", "ok"))["status"] == "ok")
    check("STATE_VARIANT_OF без основы - unresolved",
          r2.actionable(c("A:1", "B:1", "STRONG", "STATE_VARIANT_OF", "open", "ok"))["status"] == "open")
    check("другой вид связи против DERIVED_FROM без направления - остаётся ошибкой",
          r2.actionable(c("A:1", "B:1", "CANDIDATE", "DERIVED_FROM", "open", "wrong"))["status"] == "wrong")
    check("RECOLOR_OF без направления - засчитан",
          r2.actionable(c("A:1", "B:1", "STRONG", "RECOLOR_OF", "open", "ok"))["status"] == "ok")
    check("NONE - остаётся неверным", r2.actionable(c("A:1", "B:1", "STRONG", "NONE", "none", "wrong"))["status"]
          == "wrong")

    cl = [c("XBASE1:99", "XB1BR:99", "CANDIDATE", "RECOLOR_OF", "open", "ok"),
          c("A:1", "B:1", "STRONG", "RECOLOR_OF", "open", "ok"),
          c("A:1", "K:1", "STRONG", "DERIVED_FROM", "open", "ok"),
          c("E:1", "F:1", "CANDIDATE", "NONE", "none", "wrong"),
          c("G:1", "H:1", "CANDIDATE", "DERIVED_FROM", "asset_derived", "ok")]
    s = r2.slices(cl, [["XBASE1:99", "XB1BR:99"]], set())
    g = s["relation_precision_gate"]
    check("gate: strict_blind по правилу - 2 из 3", (g["ok"], g["closed"]) == (2, 3))
    check("all по правилу - 3 из 4", (s["relation_precision_all"]["ok"], s["relation_precision_all"]["closed"]) == (3, 4))
    check("STRONG primary - 1 из 1", (s["strong_relation_precision_primary"]["ok"],
                                      s["strong_relation_precision_primary"]["closed"]) == (1, 1))
    check("без правила - 3 из 4 в strict_blind", (s["raw_strict_blind"]["ok"], s["raw_strict_blind"]["closed"]) == (3, 4))
    check("unresolved назван", s["unresolved_by_rule"] == [["A:1", "K:1", "STRONG", "DERIVED_FROM", "open"]])

    import routing_holdout_table as rt
    cl2 = cl + [c("M:1", "N:1", "CANDIDATE", "OPEN", "open", "open")]
    s2 = r2.slices(cl2, [["XBASE1:99", "XB1BR:99"]], set())
    t = rt.table({"relations": s2, "supplement": None}, [["XBASE1:99", "XB1BR:99"]])
    g = t["relation_precision_gate"]
    check("таблица ворот: correct 2, wrong 1, unresolved 1, ref_open 1, знаменатель 3",
          (g["correct"], g["wrong"], g["unresolved"], g["ref_open"], g["denominator"]) == (2, 1, 1, 1, 3))
    a_ = t["relation_precision_all"]
    check("таблица all: XBASE-пара в correct", (a_["correct"], a_["denominator"], a_["claims"]) == (3, 4, 6))
    st_ = t["strong_relation_precision_primary"]
    check("таблица STRONG primary: 1 correct, 1 unresolved", (st_["correct"], st_["unresolved"], st_["denominator"])
          == (1, 1, 1))
    check("без дополнения - пусто", t["strong_relation_precision_supplemental"] is None)

    rels = {"A:1": [{"kind": "RECOLOR_OF", "level": "STRONG", "relative": "P:1", "side": "base"},
                    {"kind": "RECOLOR_OF", "level": "STRONG", "relative": "Q:1", "side": "base"},
                    {"kind": "RECOLOR_OF", "level": "CANDIDATE", "relative": "Z:1", "side": "base"}]}
    supp = [{"asset_id": "A:1", "relative": "P:1", "ref_pair_relation": "RECOLOR_OF", "direction": "open"},
            {"asset_id": "A:1", "relative": "Q:1", "ref_pair_relation": "NONE", "direction": "none"}]
    sp = r2.supp_slices(rels, supp, ["A:1"], [["A:1", "P:1"], ["A:1", "Q:1"]])
    st = sp["strong_relation_precision_supplemental"]
    check("дополнение: STRONG 1 из 2, чужое утверждение не входит", (st["ok"], st["closed"], st["claims"]) == (1, 2, 2))
    check("формат дополнения: верные пары - без ошибок", r2.check_supp(supp, [["A:1", "P:1"], ["A:1", "Q:1"]]) == [])
    check("формат дополнения: лишняя пара - ошибка", r2.check_supp(supp, [["A:1", "P:1"]]) != [])
    bad = [dict(supp[0], ref_pair_relation="KIT")]
    check("формат дополнения: чужое значение - ошибка", r2.check_supp(bad, [["A:1", "P:1"]]) != [])

    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "answers_vitali.tsv"), "w").close()
        try:
            r2.amend2(d)
            check("вторая поправка после ответов - отказ", False)
        except SystemExit:
            check("вторая поправка после ответов - отказ", True)

    print("итог: %s" % ("все проверки прошли" if not FAILS else "провалено %d" % len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
