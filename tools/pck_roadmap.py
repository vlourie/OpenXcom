#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Очередь на перерисовку по данным переписи (tools\pck_census.py).

Две мысли, ради которых это написано.

ПЕРВАЯ: порядок задаёт охват, а не размер набора. Набор из 41 кадра, лежащий на полумиллионе
клеток, важнее набора из 155 кадров, который встречается на одной карте.

ВТОРАЯ: цена набора падает по мере движения по очереди. Кадры повторяются МЕЖДУ наборами:
из 36 202 кадров игры точных рисунков только 22 601. Поэтому у каждого набора считается не
число кадров, а сколько НОВЫХ рисунков он добавляет к уже нарисованным. Двадцатый набор
в очереди почти целиком состоит из того, что нарисовано в первых девятнадцати, и стоит
несколько кадров вместо сотни.

    py -3 tools\pck_roadmap.py --census census --out census

Порядок жадный: на каждом шаге берётся набор с наибольшим числом клеток. Набор всегда берётся
ЦЕЛИКОМ - соседние клетки одного набора игрок видит рядом, и рисовать их порознь нельзя
(грабли R-006: заплатки под объектами).
"""
import argparse
import csv
import os
from collections import defaultdict

ENC = "utf-8-sig"


def read_tsv(path):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path, header, rows):
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join("" if v is None else str(v) for v in r) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default="census")
    ap.add_argument("--out", default="census")
    ap.add_argument("--kind", default="TERRAIN", help="раздел: TERRAIN, UNITS, . (все)")
    args = ap.parse_args()

    frames = read_tsv(os.path.join(args.census, "frames.tsv"))
    if args.kind and args.kind != ".":
        frames = [r for r in frames if r["раздел"] == args.kind]
    for r in frames:
        r["клеток"] = int(r["клеток"])
        r["блоков"] = int(r["блоков"])

    per_set = defaultdict(list)
    for r in frames:
        per_set[r["набор"]].append(r)

    # Вес набора берём из sets.tsv: там клетки посчитаны ПО ЗАПИСЯМ MCD. Сумма по кадрам
    # была бы больше, потому что анимированная запись рисует одну клетку восемью кадрами.
    sets_tsv = {r["набор"]: r for r in read_tsv(os.path.join(args.census, "sets.tsv"))}
    tiles_of = {s: int(sets_tsv[s]["клеток"]) if s in sets_tsv else 0 for s in per_set}
    blocks_of = {s: int(sets_tsv[s]["блоков"]) if s in sets_tsv else 0 for s in per_set}
    total_tiles = sum(tiles_of.values())

    order = sorted(per_set, key=lambda s: (-tiles_of[s], s))

    drawn_exact = set()
    drawn_recolor = set()
    rows = []
    cum_tiles = 0
    cum_new = 0
    for pos, s in enumerate(order, 1):
        rs = per_set[s]
        new_ex = {r["точный"] for r in rs} - drawn_exact
        # из новых рисунков часть - перекраска уже нарисованного: её можно получить
        # пересчётом палитры, а не новой генерацией
        new_rc = set()
        recolor_only = 0
        for r in rs:
            if r["точный"] in new_ex:
                if r["раскраска"] in drawn_recolor or r["раскраска"] in new_rc:
                    recolor_only += 1
                else:
                    new_rc.add(r["раскраска"])
        anim = len({r["анимация"] for r in rs if r["анимация"]})
        mirrors = sum(1 for r in rs if r["зеркален"] == "1")
        cum_tiles += tiles_of[s]
        cum_new += len(new_rc)
        rows.append([pos, s, len(rs), len({r["точный"] for r in rs}), len(new_ex), len(new_rc),
                     recolor_only, mirrors, anim, tiles_of[s], blocks_of[s],
                     round(100.0 * cum_tiles / total_tiles, 2) if total_tiles else 0, cum_new])
        drawn_exact |= new_ex
        drawn_recolor |= new_rc

    write_tsv(os.path.join(args.out, "roadmap.tsv"),
              ["место", "набор", "кадров", "разных", "новых", "рисовать",
               "перекраской", "зеркальных", "анимаций", "клеток", "блоков",
               "охват_клеток_%", "нарисовано_всего"],
              rows)

    # где проходят рубежи охвата
    marks = {}
    for pct in (25, 50, 75, 90, 95, 99):
        for r in rows:
            if r[11] >= pct:
                marks[pct] = r
                break

    lines = []
    lines.append("# Очередь на перерисовку: %s" % args.kind)
    lines.append("")
    lines.append("Построено `tools/pck_roadmap.py` по переписи `tools/pck_census.py`.")
    lines.append("")
    lines.append("Всего наборов %d, кадров %d, клеток на картах %d."
                 % (len(order), len(frames), total_tiles))
    lines.append("")
    lines.append("## Сколько рисовать ради какого охвата")
    lines.append("")
    lines.append("| охват клеток | наборов | рисунков нарисовать |")
    lines.append("|---|---|---|")
    for pct in (25, 50, 75, 90, 95, 99):
        r = marks.get(pct)
        if r:
            lines.append("| %d%% | %d | %d |" % (pct, r[0], r[12]))
    lines.append("| 100%% | %d | %d |" % (len(rows), rows[-1][12] if rows else 0))
    lines.append("")
    lines.append("«Рисунков нарисовать» - накопленное число НОВЫХ картинок с учётом того, что")
    lines.append("повторы и перекраски берутся из уже нарисованного.")
    lines.append("")
    lines.append("## Первые сорок наборов")
    lines.append("")
    lines.append("| # | набор | кадров | рисовать | перекраской | анимаций | клеток | блоков | охват |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows[:40]:
        lines.append("| %d | %s | %d | **%d** | %d | %d | %d | %d | %.1f%% |"
                     % (r[0], r[1], r[2], r[5], r[6], r[8], r[9], r[10], r[11]))
    lines.append("")
    with open(os.path.join(args.out, "roadmap.md"), "w", encoding=ENC, newline="") as f:
        f.write("\n".join(lines) + "\n")

    print("наборов: %d, кадров: %d, клеток: %d" % (len(order), len(frames), total_tiles))
    for pct in (25, 50, 75, 90, 95, 99):
        r = marks.get(pct)
        if r:
            print("  %2d%% клеток  -> %3d наборов, нарисовать %5d рисунков" % (pct, r[0], r[12]))
    print("  100%% клеток -> %3d наборов, нарисовать %5d рисунков" % (len(rows), rows[-1][12] if rows else 0))
    print("таблицы: %s" % os.path.abspath(args.out))


if __name__ == "__main__":
    main()
