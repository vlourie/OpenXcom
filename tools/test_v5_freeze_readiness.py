#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверки V5_FREEZE_READINESS_V1 без данных: условия заморозки, две строки KITSUNE, точность, AR1 по полосам."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import relation_taxonomy as tx         # noqa: E402
import v5_freeze_readiness as fr       # noqa: E402

FAIL = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAIL.append(name)


def gates(**over):
    G = {g: {"gate": g, "value": 1.0, "n": 20, "need": 0.7, "status": "PASS"} for g in fr.FREEZE_GATES}
    for g, st in over.items():
        G[g] = dict(G[g], status=st)
    return G


def val(ce=(0.97, 100), st=(0.97, 70)):
    return {"candidate_existence": {"value": ce[0], "n": ce[1], "ok": 0, "open": 0},
            "strong_composite_subtype": {"value": st[0], "n": st[1], "ok": 0, "open": 0}}


class Claims:
    def __init__(self, cl):
        self.cl = cl

    def pair(self, a, b):
        return [c for c in self.cl if set(c["pair"]) == {a, b}]

    def of(self, a):
        return [c for c in self.cl if a in c["pair"]]


def claim(a, b, group, ex="RELATED_CANDIDATE"):
    return {"pair": [a, b], "group": group, "existence": ex,
            "support": [{"detector": "ASM", "rule": "AOc"}]}


def res(danger=False, creative=False):
    K = fr.KITSUNE
    return {"score": [{"asset_id": K, "danger": danger, "creative": creative}],
            "pc": [(K, "C_INT_HALF:47", ("RELATED", {"COMPOSITE"}), None),
                   (K, "OTHER:1", ("NONE", set()), None)]}


def main():
    # условия заморозки: все 9 PASS -> PASS; один FAIL -> FAIL; мало закрытых -> не PASS
    rows, v = fr.readiness(gates(), val(), 0)
    check("9 conditions", len(rows) == 9)
    check("all pass", v["freeze_readiness"] == "PASS")
    names = [r["cond"] for r in rows]
    check("renamed", "composite_discovery_recall" in names and "PRE_REVIEW_DANGEROUS" in names)
    check("v5 gate fail", fr.readiness(gates(dangerous_creative_standalone="FAIL"), val(), 0)[1]["freeze_readiness"]
          == "FAIL")
    check("asm precision fail", fr.readiness(gates(), val(st=(0.90, 70)), 0)[1]["assembly_validation"] == "FAIL")
    check("small sample not pass", fr.readiness(gates(), val(ce=(1.0, 5)), 0)[1]["freeze_readiness"] ==
          "INCONCLUSIVE")
    # KITSUNE-случай: legacy и сборка проходят, а после ревью опасный есть -> заморозка FAIL
    _r, v = fr.readiness(gates(), val(), 1)
    check("post-review blocks freeze", (v["legacy_gates"], v["assembly_validation"], v["post_review_safety"],
                                        v["freeze_readiness"]) == ("PASS", "PASS", "FAIL", "FAIL"))

    # точность только по закрытым
    pr = fr.precision([{"f": "yes"}, {"f": "no"}, {"f": "OPEN"}, {"f": "yes"}], "f")
    check("precision closed", pr[0] == 2 / 3 and pr[1:] == (3, 2, 1))

    # KITSUNE: держит чужой кандидат, отвергнутый слепой проверкой -> SAFE via REVIEW / MISSED, вердикт виден
    K = fr.KITSUNE
    C = Claims([claim(K, "C_INT_HALF_XCOM:48", "composite")])
    by_pair = {tx.pk(K, "C_INT_HALF_XCOM:48"): {"q": "C132", "existence": "NONE", "closed": ["NONE"], "open": []}}
    k = fr.kitsune(res(), C, by_pair)
    check("kitsune safe via review", k["safety"] == "SAFE via REVIEW")
    check("kitsune missed", k["true_relation_discovery"] == "MISSED")
    check("kitsune blind none shown", k["held_by"][0]["blind"]["existence"] == "NONE")
    check("kitsune only true pairs", [x["pair"][1] for x in k["true_pairs"]] == ["C_INT_HALF:47"])
    # контроль: довод на истинной паре -> FOUND; опасный кадр -> DANGEROUS
    C2 = Claims([claim(K, "C_INT_HALF:47", "composite")])
    check("kitsune found", fr.kitsune(res(), C2, {})["true_relation_discovery"] == "FOUND")
    check("kitsune dangerous", fr.kitsune(res(danger=True, creative=True), Claims([]), {})["safety"] == "DANGEROUS")
    check("kitsune not checked", fr.kitsune(res(), C, {})["held_by"][0]["blind"] is None)

    # AR1: полосы границ; 0.80 и выше - не «только границы», в полосах не считается
    check("band low", fr.band(0.3, fr.AR_BANDS) == "0.00-0.50")
    check("band mid", fr.band(0.74, fr.AR_BANDS) == "0.65-0.80")
    check("band edge", fr.band(0.5, fr.AR_BANDS) == "0.50-0.65")

    def ar(q, st, border, derived, shift=(0, 1)):
        return {"q": q, "a": "A:1", "b": "B:2", "stratum": st, "derived": derived, "closed": [],
                "info": {"scores": {"shift": list(shift), "topology": border, "fmax": 0.9}}}
    A = fr.ar1_analysis([ar("1", "AR1_BORDER_ONLY", 0.2, "no"), ar("2", "AR1_BORDER_ONLY", 0.6, "yes"),
                         ar("3", "AR1_BORDER_ONLY", 0.7, "OPEN"), ar("4", "AR1_TRIGGER", 0.9, "yes", (1, 1))])
    check("ar1 band counts", A["border_only_by_band"] == {"0.00-0.50": {"no": 1}, "0.50-0.65": {"yes": 1},
                                                          "0.65-0.80": {"OPEN": 1}})
    check("ar1 high band closed", (A["border_ge_0.5_closed"], A["border_ge_0.5_ok"]) == (1, 1))
    check("ar1 trigger shift", A["triggers_by_shift"] == {"shift 2 yes": 1})

    print("\n%s" % ("всё прошло" if not FAIL else "провалено: %d" % len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
