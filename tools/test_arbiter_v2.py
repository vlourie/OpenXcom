#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка арбитра V2 без модели: перевод позиции в кандидата, сведение двух порядков, маршрут, метрики.

    py -3.13 tools/test_arbiter_v2.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
sys.stdout.reconfigure(encoding="utf-8")
import arbiter as ar                                   # noqa: E402
import arbiter_v2 as v2                                # noqa: E402

bad = 0


def check(name, ok):
    global bad
    print(("ok   " if ok else "FAIL ") + name)
    bad += not ok


def vis(order, dec):
    return v2.norm_visual({"decision": dec}, order)


def rel(r):
    return v2.norm_relation({"relation": r})


# ---- перевод позиции и сведение
check("ab FIRST = A, ba FIRST = B", (vis("ab", "FIRST")["pick"], vis("ba", "FIRST")["pick"]) == ("A", "B"))
cases = [
    (("FIRST", "SECOND"), ("STABLE_A", "A", False)),        # ab выбрал A, ba выбрал A
    (("SECOND", "FIRST"), ("STABLE_B", "B", False)),
    (("FIRST", "FIRST"), ("ORDER_UNSTABLE", None, True)),   # оба раза первая позиция - перекос
    (("SECOND", "SECOND"), ("ORDER_UNSTABLE", None, True)),
    (("FIRST", "CANNOT_TELL"), ("PARTIAL", None, False)),
    (("NEITHER", "SECOND"), ("PARTIAL", None, False)),
    (("NEITHER", "NEITHER"), ("NEITHER", None, False)),
    (("NEITHER", "CANNOT_TELL"), ("CANNOT_TELL", None, False)),
    (("CANNOT_TELL", "CANNOT_TELL"), ("CANNOT_TELL", None, False)),
    (("FIRST", "maybe"), ("INVALID", None, False)),
]
for (a, b), want in cases:
    check("сведение ab=%s ba=%s -> %s" % (a, b, want[0]), v2.combine_visual(vis("ab", a), vis("ba", b)) == want)
check("нет ответа в одном порядке - INVALID", v2.combine_visual(vis("ab", "FIRST"), None)[0] == "INVALID")

check("отношение: совпало - REL_STABLE и оно",
      v2.combine_relation(rel("SAME"), rel("SAME")) == ("REL_STABLE", "SAME"))
check("отношение: CANNOT_TELL дважды - устойчивое воздержание",
      v2.combine_relation(rel("CANNOT_TELL"), rel("CANNOT_TELL")) == ("REL_STABLE", "CANNOT_TELL"))
check("отношение: разошлось - REL_ORDER_UNSTABLE, для маршрута CANNOT_TELL",
      v2.combine_relation(rel("SAME"), rel("DIFFERENT")) == ("REL_ORDER_UNSTABLE", "CANNOT_TELL"))
check("отношение: не по форме - REL_INVALID",
      v2.combine_relation(rel("SAME"), rel("ALIKE")) == ("REL_INVALID", "CANNOT_TELL"))

check("маршрут: устойчивый выбор + SAME -> LIGHT", v2.route_v2("STABLE_A", "SAME") == ar.LIGHT)
check("маршрут: устойчивый выбор + BROADER_NARROWER -> LIGHT", v2.route_v2("STABLE_B", "BROADER_NARROWER") == ar.LIGHT)
check("маршрут: устойчивый выбор + RELATED -> HARD", v2.route_v2("STABLE_A", "RELATED_BUT_DIFFERENT") == ar.HARD)
check("маршрут: неустойчивый + SAME -> HARD", v2.route_v2("ORDER_UNSTABLE", "SAME") == ar.HARD)
check("маршрут: PARTIAL + SAME -> HARD", v2.route_v2("PARTIAL", "SAME") == ar.HARD)

x = {"A": {"proposed_name": "cow", "proposed_category": "other", "short_description": "white cow"},
     "B": {"proposed_name": "log pile", "proposed_category": "debris", "short_description": "snowy logs"},
     "facts": "- MCD: object record"}
