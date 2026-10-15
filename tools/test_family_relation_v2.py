#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/family_relation_v2.py на синтетике: прямая пара в одном рабочем семействе - VERIFIED_DIRECT,
вне - DIRECT_NEW; рабочая связь, не прошедшая строгий тест, - LEGACY_RELATION (не удаляется); пара не повторяется;
канон семейства - основа; без канона основа - кадр, что чаще на картах (при равенстве младший ключ); family_id нет.

    py -3.13 tools/test_family_relation_v2.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import family_relation_v2 as fr  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fam_of = {"A:1": "F1", "A:2": "F1", "B:1": "F2", "C:1": "F3"}
    canonical_of = {"F1": "A:1", "F2": "B:1", "F3": "C:1"}
    places = {"B:1": 5, "D:1": 9, "E:1": 3, "E:2": 3}
    pairs = [("A:2", "A:1", "STRONG", 1.0, 1.0, 1.0), ("B:1", "D:1", "CANDIDATE", 0.99, 0.99, 0.99),
             ("E:2", "E:1", "CANDIDATE", 1.0, 1.0, 1.0)]
    links = [("A:1", "A:2", "F1", 1.0, 1.0, 1.0, True, ""), ("C:1", "C:2", "F3", 0.9, 0.5, 0.5, False, "силуэт")]
    rows = fr.classify(pairs, links, fam_of, {}, places, canonical_of)
    got = {(r["asset_a"], r["asset_b"]): r for r in rows}
    check("пара в одном семействе - VERIFIED_DIRECT, канон основа",
          got.get(("A:1", "A:2"), {}).get("status") == "VERIFIED_DIRECT"
          and got[("A:1", "A:2")]["direction_source"] == "family_canonical")
    check("рабочая связь той же пары не повторяется", len([r for r in rows if {r["asset_a"], r["asset_b"]} ==
                                                            {"A:1", "A:2"}]) == 1)
    check("пара вне одного семейства - DIRECT_NEW, основа чаще на картах",
          got.get(("D:1", "B:1"), {}).get("status") == "DIRECT_NEW")
    check("при равенстве мест основа - младший ключ", ("E:1", "E:2") in got)
    leg = got.get(("C:1", "C:2"), {})
    check("не прошедшая строгий тест рабочая связь - LEGACY_RELATION, direct no",
          leg.get("status") == "LEGACY_RELATION" and leg.get("direct") == "no")
    check("прямые рёбра direct yes, human_verified no",
          all(r["direct"] == "yes" and r["human_verified"] == "no" for r in rows if r["status"] in fr.DIRECT))
    check("family_id в строках нет", all("family_id" not in r for r in rows) and "family_id" not in fr.COLS)
    print("\nпровалов: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
