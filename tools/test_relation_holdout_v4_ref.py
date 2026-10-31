#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка relation_holdout_v4_ref на синтетике, без установки игры: правила эталона и итога специалиста 02.10.

  - машинные факты: побайтовая копия закрывает EXACT_COPY и существование при судьях NONE против RELATED; ребро MCD
    закрывает только существование; контроль - без фактов EXACT_COPY остаётся открытым
  - статусы осей: CLOSED / PARTIAL / OPEN подтипа, OPEN существования
  - итог: доля с n < N_MIN - INSUFFICIENT_SAMPLE и INCONCLUSIVE, не PASS и не FAIL; счётчик - FAIL при любом n;
    доля с n >= N_MIN - как в замороженном вердикте
  - компоненты: helped / unnecessary / hurt / open по доводам утверждения
  - замок: решения меняются от любой правки истины
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import relation_holdout_v4 as hv                                # noqa: E402
import relation_holdout_v4_ref as rf                            # noqa: E402
import relation_truth_v2 as tv                                  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def test_facts():
    ex, cl, op = tv.combine_pair({"EXACT_COPY"}, {"NONE"}, True)
    check("контроль: без фактов EXACT_COPY при споре судей не закрыт", "EXACT_COPY" not in cl)
    e2, c2, o2 = rf.apply_facts(ex, cl, op, ["BYTE_EXACT_COPY"])
    check("побайтовая копия закрывает EXACT_COPY и существование", e2 == "RELATED" and "EXACT_COPY" in c2
          and "EXACT_COPY" not in o2)
    ex, cl, op = tv.combine_pair({"NONE"}, {"NONE"}, True)
    e3, c3, o3 = rf.apply_facts(ex, cl, op, ["BYTE_EXACT_COPY"])
    check("оба судьи NONE не отменяют побайтовую копию", e3 == "RELATED" and c3 == {"EXACT_COPY"} and not o3)
    ex, cl, op = tv.combine_pair({"STATE_VARIANT"}, {"NONE"}, True)
    e4, c4, o4 = rf.apply_facts(ex, cl, op, ["MCD_EDGE:die"])
    check("ребро MCD: существование закрыто, подтип судей открыт", e4 == "RELATED" and not c4
          and o4 == {"STATE_VARIANT"} and rf.statuses(e4, c4, o4) == ("CLOSED", "OPEN"))
    e5, c5, o5 = rf.apply_facts(*tv.combine_pair({"MIRRORED_VARIANT_PEER"}, set(), True), ["BYTE_MIRROR"])
    check("побайтовое отражение закрывает MIRRORED_VARIANT_PEER", "MIRRORED_VARIANT_PEER" in c5)
    e6, c6, o6 = rf.apply_facts(*tv.combine_pair({"RECOLOR_PEER"}, {"NONE"}, False), [])
    check("RELATED против NONE без факта - OPEN", e6 == "OPEN" and rf.statuses(e6, c6, o6) == ("OPEN", "OPEN"))


def test_statuses():
    check("оба NONE - закрыто NONE", rf.statuses(*tv.combine_pair({"NONE"}, {"NONE"})) == ("CLOSED", "NONE"))
    check("совпавший подтип - CLOSED",
          rf.statuses(*tv.combine_pair({"COMPOSITE"}, {"COMPOSITE"})) == ("CLOSED", "CLOSED"))
    check("расходящийся подтип - существование закрыто, подтип OPEN",
          rf.statuses(*tv.combine_pair({"COMPOSITE"}, {"STATE_VARIANT"})) == ("CLOSED", "OPEN"))
    check("частично совпавший - PARTIAL",
          rf.statuses(*tv.combine_pair({"COMPOSITE", "STATE_VARIANT"}, {"COMPOSITE"})) == ("CLOSED", "PARTIAL"))
    check("судья без взятого ярлыка (UNSURE) - OPEN",
          rf.statuses(*tv.combine_pair(set(), {"COMPOSITE"})) == ("OPEN", "OPEN"))


def gates(vals):
    return hv.gate_rows(vals)[0]


BASE = {"dangerous_creative_standalone": (0, 80), "relation_existence_precision": (0.97, 40),
        "derived_recolor_discovery": (0.8, 20), "state_discovery": (0.8, 12), "true_composite_recall": (0.75, 16),
        "automatic_action_precision": (0.96, 30), "handoff_unassigned": (0, 80)}


