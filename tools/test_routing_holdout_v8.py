#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/routing_holdout_v8.py на синтетике, у каждой проверки - контроль:
зерно V8 подставлено в отбор V7; заморозка - тело целиком, порча входа и снимка ловится, повторная заморозка запрещена;
ворота - семь, handoff_unassigned и semantic в вердикте, вердикт маршрута отдельно; инвариант графа в подсчёте - одна
пара одно утверждение (контроль: сырой подсчёт даёт два закрытых); эталон V8 - набор групп, canonical исключает
остальное, пара с ребром MCD не NONE (контроль: без ребра NONE законно); fact_only в holdout нет (контроль: подсчёт
V8 до заморозки ставит fact_only); пакет судьи - без панелей семейства и похожих, без строк семейства, с MCD в обе
стороны; диагностика MCD, R-171 и групп рисования.

    py -3.13 tools/test_routing_holdout_v8.py
"""
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import routing_holdout as rh       # noqa: E402
import routing_holdout_v7 as h7    # noqa: E402
import routing_holdout_v8 as h8    # noqa: E402
import routing_model_v8 as v8      # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def rec(frames, die=0, alt=0, ufo=0, door=0):
    fr = list(frames) * (8 // len(frames)) if len(frames) < 8 else list(frames)
    return {"n": 0, "frames": fr[:8], "ufo": ufo, "door": door, "die": die, "alt": alt, "type": 3}


def mcd(*recs):
    return v8.Mcd(recs={"S": [dict(r, n=i) for i, r in enumerate(recs)]})


def claim(a, b, level="STRONG", status="ok", kind="STATE_VARIANT_OF", source="mcd_die"):
    return {"asset_id": a, "relative": b, "level": level, "status": status, "kind": kind, "source": source}


def row(a="S:1", pipe="OBJECT_PIPELINE", edges=(), status="judged", groups=(), gid="", anchor=""):
    return {"asset_id": a, "pipeline_target": pipe, "edges": list(edges), "ref_role_status": status,
            "ref_role_groups": sorted(groups), "render_group_id": gid, "render_anchor": anchor,
            "handoff_unassigned": pipe not in h8.PIPELINES_OK}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    # -- зерно
    check("отбор V7 берёт зерно V8", h7.SEED == h8.SEED and
          h8.order("x") == hashlib.sha256((h8.SEED + "|x").encode()).hexdigest())
    check("контроль: зерно V8 не зерно V7", "v8" in h8.SEED and "v7" not in h8.SEED)

    # -- ворота
    g = h8.GATES
    check("ворота: семь порогов", all(k in g for k in (
        "dangerous_creative_standalone_max", "pipeline_logic_accuracy_min", "pipeline_logic_coverage_min",
        "strong_relation_precision_min", "strong_closed_min", "semantic_axis_accuracy_min", "handoff_unassigned_max")))
    check("ворота: значения специалиста", (g["pipeline_logic_accuracy_min"], g["pipeline_logic_coverage_min"],
                                          g["strong_relation_precision_min"], g["strong_closed_min"],
                                          g["semantic_axis_accuracy_min"], g["handoff_unassigned_max"],
                                          g["dangerous_creative_standalone_max"]) == (0.95, 0.7, 0.95, 10, 0.85, 0, 0))
    good = {"dangerous_creative_standalone": 0, "pipeline_accuracy": 1.0, "pipeline_coverage": 0.9,
            "semantic_axis_accuracy": 0.9}
    ps = {"strong": {"closed": 12, "relation_precision": 1.0}}
    rows_ok = [row()]
    c = h8.gate_checks(good, good, ps, rows_ok, g)
    check("ворота: всё прошло - PASS, ключей 7", h8.v8.verdict(c) == "PASS" and len(c) == 7)
    c = h8.gate_checks(good, good, ps, [row(pipe="")], g)
    check("handoff_unassigned: пустой конвейер - FAIL", h8.v8.verdict(c) == "FAIL" and h8.routing_verdict(c) == "PASS")
    check("контроль: REVIEW - назначение, не handoff_unassigned",
          h8.v8.verdict(h8.gate_checks(good, good, ps, [row(pipe="REVIEW")], g)) == "PASS")
    c = h8.gate_checks(dict(good, semantic_axis_accuracy=0.84), good, ps, rows_ok, g)
    check("semantic 0.84 - FAIL всего, маршрут PASS", h8.v8.verdict(c) == "FAIL" and h8.routing_verdict(c) == "PASS")
    check("semantic ровно 0.85 - прошло",
          h8.v8.verdict(h8.gate_checks(dict(good, semantic_axis_accuracy=0.85), good, ps, rows_ok, g)) == "PASS")
    c = h8.gate_checks(good, good, {"strong": {"closed": 9, "relation_precision": 1.0}}, rows_ok, g)
    check("STRONG 9 закрытых - мало данных", h8.v8.verdict(c) == "INSUFFICIENT_SAMPLE")

    # -- инвариант графа в подсчёте
    cl = [claim("S:1", "S:2", status="ok", source="mcd_die"), claim("S:1", "S:2", status="wrong", source="fr2")]
    u = h8.independent(cl)
    check("одна пара - одно утверждение, неверное перевешивает", len(u) == 1 and u[0]["status"] == "wrong" and
          u[0]["claims"] == 2)
    check("контроль: сырой подсчёт - два закрытых", v8.precision(cl)["closed"] == 2)
    u = h8.independent([claim("S:1", "S:2", level="CANDIDATE", status="open"), claim("S:2", "S:1", status="ok")])
    check("пара в обе стороны - одна, уровень старший, закрытое верно",
          len(u) == 1 and u[0]["level"] == "STRONG" and u[0]["status"] == "ok")
    ps2 = h8.precision_split([claim("A:1", "A:2"), claim("A:1", "A:2", source="x"), claim("B:1", "B:2", status="wrong")])
    check("precision_split по парам: 2 закрытых, 1 верно", ps2["strong"]["closed"] == 2 and ps2["strong"]["ok"] == 1
          and ps2["raw_claims"] == 3 and ps2["independent_pairs"] == 2)

    # -- эталон
    ref = {"S:1": {"ref_semantic_kind": "OBJECT", "ref_roles": "state|derived"},
           "S:3": {"ref_semantic_kind": "open", "ref_roles": "open"}}
    pair = {"asset_id": "S:1", "relative": "S:2", "ref_pair_relation": "STATE_VARIANT_OF", "direction": "asset_derived"}
    check("эталон: набор групп и open годятся", not h8.check_reference(ref, [pair], ["S:1", "S:3"]))
    check("canonical исключает остальное", h8.check_reference({"S:1": {"ref_semantic_kind": "OBJECT",
                                                                       "ref_roles": "canonical|state"}}, [], ["S:1"]))
    check("неизвестная группа - ошибка", h8.check_reference({"S:1": {"ref_semantic_kind": "OBJECT",
                                                                     "ref_roles": "standalone"}}, [], ["S:1"]))
    check("UNSURE в эталоне - ошибка", h8.check_reference({"S:1": {"ref_semantic_kind": "UNSURE",
                                                                   "ref_roles": "open"}}, [], ["S:1"]))
    none = dict(pair, ref_pair_relation="NONE", direction="none")
    check("ребро MCD - NONE нельзя", h8.check_reference(ref, [none], ["S:1", "S:3"], {("S:1", "S:2")}))
    check("контроль: без ребра MCD NONE законно", not h8.check_reference(ref, [none], ["S:1", "S:3"], set()))
    check("ребро MCD - OPEN можно", not h8.check_reference(ref, [dict(pair, ref_pair_relation="OPEN",
                                                                          direction="open")],
                                                           ["S:1", "S:3"], {("S:1", "S:2")}))
    check("пустая пара - ошибка", h8.check_reference(ref, [dict(pair, ref_pair_relation="")], ["S:1", "S:3"]))
    check("ref_axes: набор групп", h8.ref_axes(ref["S:1"]) == ("OBJECT_PIPELINE", {"state", "derived"}, "judged"))
    check("ref_axes: open без uninformed", h8.ref_axes(ref["S:3"]) == ("open", None, "open"))
    check("ref_axes: поверхность", h8.ref_axes({"ref_semantic_kind": "STRUCTURAL_SURFACE", "ref_roles": "modular"})[0]
          == "STRUCTURAL_PIPELINE")

    # -- утверждения: fact_only нет, дверь D1
    m = mcd(rec([0]), rec([1], die=2), rec([2]))
    fsets = {"S:2": v8.facts(m, "S:2")}
    raw = [("S:2", "S:1", "STATE_VARIANT_OF", "STRONG", "derived", "mcd_die")]
    refp = [{"asset_id": "S:2", "relative": "S:1", "ref_pair_relation": "STATE_VARIANT_OF", "direction": "asset_derived"}]
    out = h8.claims_holdout(raw, fsets, refp)
    check("входящее ребро судится, а не fact_only", out[0]["status"] == "ok")
    check("контроль: подсчёт V8 до заморозки ставит fact_only", v8.claims_v8(raw, fsets, refp)[0]["status"] == "fact_only")
    md = mcd(rec([0]), rec([1, 2, 3, 4, 5, 6, 7, 9], ufo=1), rec([9]))
    fd = {"S:9": v8.facts(md, "S:9")}
    out = h8.claims_holdout([("S:9", "S:1", "ANIMATION_FRAME_OF", "STRONG", "derived", "mcd_anim")], fd,
                            [{"asset_id": "S:9", "relative": "S:1", "ref_pair_relation": "STATE_VARIANT_OF",
                              "direction": "asset_derived"}])
    check("D1: петля двери НЛО, Frame[7] - состояние", out[0]["kind"] == "STATE_VARIANT_OF" and out[0]["status"] == "ok")
    out = h8.claims_holdout([("S:9", "S:1", "ANIMATION_FRAME_OF", "STRONG", "derived", "mcd_anim")], fd,
                            [{"asset_id": "S:9", "relative": "S:1", "ref_pair_relation": "STATE_VARIANT_OF",
                              "direction": "asset_derived"}], door=False)
    check("контроль: без D1 - анимация, неверно", out[0]["status"] == "wrong")

    # -- диагностика MCD
    e = lambda rule, t: {"rule": rule, "target": t, "relation_type": "X"}        # noqa: E731
    rows = [row("S:1", edges=[e("R3a", "S:2"), e("R3m", "S:3"), e("D1", "S:4"), e("R5", "S:5")])]
    pb = {"S:1": [{"relative": "S:2", "ref_pair_relation": "ANIMATION_FRAME_OF"},
                  {"relative": "S:3", "ref_pair_relation": "ANIMATION_FRAME_OF"}]}
    mo = h8.mcd_outcomes(rows, pb)
    check("MCD: анимация верна, разрушение неверно, дверь без пары не решена, R5 не считается",
          mo["animation"] == {"triggered": 1, "correct": 1, "wrong": 0, "unresolved": 0} and
          mo["die"]["wrong"] == 1 and mo["door_state"]["unresolved"] == 1)

    # -- R-171
    fz = {"S:2": v8.facts(m, "S:2"), "S:1": v8.facts(m, "S:1")}
    r = h8.r171([row("S:2"), row("S:1")], fz, {"S:2": [{"relative": "S:1", "ref_pair_relation": "STATE_VARIANT_OF"}]})
    check("R-171: кадр только со входящим ребром, пара закрыта", r["incoming_only_frames"] == 1 and
          r["incoming_only_pairs_closed"] == 1 and r["frames_with_incoming"] == 1)
    check("контроль: исходящее ребро (S:1) не считается", "S:1:" not in " ".join(r["assets"]))

    # -- группы рисования
    rs = [row("A:1", gid="rg:A:1+B:1", anchor="A:1"), row("B:1", gid="rg:A:1+B:1", anchor="A:1"),
          row("C:1", gid="rg:C:1+D:1", anchor="C:1")]
    check("группы: 2, якорь из оригинала 1, по ключу 1",
          h8.render_stats(rs, {"A"}) == {"groups": 2, "anchor_from_origin": 1, "anchor_by_key": 1})

    # -- пакет судьи
    card = {"n": 1, "asset": "S:2", "panels": [["1. кадр", "01_sprite.png"], ["6. семейство", "01_family.png"],
                                               ["8. похожие, sim", "01_similar.png"], ["5. MCD", "01_states.png"]],
            "facts": "- tileset S\n- same object in other tilesets/colours: X:1\n- possible other sides of it: X:2",
            "notes": ["место 1", "6. семейство и «другой бок» - нет"]}
    check("контроль: строки семейства узнаются", bool(rh.FAMILY_LINE.match("- same object in other tilesets/colours: X")))
    pe = h8.pack_entry(card, m, ["S:1", "Q:7"])
    check("пакет: без семейства и похожих", [f for _t, f in pe["panels"]] == ["01_sprite.png", "01_states.png"])
    check("пакет: факты и заметки без семейства", pe["facts"] == "- tileset S" and pe["notes"] == ["место 1"])
    check("пакет: MCD в обе стороны", any("входящие" in x for x in pe["mcd"]) and
          any("S:1" in x for x in pe["mcd"]) and pe["mcd_edge_with"].keys() == {"S:1"})
    check("пакет: без уверенности и правил", not any(k in json.dumps(pe, ensure_ascii=False)
                                                     for k in ("STRONG", "CANDIDATE", "rg:", "R3m", "sim")))

    # -- заморозка
    with tempfile.TemporaryDirectory() as t:
        inp, code = os.path.join(t, "in.tsv"), os.path.join(t, "code.py")
        for f, s in ((inp, "a\tb\n"), (code, "x = 1\n")):
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(s)
        out = os.path.join(t, "out")
        d = h8.freeze(out, {"x": inp}, [code])
        check("заморозка: тело целиком", set(h8.BODY) <= set(d) and d["gates"] == h8.GATES)
        check("заморозка: инвариант графа и досье R-171", "одно хранимое ребро" in d["invariants"]["graph"] and
              "входящие" in json.dumps(d["dossier"], ensure_ascii=False))
        check("заморозка: D1 PROVISIONAL, L1 INACTIVE", d["model"]["D1"] == "PROVISIONAL" and d["model"]["L1"] == "INACTIVE")
        check("снимок читается", h8.load_freeze(out)["sha256"] == d["sha256"])
        try:
            h8.freeze(out, {"x": inp}, [code])
            check("повторная заморозка запрещена", False)
        except SystemExit:
            check("повторная заморозка запрещена", True)
        with open(code, "a", encoding="utf-8") as fh:
            fh.write("y = 2\n")
        check("правка кода видна", h8.code_changed(d) == [code])
        snap = d["inputs"]["x"]
        with open(snap, "a", encoding="utf-8") as fh:
            fh.write("c\td\n")
        try:
            h8.load_freeze(out)
            check("порча входа ловится", False)
        except SystemExit:
            check("порча входа ловится", True)
        fz_ = os.path.join(out, "FREEZE.json")
        dd = json.load(open(fz_, encoding="utf-8-sig"))
        dd["gates"]["semantic_axis_accuracy_min"] = 0.5
        with open(fz_, "w", encoding="utf-8") as fh:
            json.dump(dd, fh)
        try:
            h8.load_freeze(out)
            check("правка ворот в снимке ловится", False)
        except SystemExit:
            check("правка ворот в снимке ловится", True)

    print("\nпроверок не прошло: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
