#!/usr/bin/env python3
"""Парная проверка REPEATED_BLOCKED_STEP_V1 по исходу боя (второе мнение 01.10, п. 17.4, ожидание 2) - пассивно.

Пары серий одной сборки и одной машины: база с OXCE_AI_BLOCKED_STEP=0 и вариант с =1, те же зёрна. Каждый бой - «затронут»
или «не затронут» правилом; исход (how, turn, outcome, потери) сравнивается по ключу seed= want=: сдвиг допустим только
у затронутых, у незатронутых исход обязан совпасть - иначе расследовать сам V1 (развилка или побочка), а не читать результат.

«Затронут» - по правилу движка, а не по упрощению blocked_kr (там память только у остановки на первом шаге решения,
а движок помнит любую): AiProbe::blockedStepStop (UnitWalkBState, остановка юнитом) запоминает клетку, где юнит встал,
ход и ревизию известного, та же клетка, ход и ревизия - добавить направление; blockedStepDecide стирает память при
другом ходе, клетке или ревизии в начале решения; blockedStepPlan подавляет, если первый шаг пути из запомненных.
  по базе (=0): правило симулируется по записи - решение, которое V1 подавил бы (memo_base);
  по варианту (=1): настоящие blockstep.suppressed в следе (supp_var).
До первого подавления пара обязана идти байт в байт, поэтому оба признака обязаны совпасть (столбец agree), а
незатронутый бой - совпасть во всех потоках rec, cand, tiles, path после вырезки шума флага (cfg, значение флага в
заголовке, элементы следа blockstep.*; столбец streams_differ); а не только по исходу.

Пункт 9 вердикта - два разных явления:
  repeat - физический повтор: решение под памятью снова остановлено юнитом на том же шаге (V1 обязан срезать до 0);
  goal_repeat - повторный выбор той же цели: решение того же юнита в том же ходу с той же base.to, что у предыдущего,
    сорванного остановкой юнитом (V1 этого не обещает: он меняет первый шаг, а не цель).

  py -3.13 tools/ai_speed/blocked_pair.py --arena E:/OXCE_AIWorker/results/arena c53s23:v53s23 c53s24:v53s24 --show 1157,1460
Построчно - runs/blocked_pair.tsv.
"""
import argparse
import collections
import csv
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import probe_work  # noqa: E402
import series_eq  # noqa: E402

# шум флага в потоках пары: cfg записи, значение флага в заголовке, элементы следа прибора V1
FLAG_NOISE = r'"cfg":"[0-9a-f]+",|"OXCE_AI_BLOCKED_STEP":"[01]",|,"blockstep[^"]*"|"blockstep[^"]*",?'
STREAMS = (".rec.gz", ".cand.gz", ".tiles.gz", ".path.gz")

OUT = Path(__file__).resolve().parent / "runs"
COLS = ("how", "turn", "outcome", "pdead", "hdead", "livesoldiers", "livealiens")
STOP = re.compile(r"walk\.stop\.unit (\d+,\d+,\d+)>(\d+,\d+,\d+) d(\d+) .* kr([0-9a-f]+)")


