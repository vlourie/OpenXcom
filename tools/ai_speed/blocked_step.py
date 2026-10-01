#!/usr/bin/env python3
"""REPEATED_BLOCKED_STEP_V1 - сводка счётчиков правила по серии (build-ai51 и новее, флаг OXCE_AI_BLOCKED_STEP).

Счётчики лежат в столбце tac таблицы серии (<метка>.tsv) как p./h.blockstep.<имя> - его сохраняет ai_probe.py обеих
машин; полная строка [AIBLOCKSTEP] есть только в openxcom.log. Без флага счётчиков нет ни одного - так проверяется,
что выключенное правило молчит. Имена: recorded (остановка юнитом запомнена), suppressed (решение снова выбрало
запомненный первый шаг), из них rerouted (путь к той же цели найден в обход) и no_path (обхода нет, юнит стоит),
inv.rev / inv.turn (память снята по ревизии известного или по новому ходу), src.<источник> - подавления по источнику
решения. Безопасность правила (шаг, остановленный при той же ревизии, позже не прошёл) проверяет blocked_kr.py.

  py -3.13 tools/ai_speed/blocked_step.py E:/OXCE_AIWorker/results/arena/b51s40.tsv [ещё ...] [--by-battle]"""
import argparse
import collections
import csv
import sys
from pathlib import Path

NAMES = ("recorded", "suppressed", "rerouted", "no_path", "inv.rev", "inv.turn")


def tac(cell):
    out = {}
    for part in (cell or "").split(","):
        name, _, n = part.rpartition(":")
        if name.startswith(("p.blockstep.", "h.blockstep.")) and n.isdigit():
            out[name] = int(n)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--by-battle", action="store_true", help="строка на каждый бой, где правило сработало")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    for path in a.files:
        tot = collections.Counter()
        battles = touched = 0
        rows = []
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                battles += 1
                t = tac(r.get("tac"))
                if t:
                    touched += 1
                    rows.append((r.get("seed"), r.get("want"), r.get("how"), t))
                tot.update(t)
        print(f"{path.name}: боёв {battles}, с правилом {touched}")
        for side, p in (("player", "p."), ("hostile", "h.")):
            row = {n: tot.get(f"{p}blockstep.{n}", 0) for n in NAMES}
            if any(row.values()):
                print(f"  {side:8s} " + "  ".join(f"{n}={v}" for n, v in row.items()))
                src = sorted(((k[len(p) + len("blockstep.src."):], v) for k, v in tot.items()
                              if k.startswith(p + "blockstep.src.")), key=lambda kv: -kv[1])
                if src:
                    print("           по источнику: " + ", ".join(f"{n}:{v}" for n, v in src))
        if a.by_battle:
            for seed, want, how, t in rows:
                short = " ".join(f"{k.replace('blockstep.', '')}={v}" for k, v in sorted(t.items()) if ".src." not in k)
                print(f"    {seed} {want} {how}: {short}")


if __name__ == "__main__":
    main()
