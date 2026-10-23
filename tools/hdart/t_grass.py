#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Трава MOUNTGRASS:0 (+ варианты .v1-.v7) - тикет XP-000242: вариант V2 (Vitali 23.10).

V2 - квантильный тон-мап яркости на рампу классики, 60% соответствия + размытая яркость 0.5; структура и альфа HD сохранены.
Кадры уже готовы: art/_review/tickets_2026-10-23/grass_fix/V2/TERRAIN/MOUNTGRASS.PCK/{0,0.v1..0.v7}.png (их собрал разбор,
скрипт разбора остался в scratchpad - здесь только установка). Семья: у MOUNTGRASS:0 копий в других наборах нет (уникальный
хеш классики, ticket_family.py MOUNTGRASS:0 - 0 членов; t_grass_family.tsv относится к MOUNTGRASS:7/27/29, не к :0).

    py -3.13 tools/hdart/t_grass.py             # проверка файлов
    py -3.13 tools/hdart/t_grass.py --install --yes   # в мод hd через манифест (под очередью правок), v4-v7 в манифест дописываются
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts  # noqa: E402

SRC = ROOT / "art" / "_review" / "tickets_2026-10-23" / "grass_fix" / "V2" / "TERRAIN" / "MOUNTGRASS.PCK"
NAMES = ["0.png"] + ["0.v%d.png" % i for i in range(1, 8)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = {"TERRAIN/MOUNTGRASS.PCK/" + n: SRC / n for n in NAMES}
    for rel, p in files.items():
        if not p.exists():
            raise SystemExit("нет " + str(p))
    print("кадров: %d" % len(files))
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(files, "t_grass", "t_grass.py 23.10 MOUNTGRASS:0 + v1-v7, вариант V2 (тон классики по рангу 60% + мягкий контраст)",
                         "Vitali 23.10 (XP-000242, трава), вариант V2; лист art/_review/tickets_2026-10-23/t_grass_fix.png",
                         "t242: трава MOUNTGRASS 0 + v1-v7, вариант V2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
