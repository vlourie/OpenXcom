#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""identity_routing: заморозка определений до ответов, те же картинки, оси отдельно, 8 расхождений V2.

    py -3.13 tools/test_identity_routing.py
Синтетика во временной папке, без карт.
"""
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import identity_routing as r          # noqa: E402

ENC = "utf-8-sig"


def write(path, text, enc=ENC):
    with open(path, "w", encoding=enc) as f:
        f.write(text)


def quiet(fn, *a):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a)


def tsv(path, head, rows):
    write(path, "\n".join(["\t".join(head)] + ["\t".join(x) for x in rows]) + "\n")


def setup_src(src, assets):
    os.makedirs(os.path.join(src, "img"))
    write(os.path.join(src, "holdout.json"), json.dumps({"sha256": "h", "items": [
        {"asset_id": a, "layer": "agree" if i % 2 else "fragment"} for i, a in enumerate(assets)]}))
    data = [{"n": i + 1, "asset": a, "panels": [["1. кадр", "%02d.png" % i]], "prompt": "old", "answers": ["m1", "m2"],
             "verdict": "agree", "status": "AGENT_PROPOSED", "facts": "f", "notes": []} for i, a in enumerate(assets)]
    for i in range(len(assets)):
        with open(os.path.join(src, "img", "%02d.png" % i), "wb") as f:
            f.write(bytes([i]) * 10)
    write(os.path.join(src, "index.html"), "<script>const DATA = %s, MISS = %s, CERT = [];</script>" % (
        json.dumps(data), json.dumps(["larger map crop"])), enc="utf-8")


def main():
    fails = []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    assets = ["A:%d" % i for i in range(8)]
    with tempfile.TemporaryDirectory() as t:
        src, out = os.path.join(t, "src"), os.path.join(t, "out")
        setup_src(src, assets)
        s = quiet(r.freeze_spec, out, src)
        try:
            quiet(r.freeze_spec, out, src)
            check("повторная заморозка определений - отказ", False)
        except SystemExit:
            check("повторная заморозка определений - отказ", True)
        quiet(r.make_cards, out, src)
        # перезаморозка до ответов: прежний spec в архив, новый ссылается на него; страница перестраивается
        s2 = quiet(r.freeze_spec, out, src, "правка определений до ответов")
        check("перезаморозка до ответов: архив spec.v1.json и ссылка replaces",
              os.path.exists(os.path.join(out, "spec.v1.json")) and s2["replaces"] == s["sha256"]
              and s2["refreeze_reason"] == "правка определений до ответов")
        quiet(r.make_cards, out, src)
        c = json.load(open(os.path.join(out, "cards.json"), encoding=ENC))
        check("страница перестроена по новому spec, картинки не тронуты",
              c["spec_sha256"] == s2["sha256"] and c["images_identical_to_v2"] is True)
        bad_img = os.path.join(out, "img", "00.png")
        keep = open(bad_img, "rb").read()
        with open(bad_img, "wb") as f:
            f.write(b"x")
        try:
            quiet(r.make_cards, out, src)
            check("испорченные картинки - страница не перестраивается", False)
        except SystemExit:
            check("испорченные картинки - страница не перестраивается", True)
        with open(bad_img, "wb") as f:
            f.write(keep)
        page = open(os.path.join(out, "index.html"), encoding="utf-8").read()
        check("картинки побайтно те же, что в V2", c["images_identical_to_v2"] is True)
        check("гипотезы подписаны: UNVERIFIED OLD DESCRIPTION, MODEL HYPOTHESIS",
              "UNVERIFIED OLD DESCRIPTION" in page and "MODEL HYPOTHESIS" in page and "semantic_kind" in page)

        # V2: A:0 и A:1 - расхождения класса (человек сказал кусок, эталон V1 - предмет)
        tsv(os.path.join(src, "answers_vitali.tsv"), ["asset_id", "final_identity", "status"],
            [["A:0", "x", "PART_FRAGMENT_CONFIRMED"], ["A:1", "x", "PART_FRAGMENT_CONFIRMED"]] +
            [[a, "x", "IDENTITY_VISUALLY_VERIFIED"] for a in assets[2:]])
        tsv(os.path.join(src, "reference.tsv"), ["asset_id", "ref_status"],
            [[a, "IDENTITY_VISUALLY_VERIFIED"] for a in assets])
        ref = [["A:0", "OBJECT_PART", "COMPOSITE_PART", "quarter dome", "open", "", "composite_relation", "e"],
               ["A:1", "OBJECT_PART", "STANDALONE_RENDER", "gear strut", "closed", "", "MCD", "e"],
               ["A:2", "OBJECT", "STANDALONE_RENDER", "chair", "closed", "", "MCD", "e"],
               ["A:3", "TERRAIN_RELIEF", "EXCLUDE", "rock", "closed", "", "MCD", "e"],
               ["A:4", "open", "open", "?", "open", "", "unresolved", "e"],
               ["A:5", "OBJECT_PART", "COMPOSITE_PART", "hull", "closed", "", "MCD", "e"],
               ["A:6", "OBJECT", "STANDALONE_RENDER", "table", "closed", "", "MCD", "e"],
               ["A:7", "OBJECT", "STATE_VARIANT", "broken table", "closed", "", "state_variant_pair", "e"]]
        tsv(os.path.join(out, "reference_v2.tsv"), r.REF_HEAD, ref)
        ans = [["A:0", "dome", "OBJECT_PART", "COMPOSITE_PART", "", ""],
               ["A:1", "strut", "OBJECT_PART", "STANDALONE_RENDER", "", ""],
               ["A:2", "chair", "OBJECT", "STANDALONE_RENDER", "", ""],
               ["A:3", "rock", "OBJECT", "STANDALONE_RENDER", "", ""],            # опасно: рельеф одиночным заказом
               ["A:4", "?", "UNSURE", "REVIEW", "larger map crop", ""],
               ["A:5", "hull", "OBJECT_PART", "COMPOSITE_PART", "", ""],
               ["A:6", "table", "OBJECT", "COMPOSITE_PART", "", ""],          # сверхосторожно: свой заказ в составной
               ["A:7", "table", "OBJECT", "STANDALONE_RENDER", "", ""]]       # опасно: состояние одиночным заказом
        tsv(os.path.join(out, "answers_vitali.tsv"), r.ANS_HEAD, ans)
        try:
            quiet(r.freeze_spec, out, src)
            check("определения после ответов не замораживаются", False)
        except SystemExit:
            check("определения после ответов не замораживаются", True)
        res = quiet(r.report, out, src)
        t_ = res["total"]
        check("оси отдельно: смысл 6/7, маршрут 4/7 (open и UNSURE/REVIEW вне знаменателя)",
              t_["semantic_kind_accuracy"] == round(6 / 7, 3) and t_["semantic_kind_n"] == 7
              and t_["render_unit_accuracy"] == round(4 / 7, 3) and t_["render_unit_n"] == 7)
        check("опасный одиночный: EXCLUDE и STATE_VARIANT ушли STANDALONE_RENDER - 2",
              t_["dangerous_false_standalone"] == 2)
        check("сверхосторожный: эталон STANDALONE, ответ COMPOSITE_PART - 1", t_["overconservative_routing"] == 1)
        m = res["v2_mismatches"]
        check("расхождения V2 (2) - обе перестали быть ошибкой маршрута", m["n"] == 2 and m["routing_error_gone"] == 2
              and m["routing_error_left"] == 0 and m["routing_unresolved"] == 0 and m["both_agree"] == 2)
        check("unsure, review и нехватка контекста 1/8", t_["unsure_rate"] == 0.125
              and t_["review_rate"] == 0.125 and t_["missing_context_rate"] == 0.125)
        check("четыре числа: 2 из 2 расхождений сняты, опасных 2, сверхосторожных 1, не оценено 1 (REVIEW 1, open 1)",
              res["four"] == {"v2_mismatches_resolved": 2, "v2_mismatches": 2, "dangerous_false_standalone": 2,
                              "overconservative_routing": 1, "routing_unresolved": 1, "routing_review": 1,
                              "routing_ref_open": 1})
        md = open(os.path.join(out, "report.md"), encoding=ENC).read()
        check("четыре числа - первыми, до матрицы; OBJECT_PART + STANDALONE_RENDER списком (A:1)",
              md.index("## Четыре числа") < md.index("## Маршрут B: матрица")
              and "| A:1 | OBJECT_PART / STANDALONE_RENDER | OBJECT_PART / STANDALONE_RENDER |" in md)
        check("в отчёте таблица переходов 8 расхождений и матрица маршрута сеткой",
              "ошибка маршрута осталась" in md and "| ответ \\ эталон | STAND | COMP | MOD | STATE | DERIV | EXCL | open |"
              in md and "| STAND | 2 | . | . | 1 | . | 1 | . |" in md)

        # подделка определений после заморозки
        p = os.path.join(out, "spec.json")
        d = json.load(open(p, encoding=ENC))
        d["spec"]["precedence"] = "иначе"
        write(p, json.dumps(d))
        try:
            quiet(r.report, out, src)
            check("определения изменены после заморозки - отказ", False)
        except SystemExit:
            check("определения изменены после заморозки - отказ", True)

    print("итог:", "все проверки прошли" if not fails else "провалено %d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
