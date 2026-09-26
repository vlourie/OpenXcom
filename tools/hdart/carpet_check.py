# -*- coding: utf-8 -*-
"""Кадры-ковры без вариантов (грабли R-039).

Кадр, которым замощено поле, при одной картинке на всё поле даёт ромбическую решётку при любом
качестве рисунка. Движок умеет варианты <N>.v1.png ... (HdSprites, MAX_VARIANTS) и раскладывает их
узором. Скрипт берёт из переписи частые кадры сплошного поля (census/frames.tsv - клеток,
census/ground.tsv - поле) и смотрит в тот пак мода, который читает игра, сколько у них вариантов.

    py -3 tools\\hdart\\carpet_check.py                  # отчёт, код 0
    py -3 tools\\hdart\\carpet_check.py --strict         # код 1, если есть ковёр с HD-кадром и без вариантов
    py -3 tools\\hdart\\carpet_check.py --min-cells 5000 --need 3

Пак по умолчанию - копия мода в установке Пираток: её грузит игра и её берёт сборка (R-081, R-087).
"""
import argparse
import os
import sys
import common

ENC = "utf-8-sig"
DEFAULT_MOD = os.path.join(common.GAME_HD, "hd", "TERRAIN")


def read_tsv(path):
    with open(path, encoding=ENC) as f:
        head = f.readline().rstrip("\r\n").split("\t")
        for line in f:
            yield dict(zip(head, line.rstrip("\r\n").split("\t")))


def pack_dir(mod, name):
    """Папка пака <НАБОР>.PCK без учёта регистра; None, если пака нет."""
    want = (name + ".PCK").upper()
    for d in os.listdir(mod):
        if d.upper() == want and os.path.isdir(os.path.join(mod, d)):
            return os.path.join(mod, d)
    return None


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default="census")
    ap.add_argument("--mod", default=DEFAULT_MOD, help="папка TERRAIN мода, которую читает игра")
    ap.add_argument("--min-cells", type=int, default=5000, help="ковёр - кадр поля не меньше чем на стольких клетках карт")
    ap.add_argument("--need", type=int, default=3, help="сколько вариантов .v1..vN нужно ковру")
    ap.add_argument("--strict", action="store_true", help="код 1, если есть ковёр с HD-кадром без вариантов")
    a = ap.parse_args(argv)

    field = {(r["набор"].upper().replace(".PCK", ""), r["кадр"]): r["поле"] == "1"
             for r in read_tsv(os.path.join(a.census, "ground.tsv")) if r["раздел"] == "TERRAIN"}
    carpets = []
    for r in read_tsv(os.path.join(a.census, "frames.tsv")):
        if r["раздел"] != "TERRAIN" or not r["клеток"].isdigit():
            continue
        key = (r["набор"].upper(), r["кадр"])
        if int(r["клеток"]) >= a.min_cells and field.get(key):
            carpets.append((int(r["клеток"]), key[0], key[1]))
    carpets.sort(reverse=True)

    if not os.path.isdir(a.mod):
        print("нет папки мода:", a.mod)
        return 2
    bad = no_hd = packed = 0
    print("ковров (поле, от %d клеток): %d; пак: %s" % (a.min_cells, len(carpets), a.mod))
    for cells, name, frame in carpets:
        d = pack_dir(a.mod, name)
        files = set(os.listdir(d)) if d else set()
        if d and "pack.hdp" in files:
            packed += 1
            print("  ?  %-22s %4s  %7d клеток  пак в pack.hdp, варианты не видны" % (name, frame, cells))
            continue
        if frame + ".png" not in files:
            no_hd += 1
            continue
        n = sum(1 for v in range(1, 17) if "%s.v%d.png" % (frame, v) in files)
        if n < a.need:
            bad += 1
            print("  !! %-22s %4s  %7d клеток  вариантов %d из %d" % (name, frame, cells, n, a.need))
    print("без вариантов: %d, без HD-кадра: %d, в pack.hdp: %d" % (bad, no_hd, packed))
    return 1 if a.strict and bad else 0


if __name__ == "__main__":
    sys.exit(main())
