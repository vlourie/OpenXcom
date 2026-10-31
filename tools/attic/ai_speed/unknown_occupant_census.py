#!/usr/bin/env python3
"""AI_UNKNOWN_OCCUPANT_PATH_STALL - пассивная перепись по архивам серий (второе мнение 02.10 по п. 17.11: корень -
маршрут через клетку юнита, которого Pathfinding::isBlocked считает свободной). Движок не трогает, игра не
запускается.

isBlocked (Pathfinding.cpp, O_FLOOR): юнит в клетке - препятствие для своей фракции всегда; для бота (FACTION_PLAYER) -
если u->getVisible() (виден стороне игрока); для врага (FACTION_HOSTILE) - если u в getUnitsSpottedThisTurn() ЭТОГО
юнита. Значит, каждый walk.stop.unit на чужом юните - по определению шаг в клетку, которую план считал свободной.

Событие - walk.stop.unit в исполнении решения (AIEXEC trail): с клетки F в клетку Q, блокер buT, knownRevision kr.
  первый шаг - F == клетка решения, иначе mid-path;
  goal=Q - цель хода (base.to) сама клетка Q;
  known - T среди кандидатов атаки этого решения (AICAND, k=a): сторона знала T иначе, чем через isBlocked;
  known_pos - и позиция кандидата == Q.
Подавление V1 (blockstep.suppressed dN -> none) в ту же клетку - попытка без шага, считается к эпизоду.

Эпизод - (бой, юнит, ход, Q). Исход в ходу по решениям юнита после первой попытки:
  moved  - юнит ушёл с клетки первой попытки (позиция решения или после исполнения другая);
  held   - не ушёл, и последнее решение в ходу - снова попытка в Q;
  stayed - не ушёл, но последнее решение - другое (выстрел, ожидание и т.п.).
Повтор - попыток (шагов + подавлений V1) в эпизоде >= 2. Серия - эпизоды на той же (юнит, F, Q) в ходы юнита подряд;
чем кончилась: battle_end (до конца боя) или free (в следующем ходу юнита эпизода уже нет).

  py -3.13 tools/ai_speed/unknown_occupant_census.py --arena E:/OXCE_AIWorker/results/arena c53s23 ...
События - runs/unknown_occ_<метка>.tsv (эпизоды), сводка - --summary <префикс>..."""
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

RX_STOP = re.compile(r"walk\.stop\.unit (\d+),(\d+),(\d+)>(\d+),(\d+),(\d+) d(\d)\b.*? bu(-?\d+)(?: kr([0-9a-f]+))?")
RX_SUPP = re.compile(r"blockstep\.suppressed d(\d) -> none")
RX_STATE = re.compile(r"unit=(\d+) type=\S+ faction=(\d)")
# Pathfinding::dir_x / dir_y (src/Battlescape/Pathfinding.h), направление 0 - (0,-1), R-084
DIR = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
SRC = ("firepoint", "patrol", "escape", "melee", "ambush", "leeroy")
COLS = ["label", "battle", "terrain", "how", "bturn", "side", "unit", "turn", "f", "q", "blocker", "rel", "n_stop",
        "n_first", "n_mid", "n_supp", "goal_q", "known", "known_pos", "kr_n", "src", "outcome", "run", "run_end"]


def src_class(src):
    s = (src or "").split(".")[0]
    return s if s in SRC else "other"


def step(c, d):
    return (c[0] + DIR[d][0], c[1] + DIR[d][1], c[2])


def gz_lines(path, grep_args=None):
    cmd = ["gzip", "-dc", str(path)]
    p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    if grep_args:
        p2 = subprocess.Popen(["grep"] + grep_args, stdin=p1.stdout, stdout=subprocess.PIPE)
        p1.stdout.close()
        for raw in p2.stdout:
            yield raw.decode("utf-8", "replace")
        p2.wait()
    else:
        for raw in p1.stdout:
            yield raw.decode("utf-8", "replace")
    p1.wait()