def table(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {(r["seed"], r["want"]): r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}


def key_of(head):
    """начало строки 'seed=N want=X [..' -> (N, X)"""
    f = dict(p.split("=", 1) for p in head.split(" [", 1)[0].split() if "=" in p)
    return f.get("seed"), f.get("want")


def cell(p):
    return ",".join(str(x) for x in p)


def load(path):
    """бой -> {rec: решение}: ход, юнит, клетка начала, цель, остановки юнитом, kr.dec, первый шаг, подавлений"""
    B = collections.defaultdict(dict)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if "{" not in line:
                continue
            head = line[:line.index("{")]
            if "[AIREC]" in head:
                r = json.loads(line[line.index("{"):])
                d = B[key_of(head)].setdefault(r["rec"], {})
                base = r.get("base") or {}
                d.update(turn=r["turn"], unit=r["unit"], start=cell(r["state"]["pos"]),
                         to=cell(base["to"]) if base.get("to") else None)
            elif "[AIEXEC]" in head:
                r = json.loads(line[line.index("{"):])
                d = B[key_of(head)].setdefault(r["rec"], {})
                trail = r.get("trail") or []
                d["stops"] = [(m.group(1), m.group(2), int(m.group(3)), m.group(4))
                              for m in (STOP.search(t) for t in trail) if m]
                d["krdec"] = next((t.split()[1] for t in trail if t.startswith("kr.dec ")), None)
                d["first"] = next((int(t.split()[1][1:]) for t in trail if t.startswith("walk.first ")), None)
                d["supp"] = sum(t.startswith("blockstep.suppressed") for t in trail)
    return B


def simulate(recs):
    """(решений, которые V1 подавил бы; из них снова остановлены тем же шагом; повторов цели после сорванного хода;
    подавлений по следу; первое решение под правилом)"""
    mem = {}   # юнит -> [ход, клетка, ревизия, направления]
    last = {}  # юнит -> (ход, цель) последнего решения, сорванного остановкой юнитом
    would = repeat = goal = supp = 0
    first_rec = None
    for rec in sorted(recs):
        d = recs[rec]
        if "unit" not in d:
            continue
        u = d["unit"]
        supp += d.get("supp", 0)
        m = mem.get(u)
        if m and (m[0] != d["turn"] or m[1] != d["start"] or m[2] != d.get("krdec")):
            del mem[u]
            m = None
        if m and d.get("first") in m[3]:
            would += 1
            first_rec = rec if first_rec is None else first_rec
            if any(s[0] == m[1] and s[2] == d["first"] for s in d.get("stops", [])):
                repeat += 1
        lg = last.pop(u, None)
        if lg and lg[0] == d["turn"] and d.get("to") is not None and lg[1] == d["to"]:
            goal += 1
        for a, b, dr, kr in d.get("stops", []):
            m = mem.get(u)
            if m and m[0] == d["turn"] and m[1] == a and m[2] == kr:
                if dr not in m[3]:
                    m[3].append(dr)
            else:
                mem[u] = [d["turn"], a, kr, [dr]]
        if d.get("stops"):
            last[u] = (d["turn"], d.get("to"))
    return would, repeat, goal, supp, first_rec


def shift(b, v):
    if all(b[c] == v[c] for c in COLS):
        return "same"
    if b["how"] == "timeout" and v["how"] != "timeout":
        return "timeout->over"
    if b["how"] != "timeout" and v["how"] == "timeout":
        return "over->timeout"
    return "outcome" if b["outcome"] != v["outcome"] else "turn/losses"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pairs", nargs="+", help="база:вариант")
    ap.add_argument("--arena", default="", help="папка серий (пусто - рабочая папка стенда)")
    ap.add_argument("--show", default="", help="зёрна через запятую - напечатать бои подробно")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    arena = Path(a.arena) if a.arena else probe_work() / "arena"
    show = set(a.show.split(",")) if a.show else set()
    rows, summary = [], collections.Counter()
    for pair in a.pairs:
        base, var = pair.split(":")
        B, V = table(arena / f"{base}.tsv"), table(arena / f"{var}.tsv")
        sb = {k: simulate(r) for k, r in load(arena / f"{base}.rec.gz").items()}
        sv = {k: simulate(r) for k, r in load(arena / f"{var}.rec.gz").items()}
        div = collections.defaultdict(list)  # бой -> потоки, разошедшиеся после вырезки шума флага
        for ext in STREAMS:
            ha, hb = series_eq.stream(arena / f"{base}{ext}", FLAG_NOISE), series_eq.stream(arena / f"{var}{ext}", FLAG_NOISE)
            if ha is None or hb is None:
                print(f"{pair}: нет {ext} у {base if ha is None else var}")
                continue
            for kk in set(ha[0]) | set(hb[0]):
                if ha[0].get(kk) != hb[0].get(kk):
                    div[kk].append(ext.split(".")[1])
        for k in sorted(set(B) | set(V)):
            if k not in B or k not in V:
                print(f"НЕТ БОЯ {k} в {base if k not in B else var}")
                summary["нет пары"] += 1
                continue
            wb, rb, gb, _, fb = sb.get(k, (0, 0, 0, 0, None))
            wv, rv, gv, pv, _ = sv.get(k, (0, 0, 0, 0, None))
            aff = "yes" if wb else "no"
            s = shift(B[k], V[k])
            summary[aff, s] += 1
            rows.append({"pair": pair, "seed": k[0], "want": k[1], "affected": aff, "agree": int(bool(wb) == bool(pv)),
                         "memo_base": wb, "first_rec": fb if fb is not None else "", "supp_var": pv,
                         "repeat_base": rb, "repeat_var": rv, "goal_repeat_base": gb, "goal_repeat_var": gv, "shift": s,
                         "streams_differ": ",".join(div.get(k, [])),
                         **{f"b_{c}": B[k][c] for c in COLS}, **{f"v_{c}": V[k][c] for c in COLS}})
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "blocked_pair.tsv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    dis = [r for r in rows if not r["agree"]]
    print(f"боёв в парах: {len(rows)}; затронуты V1 (симуляция по базе): {sum(r['affected'] == 'yes' for r in rows)}; "
          f"подавления в варианте: {sum(r['supp_var'] > 0 for r in rows)}; признаки не совпали: {len(dis)}")
    for r in dis[:20]:
        print(f"  НЕ СОВПАЛИ {r['pair']} {r['seed']} {r['want']}: база бы подавила {r['memo_base']}, вариант подавил {r['supp_var']}")
    for aff in ("yes", "no"):
        g = [r for r in rows if r["affected"] == aff]
        print(f"  affected={aff}: {len(g)} боёв - " + ", ".join(f"{kk[1]} {v}" for kk, v in sorted(summary.items())
                                                             if kk[0] == aff))
        print(f"    timeout база {sum(r['b_how'] == 'timeout' for r in g)}, вариант {sum(r['v_how'] == 'timeout' for r in g)};"
              f" физических повторов шага база {sum(r['repeat_base'] for r in g)}, вариант {sum(r['repeat_var'] for r in g)};"
              f" повторов цели после срыва база {sum(r['goal_repeat_base'] for r in g)}, вариант {sum(r['goal_repeat_var'] for r in g)}")
    sd = [r for r in rows if r["affected"] == "no" and r["streams_differ"]]
    print(f"потоки разошлись у незатронутых: {len(sd)} (rec, cand, tiles, path без шума флага)"
          + "".join(f"\n  {r['pair']} {r['seed']} {r['want']}: {r['streams_differ']}" for r in sd[:20]))
    print(f"затронутые без расхождения rec: {sum(r['affected'] == 'yes' and 'rec' not in r['streams_differ'] for r in rows)}")
    changed_no = [r for r in rows if r["affected"] == "no" and r["shift"] != "same"]
    print(f"исход сменился у незатронутых: {len(changed_no)}"
          + ("".join(f"\n  {r['pair']} {r['seed']} {r['want']}: {r['shift']} "
                     f"{r['b_how']}/{r['b_turn']}/{r['b_outcome']} -> {r['v_how']}/{r['v_turn']}/{r['v_outcome']}"
                     for r in changed_no)))
    # сводка по паре и гейты приёмки (второе мнение 02.10): предсказание по базе = подавления варианта, ни ложных,
    # ни пропущенных; у незатронутых все четыре потока одинаковы
    summ = []
    for pair in a.pairs + ["ИТОГО"]:
        g = [r for r in rows if pair in ("ИТОГО", r["pair"])]
        un = [r for r in g if r["affected"] == "no"]
        summ.append({
            "pair": pair, "battles": len(g),
            "predicted_affected": sum(r["memo_base"] > 0 for r in g),
            "actual_suppressed": sum(r["supp_var"] > 0 for r in g),
            "false_positive": sum(r["memo_base"] > 0 and not r["supp_var"] for r in g),
            "false_negative": sum(not r["memo_base"] and r["supp_var"] > 0 for r in g),
            "unaffected_stream_diff": sum(bool(r["streams_differ"]) for r in un),
            "unaffected_outcome_diff": sum(r["shift"] != "same" for r in un),
            "phys_repeat": f"{sum(r['repeat_base'] for r in g)}->{sum(r['repeat_var'] for r in g)}",
            "goal_repeat": f"{sum(r['goal_repeat_base'] for r in g)}->{sum(r['goal_repeat_var'] for r in g)}",
            "timeout": f"{sum(r['b_how'] == 'timeout' for r in g)}->{sum(r['v_how'] == 'timeout' for r in g)}",
            "timeout_to_over": sum(r["shift"] == "timeout->over" for r in g),
            "over_to_timeout": sum(r["shift"] == "over->timeout" for r in g),
            "outcome_changed": sum(r["b_outcome"] != r["v_outcome"] for r in g),
            "deaths_changed": sum(r["b_pdead"] != r["v_pdead"] or r["b_hdead"] != r["v_hdead"] for r in g),
        })
    with open(OUT / "blocked_pair_summary.tsv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0]), delimiter="\t")
        w.writeheader()
        w.writerows(summ)
    print("\n" + "\t".join(summ[0]))
    for s_ in summ:
        print("\t".join(str(x) for x in s_.values()))
    t = summ[-1]
    gates = {"predicted == actual": t["predicted_affected"] == t["actual_suppressed"],
             "false_positive 0": t["false_positive"] == 0, "false_negative 0": t["false_negative"] == 0,
             "unaffected streams identical": t["unaffected_stream_diff"] == 0}
    print("ГЕЙТЫ: " + ", ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in gates.items()))
    for r in rows:
        if r["seed"] in show:
            print(f"бой {r['seed']} {r['want']} ({r['pair']}): affected={r['affected']} подавил бы {r['memo_base']} "
                  f"(первое rec {r['first_rec']}), подавлено {r['supp_var']}; повтор шага {r['repeat_base']} -> {r['repeat_var']},"
                  f" повтор цели {r['goal_repeat_base']} -> {r['goal_repeat_var']};"
                  f" {r['b_how']}/{r['b_turn']}/{r['b_outcome']} -> {r['v_how']}/{r['v_turn']}/{r['v_outcome']}")
    print(f"построчно: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
