#!/usr/bin/env python3
"""MUTUAL_BLOCKED_STEP - пассивное определение класса по записи серии, до любого кода в движке (второе мнение 01.10).

Эпизод: A остановлен B (walk.stop.unit клетка_A>клетка_B ... buB) и B остановлен A на тех же двух клетках, по ходам
подряд; промежуток без взаимной остановки эпизод не рвёт, если ни один из пары не ушёл со своей клетки.
Класс MUTUAL_BLOCKED_STEP - эпизод, где одновременно:
  - никто из пары другого не видит (seen 0 во всех остановках);
  - не меньше MIN_TURNS ходов и MIN_STOPS остановок с каждой стороны (повтор без продвижения);
  - не меньше 80 % решений каждый начинает уже на клетке остановки (стоит и упирается, а не дошёл издалека);
  - без продвижения по ОВ: не меньше 80 % остановок каждой стороны - не дальше поворота от ОВ в начале решения
    (потрачено не больше TURN_TU: только развернулся и упёрся первым шагом; на 1458 бот тратит 1-4, враг 0;
    от хода к ходу ОВ могут разниться - это не продвижение).
Ревизию известного ИИ запись не несёт; «не видит» - косвенно: путь обходит известных юнитов, взаимная остановка
значит, что оба друг для друга неизвестны.

Печатает по эпизодам: ходы, остановки, доли «начато на клетке», ОВ, источники решений (base.src), чем кончился
(ушёл с клетки / больше не решает / бой кончился / до конца записи на тех же клетках).

  py -3.13 tools/ai_speed/mutual_episodes.py fx46off fx46on2
  py -3.13 tools/ai_speed/mutual_episodes.py --arena E:/OXCE_AIWorker/results/arena b46fp23 f46fp23"""
import argparse
import collections
import gzip
import json
import re
import sys
from pathlib import Path

from _common import probe_work

RX = re.compile(r"walk\.stop\.unit (\d+,\d+,\d+)>(\d+,\d+,\d+) .* bu(\d+)")
MIN_TURNS = 2
MIN_STOPS = 3
ON_CELL = 0.8
NO_SPEND = 0.8
TURN_TU = 4


def cell(p):
    return ",".join(str(x) for x in p)


def load(path):
    """бой -> recs: rec -> (ход, юнит, позиция, ОВ, src); stops; pos: юнит -> ход -> позиция в первом решении хода"""
    B = collections.defaultdict(lambda: {"recs": {}, "stops": [], "pos": collections.defaultdict(dict)})
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if "{" not in line:
                continue
            head = line[:line.index("{")]
            if "[AIREC]" in head:
                r = json.loads(line[line.index("{"):])
                st = r["state"]
                b = B[head.split(" [", 1)[0]]
                b["recs"][r["rec"]] = (r["turn"], r["unit"], cell(st["pos"]), st["tu"], (r.get("base") or {}).get("src"))
                b["pos"][r["unit"]].setdefault(r["turn"], cell(st["pos"]))
            elif "[AIEXEC]" in head and "walk.stop.unit" in line:
                r = json.loads(line[line.index("{"):])
                for t in r.get("trail") or []:
                    m = RX.search(t)
                    if m:
                        B[head.split(" [", 1)[0]]["stops"].append(
                            (r["rec"], r["unit"], m.group(1), m.group(2), int(m.group(3)), r.get("tu"), r.get("seen")))
    return B


def stayed(b, a, blk, fa, ta, t0, t1):
    pa, pb = b["pos"].get(a, {}), b["pos"].get(blk, {})
    return all(pa.get(t, fa) == fa and pb.get(t, ta) == ta for t in range(t0 + 1, t1 + 1))


def ending(b, a, blk, fa, ta, last):
    pa, pb = b["pos"].get(a, {}), b["pos"].get(blk, {})
    later = sorted(t for t in set(pa) | set(pb) if t > last)
    if not later:
        return "бой кончился (решений после нет)"
    for t in later:
        moved = []
        if t in pa and pa[t] != fa:
            moved.append(f"{a} ушёл на {pa[t]}")
        if t in pb and pb[t] != ta:
            moved.append(f"{blk} ушёл на {pb[t]}")
        if moved:
            return f"ход {t}: " + ", ".join(moved)
        if max(pa, default=0) < t:
            return f"ход {t}: {a} больше не решает (погиб/выбыл)"
        if max(pb, default=0) < t:
            return f"ход {t}: {blk} больше не решает (погиб/выбыл)"
    return f"до конца записи на тех же клетках (последний ход {later[-1]})"


