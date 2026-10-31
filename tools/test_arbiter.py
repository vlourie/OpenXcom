#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""arbiter: разбор ответа, переход HARD -> LIGHT, FALSE_CONFIDENT, заморозка - без модели (Pipeline v2, P1-C).

  * ответ только из готовых значений: решение и связь вне списка - не по форме, идёт как «не знаю»;
  * переход в LIGHT - только A/B вместе с SAME или BROADER_NARROWER; CONFIRMED не выдаётся никогда;
  * FALSE_CONFIDENT: выбор A/B при правде «другой», NEITHER; BOTH - не ошибка; CANNOT_TELL - не выбор;
  * пороги 5 и 10 процентов;
  * отбор держит разнообразие наборов и не зависит от порядка входа;
  * правка снимка или входной картинки после заморозки останавливает run.

    py -3.13 tools/test_arbiter.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
sys.stdout.reconfigure(encoding="utf-8")

import arbiter as ar                     # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def ans(dec, rel, ev=("sprite",)):
    return ar.normalize({"decision": dec, "relation": rel, "reason_short": "x", "evidence_used": list(ev)})


# ---- форма ответа
a = ar.normalize({"decision": "a", "relation": "broader narrower", "evidence_used": ["sprite", "map name"]})
check("регистр и пробелы приводятся к форме", a["valid"] and a["decision"] == "A" and a["relation"] == "BROADER_NARROWER")
check("улики только из списка", a["evidence_used"] == ["sprite"])
b = ar.normalize({"decision": "Wooden Barrel", "relation": "SAME"})
check("третье имя вместо решения - не по форме", not b["valid"] and "decision" in b["invalid"])
check("пустой ответ - не по форме", not ar.normalize({})["valid"])

# ---- переход
check("A + SAME -> LIGHT", ar.route(ans("A", "SAME")) == ar.LIGHT)
check("B + BROADER_NARROWER -> LIGHT", ar.route(ans("B", "BROADER_NARROWER")) == ar.LIGHT)
check("A + RELATED_BUT_DIFFERENT -> HARD", ar.route(ans("A", "RELATED_BUT_DIFFERENT")) == ar.HARD)
check("A + DIFFERENT -> HARD", ar.route(ans("A", "DIFFERENT")) == ar.HARD)
check("NEITHER -> HARD", ar.route(ans("NEITHER", "SAME")) == ar.HARD)
check("CANNOT_TELL -> HARD", ar.route(ans("CANNOT_TELL", "SAME")) == ar.HARD)
check("не по форме -> HARD", ar.route(b) == ar.HARD)
routes = {ar.route(ans(d, r)) for d in ar.DECISIONS for r in ar.RELATIONS}
check("CONFIRMED не выдаётся никогда", routes <= {ar.LIGHT, ar.HARD})

# ---- FALSE_CONFIDENT
T = lambda t: {"truth": t}
check("выбрал A, правда A - не ошибка", ar.false_confident(ans("A", "SAME"), T("A")) is False)
check("выбрал A, правда BOTH - не ошибка", ar.false_confident(ans("A", "SAME"), T("BOTH")) is False)
check("выбрал A, правда B - ошибка", ar.false_confident(ans("A", "DIFFERENT"), T("B")) is True)
check("выбрал B, правда NEITHER - ошибка", ar.false_confident(ans("B", "SAME"), T("NEITHER")) is True)
check("CANNOT_TELL - не ложно-уверенный", ar.false_confident(ans("CANNOT_TELL", "SAME"), T("NEITHER")) is False)
check("NEITHER при правде A - не ложно-уверенный", ar.false_confident(ans("NEITHER", "SAME"), T("A")) is False)
check("выбор без правды - не сверяется", ar.false_confident(ans("A", "SAME"), None) is None)
check("человек сам не знает - не сверяется", ar.false_confident(ans("A", "SAME"), T("CANNOT_TELL")) is None)
check("исход: выбор совпал / BOTH - верно", ar.outcome(ans("A", "SAME"), T("A")) == "correct"
      and ar.outcome(ans("B", "SAME"), T("BOTH")) == "correct")
