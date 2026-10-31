#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разбор строк [AIBENCH] из openxcom.log в таблицу времени хода ИИ.

Использование:
    python parse_aibench.py <путь к openxcom.log> [--csv out.csv]
"""
import argparse
import re
import sys
from collections import defaultdict

LINE = re.compile(
    r"\[AIBENCH\]\s+turn=(?P<turn>\d+)\s+side=(?P<side>\w+)\s+brutal=(?P<brutal>-?\d+)"
    r"\s+perfOpt=(?P<perf>\d+)\s+cheat=(?P<cheat>-?\d+)\s+calls=(?P<calls>\d+)"
    r"\s+totalMs=(?P<total>\d+)\s+avgMs=(?P<avg>[\d.eE+-]+)\s+maxMs=(?P<max>\d+)"
    r"\s+avgReach=(?P<areach>\d+)\s+maxReach=(?P<mreach>\d+)"
)


def read_rows(path):
    rows = []
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        for line in fh:
            m = LINE.search(line)
            if m:
                d = m.groupdict()
                for k in ("turn", "brutal", "perf", "cheat", "calls", "total", "max", "areach", "mreach"):
                    d[k] = int(d[k])
                d["avg"] = float(d["avg"])
                rows.append(d)
    return rows


def pct(values, q):
    if not values:
        return 0.0
    s = sorted(values)
    i = min(len(s) - 1, int(round(q * (len(s) - 1))))
    return s[i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--csv")
    args = ap.parse_args()

    rows = read_rows(args.log)
    if not rows:
        print("В логе нет строк [AIBENCH]. Собран ли пропатченный бинарник?")
        return 1

    print("=== Ходы ===")
    print(f"{'ход':>4} {'сторона':<8} {'brutal':>6} {'вызовов':>8} {'всего мс':>9} "
          f"{'средн мс':>9} {'макс мс':>8} {'клеток ср':>10}")
    for r in rows:
        print(f"{r['turn']:>4} {r['side']:<8} {r['brutal']:>6} {r['calls']:>8} "
              f"{r['total']:>9} {r['avg']:>9.1f} {r['max']:>8} {r['areach']:>10}")

    print("\n=== Сводка по сторонам ===")
    by_side = defaultdict(list)
    for r in rows:
        by_side[r["side"]].append(r)

    for side, rs in sorted(by_side.items()):
        totals = [r["total"] for r in rs]
        maxes = [r["max"] for r in rs]
        calls = sum(r["calls"] for r in rs)
        print(f"\n{side}: ходов {len(rs)}, вызовов ИИ {calls}")
        print(f"  время на ход:   медиана {pct(totals,0.5):.0f} мс, "
              f"p90 {pct(totals,0.9):.0f} мс, максимум {max(totals)} мс")
        print(f"  время на юнита: максимум {max(maxes)} мс")
        print(f"  клеток в разборе: средн {sum(r['areach'] for r in rs)//len(rs)}, "
              f"макс {max(r['mreach'] for r in rs)}")
        worst = max(totals)
        print(f"  --> {worst/1000.0:.1f} с на ход; "
              f"1000 боёв по 20 ходов = {worst*20*1000/1000/3600:.1f} ч на один поток")

    if args.csv:
        import csv
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nCSV: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
