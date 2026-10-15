#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PHOTO acceptance v1: машинные проверки, подложка рендера, итог и сверка с человеком. Синтетика, без карт
и видеокарты.

  * photo_render.prompt_for: цвет подложки назван в тексте, серая фраза PHOTO заменена, фраза специалиста в
    конце; у цветной подложки нет слова neutral;
  * detect_panel: подложка ответа по краю, тело в середине не мешает;
  * checks: ответ как оригинал - все PASS; подложка ушла - RERENDER, пока есть попытки, потом REVIEW;
    без ножки - MISSING_MAJOR_PART FAIL; без низа - FOOTPRINT FAIL; тело цвета подложки ответа -
    SILHOUETTE RERENDER; outcome: PASS со второй попытки - PASS_AFTER_RERENDER, незакрытый RERENDER - REVIEW;
  * report: машина PASS + человек FAIL считается false-accept, ворота по порогам специалиста.

    py -3.13 tools/test_photo_accept.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import photo_accept as pa               # noqa: E402
import photo_base as pb                 # noqa: E402
import photo_render as pr               # noqa: E402

FAIL = []
PANEL = np.array([176, 176, 182], np.uint8)
RED = (200, 40, 40)


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def frame():
    """16x20: тело 2..13 x 2..15 красное, ножка x=4 y=16..18."""
    a = np.zeros((20, 16, 4), np.uint8)
    a[2:16, 2:14] = RED + (255,)
    a[16:19, 4] = RED + (255,)
    return Image.fromarray(a, "RGBA")


def render(fr, leg=True, bottom=True, body=RED, panel=PANEL):
    a = np.asarray(fr).copy()
    rgb = np.where(a[..., 3:4] > 0, np.array(body, np.uint8), panel).astype(np.uint8)
    if not leg:
        rgb[16:19, 4] = panel
    if not bottom:                          # низ тела и ножка не нарисованы
        rgb[12:19] = panel
    up = np.repeat(np.repeat(rgb, 4, 0), 4, 1)
    pad = np.zeros((up.shape[0] + 32, up.shape[1] + 32, 3), np.uint8) + panel
    pad[16:-16, 16:-16] = up
    return Image.fromarray(pad, "RGB")


def run(hd, asked=PANEL, left=True):
    fr = frame()
    im, rep, g, m_u = pb.cut(fr, hd, asked=asked)
    delta = float(np.abs(pr.detect_panel(hd) - np.asarray(asked, np.float32)).max())
    c = pa.checks(rep, delta, left, pa.footprint(g, m_u))
    return c, pa.machine_verdict(c), rep


# 1. промпт и подложка
t = pr.prompt_for("wooden crate", "grey_light", (176, 176, 182))
check("серая: цвет в тексте и фраза специалиста", "RGB(176, 176, 182)" in t and
      t.endswith("The background must remain completely flat and unchanged.") and "uniform neutral background" in t)
check("серая фраза PHOTO заменена цветом", pr.GREY_PHRASE not in t and "panel of colour RGB(176, 176, 182)" in t)
t = pr.prompt_for("wooden crate", "blue", (70, 90, 200))
check("цветная: без слова neutral", "uniform background: RGB(70, 90, 200)" in t and "neutral" not in t)
fr = frame()
det = pr.detect_panel(render(fr))
check("подложка ответа по краю (%s)" % det.tolist(), float(np.abs(det - PANEL).max()) < 1)

# 2. проверки машины
c, v, rep = run(render(fr))
# ALPHA здесь не смотрим: у синтетики ступенчатый край x4, матт по контуру даёт кайму подложки, какой у
# настоящих ответов нет (made01: rim_panel не выше 0.31) - альфа проверяется отдельно, по отчёту
check("ответ как оригинал - форма PASS (%s)" % {k: c[k][0] for k in c},
      all(c[k][0] in ("PASS", "N/A") for k in c if k != "ALPHA"))
check("  прорезей нет - OPENING_PRESERVATION N/A", c["OPENING_PRESERVATION"][0] == "N/A")
drift = np.array([150, 150, 150], np.uint8)
c, v, _ = run(render(fr, panel=drift))
check("подложка ушла на 32 - PANEL RERENDER (%s)" % c["PANEL"][1], c["PANEL"][0] == "RERENDER")
c, v, _ = run(render(fr, panel=drift), left=False)
check("  попыток не осталось - PANEL REVIEW, не FAIL", c["PANEL"][0] == "REVIEW")
c, v, _ = run(render(fr, leg=False))
check("без ножки - MISSING_MAJOR_PART FAIL (%s)" % c["MISSING_MAJOR_PART"][1],
      c["MISSING_MAJOR_PART"][0] == "FAIL" and v == "FAIL")