p_ab, p_ba = v2.visual_prompt(x, "ab"), v2.visual_prompt(x, "ba")
check("запрос ab: FIRST - A", "FIRST guess: cow" in p_ab and "SECOND guess: log pile" in p_ab)
check("запрос ba: FIRST - B", "FIRST guess: log pile" in p_ba and "SECOND guess: cow" in p_ba)
r = v2.relation_prompt(x, "ab")
check("отношение: имя и категория, без описания", "cow (other)" in r and "white cow" not in r)
check("версия V2 не совпадает с V1 и зависит от запроса",
      v2.v2_rev() != ar.arb_rev() and v2.v2_rev().startswith("v2-"))
r0, q0 = v2.reduce_rev(), v2.v2_rev()
keep = v2.combine_visual


def other_combine(ab, ba):
    return "INVALID", None, False


v2.combine_visual = other_combine
r1 = v2.reduce_rev()
v2.combine_visual = keep
check("reduce_rev меняется с кодом сведения, v2_rev - нет", r0 != r1 and v2.reduce_rev() == r0 and v2.v2_rev() == q0)


def kk(**kw):
    from collections import Counter
    k = Counter(n=100, answered=100, truth=100, stale=0, verified_light=30, fc_stable_total_pct=0.02,
                fc_light_verified_pct=0.0)
    for a, b in kw.items():
        k[a] = b
    k["truth_sources"] = kw.get("truth_sources", {"HUMAN_VITALI": 100})
    return k


check("приговор: полный прогон, обе доли малы - хорошо", v2.acceptance(kk())[0] == "хорошо")
check("приговор: недоспрошено - нет", v2.acceptance(kk(answered=90))[0] is None
      and "недоспрошено 10" in v2.acceptance(kk(answered=90))[1])
check("приговор: без полной правды - нет", v2.acceptance(kk(truth=99))[0] is None)
check("приговор: ответы другой версии - нет", v2.acceptance(kk(stale=1))[0] is None)
check("приговор: мало проверяемых LIGHT - нет", v2.acceptance(kk(verified_light=5))[0] is None)
check("приговор: FC_STABLE 1 %, но FC_LIGHT 20 % - массово не применять",
      v2.acceptance(kk(fc_stable_total_pct=0.01, fc_light_verified_pct=0.2))[0] == "массово не применять")
check("приговор по правде модели помечен как согласие моделей",
      "согласие моделей" in v2.acceptance(kk(truth_sources={"CODEX_BLIND": 100}))[1])
check("верхняя граница: 0 из 20 - около 12 %", 0.11 < v2.upper95(0, 20) < 0.13)

