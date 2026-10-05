#!/usr/bin/env python3
"""MELEE_DIAGONAL_NO_LOF - пассивная перепись по архивам серий (второе мнение 02.10: MUTUAL_DIAGONAL_BLOCK -
NO GO как отдельное правило, корень изучать пассивно). Движок не трогает, игра не запускается.

Состояние S - решение юнита A на клетке P, у которого среди кандидатов атаки (AICAND acts) есть цель T на клетке
Q по диагонали (тот же этаж), рукопашная на T есть и вся с lof 0 (validMeleeRange ложен), выстрелов на T с lof 1
нет. Позиция цели - из самого кандидата ("to"), то есть та, которую знает ИИ.
W - в исполнении этого решения первый шаг упёрся в Q: walk.stop.unit P>Q ... buT или blockstep.suppressed в Q
-> none (V1).

Группа - (A, T, ход), считая с первого решения в S. Исход группы по решениям A после него в том же ходу:
  attacked  - атаковал T (base k=a, to = Q);
  moved     - ушёл с P (позиция решения или после исполнения не P);
  dropped   - решения ещё были, но последнее в ходу - уже не попытка в Q;
  held      - последнее решение A в ходу - снова попытка в Q (W) или S без хода.
Через ходы: подряд идущие группы W с исходом held на тех же P, Q - серия; чем кончилась (следующий ход A: attacked /
moved / dropped / до конца боя) и исход боя.

Для W ещё: откуда ход (base.src: firepoint, patrol.node, melee...), куда (base.to == Q - цель хода сама клетка
цели), ближайшая ли T из целей кандидатов (findFirePoint берёт ближайшего известного), видел ли (seen).

  py -3.13 tools/ai_speed/diag_nolof_census.py --arena E:/OXCE_AIWorker/results/arena c53s23 c53s24 ...
События - runs/diag_nolof_<метка>.tsv (группы), сводка - --summary <префикс>..."""
import argparse
import collections
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ENC_R, ENC_W, OUT  # noqa: E402

RX_STOP = re.compile(r"walk\.stop\.unit (\d+),(\d+),(\d+)>(\d+),(\d+),(\d+) d(\d)\b.*? bu(-?\d+)")
RX_SUPP = re.compile(r"blockstep\.suppressed d(\d) -> (none|d\d)")
# Pathfinding::dir_x / dir_y (src/Battlescape/Pathfinding.h), направление 0 - (0,-1), R-084
DIR = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
T_HIT = 10
SHOTS = (7, 8, 9)
COLS = ["label", "battle", "terrain", "how", "bturn", "side", "a", "t", "p", "q", "turn", "n_dec", "n_s", "n_w",
        "w_first", "outcome", "src", "to_q", "nearest", "seen", "run", "run_end"]


def diag(p, q):
    return abs(p[0] - q[0]) == 1 and abs(p[1] - q[1]) == 1 and p[2] == q[2]


def step(c, d):
    return (c[0] + DIR[d][0], c[1] + DIR[d][1], c[2])


