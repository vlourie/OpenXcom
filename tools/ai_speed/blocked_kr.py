#!/usr/bin/env python3
"""REPEATED_BLOCKED_STEP_V1 - проверка безопасности подавления по ревизии известного (второе мнение 01.10).

Правило-кандидат: после walk.stop.unit A>B юнит в том же своём ходу, стоя на A, не выбирает первый шаг A->B, пока
ревизия известного ИИ (AiProbe::knownRevision) та же, что в момент остановки. Безопасно, только если такой шаг при
неизменной ревизии потом ни разу не прошёл. Запись build-ai48 и новее несёт для этого (только для юнитов, у которых
в этом ходу уже была остановка, стоя на её клетке):
  walk.stop.unit ... bu<id> kr<ревизия>  - ревизия в момент остановки;
  kr.dec <ревизия>                       - ревизия в начале следующего решения (первый элемент следа [AIEXEC]);
  walk.first d<направление>              - первый шаг запланированного пути (d у остановки - тот же счёт направлений).

Каждое такое решение (память - последняя остановка юнита в этом ходу на клетке начала решения):
  та же ревизия, тот же первый шаг, снова остановлен юнитом - подавление сберегло бы ходьбу;
  та же ревизия, тот же первый шаг, прошёл (ушёл с A, остановки A>B нет) - ЛОЖНОЕ подавление, обязано быть 0;
  та же ревизия, другой шаг или не ходил - правило не меняет выбор;
  ревизия другая - правило память снимает.

  py -3.13 tools/ai_speed/blocked_kr.py --arena E:/OXCE_AIWorker/results/arena b48kr1"""
import argparse
import collections
import gzip
import json
import re
import sys
from pathlib import Path

import blocked_repeat as br
from _common import probe_work

STOP = re.compile(r"walk\.stop\.unit (\d+,\d+,\d+)>(\d+,\d+,\d+) d(\d+) .* bu(\d+) kr([0-9a-f]+)")
HOSTILE = 1000000


def cell(p):
    return ",".join(str(x) for x in p)


def load(path):
    """бой -> {rec: решение}: ход, юнит, клетка начала и после, остановки юнитом, kr.dec, первый шаг"""
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
                d.update(turn=r["turn"], unit=r["unit"], start=cell(r["state"]["pos"]), tu=r["state"].get("tu"),
                         src=(r.get("base") or {}).get("src"))
            elif "[AIEXEC]" in head:
                r = json.loads(line[line.index("{"):])
                d = B[key].setdefault(r["rec"], {})
                d["end"] = cell(r["pos"]) if r.get("pos") else None
                trail = r.get("trail") or []
                d["stops"] = [(m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), m.group(5))
                              for m in (STOP.search(t) for t in trail) if m]
                d["krdec"] = next((t.split()[1] for t in trail if t.startswith("kr.dec ")), None)
                d["first"] = next((int(t.split()[1][1:]) for t in trail if t.startswith("walk.first ")), None)
    return B


def group(src):
    """источник хода решения -> группа для сводки"""
    src = src or "?"
    for g in ("firepoint", "escape", "ambush", "melee"):
        if src.startswith(g):
            return g
    return "patrol" if src.startswith("patrol") else "прочие"


