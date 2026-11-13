"""Movement diagnosis: what really changes when a walking order is replaced. Per replaced order: the squad's objective before and after from its task lines, the old and the new target of the unit,
the old target's and the new target's distance to the new objective, the walking cost left. Ends with what a stable order would keep: the old target still serves the new objective (read only)."""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from classify import run_table  # noqa: E402
from lib import kv, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def task_lines(L, squad):
    out = []
    for i, s in enumerate(L):
        if s.startswith("[HIVETASK]") and f"squad={squad} " in s:
            k = kv(s)
            if k.get("kind") in ("contact", "sector_node") and ("objective" in k or "pos" in k or "at" in k):
                out.append((i, k))
    return out


def med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def analyse(run, show=False):
    L, rows, decisions = run_table(run)
    print("==", run)
    if show:
        for s in [s for s in L if s.startswith("[HIVETASK]")][:4]:
            print("  sample", s[:230])
    by_unit = {}
    for o in rows:
        by_unit.setdefault(o["unit"], []).append(o)
    for v in by_unit.values():
        v.sort(key=lambda x: x["line0"])
    cache = {}
    res = []
    for o in rows:
        if o.get("reason") != "replaced":
            continue
        if o["squad"] not in cache:
            cache[o["squad"]] = task_lines(L, o["squad"])
        t = [x for x in cache[o["squad"]] if x[0] <= o["line1"]]
        new = t[-1][1] if t else None
        old = next((x[1] for x in reversed(t[:-1])), None)
        nxt = next((n for n in by_unit[o["unit"]] if n["line0"] >= o["line1"] - 3 and n["id"] != o["id"]), None)
        field = "objective" if new and "objective" in new else "pos" if new and "pos" in new else "at"
        g1 = tup(new[field]) if new else None
        g0 = tup(old[field]) if old and field in old else None
        same = bool(new and old and new.get("contact") and new.get("contact") == old.get("contact"))
        left = max(o["note"].get("path_tu", 0) - o["walk_tu"], 0)
        res.append(dict(o=o, same=same, other=bool(new and old and new.get("contact") and old.get("contact") and not same), g0=g0, g1=g1, nxt=nxt, left=left, here=o["end"]))
    S = [r for r in res if r["same"] and r["g0"] and r["g1"] and r["nxt"]]
    print(" replaced", len(res), "same contact, with both objectives and a next order", len(S))
    print(" contact moved: median", med([dist(r["g0"], r["g1"]) for r in S]), Counter(min(dist(r["g0"], r["g1"]) // 5 * 5, 30) for r in S).most_common())
    print(" target moved: median", med([dist(r["o"]["target"], r["nxt"]["target"]) for r in S]))
    print(" old target to the new objective: median", med([dist(r["o"]["target"], r["g1"]) for r in S]), "; new target to the new objective: median", med([dist(r["nxt"]["target"], r["g1"]) for r in S]))
    print(" old target nearer or equal to the new objective than the new target:", sum(dist(r["o"]["target"], r["g1"]) <= dist(r["nxt"]["target"], r["g1"]) for r in S), "of", len(S))
    print(" kinds of the next order:", Counter(r["nxt"]["why"] for r in S).most_common(6), "; of the replaced:", Counter(r["o"]["why"] for r in S).most_common(6))
    print(" unit closer to new target than to old:", sum(dist(r["here"], r["nxt"]["target"]) < dist(r["here"], r["o"]["target"]) for r in S), "further or same:", sum(dist(r["here"], r["nxt"]["target"]) >= dist(r["here"], r["o"]["target"]) for r in S))
    # what a stability rule could save: the order counted as 'task changed'
    tc = [r for r in res if r["o"]["cause"] == "задача изменилась"]
    kept = Counter()
    for r in tc:
        o = r["o"]
        turns = "1" if o["note"].get("reach") == "full" or r["left"] <= o["tu0"] else ("2" if r["left"] <= 2 * o["tu0"] else "3+")
        kind = "тот же контакт" if r["same"] else ("другой контакт" if r["other"] else o["trigger"].split(":")[0] or "нет")
        kept[(kind, turns)] += 1
    print(" 'task changed' by kind and turns left:", sorted(kept.items()))
    same_tc = [r for r in tc if r["same"]]
    print(" 'task changed', same contact:", len(same_tc), "other contact:", sum(r["other"] for r in tc), "the rest:", len(tc) - len(same_tc) - sum(r["other"] for r in tc))
    # per turn: units reordered, the orders replaced in one go in one squad
    burst = Counter((o["squad"], o["turn1"]) for o in rows if o.get("reason") == "replaced")
    print(" replaced in one squad in one turn: median", med(list(burst.values())), "max", max(burst.values()), "turns", len(burst))
    arrived = [o for o in rows if o["cause"] == "выполнен"]
    print(" arrived: by reach", Counter(o["note"].get("reach") for o in arrived).most_common(), "; turns to arrive", Counter(o["turn1"] - o["turn0"] for o in arrived).most_common(4))
    return res


if __name__ == "__main__":
    analyse("hh4_JA_M6_s2", True)
    analyse("hh6_JV_M3_s1")