# ---- сводка на искусственной сотне из четырёх
tmp = tempfile.mkdtemp()
try:
    items = [{"asset_id": "S:%d" % i, "class": ar.CLASSES[i], "A": {"proposed_name": "a"},
              "B": {"proposed_name": "b"}, "facts": "", "inputs": {}} for i in range(4)]
    snap = {"snapshot_id": "arbiter-control-100-t9", "items": items}
    snap["items_hash"] = ar.h12(items)
    path = os.path.join(tmp, "arbiter-control-100-t9.json")
    ar.save_json(path, snap, readonly=True)
    d = os.path.join(tmp, "arbiter-control-100-t9")
    rd = os.path.join(d, "runs", v2.v2_rev())
    os.makedirs(rd)
    plan = {  # ab, ba, отношение
        "S:0": ("FIRST", "SECOND", "SAME"),          # STABLE_A, LIGHT; правда B -> FC_STABLE и FC_LIGHT
        "S:1": ("FIRST", "FIRST", "SAME"),           # ORDER_UNSTABLE, перекос; правда B - не FC
        "S:2": ("SECOND", "FIRST", "DIFFERENT"),     # STABLE_B, HARD; правда B - верно
        "S:3": ("CANNOT_TELL", "FIRST", "SAME"),     # PARTIAL; правда A - не FC
    }
    answers = {}
    for aid, (a, b, rr) in plan.items():
        answers[aid] = {"visual": {"ab": vis("ab", a), "ba": vis("ba", b)}, "rel": {"ab": rel(rr), "ba": rel(rr)},
                        "v2_rev": v2.v2_rev(), "inputs": {}}
    ar.save_json(os.path.join(rd, "answers.json"), answers)
    ar.save_truth(d, {"S:0": {"truth": "B", "who": "codex", "when": "t"},
                      "S:1": {"truth": "B", "who": "codex", "when": "t"},
                      "S:2": {"truth": "B", "who": "codex", "when": "t"},
                      "S:3": {"truth": "A", "who": "codex", "when": "t"}})
    v1d = os.path.join(d, "runs", v2.V1_REV)
    os.makedirs(v1d)
    ar.save_json(os.path.join(v1d, "answers.json"), {   # V1: S:0, S:1 и S:3 уверенно неверны
        "S:0": {"decision": "A", "relation": "SAME", "valid": True},
        "S:1": {"decision": "A", "relation": "SAME", "valid": True},
        "S:2": {"decision": "B", "relation": "DIFFERENT", "valid": True},
        "S:3": {"decision": "B", "relation": "SAME", "valid": True}})
    out = v2.report(path)
    k = out["per_class"]["ALL"]
    check("состояния: STABLE_A 1, STABLE_B 1, ORDER_UNSTABLE 1, PARTIAL 1",
          (k["state_STABLE_A"], k["state_STABLE_B"], k["state_ORDER_UNSTABLE"], k["state_PARTIAL"]) == (1, 1, 1, 1))
    check("ORDER_UNSTABLE_RATE 50 %, ORDER_BIAS_RATE 25 %",
          (k["order_unstable_rate"], k["order_bias_rate"]) == (0.5, 0.25))
    check("FALSE_CONFIDENT_STABLE 1 из 4 (25 %), в LIGHT 1 из 1",
          (k["fc_stable"], k["fc_stable_total_pct"], k["fc_light"], k[ar.LIGHT]) == (1, 0.25, 1, 1))
    check("сравнение с V1: было FC 3, осталось 1 (S:0), ушло в HARD 2 (S:1, S:3), новых 0",
          (k["v1_fc"], k["v1_fc_now_fc"], k["v1_fc_now_hard"], k["new_fc"]) == (3, 1, 2, 0))
    with open(os.path.join(rd, "summary.txt"), encoding="utf-8-sig") as f:
        s = f.read()
    check("summary.txt: источник правды и главные строки",
          s.startswith("TOTAL\nanswered: 4/4\nlabeled: 4/4\ntruth_source: CODEX_BLIND 4\n")
          and "ORDER_UNSTABLE_RATE 50.0 %\n" in s and "FALSE_CONFIDENT_STABLE_total_pct 25.0 %\n" in s
          and "FALSE_CONFIDENT_LIGHT 1 of 1 verified LIGHT (100.0 %" in s and "RELATION_STABLE_RATE 100.0 %" in s
          and "verdict: -\nverdict_note: нет приговора: проверяемых LIGHT 1 < 20" in s
          and all(c.upper() in s for c in ar.CLASSES))
    # недоспрошенный ассет (есть ab, нет ba) в сводку не идёт
    answers["S:3"]["visual"].pop("ba")
    ar.save_json(os.path.join(rd, "answers.json"), answers)
    k = v2.report(path)["per_class"]["ALL"]
    check("недоспрошенный ассет не считается", (k["answered"], k["no_answer"]) == (3, 1))
    check("неполный прогон - приговора нет", k["verdict"] is None and "недоспрошено 1" in k["verdict_note"])
    answers["S:3"]["visual"]["ba"] = vis("ba", "FIRST")
    answers["S:2"]["inputs"] = {"sprite": "x"}
    ar.save_json(os.path.join(rd, "answers.json"), answers)
    ar.save_truth(d, {"S:0": {"truth": "CANNOT_TELL", "who": "codex", "when": "t"},
                      "S:1": {"truth": "B", "who": "codex", "when": "t"},
                      "S:2": {"truth": "B", "who": "codex", "when": "t"},
                      "S:3": {"truth": "A", "who": "codex", "when": "t"}})
    k = v2.report(path)["per_class"]["ALL"]
    check("входы изменились - ответ устаревший, приговора нет",
          k["stale"] == 1 and "другой версии или других входов 1" in k["verdict_note"])
    check("устойчивый LIGHT при правде CANNOT_TELL посчитан отдельно и не в verified",
          (k["stable_truth_ct"], k["stable_light_truth_ct"], k["verified_light"], k["fc_light"]) == (1, 1, 0, 0))
finally:
    for root, _d, files in os.walk(tmp):
        for fn in files:
            os.chmod(os.path.join(root, fn), 0o644)
    shutil.rmtree(tmp)

print("\nвсё верно" if not bad else "\nОШИБОК: %d" % bad)
sys.exit(1 if bad else 0)