def classify(recs):
    """решения под памятью: (класс, юнит, память остановки, источник хода решения)"""
    out = []
    mem = {}  # юнит -> (ход, A, B, d, блокирующий, kr) последней остановки
    for rec in sorted(recs):
        d = recs[rec]
        if "unit" not in d:
            continue
        u = d["unit"]
        m = mem.get(u)
        if m and m[0] == d["turn"] and m[1] == d["start"]:
            if d.get("krdec") is None:
                out.append(("нет kr.dec (запись без прибора?)", u, m))
            elif d["krdec"] != m[5]:
                passed = (d.get("first") == m[3] and not any(s[0] == m[1] and s[1] == m[2] for s in d.get("stops", []))
                          and d.get("end") and d["end"] != m[1])
                out.append(("ревизия другая, тот же шаг ПРОШЁЛ" if passed else "ревизия другая, не прошёл тем же шагом", u, m))
            elif d.get("first") != m[3]:
                out.append(("та же ревизия, другой шаг или не ходил", u, m))
            elif any(s[0] == m[1] and s[1] == m[2] for s in d.get("stops", [])):
                out.append(("та же ревизия, тот же шаг, снова остановлен - сберегло бы", u, m))
            elif d.get("end") and d["end"] != m[1]:
                out.append(("та же ревизия, тот же шаг, ПРОШЁЛ - ложное подавление", u, m))
            else:
                out.append(("та же ревизия, тот же шаг, остался на A по другой причине", u, m))
            out[-1] = out[-1] + (d.get("src"),)
        for a, b, dr, blk, kr in d.get("stops", []):
            if a == d["start"]:  # остановка первого шага: память юнита на этот ход
                mem[u] = (d["turn"], a, b, dr, blk, kr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--arena", default="", help="папка серий (пусто - рабочая папка стенда)")
    a = ap.parse_args()
    arena = Path(a.arena) if a.arena else probe_work() / "arena"
    sys.stdout.reconfigure(encoding="utf-8")
    total = collections.Counter()
    side = collections.Counter()
    false_ = []
    n_stops = 0
    cand_src = collections.Counter()
    cand_raw = collections.Counter()
    accum = collections.Counter()
    for lab in a.labels:
        B = load(arena / f"{lab}.rec.gz")
        for battle, recs in B.items():
            n_stops += sum(len(d.get("stops", [])) for d in recs.values())
            per_turn = collections.defaultdict(set)  # (юнит, ход, A) -> остановленные первые шаги
            for d in recs.values():
                for st in d.get("stops", []):
                    if "unit" in d and st[0] == d["start"]:
                        per_turn[d["unit"], d["turn"], st[0]].add(st[2])
            for v in per_turn.values():
                accum[min(len(v), 3)] += 1
            for cls, u, m, src in classify(recs):
                total[cls] += 1
                if cls.startswith("та же ревизия, тот же шаг"):
                    cand_src[group(src)] += 1
                    cand_raw[src] += 1
                side[("бот" if u < HOSTILE else "враг") + (" / свой" if (u >= HOSTILE) == (m[4] >= HOSTILE) else " / чужой"), cls] += 1
                if "ложное" in cls:
                    false_.append(f"{lab} {battle} юнит {u} ход {m[0]} {m[1]} > {m[2]} блок {m[4]}")
        print(f"{lab}: боёв {len(B)}", flush=True)
    print(f"\nостановок юнитом с kr: {n_stops}; решений под памятью: {sum(total.values())}")
    for k, v in total.most_common():
        print(f"  {v:7d}  {k}")
    print("\nпо сторонам (юнит / блокирующий):")
    for (s, k), v in sorted(side.items()):
        print(f"  {s:14s} {v:7d}  {k}")
    print(f"\nложных подавлений: {len(false_)}")
    for x in false_[:50]:
        print("  " + x)
    # прежний замер blocked_repeat: B свободна к следующему решению юнита в том же ходу после 1-й остановки - чем
    # объясняется по kr (снята память или ревизия та же)
    expl = collections.Counter()
    for lab in a.labels:
        K = load(arena / f"{lab}.rec.gz")
        for battle, recs in br.load(arena / f"{lab}.rec.gz").items():
            for c in br.chains(recs):
                r = br.after_n(c, 1)
                if not (r and r[0]):
                    continue
                rec1, turn1 = c["stops"][0][0], c["stops"][0][1]
                nxt = next((rr for rr, d in c["tl"] if rr > rec1 and d["turn"] == turn1), None)
                d = K[battle].get(nxt, {})
                st = [s for s in K[battle][rec1].get("stops", []) if s[0] == c["A"] and s[1] == c["B"]]
                if d.get("krdec") is None or not st:
                    expl["нет kr.dec (решение не на A)"] += 1
                elif st[0][4] != d["krdec"]:
                    expl["ревизия другая"] += 1
                elif d.get("first") != st[0][2]:
                    expl["ревизия та же, выбрал другой шаг или не ходил"] += 1
                elif any(s[0] == c["A"] and s[1] == c["B"] for s in d.get("stops", [])):
                    expl["ревизия та же, тот же шаг снова остановлен"] += 1
                else:
                    expl["ревизия та же, тот же шаг ПРОШЁЛ"] += 1
    same = [k for k in total if k.startswith("та же ревизия, тот же шаг")]
    print("\nсводка для второго мнения:")
    print(f"  memory_candidates (та же ревизия и тот же первый шаг): {sum(total[k] for k in same)}")
    print(f"  false_suppressions: {len(false_)}")
    print(f"  invalidated_before_retry (B свободна к следующему решению того же хода, blocked_repeat): "
          f"{expl['ревизия другая']} из {sum(expl.values())}  {dict(expl)}")
    print(f"  same_turn_success_after_changed_kr: {total['ревизия другая, тот же шаг ПРОШЁЛ']}"
          f" из {total['ревизия другая, тот же шаг ПРОШЁЛ'] + total['ревизия другая, не прошёл тем же шагом']}")
    print("\nmemory_candidates по источнику хода: " + ", ".join(f"{k} {v}" for k, v in cand_src.most_common()))
    print("  подробно: " + ", ".join(f"{k} {v}" for k, v in cand_raw.most_common()))
    print("ходов юнита с остановленными первыми шагами с одной клетки, разных шагов: "
          + ", ".join(f"{'3+' if k == 3 else k} - {accum[k]}" for k in sorted(accum)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
