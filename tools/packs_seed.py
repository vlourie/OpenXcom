"""Список наборов для дорожной карты сайта: census/sets.tsv -> portal/deploy/seed/packs.json.

Сайт игровых данных не держит и держать не должен, а сказать «этот набор не смотрел никто» без
списка наборов нельзя. Поэтому перепись, посчитанная с установленной игры, уезжает на сайт одним
файлом; портал кладёт его в таблицу командой `Xp.Portal packs --file`.

В файл идут только наборы, у которых есть HD-кадры: проверять нечего там, где пака нет.

    python tools/packs_seed.py              собрать
    python tools/packs_seed.py --all        включая наборы без HD
"""
import argparse
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENSUS = os.path.join(ROOT, "census", "sets.tsv")
OUT = os.path.join(ROOT, "portal", "deploy", "seed", "packs.json")
ENC_R = "utf-8-sig"
# читает этот файл .NET рядом с community.json, а не PowerShell, и кириллицы в нём нет:
# спецификация тут не нужна и только разошлась бы с соседним файлом (грабли R-001, исключение)
ENC_W = "utf-8"


def rows(path):
    with open(path, encoding=ENC_R, newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            yield row


def number(row, key, cast=int, default=0):
    value = (row.get(key) or "").strip().replace(",", ".")
    try:
        return cast(value)
    except ValueError:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default=CENSUS)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--all", action="store_true", help="включая наборы, у которых нет HD-кадров")
    args = ap.parse_args()

    if not os.path.exists(args.census):
        print("нет переписи %s — сначала python tools/pck_census.py" % args.census)
        return 1

    packs, skipped = [], 0
    for row in rows(args.census):
        hd = number(row, "есть_hd")
        if hd == 0 and not args.all:
            skipped += 1
            continue
        packs.append({
            "section": (row.get("раздел") or "TERRAIN").strip().upper(),
            "name": (row.get("набор") or "").strip().upper(),
            "frames": number(row, "кадров"),
            "pictures": number(row, "разных"),
            "hdFrames": hd,
            "cells": number(row, "клеток"),
            "cellShare": number(row, "доля_клеток_%", float, 0.0),
        })

    packs.sort(key=lambda p: (p["section"], p["name"]))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding=ENC_W, newline="\n") as f:
        json.dump({"packs": packs}, f, ensure_ascii=False, indent=2)
        f.write("\n")

    frames = sum(p["frames"] for p in packs)
    pictures = sum(p["pictures"] for p in packs)
    print("%s: наборов %d, кадров %d, разных картинок %d; без HD пропущено %d"
          % (os.path.relpath(args.out, ROOT), len(packs), frames, pictures, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
