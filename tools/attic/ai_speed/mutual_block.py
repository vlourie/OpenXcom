#!/usr/bin/env python3
"""Взаимные блокировки в записи серии: юнит A остановлен юнитом B (walk.stop.unit ... buB), а B - юнитом A, на тех же
двух клетках. Печатает пары по боям и число остановок с каждой стороны.

  py -3.13 tools/ai_speed/mutual_block.py fx46off fx46on2

На RITUAL_CAVE (зёрна 1101, 1157, 1405, 1453, 1458, 1704) все цепочки 201 - такие пары по диагонали: юниты не видят
друг друга, и путь каждого идёт через клетку другого. FIREPOINT_BLOCKED укорачивает серии, но пару не разводит."""
import collections, gzip, json, re, sys

from _common import probe_work

RX = re.compile(r"walk\.stop\.unit (\d+,\d+,\d+)>(\d+,\d+,\d+) .* bu(\d+)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    arena = probe_work() / "arena"
    for label in sys.argv[1:]:
        stops = collections.Counter()
        with gzip.open(arena / (label + ".rec.gz"), "rt", encoding="utf-8") as f:
            for line in f:
                if "[AIEXEC]" not in line or "walk.stop.unit" not in line:
                    continue
                seed = line.partition(" [")[0]  # бой = seed + want: seed повторяется в миссиях (R-206)
                r = json.loads(line[line.index("{"):])
                for t in r.get("trail") or []:
                    m = RX.search(t)
                    if m:
                        stops[(seed, r["unit"], m.group(1), int(m.group(3)), m.group(2))] += 1
        pairs = {}
        for (seed, a, fa, b, ta), n in stops.items():
            back = stops.get((seed, b, ta, a, fa), 0)
            if back and a < b:
                pairs[(seed, a, b, fa, ta)] = (n, back)
        print("==", label, "взаимных пар:", len(pairs))
        for (seed, a, b, fa, ta), (n, back) in sorted(pairs.items()):
            print(f"  зерно {seed}: {a} на {fa} <-> {b} на {ta}, остановок {n} / {back}")


if __name__ == "__main__":
    main()
