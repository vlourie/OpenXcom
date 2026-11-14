# -*- coding: utf-8 -*-
"""hd/FX/shots.txt: оружие -> класс выстрела (лазер/плазма/гаусс) -> размер (малый/средний/большой). Тикет XP-000544.

Движок (src/Engine/HdShots.cpp) читает строки "shot <предмет> laser|plasma|gauss small|medium|large" и рисует такому оружию
выстрел «как в классике» (опция oxceHdClassicShots). Предмета нет в файле - выстрел рисуется как раньше.

Источник - таблица census/tickets/XP-000544/weapon_class.tsv (её делает scripts/weapon_class.py тикета по рулсету Пираток).
Берутся только строки с классом laser/plasma/gauss; класс «?» (64 предмета, класс угадан по строке листа) не включается, кроме явного списка PROMOTE (тикет XP-000555).

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
# Тикет XP-000555: оружие класса «?» (в имени нет LASER/PLASMA/GAUSS), у которого строка листа снаряда и тип урона патрона
# говорят одно и то же: damageType 4 (лазер) + строки 16/18; damageType 5 (плазма) + строка 15. Это обычные стволы
# (лазган/лазпистолет ЕС, карабины Косморейнджеров, Крюгер, АйГан, Хакссор, Пчела-убийца), а не магия и не чудища.
# Размер берётся из таблицы как есть. Остальной «?» (лучеметы, электро, варп, посох, глаза, башни) не включается.
PROMOTE = {
    "STR_ES_PISTOL": "laser", "STR_ES_RIFLE": "laser", "STR_ES_SNIPER": "laser", "STR_ES_HEAVY": "laser",
    "STR_SR_PISTOL": "laser", "STR_SR_RIFLE": "laser", "STR_SR_SHOTGUN": "laser",
    "STR_KRUGER": "plasma", "STR_IGUN": "plasma", "STR_HAXXOR": "plasma", "STR_HORNET": "plasma",
}
# Тикет XP-000570 (Vitali 14.11, вариант B): семья Hell (урон 5 - плазма, лист трассера 1/2/3) стреляет как классическая
# плазма. В таблице 544 этих стволов нет вовсе, поэтому размер задан здесь тем же правилом, что в weapon_class.py:
# PISTOL/SMG - малый, вес 25+ - большой, остальное - средний.
EXTRA = {
    "STR_HELL_PISTOL": ("plasma", "small"), "STR_HELL_SMG": ("plasma", "small"),
    "STR_HELL_RIFLE": ("plasma", "medium"), "STR_HELL_SHOTGUN": ("plasma", "medium"),
    "STR_HELLFIST": ("plasma", "medium"), "STR_HELLGUN": ("plasma", "medium"),
    "STR_HELL_CHAINGUN": ("plasma", "large"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", action="append", required=True, help="каталог hd мода (кладём в <out>/FX/shots.txt)")
    ap.add_argument("--tsv", default=TSV)
    args = ap.parse_args()
    lines = []
    count = {}
    with open(args.tsv, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            cls = row["class"] if row["class"] in CLASSES else PROMOTE.get(row["item"] if row["class"] == "?" else "", "")
            if cls not in CLASSES or row["size"] not in SIZES:
                continue
            lines.append((row["item"], cls, row["size"]))
            count[(cls, row["size"])] = count.get((cls, row["size"]), 0) + 1
    have = {i for i, _, _ in lines}
    for item, (cls, size) in EXTRA.items():
        if item not in have:
            lines.append((item, cls, size))
            count[(cls, size)] = count.get((cls, size), 0) + 1
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
