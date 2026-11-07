#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка relation_holdout_v7 на синтетике, без установки игры (RELATION_SAFETY_MODEL_V7 holdout, специалист 02.10).

  отбор: один кадр на набор, недобор слоя не переносится в другие слои, добор внутри слоя
  редкие: single_place - только GENERATE object с places 1, sparse_place - 2-3
  исключения: снимки данных (inputs, img, frames.tsv...) и раунды-сканы всей очереди не исключают
  проход детекторов: детектор не считается, когда его подслой полон; классы доводов по подслоям
  ворота: handoff_unassigned > 0 - FAIL; доля с n < 10 - INSUFFICIENT_SAMPLE, вердикт INCONCLUSIVE; всё - PASS
  unique saves: кадр найден только с RAR, опасный только без RAR
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import relation_holdout_v7 as H                                  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def row(key, places=4, action="GENERATE", cls="object"):
    return {"key": key, "asset_id": key, "rank": "1", "kind": "x", "action": action, "places": str(places),
            "asset_class": cls, "status": "", "family": ""}


# ---------------------------------------------------------------- отбор
pool = {"a1": [(k, row(k), "") for k in ("S1:1", "S2:1", "S3:1")],
        "a2": [(k, row(k), "") for k in ("S1:2",)],                     # набор S1 уже может быть занят
        "b1": [(k, row(k), "") for k in ("S1:3", "S4:1")]}
layers = (("A", 4, (("a1", 2), ("a2", 1))), ("B", 3, (("b1", 3),)))
items, short = H.select(pool, layers)
sets = [H.pset(x["asset_id"]) for x in items]
check("один кадр на набор", len(sets) == len(set(sets)))
la = [x for x in items if x["layer"] == "A"]
lb = [x for x in items if x["layer"] == "B"]
check("слой A: добор внутри слоя до 3 из 4, недобор записан", len(la) == 3 and "A" in short)
check("слой B: недобор не взят из A (только S4:1)", [x["asset_id"] for x in lb] == ["S4:1"] and "B" in short)
check("зерно своё: порядок не как у V5", H.order("x") != H.h5.order("x"))
items2, _s = H.select(pool, layers)
check("отбор воспроизводим", items == items2)

# ---------------------------------------------------------------- редкие
sp = H.sparse_pools([row("P:1", 1), row("P:2", 2), row("P:3", 3), row("P:4", 4), row("P:5", 1, "DERIVE"),
                     row("P:6", 1, cls="structural"), row("P:7", 0)])
check("single_place: только GENERATE object places 1", [x[0] for x in sp["single_place"]] == ["P:1"])
check("sparse_place: places 2-3", [x[0] for x in sp["sparse_place"]] == ["P:2", "P:3"])

# ---------------------------------------------------------------- исключения по раундам
tmp = tempfile.mkdtemp()
try:
    def put(*parts, text):
        fp = os.path.join(tmp, *parts)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(text)
    put("round-a", "holdout.json", text=json.dumps({"items": [{"asset_id": "AA:1"}]}))
    put("round-a", "inputs", "generation.tsv", text="AA:2\n")
    put("round-a", "img", "x.json", text="AA:3")
    put("round-a", "sub", "frames.tsv", text="AA:4")
    put("round-a", "notes.md", text="AA:5")
    put("families-recolor-v2", "scan.tsv", text="AA:6")
    put("round-b", "found.tsv", text="aa:7\tZZ:9")
    per = H.round_keys(tmp, {"AA:%d" % i for i in range(1, 8)}, set(H.WHOLE_QUEUE_ROUNDS))
    check("берутся json и tsv раундов, регистр не важен", per.get("round-a") == {"AA:1"} and per.get("round-b") ==
          {"AA:7"})
    check("снимки и картинки не исключают (inputs, img, frames.tsv), .md не читается",
          not ({"AA:2", "AA:3", "AA:4", "AA:5"} & set().union(*per.values())))
    check("скан всей очереди не исключает", "families-recolor-v2" not in per)
    check("ключ вне очереди не берётся", "ZZ:9" not in set().union(*per.values()))
finally:
    shutil.rmtree(tmp)

# ---------------------------------------------------------------- проход детекторов
calls = {"AR2": 0, "RC": 0, "ASM": 0, "TC": 0, "AG": 0}


