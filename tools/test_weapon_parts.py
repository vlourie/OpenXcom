#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверки tools/hdart/weapon_parts (разбор специалиста 05.10: проверка давала и ложный FAIL, и ложный PASS).

Синтетика:
- итог конструкции по покрытию: неизмеренный стык, стык по цвету, лишнее - вопросы к независимой проверке, итог
  не понижают; деталь FAIL по покрытию - итог FAIL;
- размещение отдельно: PASS / DECISION_WIDE (уходит с .wide, решает Vitali) / FAIL;
- размер по родной альфе: ±2 % PASS, ±4 % и дальше FAIL (допуск ±3 % - граница, без поблажки в полпикселя);
- срез размещением: пороги 1 и 16 HD-пикселей; срезанное в габарите оригинала (оригинал за клетками) и за
  габаритом (ответ шире) считаются раздельно;
- разметка: пиксель цвета соседней детали в чужом прямоугольнике у границы уходит соседу, ровная деталь не трогается;
- стык: прямой контакт мерится, Г-образный - «стык не прямой».
Данные (нужен census/items/export, нет - пропуск): нож W-079 - оригинал x4 проходит профиль, сужение острия на
пиксель (строки 0-5) и пятки (12-18) - FAIL профиля.
Запуск: py -3.13 tools/test_weapon_parts.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "hdart"))

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import weapon_fit as wf                 # noqa: E402
import weapon_parts as wp               # noqa: E402

K = wp.K
fails_total = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails_total.append(name)


def joints_overall():
    """Указание специалиста 05.10 (вторая правка): цветовая мерка вспомогательная, NOT_MEASURED относится к замеру,
    а не к предмету - итог не понижают, становятся вопросами к независимой проверке."""
    res = [{"part": "a", "verdict": "PASS", "why": [], "notes": [], "center": (0, 0), "color_de": 5.0}]
    spec = {"parts": [{"name": "a"}]}
    jm = {"a": "a", "b": "b", "verdict": "PASS", "status": "MEASURED", "why": "", "toward": "b"}
    jn = {"a": "a", "b": "c", "verdict": wp.NOT_MEASURED, "status": wp.NOT_MEASURED,
          "why": "стык a|c не измерен: цвета деталей близки (ΔE 2)"}
    jf = {"a": "a", "b": "d", "verdict": "FAIL", "status": "MEASURED", "why": "FAIL стык a|d +3.0", "toward": "d"}
    v, _w, qs, _li = wp.overall(res, [], 0, spec, [jm])
    check("все стыки измерены и PASS - итог PASS, вопросов нет", v == "PASS" and not qs)
    v, _w, qs, _li = wp.overall(res, [], 0, spec, [jm, jn])
    check("неизмеренный стык - итог PASS, вопрос JOINT_NOT_MEASURED (%s, %s)" % (v, [q["kind"] for q in qs]),
          v == "PASS" and [q["kind"] for q in qs] == ["JOINT_NOT_MEASURED"])
    v, _w, qs, _li = wp.overall(res, [], 0, spec, [jf])
    check("стык FAIL по цвету - не дефект, вопрос JOINT_COLOR (%s)" % v,
          v == "PASS" and bool(qs) and qs[0]["kind"] == "JOINT_COLOR")
    res2 = [dict(res[0], verdict="FAIL", why=["FAIL конец сверху +3.0"])]
    v, _w, _qs, _li = wp.overall(res2, [], 0, spec, [jn])
    check("деталь FAIL по покрытию - итог FAIL (%s)" % v, v == "FAIL")
    v, _w, qs, li = wp.overall(res, [{"px": 4, "box": [1, 2, 3, 4]}], 5, spec, [])
    check("лишнее - вопрос EXTRA, пиксели без разметки - вопрос разметки, итог PASS (%s)" % v,
          v == "PASS" and qs[0]["kind"] == "EXTRA" and bool(li))


def placement():
    for tot, left, want in ((0.5, 0.5, "PASS"), (10.0, 10.0, "PASS"), (60.0, 0.0, "DECISION_WIDE"),
                            (60.0, 40.0, "FAIL")):
        r = wp.placement({"total_hd": tot, "wide_left_hd": left, "cut_wider_hd": 0.0})
        check("размещение: срез %.1f, с .wide %.1f - %s (вышло %s)" % (tot, left, want, r["verdict"]),
              r["verdict"] == want)


def size():
    m = np.zeros((48, 32), bool)
    m[10:40, 10:20] = True              # 10 x 30 пикселей базы
    for w, want in ((100, "PASS"), (104, "PASS"), (108, "FAIL"), (116, "FAIL")):
        a = np.zeros((320, 140), np.float32)
        a[10:310, 10:10 + w] = 1.0      # ответ 300 в высоту
        rep, _s = wp.size_native(a, m)
        check("размер: ответ %dx300 против 10x30 - %s (вышло %s, %+.1f%%)" % (w, want, rep["verdict"],
                                                                         rep["uniform_dw_pct"]), rep["verdict"] == want)


