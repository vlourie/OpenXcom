#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""identity_holdout: отбор, заморозка ворот до ответов, отчёт по слоям (специалист 01.10).

Главное: общий процент хороший, а один слой провален - ворота FAIL (контроль: без провала слоя - PASS).

    py -3.13 tools/test_identity_holdout.py
Без карт и видеокарты: синтетика во временной папке.
"""
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import identity_holdout as h          # noqa: E402

ENC = "utf-8-sig"
V, F, U = "IDENTITY_VISUALLY_VERIFIED", "PART_FRAGMENT_CONFIRMED", "UNSURE"
REF_HEAD = ["asset_id", "ref_status", "identity_ok", "old_rejected", "structural_ok", "semantic_ok",
            "truth_identity", "relation", "old_ok", "sources"]


def write(path, text):
    with open(path, "w", encoding=ENC) as f:
        f.write(text)


def setup(d, items):
    """items: [(asset, layer)] -> holdout.json и cards.json."""
    its = [{"asset_id": a, "layer": lay} for a, lay in items]
    write(os.path.join(d, "holdout.json"), json.dumps({"n": len(its), "sha256": h.digest(its), "items": its,
                                                       "created": "t"}))
    write(os.path.join(d, "cards.json"), json.dumps({"title": "t", "cards": [
        {"asset": a, "prompt": "old", "card_complete": True} for a, _l in items]}))


def answers(d, rows):
    write(os.path.join(d, "answers_vitali.tsv"), "\n".join(
        ["asset_id\tfinal_identity\tstatus\tmissing_context\tnote"] +
        ["%s\t%s\t%s\t%s\t" % r for r in rows]) + "\n")


def reference(d, rows):
    write(os.path.join(d, "reference.tsv"), "\n".join(["\t".join(REF_HEAD)] + ["\t".join(r) for r in rows]) + "\n")


def ref(a, st, sem="yes", old="yes"):
    return [a, st, "yes", "yes", "", sem, "x", "", old, "MCD"]


def quiet(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*a)


def main():
    fails = []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    # отбор: один ассет на набор, виденные и классы человека вне, слой по блокерам
    rows = [
        {"asset_id": "S:1", "key": "S:1", "rank": "1", "kind": "один", "places": "9", "action": "GENERATE",
         "status": "BLOCKED", "blockers": "identity part_fragment_suspect", "identity_status": "AGENT_PROPOSED"},
        {"asset_id": "S:2", "key": "S:2", "rank": "2", "kind": "один", "places": "9", "action": "GENERATE",
         "status": "BLOCKED", "blockers": "identity part_fragment_suspect", "identity_status": "AGENT_PROPOSED"},
        {"asset_id": "T:1", "key": "T:1", "rank": "3", "kind": "один", "places": "9", "action": "GENERATE",
         "status": "BLOCKED", "blockers": "identity", "identity_status": "AGENT_PROPOSED"},
        {"asset_id": "Q:1", "key": "Q:1", "rank": "4", "kind": "один", "places": "9", "action": "EXCLUDE",
         "status": "STRUCTURAL", "blockers": "", "identity_status": "REVIEW_REQUIRED"},
        {"asset_id": "R:1", "key": "R:1", "rank": "5", "kind": "один", "places": "9", "action": "GENERATE",
         "status": "BLOCKED", "blockers": "identity", "identity_status": "REVIEW_REQUIRED"},
        {"asset_id": "W:1", "key": "W:1", "rank": "6", "kind": "один", "places": "9", "action": "GENERATE",
         "status": "BLOCKED", "blockers": "identity", "identity_status": "REVIEW_REQUIRED"},
    ]
    pick, pool, short = h.select(rows, {"T:1": {"verdict": "agree"}}, {"R:1"}, {"W:1"})
    got = {x["asset_id"]: x["layer"] for x in pick}
    check("отбор: один на набор, виденные и классы человека вне, EXCLUDE вне",
          len([a for a in got if a.startswith("S:")]) == 1 and got.get("T:1") == "agree"
          and not {"Q:1", "R:1", "W:1"} & set(got) and pool == {"fragment": 2, "agree": 1})

    with tempfile.TemporaryDirectory() as d:
        items = [("A:%d" % i, "agree") for i in range(10)] + [("F:%d" % i, "fragment") for i in range(4)] + \
                [("C:1", "confirmed"), ("C:2", "confirmed")]
        setup(d, items)
        answers(d, [("A:0", "x", V, "")])
        try:
            quiet(h.freeze_gates, d)
            check("ворота после ответов не замораживаются", False)
        except SystemExit:
            check("ворота после ответов не замораживаются", True)
        os.remove(os.path.join(d, "answers_vitali.tsv"))
        quiet(h.freeze_gates, d)
        try:
            quiet(h.freeze_gates, d)
            check("повторная заморозка ворот - отказ", False)
        except SystemExit:
            check("повторная заморозка ворот - отказ", True)

        # 16 предметов: agree и confirmed все верны, fragment 2 из 4 названы предметом -> слой 50 %
        refs = [ref(a, V) for a, lay in items if lay != "fragment"] + [ref(a, F) for a, lay in items if lay == "fragment"]
        refs[-1 - 4] = ref("C:2", V, old="no")                   # прежнее подтверждение C:2 опровергнуто
        reference(d, refs)
        ans = [(a, "x", V, "") for a, lay in items if lay != "fragment"] + \
              [("F:0", "x", F, ""), ("F:1", "x", F, ""), ("F:2", "x", V, ""), ("F:3", "x", V, "")]
        answers(d, ans)
        r = quiet(h.holdout_report, d)
        lay = r["layers"]
        check("общий класс 14/16 = 0.875, слой fragment 0.5 - ворота FAIL на слое",
              r["total"]["class_accuracy"] == 0.875 and lay["fragment"]["class_accuracy"] == 0.5
              and r["checks"]["слой fragment (n=4): class_accuracy >= 0.75"] is False and r["passed"] is False)
        check("ложный самостоятельный - кусок назван предметом: 2/16",
              r["total"]["false_standalone"] == 2 and r["total"]["false_standalone_rate"] == 0.125)
        check("confirmed: прежнее подтверждение опровергнуто 1/2 - метрика, а не провал",
              lay["confirmed"]["old_human_confirmation_overturned"] == "1/2" and lay["confirmed"]["class_accuracy"] == 1.0)

        # контроль: те же данные, fragment весь верен -> PASS
        ans_ok = [x if not x[0].startswith("F:") else (x[0], "x", F, "") for x in ans]
        answers(d, ans_ok)
        r = quiet(h.holdout_report, d)
        check("контроль: без провала слоя ворота PASS", r["passed"] is True and r["total"]["class_accuracy"] == 1.0)

        # UNSURE - только в unsure_rate; semantic open - вне знаменателя названий
        ans_u = [("A:0", "", U, "larger map crop")] + ans_ok[1:]
        answers(d, ans_u)
        refs_s = [ref(x[0], x[1], sem="open") if x[0] == "A:1" else
                  (ref(x[0], x[1], sem="no") if x[0] == "A:2" else x) for x in refs]
        refs_s = [ref("C:2", V, old="no") if x[0] == "C:2" else x for x in refs_s]
        reference(d, refs_s)
        r = quiet(h.holdout_report, d)
        t = r["total"]
        check("UNSURE вне знаменателя класса, в unsure_rate и missing_context_rate",
              t["class_n"] == 15 and t["class_accuracy"] == 1.0 and t["unsure_rate"] == 0.062
              and t["missing_context_rate"] == 0.062)
        check("semantic open вне знаменателя, no в нём: 13/14",
              t["semantic_n"] == 14 and t["semantic_accuracy"] == round(13 / 14, 3))

    # общий процент хорош, все общие ворота пройдены, а слой fragment провален - FAIL только на слое
    with tempfile.TemporaryDirectory() as d:
        items = [("A:%d" % i, "agree") for i in range(30)] + [("F:%d" % i, "fragment") for i in range(4)]
        setup(d, items)
        quiet(h.freeze_gates, d)
        reference(d, [ref(a, V) for a, lay in items if lay == "agree"] + [ref(a, F) for a, lay in items if lay != "agree"])
        answers(d, [(a, "x", V, "") for a, lay in items if lay == "agree"] +
                [("F:0", "x", F, ""), ("F:1", "x", F, ""), ("F:2", "x", "NOT_OBJECT", ""), ("F:3", "x", "NOT_OBJECT", "")])
        r = quiet(h.holdout_report, d)
        common = {k: v for k, v in r["checks"].items() if not k.startswith("слой")}
        check("общий класс 32/34 и все общие ворота пройдены, слой fragment 0.5 - FAIL",
              r["total"]["class_accuracy"] == round(32 / 34, 3) and all(v is True for v in common.values())
              and r["checks"]["слой fragment (n=4): class_accuracy >= 0.75"] is False and r["passed"] is False)

    # слой n=2 (меньше layer_hard_min_n) с одной ошибкой: диагностика, holdout не валит
    with tempfile.TemporaryDirectory() as d:
        items = [("A:%d" % i, "agree") for i in range(30)] + [("K:0", "class"), ("K:1", "class")]
        setup(d, items)
        quiet(h.freeze_gates, d)
        reference(d, [ref(a, V) for a, _l in items])
        answers(d, [(a, "x", V, "") for a, _l in items[:-1]] + [("K:1", "x", "NOT_OBJECT", "")])
        r = quiet(h.holdout_report, d)
        check("слой class n=2, 1 ошибка из 2: в диагностике, не в воротах; общие 31/32 - PASS",
              r["passed"] is True and not any(k.startswith("слой class") for k in r["checks"])
              and r["diagnostics"] == {"слой class (n=2, диагностика): ошибок класса <= 1": True}
              and r["layers"]["class"]["class_accuracy"] == 0.5)
        answers(d, [(a, "x", V, "") for a, _l in items[:-2]] + [("K:0", "x", F, ""), ("K:1", "x", F, "")])
        r = quiet(h.holdout_report, d)
        check("слой class n=2, 2 ошибки: диагностика нет, ворота решают общие числа",
              r["diagnostics"]["слой class (n=2, диагностика): ошибок класса <= 1"] is False
              and r["total"]["class_accuracy"] == round(30 / 32, 3) and r["passed"] is True)

        with open(os.path.join(d, "holdout_report.md"), encoding=ENC) as f:
            md = f.read()
        check("отчёт: три блока GLOBAL, BY LAYER, OLD CONFIRMATIONS",
              all(s in md for s in ("## GLOBAL", "## BY LAYER", "## OLD CONFIRMATIONS")))

    # две оси эталона: класс кусок закрыт, название open - в точности класса считается, в названиях нет
    with tempfile.TemporaryDirectory() as d:
        items = [("A:%d" % i, "agree") for i in range(4)] + [("F:%d" % i, "fragment") for i in range(4)]
        setup(d, items)
        quiet(h.freeze_gates, d)
        reference(d, [ref(a, V) for a, lay in items if lay == "agree"] +
                  [ref(a, F, sem="open") for a, lay in items if lay == "fragment"])
        answers(d, [(a, "x", V if lay == "agree" else F, "") for a, lay in items])
        r = quiet(h.holdout_report, d)
        fr = r["layers"]["fragment"]
        check("кусок с названием open: класс 4/4 в знаменателе, названий 0 из слоя",
              fr["class_n"] == 4 and fr["class_accuracy"] == 1.0 and fr["semantic_n"] == 0
              and r["total"]["semantic_n"] == 4)

    # перезаморозка ворот: только до ответов, прежние в архив, ссылка на прежний хэш
    with tempfile.TemporaryDirectory() as d:
        setup(d, [("A:0", "agree")])
        quiet(h.freeze_gates, d)
        first = h.load_gates(d)["sha256"]
        quiet(h.freeze_gates, d, "правило слоёв")
        g = h.load_gates(d)
        check("перезаморозка до ответов: gates.v1.json, replaces = прежний хэш",
              os.path.exists(os.path.join(d, "gates.v1.json")) and g["replaces"] == first
              and g["refreeze_reason"] == "правило слоёв")
        answers(d, [("A:0", "x", V, "")])
        try:
            quiet(h.freeze_gates, d, "ещё раз")
            check("перезаморозка после ответов - отказ", False)
        except SystemExit:
            check("перезаморозка после ответов - отказ", h.load_gates(d)["sha256"] == g["sha256"])

    with tempfile.TemporaryDirectory() as d:
        setup(d, [("A:0", "agree")])
        quiet(h.freeze_gates, d)
        # подделка ворот после заморозки
        p = os.path.join(d, "gates.json")
        g = json.load(open(p, encoding=ENC))
        g["thresholds"]["class_accuracy_min"] = 0.5
        write(p, json.dumps(g))
        try:
            quiet(h.holdout_report, d)
            check("ворота изменены после заморозки - отказ", False)
        except SystemExit:
            check("ворота изменены после заморозки - отказ", True)

    print("итог:", "все проверки прошли" if not fails else "провалено %d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
