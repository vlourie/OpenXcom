#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка relation_taxonomy.py на синтетике (без карт и видеокарты): политика «анимация + перекраска
сосуществуют», истина из ответов судьи, точность против набора допустимых типов, слепота пакета.

    py -3.13 tools/test_relation_taxonomy.py
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import relation_discovery_v2 as v2      # noqa: E402
import relation_discovery_v3 as v3      # noqa: E402
import relation_taxonomy as tx          # noqa: E402

FAILS = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


def found(text, words):
    """Слово целиком (CANDIDATE внутри ATTACHMENT_CANDIDATE - не слово)."""
    return [w for w in words if re.search(r"(?<![A-Za-z0-9_])" + re.escape(w), text)]


def e(typ, a, b, level="STRONG", det="RECOLOR", rule="R"):
    return v2.edge(typ, a, b, level, det, rule, "синтетика")


def build(cls, edges):
    C = cls()
    for x in edges:
        C.add(x)
    return C.finalize()


ANIM_REC = [e("ANIMATION_FAMILY", "S:1", "S:2", det="MCD", rule="M3"), e("RECOLOR_PEER", "S:1", "S:2")]


def test_policy():
    C3 = build(v3.Claims, ANIM_REC)
    check("контроль: V3 открывает тип у анимации и перекраски", all(c["type_level"] == v3.T_OPEN for c in C3.pair("S:1", "S:2")))
    CT = build(tx.TaxClaims, ANIM_REC)
    cs = {c["group"]: c for c in CT.pair("S:1", "S:2")}
    check("анимация + перекраска: оба TYPE_STRONG", all(c["type_level"] == v3.T_STRONG for c in cs.values()))
    check("перекраска при анимации - улика, не производство",
          cs["derived"]["production"] is False and cs["animation"]["production"] is True)
    check("роль вывода перекраской не даётся", "RECOLOR_PEER" not in tx.pipe_roles(CT, "S:1"))
    check("роль анимации остаётся", any("ANIMATION" in r for r in tx.pipe_roles(CT, "S:1")))
    CS = build(tx.TaxClaims, [e("ANIMATION_FAMILY", "S:1", "S:2", det="MCD"), e("DESTROYED_VARIANT_OF", "S:2", "S:1", det="MCD")])
    check("анимация против состояния - спор остаётся", all(c["type_level"] == v3.T_OPEN for c in CS.pair("S:1", "S:2")))
    CC = build(tx.TaxClaims, ANIM_REC + [e("DESTROYED_VARIANT_OF", "S:2", "S:1", det="MCD")])
    check("анимация + перекраска + состояние - спор анимации с состоянием", all(
        c["type_level"] == v3.T_OPEN for c in CC.pair("S:1", "S:2") if c["group"] in ("animation", "state")))
    CR = build(tx.TaxClaims, [e("RECOLOR_PEER", "S:1", "T:1")])
    check("перекраска без анимации - производство", CR.pair("S:1", "T:1")[0]["production"] is True)
    CA = build(tx.TaxClaims, [e("ANIMATION_FAMILY", "S:1", "S:2", level="CANDIDATE", det="MCD"), e("RECOLOR_PEER", "S:1", "S:2")])
    check("анимация только кандидат - перекраска остаётся производством",
          [c for c in CA.pair("S:1", "S:2") if c["group"] == "derived"][0]["production"] is True)


def test_truth():
    check("medium и high берутся, low нет", tx.truth_of({"COMPOSITE": "high", "ATTACHMENT_CANDIDATE": "low"}) == {"COMPOSITE"})
    check("UNSURE не берётся", tx.truth_of({"UNSURE": ""}) == set())
    check("NONE рядом с ярлыком - ярлык", tx.truth_of({"NONE": "medium", "RECOLOR_PEER": "high"}) == {"RECOLOR_PEER"})
    key = {"items": [{"q": "Q001", "a": "S:1", "b": "S:2", "tags": []}, {"q": "Q002", "a": "S:3", "b": "S:4", "tags": []}]}
    old = {tx.pk("S:1", "S:2"): "ANIMATION_FRAME_OF", tx.pk("S:3", "S:4"): "STRUCTURAL_RELATION",
           tx.pk("S:5", "S:6"): "RECOLOR_OF"}
    T = tx.build_truth(key, {"Q001": {"ANIMATION_FAMILY": "high", "RECOLOR_PEER": "medium"},
                             "Q002": {"UNSURE": ""}}, old)
    check("судья заменяет прежний эталон", T[tx.pk("S:1", "S:2")] == ({"ANIMATION_FAMILY", "RECOLOR_PEER"}, "judge"))
    check("судья не взял ничего - пара не судима", T[tx.pk("S:3", "S:4")] == (set(), "judge_unsure"))
    check("без судьи - прежний эталон в ярлыках", T[tx.pk("S:5", "S:6")] == ({"RECOLOR_PEER"}, "old"))


def test_scoring():
    CT = build(tx.TaxClaims, ANIM_REC)
    cs = CT.pair("S:1", "S:2")
    one = tx.existence_typed([({"ANIMATION_FAMILY"}, cs)])
    two = tx.existence_typed([({"ANIMATION_FAMILY", "RECOLOR_PEER"}, cs)])
    check("один ярлык: перекраска - ошибка факта", one["typed_fact_precision"] == 0.5)
    check("перекраска-улика не входит в авто-действие", one["typed_auto_judged"] == 1 and one["typed_auto_precision"] == 1.0)
    check("набор допустимых типов: обе верны", two["typed_fact_precision"] == 1.0)
    comp = build(tx.TaxClaims, [e("COMPOSITE_PART", "S:7", "S:8", det="PLACE", rule="P3")])
    r = tx.recall_labels([({"COMPOSITE"}, comp.pair("S:7", "S:8")), ({"STRUCTURAL_COUNTERPART"}, [])])
    check("составной найден", r["COMPOSITE"]["discovery"] == 1 and r["COMPOSITE"]["n"] == 1)
    check("противоположная часть - в составной не считается", r["STRUCTURAL_COUNTERPART"]["n"] == 1 and "discovery" not in r["STRUCTURAL_COUNTERPART"])
    ex = tx.existence_typed([({"NONE"}, comp.pair("S:7", "S:8"))])
    check("связь на NONE - ошибка существования", ex["existence_precision"] == 0.0)