check("исход: выбор мимо - FALSE_CONFIDENT", ar.outcome(ans("A", "SAME"), T("NEITHER")) == "false_confident")
check("исход: отказ при правде A - ошибся, но отказался", ar.outcome(ans("CANNOT_TELL", "SAME"), T("A")) == "wrong_uncertain"
      and ar.outcome(ans("NEITHER", "SAME"), T("B")) == "wrong_uncertain")
check("исход: NEITHER при NEITHER, CANNOT_TELL при CANNOT_TELL - верно",
      ar.outcome(ans("NEITHER", "SAME"), T("NEITHER")) == "correct"
      and ar.outcome(ans("CANNOT_TELL", "SAME"), T("CANNOT_TELL")) == "correct")
check("исход: выбор, а человек не знает", ar.outcome(ans("A", "SAME"), T("CANNOT_TELL")) == "picked_human_unsure")
check("исход: не по форме и без правды", ar.outcome(b, T("A")) == "invalid" and ar.outcome(ans("A", "SAME"), None) == "unlabeled")
check("пороги",(ar.verdict_of(0.05), ar.verdict_of(0.07), ar.verdict_of(0.11)) ==
      ("хорошо", "дорабатывать", "массово не применять"))

# ---- отбор
pool = ["S%d:%d" % (s, f) for s in range(10) for f in range(8)]
attrs = {a: (a.split(":")[0], "T" + a.split(":")[0], ("x", "y")) for a in pool}
got = ar.pick(pool, attrs, 10)
check("отбор: 10 разных наборов, когда их хватает", len({attrs[a][0] for a in got}) == 10)
check("отбор не зависит от порядка пула", sorted(ar.pick(list(reversed(pool)), attrs, 10)) == sorted(got))
few = ["S0:%d" % f for f in range(8)] + ["S1:0"]
got = ar.pick(few, {a: (a.split(":")[0], "T", ("x", "y")) for a in few}, 4, None, set_cap=3)
check("отбор: набор не больше предела, остаток добран", len(got) == 4 and sum(a.startswith("S0") for a in got) == 3)

