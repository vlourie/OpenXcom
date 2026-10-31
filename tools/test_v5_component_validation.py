#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверки V5_COMPONENT_VALIDATION_V1 без данных: слои, подтип по ярлыку, точность, готовность, выбор пары."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import v5_component_validation as cv   # noqa: E402

FAIL = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAIL.append(name)


def edge(level, rule, dz=0):
    return {"level": level, "rule": rule, "scores": {"offset": [1, 0, dz]}}


def row(st, ex, j1, j2, level=None, info=None):
    r = {"q": "C%03d" % (len(st) + len(j1) + len(j2)), "a": "A:1", "b": "B:2", "stratum": st,
         "family": cv.FAMILY[st], "existence": ex, "judge1": j1, "judge2": j2, "level": level,
         "info": info or {}}
    r["exist"] = {"RELATED": "yes", "NONE": "no"}.get(ex, "OPEN")
    r["composite"] = cv.subtype(r, {"COMPOSITE"})
    r["derived"] = cv.subtype(r, cv.DERIVED_SUB)
    r["attachment_only"] = False
    return r


def main():
    # слой ASM: этаж важнее уровня
    check("stratum vertical", cv.asm_stratum(edge("STRONG", "AO", dz=1)) == "ASM_VERTICAL")
    check("stratum strong", cv.asm_stratum(edge("STRONG", "AO")) == "ASM_STRONG")
    check("stratum single", cv.asm_stratum(edge("CANDIDATE", "AOs")) == "ASM_SINGLE")
    check("stratum repeat", cv.asm_stratum(edge("CANDIDATE", "AOc")) == "ASM_REPEAT_CAND")

    # подтип по ярлыку: оба - да, один - OPEN, связи нет - нет
    r = row("ASM_STRONG", "RELATED", ["COMPOSITE"], ["COMPOSITE", "STRUCTURAL_COUNTERPART"])
    check("subtype both", r["composite"] == "yes")
    r = row("ASM_STRONG", "RELATED", ["COMPOSITE"], ["ATTACHMENT_CANDIDATE"])
    check("subtype one -> OPEN", r["composite"] == "OPEN")
    r = row("ASM_STRONG", "RELATED", ["ATTACHMENT_CANDIDATE"], ["MODULAR_SECTION"])
    check("subtype none of both", r["composite"] == "no")
    r = row("ASM_STRONG", "NONE", ["NONE"], ["NONE"])
    check("subtype no relation", r["composite"] == "no")
    r = row("ASM_STRONG", "OPEN", ["UNSURE"], ["NONE"])
    check("subtype open existence", r["composite"] == "OPEN")
    r = row("AR1_TRIGGER", "RELATED", ["RECOLOR_PEER"], ["DERIVED"])
    check("derived any derived label", r["derived"] == "yes")

    # точность считает только закрытые
    rs = [row("ASM_SINGLE", "RELATED", ["COMPOSITE"], ["COMPOSITE"], "CANDIDATE") for _ in range(19)]
    rs.append(row("ASM_SINGLE", "NONE", ["NONE"], ["NONE"], "CANDIDATE"))
    rs.append(row("ASM_SINGLE", "OPEN", ["UNSURE"], ["COMPOSITE"], "CANDIDATE"))
    v, n, ok, op = cv.prec(rs, "exist", "yes")
    check("prec closed only", (v, n, ok, op) == (0.95, 20, 19, 1))
    check("verdict pass at 0.95", cv.verdict(v, n) == "PASS")
    check("verdict small sample", cv.verdict(1.0, cv.N_MIN - 1) == "INSUFFICIENT_SAMPLE")
    check("verdict no data", cv.verdict(None, 0) == "NO_DATA")

    # взвешенная: слой с большой численностью тянет сильнее
    a = [row("ASM_SINGLE", "RELATED", ["COMPOSITE"], ["COMPOSITE"], "CANDIDATE")]
    b = [row("ASM_REPEAT_CAND", "NONE", ["NONE"], ["NONE"], "CANDIDATE")]
    w = cv.weighted(a + b, "exist", "yes", {"ASM_SINGLE": 90, "ASM_REPEAT_CAND": 10},
                    {"ASM_SINGLE": 1, "ASM_REPEAT_CAND": 1})
    check("weighted by population", w == 0.9)

    # готовность: кандидаты и STRONG отдельно; отрицательные слои в точность не входят
    strong = [row("ASM_STRONG", "RELATED", ["COMPOSITE"], ["COMPOSITE"], "STRONG") for _ in range(12)]
    neg = [row("ASM_NEG_NEAR", "NONE", ["NONE"], ["NONE"]) for _ in range(30)]
    R = cv.readiness(rs + strong + neg, {}, {})
    check("readiness pass", R["verdict"] == "PASS" and R["asm_candidate_existence_precision"]["n"] == 20)
    # контроль: STRONG, у которого судьи видят только примыкание, валит подтип
    bad = strong[:10] + [row("ASM_STRONG", "RELATED", ["ATTACHMENT_CANDIDATE"], ["ATTACHMENT_CANDIDATE"], "STRONG")
                         for _ in range(2)]
    R = cv.readiness(rs + bad, {}, {})
    check("control: attachment-only STRONG fails typed", R["asm_strong_typed_precision"]["verdict"] == "FAIL"
          and R["verdict"] == "FAIL")
    # контроль: без STRONG итог не PASS
    R = cv.readiness(rs, {}, {})
    check("no strong -> inconclusive", R["verdict"] == "INCONCLUSIVE")

    # выбор пары: первый по приоритету слой, где ещё нужно; занятые кадры пропускаются
    cands = [("ASM_STRONG", "X:1", {}), ("AR1_TRIGGER", "Y:1", {}), ("ASM_NEG_NEAR", "Z:1", {})]
    check("pick priority", cv.pick(cands, dict(cv.QUOTA), set(), None)[0] == "AR1_TRIGGER")
    need = dict(cv.QUOTA, AR1_TRIGGER=0)
    check("pick skips full stratum", cv.pick(cands, need, set(), None)[0] == "ASM_STRONG")
    check("pick skips used frame", cv.pick(cands, need, {"X:1"}, None)[0] == "ASM_NEG_NEAR")
    check("pick none", cv.pick(cands, {}, set(), None) is None)

    # корзины границ
    check("border bins", (cv.border_bin(0.81), cv.border_bin(0.74), cv.border_bin(0.3)) == (">=0.8", ">=0.7", "<0.5"))

    # спецификация замораживается как JSON; порог 0.80 AR1 и параметры ASM - из модулей, не свои
    s = cv.spec()
    j = json.loads(json.dumps(s, ensure_ascii=False))
    check("spec json stable", json.loads(json.dumps(j, ensure_ascii=False)) == j)
    check("spec thresholds unchanged", s["ar1_params"]["AR_BORDER"] == 0.80 and s["asm_params"]["ASM_CORE"] == 0.75)
    check("strata unique", len({x["name"] for x in s["strata"]}) == len(cv.STRATA))

    print("всего проверок не прошло: %d" % len(FAIL))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