def cut():
    for tot, want in ((0.5, "PASS"), (10.0, "REVIEW"), (20.0, "FAIL")):
        meta = {"cells": [1, 3], "report": {"place": {"lost_off_canvas_alpha": 0.0, "cut_by_cells_alpha": tot,
                                                      "clip": "grid"}}}
        check("срез %.1f HD-пикс - %s" % (tot, want), wp.cut_check(meta)["verdict"] == want)
    off = 4
    H, W = 48, 32
    # оригинал заходит на строку 47 (у 1x3 за клетками), ответ = оригинал x4
    m = np.zeros((H, W), bool)
    m[10:48, 5:9] = True
    a = np.zeros(((H + 2 * off) * K, (W + 2 * off) * K), np.float32)
    a[off * K:(off + H) * K, off * K:(off + W) * K] = np.repeat(np.repeat(m, K, 0), K, 1)
    meta = {"cells": [1, 3], "report": {"place": {"cut_by_cells_alpha": 64.0, "clip": "grid"}}}
    r = wp.cut_check(meta, a, off, m)
    check("оригинал за клетками: в габарите 64, за ним 0 (вышло %s / %s)" % (r["cut_orig_hd"], r["cut_wider_hd"]),
          r["cut_orig_hd"] == 64.0 and r["cut_wider_hd"] == 0.0)
    # ответ выступил вправо за габарит оригинала и за клетки (столбцы 16-17)
    m2 = np.zeros((H, W), bool)
    m2[10:40, 5:16] = True
    a2 = np.zeros_like(a)
    a2[off * K:(off + H) * K, off * K:(off + W) * K] = np.repeat(np.repeat(m2, K, 0), K, 1)
    a2[(off + 20) * K:(off + 22) * K, (off + 16) * K:(off + 18) * K] = 1.0
    r = wp.cut_check(meta, a2, off, m2)
    check("ответ шире оригинала: в габарите 0, за ним 64 (вышло %s / %s)" % (r["cut_orig_hd"], r["cut_wider_hd"]),
          r["cut_orig_hd"] == 0.0 and r["cut_wider_hd"] == 64.0)


def labels_and_contact():
    H, W = 10, 20
    m = np.ones((H, W), bool)
    rgb = np.zeros((H, W, 3), np.float32)
    rgb[:, :10] = (200, 40, 40)
    rgb[:, 10:] = (40, 40, 200)
    spec = {"parts": [{"name": "a", "rects": [[0, 0, 10, 9]]}, {"name": "b", "rects": [[11, 0, 19, 9]]}]}
    lab, moved, _mx = wp.part_labels(spec, m, wp.to_lab(rgb))
    # прямоугольник a захватил столбец 10 цвета b
    check("пиксели цвета b в прямоугольнике a ушли b (%d)" % len(moved),
          len(moved) == H and (lab[:, 10] == 1).all() and (lab[:, :10] == 0).all())
    rgb2 = rgb.copy()
    rgb2[:, 10] = (200, 40, 40)
    _lab, moved2, _mx = wp.part_labels(spec, m, wp.to_lab(rgb2))
    check("ровная разметка не трогается (%d)" % len(moved2), not moved2)
    straight = np.zeros((H, W), np.int32)
    straight[:, 10:] = 1
    ct = wp.contact(straight, 0, 1)
    check("прямой контакт мерится (%s)" % (ct and ct["bad"]), ct is not None and not ct["bad"])
    ell = np.ones((20, 20), np.int32)
    ell[:10, :10] = 0                   # a - угол, b охватывает его справа и снизу
    ct = wp.contact(ell, 0, 1)
    check("Г-образный контакт - стык не прямой (%s)" % (ct and ct["bad"]), ct is not None and "не прямой" in ct["bad"])


def smooth4(rgb, m):
    c = np.repeat(np.repeat(rgb, K, 0), K, 1)
    a = np.repeat(np.repeat(m.astype(np.float32), K, 0), K, 1)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((m.shape[1] * K, m.shape[0] * K),
                                                                      Image.BILINEAR)) / 255.0
    return np.dstack([c, a * 255]).clip(0, 255).astype(np.uint8)


def knife():
    if not os.path.exists(wp.EXPORT) or wp.load_parts("W-079") is None:
        print("skip нож W-079: нет %s или разметки" % wp.EXPORT)
        return
    t = "STR_KITCHEN_KNIFE"
    spec = wp.load_parts("W-079")
    rgb, m = wf.original(t)

    def blade(rgb_, m_):
        res = wp.check_one("W-079", t, smooth4(rgb_, m_), spec, rgb, m)[0]
        r = [r for r in res if r["part"] == "blade"][0]
        return r["profile"]["verdict"], r["verdict"]
    pv, v = blade(rgb, m)
    check("нож: оригинал x4 - профиль PASS (%s, деталь %s)" % (pv, v), pv == "PASS" and v != "FAIL")
    lab = wp.label_map(spec, m)
    z = lab == 0
    ys, xs = np.nonzero(z)
    for r0, r1 in ((0, 5), (12, 18)):
        m2, rgb2 = m.copy(), rgb.copy()
        for y in range(ys.min() + r0, ys.min() + r1 + 1):
            row = xs[ys == y]
            if len(row) >= 2:
                m2[y, row.max()] = False
                rgb2[y, row.max()] = 0
        pv, v = blade(rgb2, m2)
        check("нож: клинок уже на пиксель в строках %d-%d - профиль FAIL (%s)" % (r0, r1, pv), pv == "FAIL")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    joints_overall()
    placement()
    size()
    cut()
    labels_and_contact()
    knife()
    print("итог: %s" % ("PASS" if not fails_total else "FAIL %d" % len(fails_total)))
    sys.exit(1 if fails_total else 0)