# ---- заморозка
tmp = tempfile.mkdtemp()
try:
    x = {"asset_id": "SET:1", "class": ar.CLASSES[0], "A": {"proposed_name": "a"}, "B": {"proposed_name": "b"},
         "facts": "- MCD: none", "inputs": {}}
    png = b"\x89PNG fake"
    x["inputs"] = {"sprite": ar.sha256_bytes(png), "facts": ar.sha256_bytes(x["facts"].encode("utf-8"))}
    snap = {"snapshot_id": "arbiter-control-100-test", "items": [x]}
    snap["items_hash"] = ar.h12(snap["items"])
    path = os.path.join(tmp, "arbiter-control-100-test.json")
    ar.save_json(path, snap, readonly=True)
    d = os.path.join(tmp, "arbiter-control-100-test", "inputs")
    os.makedirs(d)
    with open(os.path.join(d, "SET_1_sprite.png"), "wb") as f:
        f.write(png)
    s2, sd = ar.check_snapshot(path)
    check("целый снимок проходит", len(ar.inputs_of(s2["items"][0], sd)) == 1)
    check("снимок только для чтения", not os.access(path, os.W_OK))
    with open(os.path.join(d, "SET_1_sprite.png"), "wb") as f:
        f.write(png + b"!")
    try:
        ar.inputs_of(s2["items"][0], sd)
        check("подменённая картинка останавливает", False)
    except SystemExit:
        check("подменённая картинка останавливает", True)
    snap["items"][0]["B"]["proposed_name"] = "c"
    ar.save_json(path, snap, readonly=True)            # items_hash прежний - состав правлен
    try:
        ar.check_snapshot(path)
        check("правка состава после заморозки останавливает", False)
    except SystemExit:
        check("правка состава после заморозки останавливает", True)
    tr = {"SET:1": {"truth": "NEITHER", "who": "Vitali", "when": "t", "note": "на самом деле\tбочка"},
          "SET:2": {"truth": "A", "who": "Vitali", "when": "t", "note": ""}}
    ar.save_truth(os.path.join(tmp, "arbiter-control-100-test"), tr)
    back = ar.load_truth(os.path.join(tmp, "arbiter-control-100-test"))
    check("truth.tsv: запись и чтение", {k: v["truth"] for k, v in back.items()} == {"SET:1": "NEITHER", "SET:2": "A"}
          and back["SET:1"]["note"] == "на самом деле бочка")
    check("truth_source: Vitali - человек, codex - модель вслепую",
          back["SET:1"]["truth_source"] == "HUMAN_VITALI" and ar.truth_source("codex") == "CODEX_BLIND")
    # файл до 30.09 - без столбца truth_source: источник берётся по who
    with open(os.path.join(tmp, "arbiter-control-100-test", "truth.tsv"), "w", encoding="utf-8-sig") as f:
        f.write("asset_id\ttruth\twho\twhen\tnote\nSET:3\tB\tcodex\tt\t\n")
    back = ar.load_truth(os.path.join(tmp, "arbiter-control-100-test"))
    check("truth.tsv старого вида: источник по who", back["SET:3"]["truth_source"] == "CODEX_BLIND")
    check("версия арбитра зависит от запроса", ar.arb_rev() != ar.h12({"ask": ar.ASK + " ", "model": ar.MODEL,
          "options": ar.OPTIONS, "decisions": ar.DECISIONS, "relations": ar.RELATIONS}))
finally:
    for root, _d, files in os.walk(tmp):
        for fn in files:
            os.chmod(os.path.join(root, fn), 0o644)
    shutil.rmtree(tmp)

