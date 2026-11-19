#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Седьмая партия: разбор провалов сценариев (census/collapse/pilot7/pilot_result.tsv) и решение «игрокам / эксп.».

Сценарии и вердикты под замком не меняются - здесь только разбор того, ЧТО упало в FAIL. У седьмой партии на
полах этажей стоят непросмотренные предметы (авто-роль OBJECT, collapse_pilot7_scen), а вердикт пилота списывает
на снятое только части с разметкой ATTACHED/SURFACE. Поэтому FAIL делится на два рода:

  ДЫРА - всё лишнее упавшее стоит над выбитым полом: предмет слота o в клетке, чей пол того же этажа снят, или
         стена w/n, у которой сняты полы обеих клеток по её сторонам. Так и должно быть: пол выбит - стоявшее на
         нём падает;
  МОДЕЛЬ - всё остальное (углы, перемычки, одна опора, стена на краю дыры при целом поле с другой стороны) - тот
         же род ошибок, что у экспериментальных зданий прежних партий.

Здание игрокам: нет FAIL рода МОДЕЛЬ и в частичных сценариях (census/collapse/partial7/model_result.tsv) не упало
ничего из «должно стоять». Пропуск PFALL (модель держит пол, который правило велит уронить) не мешает - решение
Vitali 15.10 о таких зданиях прежних партий (R-353). Остальные - экспериментальные.

    py -3.13 tools\collapse_pilot7_split.py      census/collapse/pilot7/split.tsv и список на экран
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ENC = "utf-8-sig"
RESULT = "census/collapse/pilot7/pilot_result.tsv"
PARTIAL = "census/collapse/partial7/model_result.tsv"
OUT = "census/collapse/pilot7/split.tsv"


def kparse(s):
    side, rest = s.split(":")
    x, y, z = map(int, rest.split(","))
    return (side, x, y, z)


def over_hole(k, rm):
    side, x, y, z = k
    if side == "o":
        return ("f", x, y, z) in rm
    if side == "w":
        return ("f", x, y, z) in rm and ("f", x - 1, y, z) in rm
    if side == "n":
        return ("f", x, y, z) in rm and ("f", x, y - 1, z) in rm
    return False


def main():
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_pilot7_scen as P7
    en = {ru: e for tn, bn, ru, e in P7.BUILDINGS}
    kinds = {e: {"HOLE_OK": 0, "MODEL": [], "PFALL_EXTRA": []} for e in en.values()}
    for r in csv.DictReader(open(RESULT, encoding=ENC), delimiter="\t"):
        if r["verdict"] != "FAIL":
            continue
        e = en[r["label"]]
        extra = [kparse(s) for s in r["fallen_examples"].split()]
        # примеры - первые 6 из «упало минус прикреплённое к снятому»: разбор годен, только если они все
        if len(extra) != int(r["fallen"]) - int(r["fallen_attached_to_removed"]):
            raise SystemExit("%s %s z%s: лишних упавших больше, чем примеров" % (e, r["scenario"], r["z"]))
        rm = {kparse(s) for s in r["removed"].split()}
        if all(over_hole(k, rm) for k in extra):
            kinds[e]["HOLE_OK"] += 1
        else:
            kinds[e]["MODEL"].append("%s z%s: %s" % (r["scenario"], r["z"], " ".join(
                "%s:%d,%d,%d" % k for k in extra if not over_hole(k, rm))))
    for r in csv.DictReader(open(PARTIAL, encoding=ENC), delimiter="\t"):
        if int(r["must_stand_fallen"]):
            kinds[en[r["label"]]]["PFALL_EXTRA"].append("%s z%s: %s" % (r["side"], r["z"], r["extra_examples"]))
    rows = []
    for tn, bn, ru, e in P7.BUILDINGS:
        k = kinds[e]
        to = "эксп." if k["MODEL"] or k["PFALL_EXTRA"] else "игрокам"
        rows.append([e, "%s/%s" % (tn, bn), to, str(k["HOLE_OK"]), "; ".join(k["MODEL"]), "; ".join(k["PFALL_EXTRA"])])
    with open(OUT, "w", encoding=ENC) as f:
        f.write("label\tblock\tto\tfail_hole_ok\tfail_model\tpfall_must_stand_fallen\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    for r in rows:
        print("%-13s %-8s дыра %d  %s %s" % (r[0], r[2], int(r[3]), r[4], ("PFALL: " + r[5]) if r[5] else ""))
    print("игрокам %d, эксп. %d -> %s" % (sum(r[2] == "игрокам" for r in rows), sum(r[2] != "игрокам" for r in rows), OUT))
    print("EXPERIMENTAL7 =", sorted(r[0] for r in rows if r[2] != "игрокам"))


if __name__ == "__main__":
    main()
