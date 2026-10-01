#!/usr/bin/env python3
"""REPEATED_BLOCKED_STEP - судьба повторных остановок первого шага, пассивно по записи серии (второе мнение 01.10).

Правило-кандидат не знает второго юнита: только «мой первый шаг A->B уже N раз подряд упёрся в юнита»
(walk.stop.unit A>B, где A - клетка начала решения). Вопрос до кода: как часто после N-й остановки клетка B
освобождается сама - тогда подавление после N слишком рано. Цепочка юнита: решения подряд, начатые на A, с остановкой
первого шага A->B; решение на A без ходьбы (поворот, выстрел, конец) цепочку не рвёт, другой первый шаг - рвёт.

Для каждой цепочки, дошедшей до N, после N-й остановки:
  free_next  - к следующему решению юнита блокирующий уже не на B (тот же шаг прошёл бы);
  free_turn  - освободил B до конца того же хода юнита;
  free_next_turn - к первому решению юнита в следующем ходу;
  чем кончилась цепочка: ушёл с A, когда B свободна (успех) / ушёл с A в обход, B занята (обход) /
  до конца записи на A (упёрся до конца) / другой первый шаг с A (сменил шаг).
Где стоит блокирующий - по его собственным решениям (позиция в начале и после, AIEXEC pos): между своими решениями
юнит не двигается. Ревизию известного ИИ (AiProbe::knownRevision) запись не несёт - условие «известное не менялось»
здесь не проверяется, числа - верхняя граница того, что поймает правило с этим условием.

  py -3.13 tools/ai_speed/blocked_repeat.py --arena E:/OXCE_AIWorker/results/arena b46fp23 b46fp24 b46fp29 b46fp30"""
import argparse
import collections
import gzip
import json
import re
import sys
from pathlib import Path

from _common import probe_work

RX = re.compile(r"walk\.stop\.unit (\d+,\d+,\d+)>(\d+,\d+,\d+) .* bu(\d+)")
NS = (1, 2, 3, 5)
HOSTILE = 1000000  # id врага у стенда; меньше - бот (сторона игрока)


def cell(p):
    return ",".join(str(x) for x in p)


def load(path):
    """бой -> {rec: решение}; решение - ход, юнит, клетка начала, клетка после, остановки первого шага и прочие"""
    B = collections.defaultdict(dict)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if "{" not in line:
                continue
            head = line[:line.index("{")]
            key = head.split(" [", 1)[0]
            if "[AIREC]" in head:
                r = json.loads(line[line.index("{"):])
                d = B[key].setdefault(r["rec"], {})
                d.update(turn=r["turn"], unit=r["unit"], start=cell(r["state"]["pos"]),
                         src=(r.get("base") or {}).get("src"))
            elif "[AIEXEC]" in head:
                r = json.loads(line[line.index("{"):])
                d = B[key].setdefault(r["rec"], {})
                d["end"] = cell(r["pos"]) if r.get("pos") else None
                d["walk"] = r.get("walk")
                d["stops"] = [(m.group(1), m.group(2), int(m.group(3)), r.get("seen")) for m in
                              (RX.search(t) for t in r.get("trail") or []) if m]
    return B


def where(timeline, rec):
    """позиция юнита в момент rec: по последнему его решению до rec (после - конец, иначе начало)"""
    pos = None
    for r, d in timeline:
        if r >= rec:
            if pos is None:
                pos = d.get("start")
            break
        pos = d.get("end") or d.get("start")
    return pos