# ---- сводка целиком на искусственной сотне из четырёх
tmp = tempfile.mkdtemp()
try:
    items = [{"asset_id": "S:%d" % i, "class": ar.CLASSES[i], "A": {"proposed_name": "a"},
              "B": {"proposed_name": "b"}, "facts": "", "inputs": {}} for i in range(4)]
    snap = {"snapshot_id": "arbiter-control-100-t2", "items": items}
    snap["items_hash"] = ar.h12(items)
    path = os.path.join(tmp, "arbiter-control-100-t2.json")
    ar.save_json(path, snap, readonly=True)
    rd = os.path.join(tmp, "arbiter-control-100-t2", "runs", ar.arb_rev())
    os.makedirs(rd)
    answers = {}
    for aid, (d_, r_) in zip(("S:0", "S:1", "S:2", "S:3"),
                             (("A", "SAME"), ("B", "SAME"), ("CANNOT_TELL", "DIFFERENT"), ("B", "DIFFERENT"))):
        answers[aid] = dict(ans(d_, r_), route=ar.route(ans(d_, r_)))
    ar.save_json(os.path.join(rd, "answers.json"), answers)
    ar.save_truth(os.path.join(tmp, "arbiter-control-100-t2"), {
        "S:0": {"truth": "A", "who": "t", "when": "t"}, "S:1": {"truth": "NEITHER", "who": "t", "when": "t"},
        "S:2": {"truth": "B", "who": "t", "when": "t"}, "S:3": {"truth": "BOTH", "who": "t", "when": "t"}})
    out = ar.report(path)
    k = out["per_class"]["ALL"]
    check("сводка: верно 2, FALSE_CONFIDENT 1, ошибся но отказался 1",
          (k["out_correct"], k["out_false_confident"], k["out_wrong_uncertain"]) == (2, 1, 1))
    check("сводка: точность выбора 2 из 3, доля B у арбитра 2 из 3",
          k["choice_accuracy"] == round(2 / 3, 3) and k["b_preference"] == round(2 / 3, 3))
    check("сводка: FALSE_CONFIDENT 25 процентов - массово не применять",
          out["false_confident_rate"] == 0.25 and out["verdict"] == "массово не применять")
    with open(os.path.join(rd, "report.md"), encoding="utf-8-sig") as f:
        check("сводка: таблица правды в report.md", "доля B в правде" in f.read())
    # S:1 - единственный FALSE_CONFIDENT: связь SAME, класс CLASSES[1] (общие слова, другая категория)
    check("FALSE_CONFIDENT_BY_RELATION: SAME 1, остальные 0",
          out["false_confident_by_relation"] == {"SAME": 1, "BROADER_NARROWER": 0,
                                                 "RELATED_BUT_DIFFERENT": 0, "DIFFERENT": 0})
    check("FALSE_CONFIDENT с общими словами 1, без общих 0",
          (out["false_confident_with_shared_words"], out["false_confident_without_shared_words"]) == (1, 0)
          and ar.CLASSES[1].startswith("shared"))
    with open(os.path.join(rd, "summary.txt"), encoding="utf-8-sig") as f:
        s = f.read()
    check("summary.txt: TOTAL и четыре класса в нужной форме",
          s.startswith("TOTAL\nlabeled: 4/4\ntruth_source: HUMAN_T 4\n\ntruth:\nA 1\nB 1\nBOTH 1\nNEITHER 1\nCANNOT_TELL 0\n")
          and "arbiter:\ncorrect 2\nFALSE_CONFIDENT 1\nwrong_but_declined 1\npicked_while_human_unknown 0\ninvalid 0\n" in s
          and "choice_accuracy 66.7 %\nFALSE_CONFIDENT_total_pct 25.0 %\nFALSE_CONFIDENT_labeled_pct 25.0 %\n"
              "B_pick_rate 66.7 %\nB_truth_rate 50.0 %\n" in s
          and "FALSE_CONFIDENT_BY_CHOICE:\nA 0 of 1 verified picks (0.0 %)\nB 1 of 2 verified picks (50.0 %)\n" in s
          and "FALSE_CONFIDENT_BY_RELATION:\nSAME 1\n" in s
          and "FALSE_CONFIDENT_SHARED_WORDS 1\nFALSE_CONFIDENT_NO_SHARED_WORDS 0" in s
          and all(c.upper() in s for c in ar.CLASSES))
    check("FALSE_CONFIDENT_BY_CHOICE: A 0 из 1, B 1 из 2",
          out["false_confident_by_choice"] == {"A": {"false_confident": 0, "verified_picks": 1, "rate": 0.0},
                                               "B": {"false_confident": 1, "verified_picks": 2, "rate": 0.5}})
    # разметка неполная: S:2 и S:3 не размечены - знаменатели расходятся, FC 1 из 4 всех и 1 из 2 размеченных
    ar.save_truth(os.path.join(tmp, "arbiter-control-100-t2"), {
        "S:0": {"truth": "A", "who": "t", "when": "t"}, "S:1": {"truth": "NEITHER", "who": "t", "when": "t"}})
    out = ar.report(path)
    k = out["per_class"]["ALL"]
    with open(os.path.join(rd, "summary.txt"), encoding="utf-8-sig") as f:
        s = f.read()
    check("два знаменателя: total 25 %, labeled 50 %",
          (k["fc_total_pct"], k["fc_labeled_pct"]) == (0.25, 0.5)
          and s.startswith("TOTAL\nlabeled: 2/4\n") and "FALSE_CONFIDENT_total_pct 25.0 %" in s
          and "FALSE_CONFIDENT_labeled_pct 50.0 %" in s)
finally:
    for root, _d, files in os.walk(tmp):
        for fn in files:
            os.chmod(os.path.join(root, fn), 0o644)
    shutil.rmtree(tmp)

print("\n%s" % ("всё верно" if not FAIL else "ОШИБКИ: %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
