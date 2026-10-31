#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Восьмая партия: разбор провалов сценариев и решение «игрокам / эксп.» - правило седьмой партии
(collapse_pilot7_split: FAIL рода ДЫРА не мешает, рода МОДЕЛЬ и «должно стоять» упало в PFALL - эксп.), свои файлы:
census/collapse/pilot8/pilot_result.tsv, census/collapse/partial8/model_result.tsv.

    py -3.13 tools\collapse_pilot8_split.py      census/collapse/pilot8/split.tsv и список на экран
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from collapse_pilot7_split import ENC, kparse, over_hole

RESULT = "census/collapse/pilot8/pilot_result.tsv"
PARTIAL = "census/collapse/partial8/model_result.tsv"
OUT = "census/collapse/pilot8/split.tsv"


def main():
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_pilot8_scen as P8
    en = {ru: e for tn, bn, ru, e in P8.BUILDINGS}
    kinds = {e: {"HOLE_OK": 0, "MODEL": [], "PFALL_EXTRA": []} for e in en.values()}
    for r in csv.DictReader(open(RESULT, encoding=ENC), delimiter="\t"):
        if r["verdict"] != "FAIL":
            continue
        e = en[r["label"]]
        extra = [kparse(s) for s in r["fallen_examples"].split()]
        rm = {kparse(s) for s in r["removed"].split()}
        # примеры - первые 6: МОДЕЛЬ видна и по ним, ДЫРА - только если показаны все лишние
        if len(extra) != int(r["fallen"]) - int(r["fallen_attached_to_removed"]) and all(over_hole(k, rm) for k in extra):
            raise SystemExit("%s %s z%s: лишних упавших больше, чем примеров" % (e, r["scenario"], r["z"]))
        if all(over_hole(k, rm) for k in extra):
            kinds[e]["HOLE_OK"] += 1
        else:
            kinds[e]["MODEL"].append("%s z%s: %s" % (r["scenario"], r["z"], " ".join(
                "%s:%d,%d,%d" % k for k in extra if not over_hole(k, rm))))
    for r in csv.DictReader(open(PARTIAL, encoding=ENC), delimiter="\t"):
        if int(r["must_stand_fallen"]):
            kinds[en[r["label"]]]["PFALL_EXTRA"].append("%s z%s: %s" % (r["side"], r["z"], r["extra_examples"]))
    rows = []
    for tn, bn, ru, e in P8.BUILDINGS:
        k = kinds[e]
        to = "эксп." if k["MODEL"] or k["PFALL_EXTRA"] else "игрокам"
        rows.append([e, "%s/%s" % (tn, bn), to, str(k["HOLE_OK"]), "; ".join(k["MODEL"]), "; ".join(k["PFALL_EXTRA"])])
    with open(OUT, "w", encoding=ENC) as f:
        f.write("label\tblock\tto\tfail_hole_ok\tfail_model\tpfall_must_stand_fallen\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    for r in rows:
        print("%-16s %-8s дыра %d  %s %s" % (r[0], r[2], int(r[3]), r[4], ("PFALL: " + r[5]) if r[5] else ""))
    print("игрокам %d, эксп. %d -> %s" % (sum(r[2] == "игрокам" for r in rows), sum(r[2] != "игрокам" for r in rows), OUT))
    print("EXPERIMENTAL8 =", sorted(r[0] for r in rows if r[2] != "игрокам"))


if __name__ == "__main__":
    main()
