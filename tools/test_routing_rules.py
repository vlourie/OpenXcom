#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""routing_rules: порядок правил, одиночный - последний запасной, ворота, заморозка входов.

    py -3.13 tools/test_routing_rules.py
Синтетика, без карт.
"""
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import routing_rules as rr          # noqa: E402

ENC = "utf-8-sig"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC) as f:
        f.write(text)


def tsv(path, head, rows):
    write(path, "\n".join(["\t".join(head)] + ["\t".join(x) for x in rows]) + "\n")


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def main():
    fails = []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    # кадр: (ось A, строка generation kind / relation / blockers, эталон B)
    case = {
        "R:1": ("TERRAIN_RELIEF", ("составной", "", ""), "EXCLUDE"),           # рельеф важнее составного
        "W:1": ("NOT_OBJECT", ("один", "", ""), "EXCLUDE"),
        "S:1": ("OBJECT", ("один", "", ""), "STATE_VARIANT"),                  # в state_variants
        "D:1": ("OBJECT", ("один", "recolor", ""), "DERIVED"),
        "Q:1": ("OBJECT_PART", ("составной", "", ""), "COMPOSITE_PART"),
        "M:1": ("OBJECT", ("один", "", ""), "STRUCTURAL_MODULAR"),            # в modular_objects
        "O:1": ("OBJECT_PART", ("один", "", "part_fragment_suspect identity"), "COMPOSITE_PART"),
        "F:1": ("OBJECT", ("один", "", "identity"), "STANDALONE_RENDER"),
        "X:1": ("OBJECT", ("один", "", "identity"), "DERIVED"),                # родства в данных нет - опасно
        "U:1": ("UNSURE", ("один", "", ""), "open"),
    }
    with tempfile.TemporaryDirectory() as t:
        inp = {k: os.path.join(t, "in", os.path.basename(v)) for k, v in rr.INPUTS.items()}
        inp["semantic"], inp["reference"] = os.path.join(t, "v3", "answers_vitali.tsv"), os.path.join(t, "v3", "ref.tsv")
        inp["spec_v3"] = os.path.join(t, "v3", "spec.json")
        body = {"spec": {}, "semantic": [], "routing": [], "holdout_sha256": "h", "assets": list(case)}
        write(inp["spec_v3"], json.dumps(dict(body, sha256=rr.ir.sha(body), created="x")))
        tsv(inp["semantic"], ["asset_id", "final_identity", "semantic_kind", "render_unit", "missing_context", "note"],
            [[a, "x", c[0], "STANDALONE_RENDER", "", ""] for a, c in case.items()])
        tsv(inp["reference"], ["asset_id", "ref_semantic_kind", "ref_render_unit"], [[a, "OBJECT", c[2]] for a, c in case.items()])
        tsv(inp["generation"], ["key", "kind", "asset_id", "relation", "blockers"],
            [[a, c[1][0], a, c[1][1], c[1][2]] for a, c in case.items()])
        write(inp["families"], "[]")
        write(inp["state_variants"], json.dumps([{"asset_id": "S:1"}]))
        write(inp["modular_objects"], json.dumps([{"parts": [{"asset_id": "M:1"}], "composites": []}]))
        tsv(inp["class_decisions"], ["asset_id", "asset_class"], [["Z:9", "part_fragment"]])
        out = os.path.join(t, "out")
        quiet(rr.freeze, out, inp)
        try:
            quiet(rr.freeze, out, inp)
            check("повторная заморозка правил - отказ", False)
        except SystemExit:
            check("повторная заморозка правил - отказ", True)
        res = quiet(rr.run, out)
        by = {r["asset_id"]: (r["rule_unit"], r["rule"]) for r in res["rows"]}
        check("порядок правил: рельеф, стена, состояние, перекраска, составной, модуль",
              [by[a] for a in ("R:1", "W:1", "S:1", "D:1", "Q:1", "M:1")] ==
              [("EXCLUDE", "R1"), ("EXCLUDE", "R2"), ("STATE_VARIANT", "R3"), ("DERIVED", "R4"),
               ("COMPOSITE_PART", "R5"), ("STRUCTURAL_MODULAR", "R6")])
        check("открытый вопрос о куске - REVIEW, а не одиночный", by["O:1"] == ("REVIEW", "R7"))
        check("одиночный - только последним (R8), UNSURE - REVIEW (R9)",
              by["F:1"] == ("STANDALONE_RENDER", "R8") and by["U:1"] == ("REVIEW", "R9"))
        tt = res["total"]
        check("родства нет в данных - опасный одиночный 1, ворота FAIL",
              tt["dangerous_false_standalone"] == 1 and res["passed"] is False)
        check("точность 7/8 по решённым, охват 8/9", tt["correct"] == 7 and tt["decided"] == 8 and tt["ref_closed"] == 9)
        check("чувствительность: без R7 кусок уходит одиночным - опасных 2",
              res["sensitivity"]["R7 выключен (открытый вопрос не мешает одиночному)"]["dangerous_false_standalone"] == 2)
        # V4_R1: те же правила плюс родство и OBJECT_PART -> REVIEW, своя папка
        rels = {"X:1": [{"kind": "RECOLOR_OF", "level": "STRONG", "relative": "B:1", "side": "derived",
                         "verified": False}],
                "F:1": [{"kind": "RECOLOR_OF", "level": "STRONG", "relative": "B:2", "side": "base",
                         "verified": False}],
                "D:1": [{"kind": "FIXED_NEIGHBOUR", "level": "CANDIDATE", "relative": "N:1", "side": "part?",
                         "verified": False}]}
        inp["relations"] = os.path.join(t, "in", "relations.json")
        write(inp["relations"], json.dumps({"relations": rels}))
        out1 = os.path.join(t, "out_r1")
        quiet(rr.freeze, out1, inp, "V4_R1")
        res1 = quiet(rr.run, out1)
        by1 = {r["asset_id"]: (r["rule_unit"], r["rule"]) for r in res1["rows"]}
        check("V4_R1: кандидат родства производной стороны - REVIEW (R7r), а не одиночный",
              by1["X:1"] == ("REVIEW", "R7r") and res1["total"]["dangerous_false_standalone"] == 0)
        check("V4_R1: основа перекраски остаётся одиночной; известное родство (R4) важнее кандидата",
              by1["F:1"] == ("STANDALONE_RENDER", "R8") and by1["D:1"] == ("DERIVED", "R4"))
        rels["X:1"][0]["verified"] = True
        rels["Q2:1"] = []
        write(inp["relations"], json.dumps({"relations": rels}))
        meta = rr.metadata(inp)
        check("V4_R1: подтверждённая перекраска - DERIVED (R0v)", rr.route("X:1", "OBJECT", meta)[:2] == ("DERIVED", "R0v"))
        check("V4_R1: OBJECT_PART без родства и подтверждённой одиночности - REVIEW (R8a)",
              rr.route("Q2:1", "OBJECT_PART", meta)[:2] == ("REVIEW", "R8a"))
        meta4 = rr.metadata({k: v for k, v in inp.items() if k != "relations"})
        check("V4 без relations: OBJECT_PART по-прежнему одиночный (R8)",
              rr.route("Q2:1", "OBJECT_PART", meta4)[:2] == ("STANDALONE_RENDER", "R8"))
        tsv(inp["generation"], ["key", "kind", "asset_id", "relation", "blockers"], [])
        try:
            quiet(rr.run, out)
            check("входы изменились после заморозки - отказ", False)
        except SystemExit:
            check("входы изменились после заморозки - отказ", True)
    print("итог:", "все проверки прошли" if not fails else "провалено %d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