def arena_rows(arena, label):
    out = {}
    with open(arena / f"{label}.tsv", encoding=ENC_R, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            out[f"seed={r['seed']} want={r['want']}"] = (r["how"], r["turn"], r["terrain"])
    return out


def factions(arena, label):
    out = {}
    for line in gz_lines(arena / f"{label}.tiles.gz", ["-F", "[AISTATE]"]):
        m = RX_STATE.search(line)
        if m:
            out[(line.split(" [", 1)[0], int(m.group(1)))] = int(m.group(2))
    return out


def load_rec(arena, label):
    """recs {(бой, rec): [ход, сторона, юнит, P, acts, to, src, после, попытки [(Q, F, T, kr) | (Q, None, None, None)]]},
    порядок решений {(бой, юнит): [rec]}."""
    recs, order = {}, collections.defaultdict(list)
    for line in gz_lines(arena / f"{label}.rec.gz"):
        i = line.find("{")
        if i < 0:
            continue
        head = line[:i]
        if "[AIREC]" in head:
            r = json.loads(line[i:])
            b = head.split(" [", 1)[0]
            base = r.get("base") or {}
            recs[(b, r["rec"])] = [r["turn"], r["side"], r["unit"], tuple(r["state"]["pos"]), (r.get("cand") or {}).get("acts"),
                                   tuple(base["to"]) if base.get("to") else None, base.get("src"), None, []]
            order[(b, r["unit"])].append(r["rec"])
        elif "[AIEXEC]" in head:
            r = json.loads(line[i:])
            d = recs.get((head.split(" [", 1)[0], r["rec"]))
            if d is None:
                continue
            d[7] = tuple(r["pos"]) if r.get("pos") else None
            for t in r.get("trail") or []:
                m = RX_STOP.search(t)
                if m:
                    g = list(map(int, m.groups()[:8]))
                    d[8].append((tuple(g[3:6]), tuple(g[0:3]), g[7], m.group(9)))
                    continue
                m = RX_SUPP.search(t)
                if m:
                    d[8].append((step(d[3], int(m.group(1))), None, None, None))
    return recs, order


def load_known(arena, label, need):
    """{(бой, acts): {T: {позиции кандидата}}} - только кандидаты атаки, только нужные acts (grep -F по списку)."""
    out = {}
    if not need:
        return out
    pat = OUT / f"unknown_occ_{label}.acts.txt"
    pat.write_text("".join(f"acts={h} \n" for h in sorted({h for _, h in need})), encoding="ascii")
    for line in gz_lines(arena / f"{label}.cand.gz", ["-F", "-f", str(pat)]):
        b, rest = line.split(" [", 1)
        if not rest.startswith("AICAND] acts="):
            continue
        h = rest[len("AICAND] acts="):].split(" ", 1)[0]
        if (b, h) not in need:
            continue
        tg = {}
        for x in json.loads(rest[rest.index(" list=") + 6:]):
            if x.get("k") == "a" and "u" in x:
                tg.setdefault(x["u"], set()).add(tuple(x["to"]))
        out[(b, h)] = tg
    pat.unlink()
    return out


def census(arena, label):
    meta = arena_rows(arena, label)
    fac = factions(arena, label)
    recs, order = load_rec(arena, label)
    eps = {}
    for (b, a), seq in order.items():
        byturn = collections.defaultdict(list)
        for rec in seq:
            byturn[recs[(b, rec)][0]].append(rec)
        for turn, rs in byturn.items():
            rs.sort()
            for i, rec in enumerate(rs):
                for q, f, t, kr in recs[(b, rec)][8]:
                    key = (b, a, turn, q)
                    e = eps.setdefault(key, {"recs": [], "first": rec, "i": i, "rs": rs, "f": None, "t": None, "kr": set(),
                                             "n_stop": 0, "n_first": 0, "n_mid": 0, "n_supp": 0, "goal_q": 0,
                                             "src": collections.Counter()})
                    e["recs"].append(rec)
                    d = recs[(b, rec)]
                    e["src"][src_class(d[6])] += 1
                    e["goal_q"] += d[5] == q
                    if f is None:
                        e["n_supp"] += 1
                        continue
                    e["n_stop"] += 1
                    e["f"] = e["f"] or f
                    e["t"] = t
                    if kr:
                        e["kr"].add(kr)
                    if f == d[3]:
                        e["n_first"] += 1
                    else:
                        e["n_mid"] += 1
    # только эпизоды с настоящей остановкой на юните; подавления V1 без шага в этом ходу - след прежнего, не новый
    eps = {k: e for k, e in eps.items() if e["n_stop"]}
    need = {(k[0], recs[(k[0], r)][4]) for k, e in eps.items() for r in e["recs"] if recs[(k[0], r)][4]}
    known = load_known(arena, label, need)
    rows = []
    for (b, a, turn, q), e in eps.items():
        d0 = recs[(b, e["first"])]
        side, t = d0[1], e["t"]
        fb, fa = fac.get((b, t)), 0 if side == 0 else 1
        rel = "?" if fb is None else "ally" if fb == fa else "neutral" if fb == 2 else "enemy"
        kn = kp = 0
        for r in e["recs"]:
            tg = known.get((b, recs[(b, r)][4]), {})
            if t in tg:
                kn = 1
                kp |= q in tg[t]
        how, bturn, terrain = meta.get(b, ("?", "?", "?"))
        rows.append({"label": label, "battle": b, "terrain": terrain, "how": how, "bturn": bturn, "side": side, "unit": a,
                     "turn": turn, "f": ",".join(map(str, e["f"])), "q": ",".join(map(str, q)), "blocker": t, "rel": rel,
                     "n_stop": e["n_stop"], "n_first": e["n_first"], "n_mid": e["n_mid"], "n_supp": e["n_supp"],
                     "goal_q": e["goal_q"], "known": kn, "known_pos": int(kp), "kr_n": len(e["kr"]),
                     "src": ";".join(f"{k}:{v}" for k, v in e["src"].most_common()),
                     "outcome": outcome(recs, b, e, q), "run": 0, "run_end": ""})
    runs(rows, recs, order)
    path = OUT / f"unknown_occ_{label}.tsv"
    with open(path, "w", encoding=ENC_W, newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\")
        w.writeheader()
        w.writerows(rows)
    print(f"{label}: решений {len(recs)}, эпизодов {len(rows)} -> {path.name}", flush=True)


def outcome(recs, b, e, q):
    rs = e["rs"][e["i"]:]
    p = recs[(b, rs[0])][3]
    last_try = False
    for rec in rs:
        d = recs[(b, rec)]
        if d[3] != p or (d[7] and d[7] != p):
            return "moved"
        last_try = any(x[0] == q for x in d[8])
    return "held" if last_try else "stayed"


def runs(rows, recs, order):
    by = collections.defaultdict(dict)
    for r in rows:
        by[(r["battle"], r["unit"], r["f"], r["q"])][r["turn"]] = r
    for (b, a, f, q), tt in by.items():
        unit_turns = sorted({recs[(b, rec)][0] for rec in order[(b, a)]})
        turns = sorted(tt)
        i = 0
        while i < len(turns):
            j = i + 1
            while j < len(turns) and unit_turns.index(turns[j]) == unit_turns.index(turns[j - 1]) + 1:
                j += 1
            k = unit_turns.index(turns[j - 1])
            end = "battle_end" if k + 1 >= len(unit_turns) else "free"
            for x in turns[i:j]:
                tt[x]["run"] = j - i
                tt[x]["run_end"] = end
            i = j


def summary(prefixes):
    for pre in prefixes:
        R = []
        for path in sorted(OUT.glob(f"unknown_occ_{pre}*.tsv")):
            with open(path, encoding=ENC_R, newline="") as f:
                R += list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\"))
        if not R:
            continue
        nb = len({(r["label"], r["battle"]) for r in R})
        print(f"=== {pre}: эпизодов {len(R)} в {nb} боях")
        for side in ("0", "1"):
            X = [r for r in R if r["side"] == side]
            if not X:
                continue
            print(f"  сторона {side} ({'бот' if side == '0' else 'враг'}): эпизодов {len(X)}, блокер {dict(collections.Counter(r['rel'] for r in X))}")
            E = [r for r in X if r["rel"] == "enemy"]
            for name, Y in (("враг-блокер", E), ("свой/нейтрал", [r for r in X if r["rel"] != "enemy"])):
                if not Y:
                    continue
                src = collections.Counter()
                for r in Y:
                    for kv in filter(None, r["src"].split(";")):
                        k, v = kv.rsplit(":", 1)
                        src[k] += int(v)
                rep = [r for r in Y if int(r["n_stop"]) + int(r["n_supp"]) >= 2]
                print(f"    {name}: {len(Y)}; откуда {dict(src.most_common())}")
                print(f"      первый шаг {sum(1 for r in Y if int(r['n_first']))}, только mid-path "
                      f"{sum(1 for r in Y if not int(r['n_first']))}; цель хода = Q {sum(1 for r in Y if int(r['goal_q']))}")
                print(f"      одиночных {len(Y) - len(rep)}, повторов {len(rep)}; исход {dict(collections.Counter(r['outcome'] for r in Y))}; "
                      f"у повторов {dict(collections.Counter(r['outcome'] for r in rep))}")
                print(f"      kr менялся между остановками {sum(1 for r in Y if int(r['kr_n']) > 1)} из "
                      f"{sum(1 for r in Y if int(r['n_stop']) > 1)} с >1 остановкой")
                print(f"      known (T в кандидатах атаки) {sum(int(r['known']) for r in Y)}, known_pos (и на Q) "
                      f"{sum(int(r['known_pos']) for r in Y)}")
                runs_ = {(r["label"], r["battle"], r["unit"], r["f"], r["q"], r["run_end"]): int(r["run"]) for r in Y}
                rl = collections.Counter(min(v, 10) for v in runs_.values())
                single_free = sum(1 for r in Y if int(r["run"]) == 1 and r["run_end"] == "free"
                                  and int(r["n_stop"]) + int(r["n_supp"]) == 1)
                print(f"      серии (ходов подряд, 10 = 10+) {dict(sorted(rl.items()))}; до конца боя "
                      f"{sum(1 for k in runs_ if k[5] == 'battle_end')}; одна попытка и в следующем ходу нет {single_free}")
                bt = collections.Counter(r["how"] for r in {(r["label"], r["battle"]): r for r in Y}.values())
                long_b = {(r["label"], r["battle"]) for r in Y if int(r["run"]) >= 3 or
                          (r["run_end"] == "battle_end" and r["outcome"] == "held")}
                lb = collections.Counter(r["how"] for r in {(r["label"], r["battle"]): r for r in Y
                                                             if (r["label"], r["battle"]) in long_b}.values())
                print(f"      боёв {sum(bt.values())} по исходу {dict(bt)}; из них с серией >= 3 или held до конца боя "
                      f"{len(long_b)} по исходу {dict(lb)}")
                cave = sum(1 for r in Y if r["terrain"].startswith("CAVES_RITUAL"))
                lcave = sum(1 for b in long_b if next(r for r in Y if (r["label"], r["battle"]) == b)["terrain"].startswith("CAVES_RITUAL"))
                terr = collections.Counter(r["terrain"] for r in Y if (r["label"], r["battle"]) in long_b)
                print(f"      RITUAL_CAVE эпизодов {cave} из {len(Y)}; длинных боёв в RITUAL_CAVE {lcave} из {len(long_b)}; "
                      f"карты длинных {dict(terr.most_common(6))}")


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
