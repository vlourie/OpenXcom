#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверки relation_holdout_v5 без видеокарты: отбор без переноса недобора, ворота с малой выборкой, уровень довода
ASM, ленивый проход детекторов, заморозка."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import relation_discovery_v4 as v4     # noqa: E402
import relation_holdout_v5 as h        # noqa: E402

FAIL = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAIL.append(name)


def row(k):
    return {"asset_id": k, "rank": "1", "kind": "OBJECT", "action": "GENERATE", "places": "3"}


def entries(*keys):
    return [(k, row(k), "") for k in keys]


def test_select():
    layers = (("A", 3, (("a1", 2), ("a2", 1))), ("B", 2, (("b1", 2),)), ("C", 2, (("c1", 1), ("c2", 1))))
    pool = {"a1": entries("S1:1", "S2:1", "S3:1", "S4:1"), "a2": [],
            "b1": entries("S5:1"),                       # слой B исчерпан: 1 из 2
            "c1": entries("S6:1", "S6:2", "S7:1"), "c2": entries("S1:9")}   # S1 уже взят слоем A
    pick, short = h.select(pool, layers)
    by = {}
    for x in pick:
        by.setdefault(x["layer"], []).append(x)
    check("in-layer fill: A 3 из 3 добором a1", len(by["A"]) == 3 and "a2" in short)
    check("no transfer: B 1 из 2, недобор записан", len(by["B"]) == 1 and "B" in short)
    check("no transfer: C не взял лишнего за B", len(by["C"]) == 2)
    check("one set per holdout", len({h.pset(x["asset_id"]) for x in pick}) == len(pick))
    check("set S1 not twice (c2)", sum(h.pset(x["asset_id"]) == "S1" for x in pick) == 1)
    check("total 6 of 7", len(pick) == 6)


def test_acceptance():
    vals = {g: (0.99, 50) if k == "rate" else (0, 80) for g, k, _n in h.GATES}
    rows, v = h.acceptance(vals)
    check("all pass", v == "PASS")
    vals["state_discovery"] = (1.0, 9)
    rows, v = h.acceptance(vals)
    st = {r["gate"]: r["status"] for r in rows}
    check("n<10 insufficient", st["state_discovery"] == "INSUFFICIENT_SAMPLE" and v == "INCONCLUSIVE")
    vals["state_discovery"] = (0.1, 9)
    rows, v = h.acceptance(vals)
    check("low value with n<10 still insufficient", {r["gate"]: r["status"] for r in rows}["state_discovery"]
          == "INSUFFICIENT_SAMPLE")
    vals["POST_REVIEW_DANGEROUS"] = (1, 80)
    rows, v = h.acceptance(vals)
    check("post dangerous fails", v == "FAIL")
    vals = {g: (0.99, 50) if k == "rate" else (0, 80) for g, k, _n in h.GATES}
    vals["ASSEMBLY_STRONG_composite_precision"] = (None, 0)
    check("no data inconclusive", h.acceptance(vals)[1] == "INCONCLUSIVE")
    check("ten gates", len(h.GATES) == 10)


def test_levels():
    strong = [{"level": "STRONG", "detector": "ASM", "rule": "AOs", "target": "X:1"}]
    cand = [{"level": "CANDIDATE", "detector": "ASM", "rule": "AOc", "target": "X:1"}]
    check("asm strong by edge level", h.classify([], strong) == ["asm_strong"])
    check("asm candidate", h.classify([], cand) == ["asm_candidate"])
    check("ar2 and asm", h.classify([{"x": 1}], cand) == ["ar2", "asm_candidate"])
    check("control: v4.STRONG is not edge level", v4.STRONG != h.EDGE_STRONG)
    check("ar2 bands", (h.ar2_band(0.70), h.ar2_band(0.79), h.ar2_band(0.95), h.ar2_band(0.65))
          == ("0.70-0.75", "0.75-0.80", ">=0.90", "<0.70"))


def test_scan():
    rows = [{"key": "S%d:1" % i, "asset_id": "S%d:1" % i} for i in range(40)]
    calls = []

    def d2(k):
        calls.append(k)
        return [{"level": "STRONG", "detector": "AR2", "rule": "AR2", "target": "T:1"}]

    pools, st = h.scan(rows, d2, lambda k: [], found=3, cap=40)
    check("ar2 stops when full", len(calls) == 3 and len(pools["ar2"]) == 3)
    check("scan continues for other layers", st["scanned"] == 40)
    def da(k):
        lv = "STRONG" if int(k[1:].split(":")[0]) % 2 else "CANDIDATE"
        return [{"level": lv, "detector": "ASM", "rule": "AOs", "target": "T"}]
    pools, st = h.scan(rows, d2, da, found=3, cap=40)
    check("scan stops when all full", st["scanned"] < 40 and st["found_asm_strong"] == 3
          and st["found_asm_candidate"] == 3)


def test_rate_closed():
    rows = [{"x": "yes"}, {"x": "no"}, {"x": "OPEN"}, {"x": "yes"}]
    v, n, ok, opn = h.rate_closed(rows, "x", "yes")
    check("closed rate", (n, ok, opn) == (3, 2, 1) and abs(v - 2 / 3) < 1e-3)


def test_freeze():
    tmp = tempfile.mkdtemp(prefix="h5test_")
    try:
        src = os.path.join(tmp, "in.tsv")
        with open(src, "w", encoding="utf-8-sig") as f:
            f.write("a\tb\n1\t2\n")
        out = os.path.join(tmp, "out")
        os.makedirs(out)
        d = h.freeze(out, inputs={"x": src}, code=[h.SELF], truth={"pairs": []})
        check("freeze ar2 boundary", d["policy"]["aligned_recolor_v2"]["boundary"] == 0.70
              and "NOT VALIDATED" in d["policy"]["aligned_recolor_v2"]["not_validated"])
        check("freeze gates and n_min", len(d["gates"]) == 10 and d["n_min"] == 10)
        pm = d["pool_measurement"]
        check("freeze pool numbers", (pm["eligible_rows_with_key_exclusion"], pm["eligible_sets_with_key_exclusion"],
                                      pm["would_select_with_whole_set_exclusion"]) == (3466, 433, "2/80"))
        check("freeze known frozen defect", "known_frozen_defects" in h.BODY
              and d["known_frozen_defects"][0]["id"] == "KNOWN_FROZEN_DIAGNOSTIC_DEFECT")
        check("freeze readiness pass", d["readiness"]["verdict"]["freeze_readiness"] == "PASS")
        check("load ok", h.load_freeze(out)["sha256"] == d["sha256"])
        try:
            h.freeze(out, inputs={"x": src}, code=[h.SELF], truth={"pairs": []})
            check("refreeze refused", False)
        except SystemExit:
            check("refreeze refused", True)
        with open(d["inputs"]["x"], "a", encoding="utf-8") as f:
            f.write("3\t4\n")
        try:
            h.load_freeze(out)
            check("tampered input caught", False)
        except SystemExit:
            check("tampered input caught", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_select()
    test_acceptance()
    test_levels()
    test_scan()
    test_rate_closed()
    test_freeze()
    print("\n%s" % ("всё прошло" if not FAIL else "провалено: %d" % len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