def chains(B):
    """все цепочки боя: (юнит, A, B, блокирующий, [rec остановок], исход, решения юнита после последней остановки)"""
    out = []
    by_unit = collections.defaultdict(list)
    for rec in sorted(B):
        d = B[rec]
        if "unit" in d:
            by_unit[d["unit"]].append((rec, d))
    for unit, tl in by_unit.items():
        cur = None
        for i, (rec, d) in enumerate(tl):
            first = [s for s in d.get("stops", []) if s[0] == d["start"]]
            if first:
                a, b, blk, seen = first[0]
                if cur and (cur["A"], cur["B"]) == (a, b):
                    cur["stops"].append((rec, d["turn"], blk, seen))
                    continue
                if cur:
                    cur["end"] = "сменил шаг" if cur["A"] == a else "ушёл с A"
                    out.append(cur)
                cur = {"unit": unit, "A": a, "B": b, "stops": [(rec, d["turn"], blk, seen)], "end": None, "tl": tl}
                continue
            if not cur:
                continue
            if d["start"] != cur["A"]:
                cur["end"] = "ушёл с A"
                out.append(cur)
                cur = None
                continue
            if d.get("end") and d["end"] != cur["A"]:
                bt = by_unit.get(cur["stops"][-1][2], [])
                cur["end"] = ("ушёл, блокирующий без решений" if not bt else
                              "ушёл, B свободна" if where(bt, rec) != cur["B"] else "ушёл в обход, B занята")
                out.append(cur)
                cur = None
        if cur:
            cur["end"] = "до конца записи на A"
            out.append(cur)
    for c in out:
        c["by_blk"] = by_unit.get(c["stops"][0][2], [])
    return out


def after_n(c, n):
    """после n-й остановки: блокирующий ушёл с B к следующему решению юнита / до конца хода / к следующему ходу"""
    rec_n, turn_n, blk, _ = c["stops"][n - 1]
    tl, bt = c["tl"], c["by_blk"]
    if not bt:  # блокирующий сам не решает (не ИИ) - где он стоит, запись не знает
        return None
    later = [(r, d) for r, d in tl if r > rec_n]
    # следующее решение юнита в том же ходу и первое в следующем: свободна ли B к нему
    st = next(((r, d) for r, d in later if d["turn"] == turn_n), None)
    nt = next(((r, d) for r, d in later if d["turn"] > turn_n), None)
    free_same = bool(st) and where(bt, st[0]) != c["B"]
    free_nt = bool(nt) and where(bt, nt[0]) != c["B"]
    return free_same, bool(st), free_nt, bool(nt)


def ally(c):
    """блокирующий своей стороны (id по одну сторону от HOSTILE)"""
    return (c["unit"] >= HOSTILE) == (c["stops"][0][2] >= HOSTILE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--arena", default="", help="папка серий (пусто - рабочая папка стенда)")
    a = ap.parse_args()
    arena = Path(a.arena) if a.arena else probe_work() / "arena"
    sys.stdout.reconfigure(encoding="utf-8")
    allc = []
    for lab in a.labels:
        B = load(arena / f"{lab}.rec.gz")
        n_b = 0
        for battle, recs in B.items():
            cs = chains(recs)
            for c in cs:
                c["battle"] = f"{lab} {battle}"
            allc += cs
            n_b += 1
        print(f"{lab}: боёв {n_b}", flush=True)
    groups = (("все", lambda c: True),
              ("бот, блокирует чужой", lambda c: c["unit"] < HOSTILE and not ally(c)),
              ("бот, блокирует свой", lambda c: c["unit"] < HOSTILE and ally(c)),
              ("враг, блокирует чужой", lambda c: c["unit"] >= HOSTILE and not ally(c)),
              ("враг, блокирует свой", lambda c: c["unit"] >= HOSTILE and ally(c)))
    for side, pick in groups:
        cs = [c for c in allc if pick(c)]
        print(f"\n== {side}: цепочек {len(cs)}, остановок первого шага {sum(len(c['stops']) for c in cs)}; "
              f"увидел блокирующего хоть раз в {sum(any(s[3] for s in c['stops']) for c in cs)}")
        if not cs:
            continue
        print("N | цепочек >=N | остановок после N-й (что сняло бы подавление) | B свободна к след. решению в том же ходу | "
              "к первому решению след. хода | исходы цепочек")
        for n in NS:
            cn = [c for c in cs if len(c["stops"]) >= n]
            if not cn:
                print(f"{n} | 0")
                continue
            fn = [f for f in (after_n(c, n) for c in cn) if f]
            ends = collections.Counter(c["end"] for c in cn)

            def share(i, j):
                k, m = sum(f[i] for f in fn), sum(f[j] for f in fn)
                return f"{k}/{m} = {100 * k / m:.0f} %" if m else "-"
            print(f"{n} | {len(cn)} | {sum(len(c['stops']) - n for c in cn)} | {share(0, 1)} | {share(2, 3)} | "
                  + ", ".join(f"{k} {v}" for k, v in ends.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