c, v, _ = run(render(fr, bottom=False))
check("без низа - FOOTPRINT FAIL (%s)" % c["FOOTPRINT"][1], c["FOOTPRINT"][0] == "FAIL")
c, v, rep = run(render(fr, bottom=False, body=(176, 176, 182)))
# тело цвета подложки: матт не отделяет - форма неизвестна, не FAIL
grey_fr = Image.fromarray(np.where(np.asarray(fr)[..., 3:4] > 0, np.array([170, 170, 176, 255], np.uint8),
                                   np.zeros(4, np.uint8)).astype(np.uint8), "RGBA")
im, rep, g, m_u = pb.cut(grey_fr, render(grey_fr, bottom=False, body=(170, 170, 176)), asked=PANEL)
c = pa.checks(rep, 0.0, True, pa.footprint(g, m_u))
check("тело цвета подложки - SILHOUETTE RERENDER (%s)" % rep["geometry"], c["SILHOUETTE"][0] == "RERENDER")
check("  и опора по такому матту - не FAIL, а RERENDER (%s)" % (c["FOOTPRINT"],),
      c["FOOTPRINT"][0] != "FAIL" and pa.machine_verdict(c) == "RERENDER")
ok_rep = dict(rep, geometry="PASS", cover=1.0, iou=1.0, spill=0.0, thin_cover=None, holes_kept=None, comps_render=1,
              comps_orig=1, aspect_raw=1.0, core_panel=0.0, rim_panel=0.02, semi=0.03, alpha="PASS", alpha_why="")
check("альфа: всё в порядке - PASS", pa.checks(ok_rep, 0, True, 1.0)["ALPHA"][0] == "PASS")
check("альфа: тело не нарисовано (core 0.2) - FAIL", pa.checks(dict(ok_rep, core_panel=0.2), 0, True, 1.0)["ALPHA"][0] == "FAIL")
check("альфа: полупрозрачное 0.18 - REVIEW, не FAIL (тонкое)",
      pa.checks(dict(ok_rep, semi=0.18), 0, True, 1.0)["ALPHA"][0] == "REVIEW")
check("outcome: PASS со второй - PASS_AFTER_RERENDER", pa.outcome("PASS", 2) == "PASS_AFTER_RERENDER")
check("outcome: незакрытый RERENDER - REVIEW", pa.outcome("RERENDER", 3) == "REVIEW" and pa.outcome("FAIL", 1) == "FAIL")

# 3. сверка с человеком
tmp = tempfile.mkdtemp()
try:
    keep = pa.OUT
    pa.OUT = tmp
    os.makedirs(os.path.join(tmp, "render", "meta"))
    rows = [("A:1", "PASS", "PASS", ""), ("A:2", "PASS", "FAIL", "GEOMETRY"), ("A:3", "FAIL", "FAIL", "GEOMETRY"),
            ("A:4", "REVIEW", "PASS", ""), ("A:5", "FAIL", "PASS", "")]
    jobs = []
    for aid, m, _h, _c in rows:
        name = "pa_" + aid.replace(":", "_").lower()
        jobs.append({"asset_id": aid, "name": name, "stratum": "simple"})
        chk = {k: ["PASS", ""] for k in pa.MACHINE_CHECKS}
        with open(os.path.join(tmp, "render", "meta", name + ".json"), "w", encoding="utf-8-sig") as f:
            json.dump({"machine": m, "outcome": pa.outcome(m, 1), "attempts": [{}], "checks": chk}, f)
    with open(os.path.join(tmp, "jobs.json"), "w", encoding="utf-8-sig") as f:
        json.dump(jobs, f)
    vt = os.path.join(tmp, "v.tsv")
    with open(vt, "w", encoding="utf-8-sig") as f:
        f.write("asset_id\thuman\tfail_class\tnote\n")
        for aid, _m, h, cl in rows:
            f.write("%s\t%s\t%s\t\n" % (aid, h, cl))
    res = pa.report(vt)
    m = res["metrics"]
    check("human_accept 3/5 (%s)" % m["human_accept_rate"], m["human_accept_rate"] == 0.6)
    check("false_accept - человек FAIL среди машинных PASS: 1 из 2 (%s)" % m["machine_false_accept_rate"],
          m["machine_false_accept_rate"] == 0.5 and [r["asset_id"] for r in res["false_accepts"]] == ["A:2"])
    check("false_reject - машина FAIL среди человеческих PASS: 1 из 3", m["machine_false_reject_rate"] == 0.333)
    check("ворота не пройдены при 60 % и false-accept 50 %", not res["gate_passed"])
finally:
    pa.OUT = keep
    shutil.rmtree(tmp, ignore_errors=True)

print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
