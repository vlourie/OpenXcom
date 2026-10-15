#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка routing_holdout_v7 без данных игры: отбор по слоям (добор недостачи внутри слоя, один набор PCK на
holdout, ключ один раз), состав 60, заморозка ловит правку тела и кода. Контроль у каждого пункта.

    py -3.13 tools/test_routing_holdout_v7.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import identity_routing as ir          # noqa: E402
import routing_holdout_v7 as h7        # noqa: E402
import routing_rules_v7 as v7          # noqa: E402

FAILS = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


def row(k):
    return {"asset_id": k, "rank": "1", "kind": "один", "action": "GENERATE", "places": "3"}


def pool_full():
    pool = {}
    for _l, _q, sub in h7.LAYERS:
        for name, n in sub:
            pool[name] = [("%s_%d:%d" % (name.upper(), i, i), row("%s_%d:%d" % (name.upper(), i, i)), name)
                          for i in range(n + 3)]
    return pool


def main():
    check("состав слоёв 12/10/10/10/8/10 = 60", [q for _n, q, _s in h7.LAYERS] == [12, 10, 10, 10, 8, 10]
          and sum(q for _n, q, _s in h7.LAYERS) == h7.N_TOTAL == 60)
    check("в каждом слое сумма подслоёв = квоте", all(sum(m for _s, m in sub) == q for _n, q, sub in h7.LAYERS))
    check("поверхности: лестница, дверь, обшивка, крыша, панель, стена, кузов",
          [s for s, _m in dict((n, sub) for n, _q, sub in h7.LAYERS)["structural"]] ==
          ["stairs", "door", "hull", "roof", "panel", "wall", "vehicle_body"])
    items, short = h7.select(pool_full())
    check("полный пул - 60 без недобора", len(items) == 60 and not short)
    pool = pool_full()
    pool["mcd_alt"] = []
    items, short = h7.select(pool)
    mcd = [x for x in items if x["layer"] == "mcd_state"]
    check("пустой подслой: слой добран до 10 другими подслоями", len(mcd) == 10 and "mcd_alt" in short
          and "mcd_state" not in short and sum("добор слоя" in x["why_selected"] for x in mcd) == 2)
    pool = pool_full()
    for name in ("mcd_die", "mcd_alt", "mcd_anim", "mcd_dominance", "mcd_candidate"):
        pool[name] = pool[name][:1]
    items, short = h7.select(pool)
    check("контроль: слою не из чего добирать - недобор слоя назван",
          short.get("mcd_state") == "слой 5 из 10" and len(items) == 55)
    pool = pool_full()
    pool["fr2_verified"] = [("SAME:1", row("SAME:1"), "x"), ("SAME:2", row("SAME:2"), "x")]
    pool["fr2_new"] = [("SAME:3", row("SAME:3"), "x")] + pool["fr2_new"]
    items, _short = h7.select(pool)
    sets = [h7.pset(x["asset_id"]) for x in items]
    check("один набор PCK на holdout", len(sets) == len(set(sets)) and sets.count("SAME") == 1)
    pool = pool_full()
    pool["standalone"] = pool["standalone"] + [pool["fr2_new"][0]]
    items, _ = h7.select(pool)
    check("ключ один раз", len({x["asset_id"] for x in items}) == len(items))
    a = [x["asset_id"] for x in h7.select(pool_full())[0]]
    b = [x["asset_id"] for x in h7.select(pool_full())[0]]
    check("отбор детерминирован (зерно)", a == b)

    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.tsv")
        code = os.path.join(td, "code.py")
        for f in (src, code):
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("x\n")
        out = os.path.join(td, "hold")
        d = h7.freeze(out, inputs={"generation": src}, code=[code])
        check("заморозка: ворота V7 и handoff в теле", d["gates"] == v7.GATES and d["handoff"]["map"] == v7.HANDOFF
              and d["r7t"]["status"] == "PROVISIONAL" and d["r7t"]["requires_blind_validation"] is True)
        check("онтология v2 целиком (6 видов, SS и часть - v2)", set(d["ontology"]["semantic_kind"]) ==
              set(h7.SEMANTIC) and d["ontology"]["semantic_kind"]["STRUCTURAL_SURFACE"] ==
              v7.SEM_DEFS_V2["STRUCTURAL_SURFACE"])
        check("цельная заморозка читается", h7.load_freeze(out)["sha256"] == d["sha256"])
        try:
            h7.freeze(out, inputs={"generation": src}, code=[code])
            check("повторная заморозка запрещена", False)
        except SystemExit:
            check("повторная заморозка запрещена", True)
        with open(code, "a", encoding="utf-8") as fh:
            fh.write("y\n")
        check("правка кода видна", h7.code_changed(h7.load_freeze(out)) == [code])
        dd = ir.load_json(os.path.join(out, "FREEZE.json"))
        dd["gates"]["routing_coverage_min"] = 0.6
        ir.dump_json(os.path.join(out, "FREEZE.json"), dd)
        try:
            h7.load_freeze(out)
            check("контроль: ворота подправлены после заморозки - отказ", False)
        except SystemExit:
            check("контроль: ворота подправлены после заморозки - отказ", True)
    print("провалов: %d" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