def test_acceptance():
    g, v = rf.acceptance(gates(BASE))
    check("все ворота с выборкой - PASS", v == "PASS")
    s = dict(BASE, state_discovery=(0.5, 4))
    fr = hv.gate_rows(s)[1]
    g, v = rf.acceptance(gates(s))
    check("state 0.5 на 4 случаях: замороженный FAIL, итог INCONCLUSIVE",
          fr == "FAIL" and v == "INCONCLUSIVE" and
          [x["accepted_status"] for x in g if x["gate"] == "state_discovery"] == ["INSUFFICIENT_SAMPLE"])
    g, v = rf.acceptance(gates(dict(BASE, state_discovery=(1.0, 3))))
    check("state 1.0 на 3 случаях - не PASS, INCONCLUSIVE", v == "INCONCLUSIVE")
    g, v = rf.acceptance(gates(dict(BASE, state_discovery=(0.5, 12))))
    check("state 0.5 на 12 случаях - FAIL", v == "FAIL")
    g, v = rf.acceptance(gates(dict(BASE, state_discovery=(0.5, 4), dangerous_creative_standalone=(1, 80))))
    check("опасный одиночный - FAIL и при малой выборке state", v == "FAIL")
    g, v = rf.acceptance(gates(dict(BASE, state_discovery=(None, 0))))
    check("NO_DATA - INCONCLUSIVE", v == "INCONCLUSIVE")
    check("эффективная выборка и вид выборки в строке",
          all("effective_n" in x and x["sample_kind"] for x in g) and
          [x["sample_kind"] for x in g if x["gate"] == "automatic_action_precision"] == ["closed_actions"])


def claim(group, *edges):
    return {"group": group, "support": [dict(detector=d, rule=r, type=t) for d, r, t in edges]}


def test_components():
    rel = ("RELATED", {"RECOLOR_PEER"}, set())
    pc = [("A", "B", rel, [claim("derived", ("R4", "R4b", "NEAR_SILHOUETTE_RECOLOR"))]),
          ("A", "C", rel, [claim("derived", ("R4", "R4bs", "NEAR_SILHOUETTE_RECOLOR"), ("RECOLOR", "x", "RECOLOR"))]),
          ("A", "D", ("NONE", {"NONE"}, set()), [claim("derived", ("R4", "R4c", "SET_CORRESPONDENCE"))]),
          ("A", "E", ("OPEN", set(), set()), [claim("derived", ("MR4", "MR1s", "MIRRORED_RECOLOR"))]),
          ("A", "F", ("RELATED", {"COMPOSITE"}, set()), [claim("composite", ("P5", "P5r", "CELL"))])]
    r = rf.components(pc, tv.claim_state)
    check("R4b один - helped, с другим доводом - unnecessary",
          r["near_recolor"] == {"triggered": 2, "helped": 1, "unnecessary": 1})
    check("R4c на NONE - hurt", r["set_correspondence"] == {"triggered": 1, "hurt": 1})
    check("MR на открытой истине - open", r["mirrored_recolor"] == {"triggered": 1, "open": 1})
    check("связка клеток на закрытом составном - helped", r["cell_bundle"] == {"triggered": 1, "helped": 1})
    check("local_edit не сработал", r["local_edit"] == {})


def test_lock():
    rows = [{"q": "Q1", "a": "A:1", "b": "A:2", "existence": "RELATED", "existence_status": "CLOSED",
             "subtype_status": "CLOSED", "closed": ["EXACT_COPY"], "open": [], "facts": ["BYTE_EXACT_COPY"],
             "judges_existence": "OPEN", "judges_closed": []}]
    h1 = rf.jsha(rf.decisions(rows))
    rows[0]["subtype_status"] = "OPEN"
    check("решения замка меняются от правки статуса", rf.jsha(rf.decisions(rows)) != h1)
    c = rf.counts(rows)
    check("счётчики: факт закрыл и поменял судей", c["machine_fact_closed"] == 1 and
          c["machine_fact_changed_judges"] == 1 and c["existence_closed"] == 1)
    check("модуль и замороженные зависимости в хэшах замка",
          rf.SELF in rf.code_hashes() and "tools/hdart/relation_holdout_v4.py" in rf.code_hashes())


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    test_facts()
    test_statuses()
    test_acceptance()
    test_components()
    test_lock()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
