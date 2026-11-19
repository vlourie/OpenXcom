#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/routing_holdout_diag.py на синтетике: срезы точности родства (all / strict_blind /
strict_unseen, STRONG / CANDIDATE), исходы маршрута, ворота по strict_blind, отказ поправки после ответов.

    py -3.13 tools/test_routing_holdout_diag.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import routing_holdout as rh  # noqa: E402
import routing_holdout_diag as rd  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def claim(a, b, level, status):
    return {"asset_id": a, "relative": b, "level": level, "status": status}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cl = [claim("XBASE1:99", "XB1BR:99", "CANDIDATE", "wrong"), claim("A:1", "B:1", "STRONG", "ok"),
          claim("A:1", "NEG:1", "CANDIDATE", "ok"), claim("C:1", "D:1", "CANDIDATE", "open"),
          claim("E:1", "F:1", "CANDIDATE", "ok")]
    s = rd.subsets(cl, [["XBASE1:99", "XB1BR:99"]], {"NEG", "XB1BR"})
    check("all: 3 из 4 закрытых", (s["all"]["ok"], s["all"]["closed"]) == (3, 4))
    check("strict_blind без пары XBASE1~XB1BR: 3 из 3", (s["strict_blind"]["ok"], s["strict_blind"]["closed"]) == (3, 3))
    check("пара исключается в обе стороны", rd.subsets([claim("XB1BR:99", "XBASE1:99", "STRONG", "ok")],
                                                        [["XBASE1:99", "XB1BR:99"]], set())["strict_blind"]["claims"] == 0)
    check("strict_unseen убирает родственника из исключённого набора", s["strict_unseen"]["closed"] == 2)
    check("STRONG / CANDIDATE считаются раздельно",
          (s["all_STRONG"]["closed"], s["all_CANDIDATE"]["closed"], s["strict_blind_CANDIDATE"]["closed"]) == (1, 3, 2))
    check("убранные названы", len(s["removed_strict_blind"]) == 1 and len(s["removed_strict_unseen"]) == 1)

    def r(u, ref):
        return {"rule_unit": u, "ref_route": ref}
    cases = [(r("STANDALONE_RENDER", "COMPOSITE_PART"), "DANGEROUS_STANDALONE"),
             (r("STANDALONE_RENDER", "STANDALONE_RENDER"), "AUTO_CORRECT"),
             (r("DERIVED", "STANDALONE_RENDER"), "AUTO_WRONG"),
             (r("EXCLUDE", "open"), "AUTO_REF_OPEN"),
             (r("REVIEW", "STANDALONE_RENDER"), "REVIEW_UNNECESSARY"),
             (r("REVIEW", "DERIVED"), "REVIEW_CONSERVATIVE"),
             (r("REVIEW", "open"), "REVIEW_CONSERVATIVE")]
    check("исходы маршрута", all(rd.outcome(x) == want for x, want in cases))
    b = rd.breakdown([x for x, _w in cases])
    check("разбор покрывает все строки", sum(b.values()) == len(cases) and set(b) == set(rd.OUTCOMES))

    g = dict(rh.GATES)
    frozen = {"a": True, "b": True, "c": True, "d": True, "verified_relation_precision": False}
    ch = rd.amended_checks(frozen, {"relation_precision": 1.0, "closed": 6}, g)
    check("ворота родства заменены на strict_blind", len(ch) == 5 and list(ch.values())[-1] is True and
          "verified_relation_precision" not in ch)
    check("strict_blind с 4 закрытыми - не решено",
          list(rd.amended_checks(frozen, {"relation_precision": 1.0, "closed": 4}, g).values())[-1] is None)
    check("strict_blind 0.9 - провал",
          rh.verdict(rd.amended_checks(frozen, {"relation_precision": 0.9, "closed": 10}, g)) is False)

    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "answers_vitali.tsv"), "w").close()
        try:
            rd.amend(d)
            check("поправка после ответов - отказ", False)
        except SystemExit:
            check("поправка после ответов - отказ", True)
        os.remove(os.path.join(d, "answers_vitali.tsv"))
        open(os.path.join(d, "GATES_AMENDMENT.json"), "w").close()
        try:
            rd.amend(d)
            check("повторная поправка - отказ", False)
        except SystemExit:
            check("повторная поправка - отказ", True)

    print("итог: %s" % ("все проверки прошли" if not FAILS else "провалено %d" % len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
