#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверки POST_REVIEW_SAFETY без данных: отклонённый кандидат не спасает кадр (R-181)."""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import post_review_safety as prs        # noqa: E402
import relation_discovery_v3 as v3      # noqa: E402

FAIL = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAIL.append(name)


def claims(*cl):
    C = v3.Claims()
    for a, b, ex in cl:
        k = ("composite", frozenset((a, b)))
        C.claims[k] = {"pair": sorted((a, b)), "group": "composite", "existence": ex,
                       "support": [{"detector": "ASM", "rule": "AOc"}]}
        C.by_asset[a].add(k)
        C.by_asset[b].add(k)
    return C


def evaluate(C):
    """Игрушечный маршрут: кадр из списка опасен, если на нём нет ни одного довода."""
    return {"dangerous": {a: ["нет довода"] for a in ("K:15", "X:1", "Y:1") if not C.of(a)}}


def main():
    none = prs.closed_none(("holdout", [("K:15", "H:48", "NONE"), ("X:1", "X:2", "RELATED")]),
                           ("blind", [("Y:1", "Y:2", "OPEN"), ("S:1", "S:2", "NONE")]))
    check("closed none only", set(none) == {frozenset(("K:15", "H:48")), frozenset(("S:1", "S:2"))})

    C = claims(("K:15", "H:48", v3.CAND), ("X:1", "X:2", v3.CAND), ("Y:1", "Y:2", v3.CAND),
               ("S:1", "S:2", v3.STRONG))
    s, _post = prs.pre_post(evaluate, C, none)
    check("pre 0", s["PRE_REVIEW_DANGEROUS"] == 0)
    check("post 1 (K:15)", s["POST_REVIEW_DANGEROUS"] == 1 and s["post_dangerous"] == ["K:15"])
    check("unmasked by H:48", s["unmasked"][0]["masked_by"][0]["pair"] == ["H:48", "K:15"])
    check("open candidate kept", "Y:1" not in s["post_dangerous"])
    check("strong kept, counted", len(s["strong_on_closed_none"]) == 1 and len(s["dropped_candidates"]) == 1)
    check("original untouched", len(C.claims) == 4 and C.of("K:15"))
    # контроль: без закрытого NONE пересчёт после ревью ничего не меняет
    s0, _ = prs.pre_post(evaluate, C, {})
    check("control no truth", s0["POST_REVIEW_DANGEROUS"] == 0 and not s0["dropped_candidates"])
    # by_asset копии согласован с claims
    C2, _d, _s = prs.after_review(C, none)
    idx = defaultdict(set)
    for k, c in C2.claims.items():
        for x in c["pair"]:
            idx[x].add(k)
    check("index consistent", dict(idx) == {k: v for k, v in C2.by_asset.items() if v})

    print("\n%s" % ("всё прошло" if not FAIL else "провалено: %d" % len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
