#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""photo_decomp.decompose: главный класс из TSV разложения; нет строки и в v1 ровно один класс - он (из v1);
в v1 несколько - пусто, решает человек; класс вне набора - остановка.

    py -3.13 tools/test_photo_decomp.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
sys.stdout.reconfigure(encoding="utf-8")

import photo_decomp as pd               # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def row(a, st, v1):
    return {"asset": a, "stratum": st, "v1": v1, "v1_new": [pd.V1_TO[c] for c in v1]}


rows = [row("A:1", "dark", []), row("A:2", "simple", ["IDENTITY"]), row("A:3", "thin", ["GEOMETRY", "DETAIL"]),
        row("A:4", "simple", ["IDENTITY"])]
dec = {"A:1": {"primary": "DETAIL_LOSS", "secondary": "BAD_MATERIAL", "note": ""},
       "A:4": {"primary": "BAD_MATERIAL", "secondary": "", "note": ""}}
res = {r["asset_id"]: r for r in pd.decompose(rows, dec)}
check("из TSV: главный и второй", res["A:1"]["primary"] == "DETAIL_LOSS" and res["A:1"]["secondary"] == "BAD_MATERIAL")
check("один класс v1 без строки - он, помечено из v1",
      res["A:2"]["primary"] == "WRONG_IDENTITY" and res["A:2"]["source"] == "из v1")
check("несколько классов v1 без строки - пусто", res["A:3"]["primary"] == "")
check("строка TSV важнее v1", res["A:4"]["primary"] == "BAD_MATERIAL" and res["A:4"]["source"] == "decomp")
try:
    pd.decompose(rows, {"A:1": {"primary": "IDENTITY"}})
    check("класс вне набора - остановка", False)
except SystemExit:
    check("класс вне набора - остановка", True)
check("развилка есть на каждый класс", set(pd.FORK) == set(pd.CLASSES) == set(pd.STAGE))
try:
    pd.decompose(rows, {"A:1": {"primary": "DETAIL_LOSS", "prompt_ok": "да"}})
    check("prompt_ok не YES/NO - остановка", False)
except SystemExit:
    check("prompt_ok не YES/NO - остановка", True)

C = pd.Counter
k, t, _w = pd.decide(C({"WRONG_IDENTITY": 6, "BAD_MATERIAL": 3, "DETAIL_LOSS": 3}), 12)
check("6 из 12 - один класс SINGLE", k == "SINGLE" and t == ["WRONG_IDENTITY"])
k, t, _w = pd.decide(C({"WRONG_IDENTITY": 6, "BAD_MATERIAL": 6}), 12)
check("ничья 6 и 6 - не SINGLE, пара разных ступеней", k == "TWO_UNRELATED")
k, t, _w = pd.decide(C({"MAJOR_GEOMETRY": 5, "DETAIL_LOSS": 4, "BAD_MATERIAL": 3}), 12)
check("геометрия + детали 9 из 12 - общий структурный этап", k == "COMBINED" and set(t) == {"MAJOR_GEOMETRY", "DETAIL_LOSS"})
k, t, _w = pd.decide(C({"WRONG_IDENTITY": 5, "BAD_MATERIAL": 4, "DETAIL_LOSS": 3}), 12)
check("5+4 из 12, разные ступени - TWO_UNRELATED", k == "TWO_UNRELATED")
k, t, _w = pd.decide(C({c: 2 for c in pd.CLASSES}), 12)
check("по два на все шесть - SCATTERED", k == "SCATTERED")
k, _t, _w = pd.decide(C({"WRONG_IDENTITY": 4}), 12)
check("4 из 12 и больше ничего - не SINGLE (знаменатель - все FAIL)", k != "SINGLE")
rs = [{"primary": "WRONG_IDENTITY", "secondary": "", "prompt_ok": "NO"},
      {"primary": "BAD_MATERIAL", "secondary": "WRONG_IDENTITY", "prompt_ok": "YES"},
      {"primary": "WRONG_IDENTITY", "secondary": "", "prompt_ok": ""}]
cz = [pd.cause({"primary": p, "prompt_ok": q}) for p, q in
      [("WRONG_IDENTITY", "NO"), ("WRONG_IDENTITY", "YES"), ("BAD_MATERIAL", "YES"), ("DETAIL_LOSS", "YES"),
       ("BAD_ALPHA", "NO"), ("MAJOR_GEOMETRY", ""), ("", "YES")]]
check("лесенка - RENDERER при любом описании",
      [pd.cause({"primary": "PIXEL_STEP_TRACING", "prompt_ok": q}) for q in ("NO", "YES", "")] == ["RENDERER"] * 3)
check("лесенка в структурной группе и на структурной ступени",
      "PIXEL_STEP_TRACING" in pd.STRUCTURAL and pd.STAGE["PIXEL_STEP_TRACING"] == "structure"
      and set(pd.STRUCTURAL) <= set(pd.CLASSES))
k, t, _w = pd.decide(C({"PIXEL_STEP_TRACING": 5, "DETAIL_LOSS": 4, "WRONG_IDENTITY": 3}), 12)
check("лесенка + детали 9 из 12 - общий структурный этап", k == "COMBINED"
      and set(t) == {"PIXEL_STEP_TRACING", "DETAIL_LOSS"})
check("откуда брак: %s" % cz, cz == ["UPSTREAM", "RENDERER", "RENDERER", "RENDERER", "POSTPROCESS", "?", "?"])
check("разбор WRONG_IDENTITY по промпту (и как второй)", pd.split(rs, "WRONG_IDENTITY", "prompt_ok") ==
      {"YES": 1, "NO": 1, "?": 1})

print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