def test_reclass():
    check("существование: RELATED / NONE / OPEN", [tx.existence_class(x) for x in ({"COMPOSITE"}, {"NONE"}, set())]
          == ["RELATED", "NONE", "OPEN"])
    rp = [("S:1", "S:2", "STRUCTURAL_RELATION"), ("S:3", "S:4", "STRUCTURAL_RELATION"), ("S:5", "S:6", "STRUCTURAL_RELATION"),
          ("S:7", "S:8", "STATE_VARIANT_OF")]
    T = {tx.pk("S:1", "S:2"): ({"COMPOSITE"}, "judge"),
         tx.pk("S:3", "S:4"): ({"STRUCTURAL_COUNTERPART", "MIRRORED_VARIANT_PEER"}, "judge"),
         tx.pk("S:5", "S:6"): (set(), "judge_unsure"), tx.pk("S:7", "S:8"): ({"COMPOSITE", "STATE_VARIANT"}, "judge")}
    r = tx.composite_reclass(rp, T)
    check("знаменатель: прежний 3, новый 2 (один пришёл из состояния)",
          r["old_composite_denominator"] == 3 and r["new_true_composite_denominator"] == 2 and len(r["new_from_other_old_labels"]) == 1)
    check("переклассификация: противоположная и зеркальная, одна открыта",
          r["reclassified_to_counterpart"] == 1 and r["reclassified_to_mirrored"] == 1 and r["open"] == 1 and r["kept_composite"] == 1)
    ch = [{"q": "Q1", "a": "A", "b": "B", "tags": ["agree_derived"], "old": "RECOLOR_OF", "judge": {"RECOLOR_PEER": "high"},
           "taken": ["RECOLOR_PEER"], "agrees_old": True},
          {"q": "Q2", "a": "C", "b": "D", "tags": ["agree_none"], "old": "NONE", "judge": {"RECOLOR_PEER": "medium"},
           "taken": ["RECOLOR_PEER"], "agrees_old": False},
          {"q": "Q3", "a": "E", "b": "F", "tags": ["multi_claim"], "old": "NONE", "judge": {}, "taken": [], "agrees_old": False}]
    ca = tx.control_agreement(ch)
    check("согласие контроля 1 из 2, изменённая пара в списке",
          ca["n"] == 2 and ca["control_truth_agreement"] == 0.5 and len(ca["changed"]) == 1 and "Q2" in ca["changed"][0])


def test_answers_and_blind():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "answers"))
    with open(os.path.join(d, "answers", "judge_1.tsv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write("q\tlabel\tconfidence\tevidence\nQ001\tcomposite\tHigh\tбок\nQ001\tRECOLOR_PEER\tlow\tцвет\n"
                "Q002\tFOO\thigh\tx\nQ003\tUNSURE\t\tне видно\n")
    ans, bad = tx.read_answers(d)
    check("ответы: регистр не важен", ans["Q001"] == {"COMPOSITE": "high", "RECOLOR_PEER": "low"})
    check("неизвестный ярлык - ошибка формата", len(bad) == 1 and "FOO" in bad[0])
    check("UNSURE без уверенности принят", "UNSURE" in ans["Q003"])
    words = ("STRONG", "CANDIDATE", "MIRRORED_RECOLOR", "NEAR_RECOLOR", "RECOLOR_OF", "STRUCTURAL_RELATION",
             "DERIVED_FROM", "mirror_fire", "agree_", "typed_wrong", "existence_wrong", "multi_claim", "P3")
    check("JUDGE.md не говорит о детекторах и прежнем эталоне", not found(tx.JUDGE, words))
    check("в JUDGE.md все ярлыки схемы", all(l in tx.JUDGE for l in tx.LABELS))


def test_live_pack():
    """Если пакет уже собран: в blind/ нет ни слова о детекторах, группах отбора и прежнем эталоне."""
    blind = os.path.join(tx.OUT, "blind")
    if not os.path.isdir(blind):
        print("skip пакета нет")
        return
    words = ("STRONG", "CANDIDATE", "MIRRORED_RECOLOR", "NEAR_RECOLOR", "RECOLOR_OF", "STRUCTURAL_RELATION",
             "DERIVED_FROM", "mirror_fire", "mirror_negative", "agree_", "typed_wrong", "existence_wrong",
             "multi_claim", "structural_ref", "detector")
    hits = []
    for fn in os.listdir(blind):
        if fn.endswith(".md"):
            t = open(os.path.join(blind, fn), encoding="utf-8-sig").read()
            hits += ["%s: %s" % (fn, w) for w in found(t, words)]
    check("пакет слепой (%s)" % (", ".join(hits[:5]) or "чисто"), not hits)
    check("ключ не в пакете", not os.path.exists(os.path.join(blind, "blind_key.json")))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    test_policy()
    test_truth()
    test_scoring()
    test_reclass()
    test_answers_and_blind()
    test_live_pack()
    print("FAIL: %d" % len(FAILS) if FAILS else "все проверки прошли")
    sys.exit(1 if FAILS else 0)