def arena_rows(arena, label):
    out = {}
    with open(arena / f"{label}.tsv", encoding=ENC_R, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            out[f"seed={r['seed']} want={r['want']}"] = (r["how"], r["turn"], r["terrain"])
    return out


def load_rec(arena, label):
    """recs {(бой, rec): [ход, сторона, юнит, P, acts, k, to, src, после, seen, попытки {Q: T}]}, порядок решений
    юнитов в бою {(бой, юнит): [rec]} и для прохода по кандидатам (бой, acts) -> [rec]."""
    recs, order, byacts = {}, collections.defaultdict(list), collections.defaultdict(list)
    proc = subprocess.Popen(["gzip", "-dc", str(arena / f"{label}.rec.gz")], stdout=subprocess.PIPE)
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace")
        i = line.find("{")
        if i < 0:
            continue
        head = line[:i]
        if "[AIREC]" in head:
            r = json.loads(line[i:])
            b = head.split(" [", 1)[0]
            base = r.get("base") or {}
            acts = (r.get("cand") or {}).get("acts")
            to = tuple(base["to"]) if base.get("to") else None
            recs[(b, r["rec"])] = [r["turn"], r["side"], r["unit"], tuple(r["state"]["pos"]), acts, base.get("k"),
                                   to, base.get("src"), None, 0, {}]
            order[(b, r["unit"])].append(r["rec"])
            if acts:
                byacts[(b, acts)].append(r["rec"])
        elif "[AIEXEC]" in head:
            r = json.loads(line[i:])
            d = recs.get((head.split(" [", 1)[0], r["rec"]))
            if d is None:
                continue
            d[8] = tuple(r["pos"]) if r.get("pos") else None
            d[9] = r.get("seen", 0)
            for t in r.get("trail") or []:
                m = RX_STOP.search(t)
                if m:
                    g = list(map(int, m.groups()))
                    if tuple(g[0:3]) == d[3]:            # первый шаг с клетки решения
                        d[10][tuple(g[3:6])] = g[7]
                    continue
                m = RX_SUPP.search(t)
                if m and m.group(2) == "none":
                    d[10].setdefault(step(d[3], int(m.group(1))), None)
    proc.wait()
    return recs, order, byacts


def load_states(arena, label, recs, byacts):
    """{(бой, rec): {T: (Q, рукопашная, lof рукопашной, выстрел, lof выстрела, дальность)}} - только цели по
    диагонали; поиск идёт по строкам кандидатов с рукопашной (grep '"t":10,')."""
    out = {}
    cmd = f"gzip -dc '{arena / (label + '.cand.gz')}' | grep -F 'AICAND] acts=' | grep -F '\"t\":10,'"
    proc = subprocess.Popen(["bash", "-c", cmd], stdout=subprocess.PIPE)
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace")
        b, rest = line.split(" [", 1)
        h = rest[len("AICAND] acts="):].split(" ", 1)[0]
        ids = byacts.get((b, h))
        if not ids:
            continue
        lst = [x for x in json.loads(rest[rest.index(" list=") + 6:]) if x.get("k") == "a"]
        for rec in ids:
            p = recs[(b, rec)][3]
            tg = {}
            for x in lst:
                q = tuple(x["to"])
                e = tg.setdefault(x["u"], [q, 0, 0, 0, 0, max(abs(q[0] - p[0]), abs(q[1] - p[1]))])
                if x["t"] == T_HIT:
                    e[1] += 1
                    e[2] |= x["lof"] == 1
                elif x["t"] in SHOTS:
                    e[3] += 1
                    e[4] |= x["lof"] == 1
            near = min((e[5] for e in tg.values()), default=None)
            s = {u: (e[0], e[1], e[2], e[3], e[4], e[5] == near)
                 for u, e in tg.items() if diag(p, e[0]) and e[1] and not e[2] and not e[4]}
            if s:
                out[(b, rec)] = s
    proc.wait()
    return out


def census(arena, label):
    meta = arena_rows(arena, label)
    recs, order, byacts = load_rec(arena, label)
    states = load_states(arena, label, recs, byacts)
    groups = {}
    for (b, a), seq in order.items():
        byturn = collections.defaultdict(list)
        for rec in seq:
            byturn[recs[(b, rec)][0]].append(rec)
        for turn, rs in byturn.items():
            rs.sort()
            for i, rec in enumerate(rs):
                for t, (q, *_r, nearest) in states.get((b, rec), {}).items():
                    key = (b, a, t, turn)
                    if key in groups:
                        continue
                    groups[key] = classify(recs, states, b, a, t, q, rs[i:], nearest)
    rows = []
    for (b, a, t, turn), g in groups.items():
        how, bturn, terrain = meta.get(b, ("?", "?", "?"))
        d = recs[(b, g["first"])]
        rows.append({"label": label, "battle": b, "terrain": terrain, "how": how, "bturn": bturn, "side": d[1],
                     "a": a, "t": t, "p": ",".join(map(str, d[3])), "q": ",".join(map(str, g["q"])), "turn": turn,
                     "n_dec": g["n_dec"], "n_s": g["n_s"], "n_w": g["n_w"], "w_first": int(g["w_first"]),
                     "outcome": g["outcome"], "src": ";".join(f"{k}:{v}" for k, v in g["src"].most_common()),
                     "to_q": g["to_q"], "nearest": int(g["nearest"]), "seen": g["seen"], "run": 0, "run_end": ""})
    runs(rows, recs, order)
    path = OUT / f"diag_nolof_{label}.tsv"
    with open(path, "w", encoding=ENC_W, newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\")
        w.writeheader()
        w.writerows(rows)
    print(f"{label}: решений {len(recs)}, в S {len(states)}, групп {len(rows)}, из них с W "
          f"{sum(1 for r in rows if r['n_w'])} -> {path.name}", flush=True)


def classify(recs, states, b, a, t, q, rs, nearest):
    first = rs[0]
    p = recs[(b, first)][3]
    g = {"first": first, "q": q, "n_dec": len(rs), "n_s": 0, "n_w": 0, "w_first": False, "src": collections.Counter(),
         "to_q": 0, "nearest": nearest, "seen": 0, "outcome": "held"}
    last_w = False
    for j, rec in enumerate(rs):
        turn, side, unit, pos, acts, k, to, src, after, seen, tries = recs[(b, rec)]
        if k == "a" and to == q:
            g["outcome"] = "attacked"
            return g
        if pos != p:
            g["outcome"] = "moved"
            return g
        s = t in states.get((b, rec), {})
        w = q in tries and tries[q] in (t, None)
        g["n_s"] += s
        g["n_w"] += w
        if w:
            g["w_first"] |= j == 0
            g["src"][src] += 1
            g["to_q"] += to == q
            g["seen"] += bool(seen)
        last_w = w or s
        if after and after != p:
            g["outcome"] = "moved"
            return g
    g["outcome"] = "held" if last_w else "dropped"
    return g


def runs(rows, recs, order):
    """Серии ходов подряд с W и исходом held на тех же P, Q; чем кончились."""
    by = collections.defaultdict(dict)
    for r in rows:
        by[(r["battle"], r["a"], r["t"], r["p"], r["q"])][r["turn"]] = r
    for (b, a, t, p, q), tt in by.items():
        turns = sorted(tt)
        unit_turns = sorted({recs[(b, rec)][0] for rec in order[(b, a)]})
        i = 0
        while i < len(turns):
            j = i
            while j < len(turns) and tt[turns[j]]["n_w"] and tt[turns[j]]["outcome"] == "held" and \
                    (j == i or unit_turns.index(turns[j]) == unit_turns.index(turns[j - 1]) + 1):
                j += 1
            if j > i:
                last = turns[j - 1]
                k = unit_turns.index(last)
                if k + 1 >= len(unit_turns):
                    end = "battle_end"
                elif unit_turns[k + 1] in tt:
                    end = tt[unit_turns[k + 1]]["outcome"]
                else:
                    end = "free"                       # в следующем ходу состояния уже нет
                for x in turns[i:j]:
                    tt[x]["run"] = j - i
                    tt[x]["run_end"] = end
                i = j
            else:
                i += 1


def summary(prefixes):
    for pre in prefixes:
        R = []
        for path in sorted(OUT.glob(f"diag_nolof_{pre}*.tsv")):
            with open(path, encoding=ENC_R, newline="") as f:
                R += list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\"))
        if not R:
            continue
        print(f"=== {pre}: групп {len(R)}")
        for side in ("0", "1"):
            X = [r for r in R if r["side"] == side]
            W = [r for r in X if int(r["n_w"])]
            S = [r for r in X if not int(r["n_w"])]
            print(f"  сторона {side}: групп {len(X)} (W {len(W)}, без W {len(S)}); боёв {len({r['battle'] + r['label'] for r in X})}, "
                  f"карты {dict(collections.Counter(r['terrain'] for r in W).most_common(6))}")
            for name, Y in (("W", W), ("без W", S)):
                if not Y:
                    continue
                print(f"    {name}: исход {dict(collections.Counter(r['outcome'] for r in Y))}")
            if W:
                src = collections.Counter()
                for r in W:
                    for kv in filter(None, r["src"].split(";")):
                        k, v = kv.rsplit(":", 1)
                        src[k] += int(v)
                nw = sum(int(r["n_w"]) for r in W)
                print(f"    W: попыток {nw}, с первого решения {sum(int(r['w_first']) for r in W)} групп; цель хода = клетка "
                      f"цели {sum(int(r['to_q']) for r in W)}; T ближайшая {sum(int(r['nearest']) for r in W)} групп; "
                      f"видел {sum(int(r['seen']) for r in W)}")
                print(f"    W: откуда ход {dict(src.most_common(8))}")
                chain = collections.Counter(min(int(r['n_w']), 20) // 5 * 5 for r in W)
                print(f"    W: попыток за ход (корзины по 5, 20 = 20+) {dict(sorted(chain.items()))}")
                runs_ = {(r["label"], r["battle"], r["a"], r["t"], r["p"], r["q"], r["run_end"]): int(r["run"])
                         for r in W if int(r["run"])}
                rl = collections.Counter(min(v, 10) for v in runs_.values())
                ends = collections.Counter(k[6] for k in runs_)
                print(f"    серии held (ходов подряд, 10 = 10+): {dict(sorted(rl.items()))}; конец {dict(ends)}")
                bad = [(k, v) for k, v in runs_.items() if k[6] == "battle_end" or v >= 3]
                for k, v in sorted(bad, key=lambda x: -x[1])[:12]:
                    hw = next(r for r in W if (r["label"], r["battle"], r["a"], r["t"]) == k[:4])
                    print(f"      {k[0]} {k[1].split()[0]} {hw['terrain']} {k[2]}@{k[4]} -> {k[3]}@{k[5]}: {v} ходов, "
                          f"конец {k[6]}, бой {hw['how']}/{hw['bturn']}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser()
    ap.add_argument("--arena", default="E:/OXCE_AIWorker/results/arena")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("labels", nargs="+")
    a = ap.parse_args()
    if a.summary:
        summary(a.labels)
        return
    for label in a.labels:
        census(Path(a.arena), label)


if __name__ == "__main__":
    main()
