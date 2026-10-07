#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Форма боя по ходам: подошёл ли ИИ и идёт ли он толпой.

Читает CSV, который пишет run_series.py --states, и отвечает на вопрос,
который по исходу боя не виден: КАК менялось поведение, а не только чем
кончилось. Сравнение парное - по боям, сыгранным обоими вариантами, потому
что карты между собой различаются сильнее, чем варианты ИИ.

  python tools/aibench/geo_report.py logs/series_pz_temper_states.csv
  python tools/aibench/geo_report.py <csv> --base брутал --turns 8
"""

import argparse
import collections
import csv
import io
import math
import sys

ENC = "utf-8-sig"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# что показываем и как это назвать человеку
COLS = [("dMed", "подход"), ("spread", "разброс"), ("contact", "видят"),
        ("dMin", "ближний"), ("nAI", "живых")]


def mean_ci(values):
    """Среднее и половина 95%-интервала. Меньше двух значений - интервала нет."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    m = sum(values) / n
    if n < 2:
        return m, 0.0
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    return m, 1.96 * math.sqrt(var / n)


def load(path):
    rows = list(csv.DictReader(io.open(path, encoding=ENC)))
    if not rows:
        raise SystemExit("пусто: " + path)
    # (вариант, ход) -> {бой: строка}
    by = collections.defaultdict(dict)
    for r in rows:
        by[(r["arm"], int(r["turn"]))][r["battle"]] = r
    arms = []
    for a, _t in by:
        if a not in arms:
            arms.append(a)
    return by, arms


def table(by, arms, maxturn):
    print("=== форма боя по ходам (среднее по боям) ===")
    head = "%-14s %4s %5s" % ("вариант", "ход", "боёв")
    for _c, name in COLS:
        head += " %8s" % name
    print(head)
    for arm in arms:
        for turn in range(1, maxturn + 1):
            rs = by.get((arm, turn))
            if not rs:
                continue
            line = "%-14s %4d %5d" % (arm, turn, len(rs))
            for col, _name in COLS:
                line += " %8.1f" % (sum(float(r[col]) for r in rs.values()) / len(rs))
            print(line)
        print()


def paired(by, arms, base, maxturn):
    """Разница с базовым вариантом на одних и тех же боях."""
    for arm in arms:
        if arm == base:
            continue
        print("=== «%s» против «%s», парно по боям ===" % (arm, base))
        head = "%4s %5s" % ("ход", "пар")
        for _c, name in COLS[:3]:
            head += " %16s" % name
        print(head)
        for turn in range(1, maxturn + 1):
            a = by.get((arm, turn), {})
            b = by.get((base, turn), {})
            common = sorted(set(a) & set(b))
            if len(common) < 2:
                continue
            line = "%4d %5d" % (turn, len(common))
            for col, _name in COLS[:3]:
                d = [float(a[k][col]) - float(b[k][col]) for k in common]
                m, ci = mean_ci(d)
                line += " %+9.1f ±%5.1f" % (m, ci)
            print(line)
        print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv", help="файл от run_series.py --states")
    p.add_argument("--base", default="", help="с чем сравнивать (по умолчанию первый вариант)")
    p.add_argument("--turns", type=int, default=12, help="до какого хода показывать")
    args = p.parse_args()

    by, arms = load(args.csv)
    table(by, arms, args.turns)
    base = args.base or arms[0]
    if base not in arms:
        raise SystemExit("нет такого варианта: %s (есть: %s)" % (base, ", ".join(arms)))
    paired(by, arms, base, args.turns)


if __name__ == "__main__":
    main()
