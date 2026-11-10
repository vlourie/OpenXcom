# -*- coding: utf-8 -*-
"""hd/FX/shots.txt: оружие -> класс выстрела (лазер/плазма/гаусс) -> размер (малый/средний/большой). Тикет XP-000544.

Движок (src/Engine/HdShots.cpp) читает строки "shot <предмет> laser|plasma|gauss small|medium|large" и рисует такому оружию
выстрел «как в классике» (опция oxceHdClassicShots). Предмета нет в файле - выстрел рисуется как раньше.

Источник - таблица census/tickets/XP-000544/weapon_class.tsv (её делает scripts/weapon_class.py тикета по рулсету Пираток).
Берутся только строки с классом laser/plasma/gauss; класс «?» (64 предмета, класс угадан по строке листа) не включается.

Запуск: py -3 tools/hdart/shots_map.py --out <каталог hd мода, где лежит FX> [--out <вторая копия>]
        (например --out E:/OpenXCom/user/mods/hd/hd)
"""
import argparse
import csv
import os
import sys

TSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "census", "tickets", "XP-000544", "weapon_class.tsv")
CLASSES = ("laser", "plasma", "gauss")
SIZES = ("small", "medium", "large")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", action="append", required=True, help="каталог hd мода (кладём в <out>/FX/shots.txt)")
    ap.add_argument("--tsv", default=TSV)
    args = ap.parse_args()
    lines = []
    count = {}
    with open(args.tsv, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row["class"] not in CLASSES or row["size"] not in SIZES:
                continue
            lines.append((row["item"], row["class"], row["size"]))
            count[(row["class"], row["size"])] = count.get((row["class"], row["size"]), 0) + 1
    lines.sort()
    text = ["# written by tools/hdart/shots_map.py from weapon_class.tsv (XP-000544): shot <item> laser|plasma|gauss small|medium|large"]
    text += [f"shot {i} {c} {s}" for i, c, s in lines]
    for out in args.out:
        d = os.path.join(out, "FX")
        os.makedirs(d, exist_ok=True)
        # читает движок: без спецификации (R-001, исключение для файлов игры)
        with open(os.path.join(d, "shots.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(text) + "\n")
        print("->", os.path.join(d, "shots.txt"))
    print("предметов:", len(lines), dict(sorted(count.items())))


if __name__ == "__main__":
    sys.exit(main())
