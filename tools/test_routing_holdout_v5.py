#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/routing_holdout_v5.py на синтетике: снимок второй раз не делается и правку замечает; отбор -
один набор на весь holdout, квоты подслоёв, недобор записан; утверждения - без FIXED_NEIGHBOUR, ребро FR2 той же пары,
что детектор, не повторяется, MCD CANDIDATE не утверждение; кадр анимации засчитан только как анимация; опасный
одиночный - и при эталоне ANIMATION_FAMILY; правило частоты MCD: helped / hurt по эталону пар.

    py -3.13 tools/test_routing_holdout_v5.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import routing_holdout_v5 as h5  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def raises(f, *a):
    try:
        f(*a)
    except SystemExit:
        return True
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "in.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump({"x": 1}, f)
        out = os.path.join(tmp, "out")
        h5.freeze(out, inputs={"x": src}, code=[])
        check("снимок цел сразу после заморозки", h5.load_freeze(out)["seed"] == h5.SEED)
        check("второй снимок не делается", raises(h5.freeze, out, {"x": src}, []))
        with open(os.path.join(out, "inputs", "in.json"), "w", encoding="utf-8") as f:
            json.dump({"x": 2}, f)
        check("правка снимка входов замечена", raises(h5.load_freeze, out))
    finally:
        shutil.rmtree(tmp)

    row = {"asset_id": "", "rank": "1", "kind": "один", "action": "GENERATE", "places": "1"}
    pool = {"fr2_new": [("A:1", row, ""), ("A:2", row, ""), ("B:1", row, ""), ("C:1", row, "")],
            "fr2_verified": [("A:3", row, ""), ("D:1", row, "")],
            "standalone": [("E:%d" % i, row, "") for i in range(30)] + [("F%d:1" % i, row, "") for i in range(4)]}
    items, short = h5.select(pool)
    sets = [x["asset_id"].split(":")[0] for x in items]
    check("один набор PCK на весь holdout", len(sets) == len(set(sets)))
    check("квота подслоя не превышена", sum(x["sub"] == "fr2_new" for x in items) == 3)
    check("набор, занятый раньше, следующему подслою не достаётся",
          [x["asset_id"] for x in items if x["sub"] == "fr2_verified"] == ["D:1"])
    check("недобор записан", "fr2_verified" in short and "standalone" in short and "mcd_die" in short)
    check("всего по слоям 50", sum(q for _n, q, _s in h5.LAYERS) == h5.N_TOTAL
          and all(q == sum(m for _s, m in sub) for _n, q, sub in h5.LAYERS))

    rels = {"S:1": [{"kind": "RECOLOR_OF", "level": "STRONG", "side": "derived", "relative": "S:0"},
                    {"kind": "FIXED_NEIGHBOUR", "level": "CANDIDATE", "side": "part?", "relative": "S:9"}]}
    fr2 = {"S:1": [{"status": "VERIFIED_DIRECT", "side": "derived", "relative": "S:0", "relation": "RECOLOR_OF",
                    "confidence": "STRONG"}],
           "S:2": [{"status": "LEGACY_RELATION", "side": "derived", "relative": "S:7", "relation": "RECOLOR_OF",
                    "confidence": ""}]}
    mcd = {"S:3": [{"side": "derived", "level": "STRONG", "via": "anim", "relative": "S:4",
                    "kind": "ANIMATION_FRAME_OF", "why": ""}],
           "S:5": [{"side": "derived", "level": "CANDIDATE", "via": "die", "relative": "S:6",
                    "kind": "STATE_VARIANT_OF", "why": "", "dominance": True}]}
    raw = h5.rule_claims(rels, mcd, fr2, ["S:1", "S:2", "S:3", "S:5"])
    pairs = {(r[0], r[1]) for r in raw}
    check("FIXED_NEIGHBOUR не утверждение", ("S:1", "S:9") not in pairs)
    check("ребро FR2 той же пары, что детектор, не повторяется", sum(r[:2] == ("S:1", "S:0") for r in raw) == 1)
    check("LEGACY_RELATION не утверждение", ("S:2", "S:7") not in pairs)
    check("MCD CANDIDATE не утверждение", ("S:5", "S:6") not in pairs)
    ref = [{"asset_id": "S:3", "relative": "S:4", "ref_pair_relation": "STATE_VARIANT_OF", "direction": "asset_derived"},
           {"asset_id": "S:1", "relative": "S:0", "ref_pair_relation": "RECOLOR_OF", "direction": "asset_derived"}]
    sc = {(c["asset_id"], c["relative"]): c for c in h5.score_claims(raw, ref)}
    check("кадр анимации при эталоне STATE_VARIANT_OF - неверно", sc[("S:3", "S:4")]["status"] == "wrong")
    ref[0]["ref_pair_relation"] = "ANIMATION_FRAME_OF"
    sc = {(c["asset_id"], c["relative"]): c for c in h5.score_claims(raw, ref)}
    check("кадр анимации при эталоне ANIMATION_FRAME_OF - верно, точный вид",
          sc[("S:3", "S:4")]["status"] == "ok" and sc[("S:3", "S:4")]["exact"])
    check("перекраска верна, направление верно", sc[("S:1", "S:0")]["direction_ok"] is True)

    rows = [{"asset_id": "A", "rule_unit": "STANDALONE_RENDER", "ref_route": "ANIMATION_FAMILY"},
            {"asset_id": "B", "rule_unit": "REVIEW", "ref_route": "STANDALONE_RENDER"}]
    m = h5.metrics(rows)
    check("одиночный при эталоне ANIMATION_FAMILY - опасный", m["dangerous_false_standalone"] == 1)

    refp = [{"asset_id": "S:5", "relative": "S:6", "ref_pair_relation": "NONE"}]
    rows = [{"asset_id": "S:5", "rule_unit": "REVIEW", "ref_route": "STANDALONE_RENDER"}]
    nodom = [{"asset_id": "S:5", "rule_unit": "STATE_VARIANT", "ref_route": "STANDALONE_RENDER"}]
    dm = h5.dominance(rows, nodom, mcd, ["S:5"], refp)
    check("правило частоты сняло ложное состояние - helped", dm["triggered"] == 1 and dm["helped"] == 1)
    refp[0]["ref_pair_relation"] = "STATE_VARIANT_OF"
    dm = h5.dominance(rows, nodom, mcd, ["S:5"], refp)
    check("правило частоты сняло верное состояние - hurt", dm["hurt"] == 1 and dm["route_changed"])
    print("\nпровалов: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
