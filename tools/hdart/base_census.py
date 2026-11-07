#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Перепись построек базы для «Живой базы» (docs/research/base-living-2026-10-22.md): все типы Пираток + ваниллы,
их размер, кадры BASEBITS, статья педии (en и ru) и какие постройки рисуются одной и той же картинкой -
одна картинка рисуется моделью один раз.

    py -3.13 tools/hdart/base_census.py

Выход art/base_living/census.tsv (UTF-8 BOM) и art/base_living/in/<ТИП>.png - вход модели для каждой картинки.
"""
import csv
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import yaml                                         # noqa: E402

from facility_sheet import load_rules, sprites_map  # noqa: E402
from gen_base_anim import Facility                  # noqa: E402
from gen_base_paint import facility_input           # noqa: E402

OUT = os.path.join(ROOT, "art", "base_living")
LANG = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Language")
VANILLA_LANG = os.path.join(ROOT, "bin", "standard", "xcom1", "Language")


def strings(code):
    out = {}
    for path in (os.path.join(VANILLA_LANG, code + ".yml"), os.path.join(LANG, code + ".yml")):
        if not os.path.exists(path):
            continue
        y = yaml.safe_load(open(path, encoding="utf-8-sig")) or {}
        out.update(y.get(code) or next(iter(y.values()), {}) or {})
    return out


def clean(s):
    return " ".join(str(s or "").replace("{NEWLINE}", " ").split())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rules, articles = load_rules()
    sprites = sprites_map()
    en, ru = strings("en-US"), strings("ru")
    os.makedirs(os.path.join(OUT, "in"), exist_ok=True)
    rows, first_of = [], {}
    for t, rule in rules.items():
        fac = Facility(rule, sprites)
        if fac.missing:
            rows.append([t, "%dx%d" % (fac.cols, fac.rows), "", "нет кадров", "", "", ""])
            continue
        img, _a = facility_input(fac)
        h = hashlib.sha1(img.tobytes()).hexdigest()[:12]
        same = first_of.setdefault(h, t)
        if same == t:
            img.save(os.path.join(OUT, "in", t + ".png"))
        art = articles.get(t) or {}
        key = art.get("text", t + "_UFOPEDIA")
        rows.append([t, "%dx%d" % (fac.cols, fac.rows), ",".join(map(str, fac.indices)),
                     "" if same == t else same, clean(en.get(t)), clean(en.get(key)), clean(ru.get(key))])
    path = os.path.join(OUT, "census.tsv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["type", "size", "frames", "same_picture_as", "name_en", "pedia_en", "pedia_ru"])
        w.writerows(rows)
    uniq = sum(1 for r in rows if r[2] and not r[3])
    big = sum(1 for r in rows if r[2] and not r[3] and r[1] != "1x1")
    print("построек %d, своих картинок %d (из них больше клетки %d), без кадров %d, без педии %d"
          % (len(rows), uniq, big, sum(1 for r in rows if not r[2]), sum(1 for r in rows if r[2] and not r[5])))
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
