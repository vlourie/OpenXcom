"""Movement diagnosis: an order against its own plan for the first turn. The plan logs where the unit should end this turn (note end=); did it get there, how short, why not. Also the cause by length of the order,
the rule 'keep the walking order while its target still serves the new objective' counted on the replaced orders, and why a squad changed to another contact (read only)."""
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from classify import run_table  # noqa: E402
from lib import kv, tup  # noqa: E402
from shift import analyse as shift_analyse  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
RADIUS = 2  # ARRIVE_RADIUS, checked below against the code


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def analyse(run):
    L, rows, decisions = run_table(run)
    print("==", run)
    table = Counter()
    for o in rows:
        table[(o["note"].get("reach", "?"), o["cause"])] += 1
    for reach in ("full", "partial", "?"):
        sub = {c: n for (r, c), n in table.items() if r == reach}
        print(f"  {reach}: {sum(sub.values())}:", sorted(sub.items(), key=lambda x: -x[1]))
    plan = Counter()
    short = []
    frac = []
    why_short = Counter()
    first_mode = Counter()
    for o in rows:
        n = o["note"]
        if not n.get("end"):
            continue
        end = tup(n["end"])
        ds = [d for d in o["decs"] if d["turn"] == o["turn0"]]
        reach = n["reach"]
        if not ds:
            plan[(reach, "не получил решения в этот ход")] += 1
            continue
        posd = [d for d in ds if d["pos"]]
        at = posd[-1]["pos"] if posd else ds[-1]["frm"]
        d = dist(at, end)
        on = [x for x in ds if x["act"] == 2 and x["to"] == o["target"]]
        walked = sum(x["spent"] for x in on)
        want = min(n["path_tu"], o["tu0"])
        if want > 0:
            frac.append(walked / want)
        if d <= RADIUS:
            plan[(reach, "дошёл до конца хода по плану")] += 1
        else:
            first = ds[0]
            if not on:
                lab = "по приказу не ходил: режим %d" % first["mode"]
            else:
                st = on[-1]["stop"]
                lab = "шёл, недошёл: стоп %s" % st
            plan[(reach, lab)] += 1
            short.append(d)
            why_short[lab] += 1
    for k, v in sorted(plan.items(), key=lambda x: (x[0][0], -x[1])):
        print("   ", k, v)
    print("  short of the plan by cells: median", med(short), "n", len(short))
    frac.sort()
    print("  TU walked on order in its first turn / planned: median %.2f" % (med(frac) or 0), "n", len(frac), "; >=0.9:", sum(x >= 0.9 for x in frac), "; 0:", sum(x == 0 for x in frac))
    # reserve: planned TU left against the real stop, for those stopped by reserve
    res = [(o, x) for o in rows for x in o["decs"] if x["act"] == 2 and x["to"] == o["target"] and x["stop"] == "reserve" and x["spent"] > 0]
    print("  stopped by reserve after walking:", len(res), "TU left median", med([x["tu"] - x["spent"] for o, x in res]))
    second = [x for o in rows for x in o["decs"] if x["act"] == 2 and x["to"] == o["target"] and x["stop"] == "reserve" and x["spent"] == 0]
    print("  empty reserve walks: n>=2 in the turn:", sum(x["n"] >= 2 for x in second), "n=1:", sum(x["n"] == 1 for x in second))


    # contact events
    ev = Counter()
    for o in rows:
        pass
    return rows


def keep_rule(run):
    res = shift_analyse(run)
    for R in (6, 8, 10, 15):
        for turns in (1, 2):
            n = 0
            for r in res:
                if not r["g1"]:
                    continue
                o = r["o"]
                if dist(o["target"], r["g1"]) <= R and (o["note"].get("reach") == "full" or r["left"] <= turns * o["tu0"]) and o["cause"] == "задача изменилась":
                    n += 1
            print(f"  keep rule: old target within {R} of the new objective and at most {turns} turns left: {n} orders counted 'task changed'")


for run in ["hh4_JA_M6_s2", "hh6_JV_M3_s1", "hh3_JA_M6_s1"]:
    analyse(run)
    keep_rule(run)
src = (HERE.parent / "tree/src/Battlescape/HiveCommand.cpp").read_text(encoding="utf-8", errors="replace")
print(re.findall(r"[^\n]*ARRIVE_RADIUS\s*=[^\n]*", src)[:2])
print(re.findall(r"[^\n]*OBJECTIVE_NODE_RADIUS\s*=[^\n]*", src)[:2])
