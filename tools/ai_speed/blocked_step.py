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
import bisect
import collections
import csv
import gzip
import json
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


def kind(base):
    """действие решения по base записи: тип BattleActionType и источник"""
    t = (base or {}).get("t")
    src = (base or {}).get("src") or "?"
    if t in (None, 0):
        return "none"
    if t == 1:
        return "turn"
    if t == 2:
        return "move." + src.split(".")[0]
    if t == 3:
        return "kneel"
    if t in (6, 7, 8, 9, 10, 12, 13, 14, 16):   # BA_THROW..BA_HIT, BA_LAUNCH, пси, BA_CQB (RuleItem.h)
        return "attack"
    return f"t{t}"


def after_suppress(path):
    """Подавление: обход (rerouted) или пути нет (no_path) - и что юнит решил следующим решением.

    Запись подавления лежит в следе [AIEXEC] своего решения ('blockstep.suppressed dA -> dB' или '-> none'), следующее
    решение того же юнита в том же бою - ближайшая следующая [AIREC]: в том же ходу или уже в следующем."""
    recs = collections.defaultdict(dict)   # бой -> rec -> (ход, юнит, base)
    sup = []                               # (бой, rec, юнит, обход?)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            i = line.find("{")
            if i < 0:
                continue
            head = line[:i]
            battle = head.split(" [", 1)[0]
            if "[AIREC]" in head:
                r = json.loads(line[i:])
                recs[battle][r["rec"]] = (r["turn"], r["unit"], r.get("base"))
            elif "[AIEXEC]" in head and "blockstep.suppressed" in line:
                r = json.loads(line[i:])
                for t in r.get("trail") or []:
                    if t.startswith("blockstep.suppressed"):
                        sup.append((battle, r["rec"], r["unit"], not t.endswith("-> none")))
    nxt = collections.defaultdict(collections.Counter)
    order = collections.defaultdict(list)  # (бой, юнит) -> номера его решений по порядку
    for battle, mine in recs.items():
        for k in sorted(mine):
            order[(battle, mine[k][1])].append(k)
    for battle, rec, unit, rerouted in sup:
        mine = recs[battle]
        turn = mine.get(rec, (None,))[0]
        seq = order[(battle, unit)]
        j = bisect.bisect_right(seq, rec)
        if j >= len(seq):
            what = "решений больше нет"
        else:
            t2, _, base = mine[seq[j]]
            what = ("тот же ход: " if t2 == turn else "след. ход: ") + kind(base)
        nxt["rerouted" if rerouted else "no_path"][what] += 1
    for k in ("rerouted", "no_path"):
        if nxt[k]:
            print(f"  после {k} ({sum(nxt[k].values())}): " + ", ".join(f"{w} {n}" for w, n in nxt[k].most_common()))


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
        rec = path.with_suffix(".rec.gz")
        if rec.exists():
            after_suppress(rec)
        if a.by_battle:
            for seed, want, how, t in rows:
                short = " ".join(f"{k.replace('blockstep.', '')}={v}" for k, v in sorted(t.items()) if ".src." not in k)
                print(f"    {seed} {want} {how}: {short}")


if __name__ == "__main__":
    main()