def no_spend(xs):
    return sum(x[1] is not None and 0 <= x[5] - x[1] <= TURN_TU for x in xs) / len(xs)


def episodes(b):
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for rec, a, fa, ta, blk, tu, seen in b["stops"]:
        if rec not in b["recs"]:
            continue
        turn, _, pos, tu0, src = b["recs"][rec]
        by[(a, blk, fa, ta)][turn].append((rec, tu, seen, src, pos, tu0))
    out, done = [], set()
    for (a, blk, fa, ta), turns in by.items():
        rev = (blk, a, ta, fa)
        if rev not in by or (a, blk, fa, ta) in done:
            continue
        done |= {(a, blk, fa, ta), rev}
        tb = by[rev]
        mutual = sorted(set(turns) & set(tb))
        if not mutual:
            continue
        runs, cur = [], [mutual[0]]
        for t in mutual[1:]:
            if t - cur[-1] <= 1 or stayed(b, a, blk, fa, ta, cur[-1], t):
                cur.append(t)
            else:
                runs.append(cur)
                cur = [t]
        runs.append(cur)
        for run in runs:
            sa = [x for t in range(run[0], run[-1] + 1) for x in turns.get(t, [])]
            sb = [x for t in range(run[0], run[-1] + 1) for x in tb.get(t, [])]
            on = (sum(x[4] == fa for x in sa) / len(sa), sum(x[4] == ta for x in sb) / len(sb))
            ma, mb = no_spend(sa), no_spend(sb)
            seen = sum(1 for x in sa + sb if x[2])
            n_turns = run[-1] - run[0] + 1
            cls = (seen == 0 and n_turns >= MIN_TURNS and min(len(sa), len(sb)) >= MIN_STOPS
                   and min(on) >= ON_CELL and min(ma, mb) >= NO_SPEND)
            out.append({"a": a, "b": blk, "fa": fa, "fb": ta, "turns": (run[0], run[-1]), "na": len(sa),
                        "nb": len(sb), "on": on, "tu": (ma, mb), "seen": seen, "cls": cls,
                        "src": (dict(collections.Counter(x[3] for x in sa)), dict(collections.Counter(x[3] for x in sb))),
                        "end": ending(b, a, blk, fa, ta, run[-1])})
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--arena", default="", help="папка с <метка>.rec.gz; пусто - рабочая папка стенда")
    a = ap.parse_args()
    arena = Path(a.arena) if a.arena else probe_work() / "arena"  # R-092: пустая строка - не текущая папка
    for label in a.labels:
        eps = [(k, e) for k, b in load(arena / (label + ".rec.gz")).items() for e in episodes(b)]
        cls = [x for x in eps if x[1]["cls"]]
        print(f"== {label}: эпизодов {len(eps)}, из них MUTUAL_BLOCKED_STEP {len(cls)}, "
              f"ходов в классе {sum(e['turns'][1] - e['turns'][0] + 1 for _, e in cls)}, "
              f"остановок в классе {sum(e['na'] + e['nb'] for _, e in cls)}")
        for k, e in sorted(eps, key=lambda x: (x[0], x[1]["turns"])):
            t0, t1 = e["turns"]
            ma, mb = e["tu"]
            print(f"  {'КЛАСС' if e['cls'] else '     '} {k.split()[0]} {e['a']}@{e['fa']} <-> {e['b']}@{e['fb']}: "
                  f"ходы {t0}-{t1} ({t1 - t0 + 1}), остановок {e['na']}/{e['nb']}, "
                  f"начато на клетке {e['on'][0]:.0%}/{e['on'][1]:.0%}, без траты ОВ {ma:.0%}/{mb:.0%}, "
                  f"увидел {e['seen']}")
            print(f"        src {e['a']}: {e['src'][0]}, {e['b']}: {e['src'][1]}; конец: {e['end']}")


if __name__ == "__main__":
    main()
