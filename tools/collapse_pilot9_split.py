#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Девятая партия (лес и столбы): разбор провалов и решение «игрокам / эксп.» - правило седьмой и восьмой партий
(collapse_pilot7_split: FAIL рода ДЫРА не мешает, рода МОДЕЛЬ и «должно стоять» упало в PFALL - эксп.), свои файлы:
census/collapse/pilot9/pilot_result.tsv (сценарии 0m - только у городских блоков), census/collapse/partial9/model_result.tsv
(сценарии деревьев collapse_partial9_scen). Недопадение в PFALL (упало не всё «должно упасть») не мешает - R-353.

    py -3.13 tools\collapse_pilot9_split.py      census/collapse/pilot9/split.tsv и список на экран
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from collapse_pilot7_split import ENC, kparse, over_hole

RESULT = "census/collapse/pilot9/pilot_result.tsv"
PARTIAL = "census/collapse/partial9/model_result.tsv"
OUT = "census/collapse/pilot9/split.tsv"


def main():
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_pilot9_scen as P9
    en = {ru: e for tn, bn, ru, e in P9.BUILDINGS}
    kinds = {e: {"HOLE_OK": 0, "MODEL": [], "PFALL_EXTRA": [], "PFALL_MISS": 0} for e in en.values()}
    for r in csv.DictReader(open(RESULT, encoding=ENC), delimiter="\t"):
        if r["verdict"] != "FAIL":
            continue
        e = en[r["label"]]
        extra = [kparse(s) for s in r["fallen_examples"].split()]
        rm = {kparse(s) for s in r["removed"].split()}
        if len(extra) != int(r["fallen"]) - int(r["fallen_attached_to_removed"]) and all(over_hole(k, rm) for k in extra):
            raise SystemExit("%s %s z%s: лишних упавших больше, чем примеров" % (e, r["scenario"], r["z"]))
        if all(over_hole(k, rm) for k in extra):
            kinds[e]["HOLE_OK"] += 1
        else:
            kinds[e]["MODEL"].append("%s z%s: %s" % (r["scenario"], r["z"], " ".join(
                "%s:%d,%d,%d" % k for k in extra if not over_hole(k, rm))))
    for r in csv.DictReader(open(PARTIAL, encoding=ENC), delimiter="\t"):
        k = kinds[en[r["label"]]]
        if int(r["must_stand_fallen"]):
            k["PFALL_EXTRA"].append("%s z%s: %s" % (r["side"], r["z"], r["extra_examples"]))
        if int(r["missed"]):
            k["PFALL_MISS"] += 1
    rows = []
    for tn, bn, ru, e in P9.BUILDINGS:
        k = kinds[e]
        to = "эксп." if k["MODEL"] or k["PFALL_EXTRA"] else "игрокам"
        rows.append([e, "%s/%s" % (tn, bn), to, str(k["HOLE_OK"]), str(k["PFALL_MISS"]), "; ".join(k["MODEL"]),
                     "; ".join(k["PFALL_EXTRA"])])
    with open(OUT, "w", encoding=ENC) as f:
        f.write("label\tblock\tto\tfail_hole_ok\tpfall_missed\tfail_model\tpfall_must_stand_fallen\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    for r in rows:
        print("%-16s %-8s дыра %d недопадений %d  %s %s" % (r[0], r[2], int(r[3]), int(r[4]), r[5],
                                                           ("PFALL: " + r[6]) if r[6] else ""))
    print("игрокам %d, эксп. %d -> %s" % (sum(r[2] == "игрокам" for r in rows), sum(r[2] != "игрокам" for r in rows), OUT))
    print("EXPERIMENTAL9 =", sorted(r[0] for r in rows if r[2] != "игрокам"))


if __name__ == "__main__":
    main()
