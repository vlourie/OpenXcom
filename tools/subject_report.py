# -*- coding: utf-8 -*-
r"""Что за тему получит каждый набор плиток - до того, как запускать рисование.

    python tools\subject_report.py
    python tools\subject_report.py --only-stub     только те, где осталась заглушка

Читает .index\mod\_subjects\subject_plan.tsv (его строит tools\subject_plan.py) и
.index\mod\Piratez\set_terrains.tsv (tools\index_mod.py), прогоняет каждый набор через
ту же цепочку, что и gen_hd.py, и пишет .index\mod\_subjects\subject_report.tsv.

Колонка "откуда": SUBJECTS - написано руками на набор; террейн - через рулсеты;
имя - угадано по образцу в имени файла; ЗАГЛУШКА - темы нет.
"""

import argparse
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "hdart"))

import subjects_terrain  # noqa: E402

try:
    # gen_hd тянет numpy/PIL; если их нет (голое окружение) - работаем без SUBJECTS,
    # тогда в отчёте эти наборы уедут в "террейн"/"имя". Цепочка от этого не врёт,
    # только слегка занижает колонку SUBJECTS.
    from gen_hd import SUBJECTS  # noqa: E402
except Exception as e:  # pragma: no cover
    print("не смог прочитать SUBJECTS из gen_hd.py (%s) - отчёт без них" % e, file=sys.stderr)
    SUBJECTS = {}

ENC_R = "utf-8-sig"
ENC_W = "utf-8-sig"


def resolve(set_name, table):
    key = set_name.upper()
    if not key.endswith(".PCK"):
        key += ".PCK"
    if key in SUBJECTS:
        return SUBJECTS[key], "SUBJECTS", ""
    subj, src = subjects_terrain.subject_for_set(key, table)
    if subj:
        return subj, "террейн", src
    subj, src = subjects_terrain.subject_by_name(key)
    if subj:
        return subj, "имя", src
    return "terrain tiles and objects", "ЗАГЛУШКА", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=os.path.join(ROOT, ".index", "mod"))
    ap.add_argument("--only-stub", action="store_true", help="печатать только наборы без темы")
    args = ap.parse_args()

    plan = os.path.join(args.index, "_subjects", "subject_plan.tsv")
    tsv = os.path.join(args.index, "Piratez", "set_terrains.tsv")
    if not os.path.exists(plan):
        print("нет %s - сначала tools\\subject_plan.py" % plan, file=sys.stderr)
        return 1
    table = subjects_terrain.load_set_terrains(tsv)
    if not table:
        print("нет %s - сначала tools\\index_mod.py" % tsv, file=sys.stderr)

    rows = []
    with open(plan, encoding=ENC_R) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            subj, how, src = resolve(r["set"], table)
            rows.append({
                "set": r["set"],
                "frames": int(r["frames"]),
                "floors": int(r["floors"]),
                "откуда": how,
                "источник": src,
                "тема": subj,
            })

    out = os.path.join(args.index, "_subjects", "subject_report.tsv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding=ENC_W, newline="") as f:
        w = csv.DictWriter(f, delimiter="\t", fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in sorted(rows, key=lambda r: -r["floors"]):
            w.writerow(r)

    tot_f = sum(r["floors"] for r in rows)
    tot_k = sum(r["frames"] for r in rows)
    named = [r for r in rows if r["откуда"] != "ЗАГЛУШКА"]
    print("наборов %d, кадров %d, из них полов %d" % (len(rows), tot_k, tot_f))
    for how in ("SUBJECTS", "террейн", "имя", "ЗАГЛУШКА"):
        g = [r for r in rows if r["откуда"] == how]
        if g:
            print("  %-9s наборов %4d, полов %5d (%2d%%)" % (
                how, len(g), sum(r["floors"] for r in g),
                sum(r["floors"] for r in g) * 100 // max(tot_f, 1)))
    print("с темой: полов %d%%, кадров %d%%" % (
        sum(r["floors"] for r in named) * 100 // max(tot_f, 1),
        sum(r["frames"] for r in named) * 100 // max(tot_k, 1)))

    if args.only_stub:
        print("\nбез темы (по убыванию полов):")
        for r in sorted(rows, key=lambda r: -r["floors"]):
            if r["откуда"] == "ЗАГЛУШКА" and r["floors"] > 0:
                print("  %4d  %s" % (r["floors"], r["set"]))
    print("-> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