def fake(det, hit):
    def fn(k):
        calls[det] += 1
        return [{"rule": "r", "level": "STRONG" if det == "ASM" and k.endswith(":1") else "CANDIDATE",
                 "target": "T:0"}] if hit(k) else []
    return fn


rows = [row("Q%d:%d" % (i, j)) for i in range(30) for j in (1, 2)]
pools, stat = H.scan(rows, {"AR2": fake("AR2", lambda k: True), "RC": fake("RC", lambda k: False),
                            "ASM": fake("ASM", lambda k: True), "TC": fake("TC", lambda k: False),
                            "AG": fake("AG", lambda k: False)}, found=3, cap=60)
check("подслой ar2 полон на 3 наборах", stat["found_ar2"] == 3)
check("AR2 перестал считаться, когда ar2 полон (RC продолжает)", calls["AR2"] < calls["RC"] == 60)
check("ASM: STRONG и CANDIDATE разведены по подслоям", stat["found_asm_strong"] == 3 and
      stat["found_asm_candidate"] == 3)
check("ASM считался, пока не полны оба подслоя", calls["ASM"] < 60)
check("классы: RC -> rar, TC -> tc, AG -> ag",
      H.classify({"RC": [1], "TC": [1], "AG": [1]}) == ["rar", "tc", "ag"])

# ---------------------------------------------------------------- ворота


def r_of(vals, handoff):
    gates = [{"gate": g, "value": v, "n": n} for g, (v, n) in vals.items()]
    return {"gates": gates, "legacy": {"handoff_unassigned": (handoff, 80)}}


good = {"PRE_REVIEW_DANGEROUS": (0, 80), "POST_REVIEW_DANGEROUS": (0, 80),
        "relation_existence_precision": (0.97, 50), "related_frame_safety_recall": (0.92, 40),
        "automatic_action_precision": (0.99, 30), "derived_recolor_discovery": (0.8, 20),
        "state_discovery": (0.75, 12), "ASSEMBLY_candidate_existence_precision": (0.96, 25),
        "ASSEMBLY_STRONG_composite_precision": (1.0, 11)}
g, v = H.gates_v7(r_of(good, 0))
check("все ворота в норме - PASS", v == "PASS" and len(g) == 10)
check("у ворот есть группа (hard, typed, review, handoff)",
      {x["group"] for x in g} == {"hard", "typed", "review", "handoff"})
g, v = H.gates_v7(r_of(good, 2))
check("handoff_unassigned 2 - FAIL", v == "FAIL" and
      [x["status"] for x in g if x["gate"] == "handoff_unassigned"] == ["FAIL"])
g, v = H.gates_v7(r_of(dict(good, state_discovery=(1.0, 9)), 0))
check("state n 9 - INSUFFICIENT_SAMPLE, вердикт INCONCLUSIVE", v == "INCONCLUSIVE" and
      [x["status"] for x in g if x["gate"] == "state_discovery"] == ["INSUFFICIENT_SAMPLE"])
g, v = H.gates_v7(r_of(dict(good, related_frame_safety_recall=(0.89, 40)), 0))
check("frame safety 0.89 - FAIL", v == "FAIL")
g, v = H.gates_v7(r_of(dict(good, POST_REVIEW_DANGEROUS=(1, 80)), 0))
check("POST 1 - FAIL", v == "FAIL")
check("порог frame safety 0.90 и hard",
      ("related_frame_safety_recall", "rate", 0.90, "hard") in H.GATES)

# ---------------------------------------------------------------- unique saves
full = {"frame_safety": {"missed": {"B:1": []}}, "pp": {"pre_dangerous": [], "post_dangerous": []}}
wo = {"frame_safety": {"missed": {"B:1": [], "R:1": []}}, "pp": {"pre_dangerous": ["R:1"], "post_dangerous": []}}
u = H.unique_saves(full, wo)
check("кадр найден только с RAR, опасный только без RAR",
      u["frame_safety_only_with"] == ["R:1"] and u["dangerous_without"] == ["R:1"] and
      u["dangerous_post_without"] == [])

print("\n%s: %d провалов" % ("FAIL" if FAILS else "OK", len(FAILS)))
sys.exit(1 if FAILS else 0)
