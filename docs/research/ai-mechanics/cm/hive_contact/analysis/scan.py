"""Contact coordination, feasibility: per enemy turn of a battle log, who sees which contact by squad, what each squad is doing. Applies the episode rule written before looking: the earliest turn with a contact
seen by a squad (A), another squad not seeing it with its commander within CONTACT_REACH of it and at least two armed members standing (B), and a third with its own task, no contact within HOLD_EXIT_RADIUS (C) (read only)."""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
REACH, NEAR = 24, 12


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def scan(run, show=4):
    L = read(run)
    squad_of = {}
    weapon = {}
    for s in L:
        if s.startswith("[HIVEUNIT]"):
            k = kv(s)
            weapon[int(k["id"])] = k.get("weapon")
    turns = defaultdict(lambda: dict(fair=[], contacts={}, squads={}, line=None))
    for i, s in enumerate(L):
        if s.startswith("[HIVESQUAD]"):
            k = kv(s)
            if "members" in k and "id" in k:
                for m in k["members"].split(","):
                    squad_of[int(m.rstrip("LSMA"))] = int(k["id"])
            elif "join" in k:
                squad_of[int(k["join"])] = int(k["squad"])
            elif "merged" in k:
                for u, q in list(squad_of.items()):
                    if q == int(k["merged"]):
                        squad_of[u] = int(k["into"])
        elif s.startswith("[HIVEFAIR]"):
            k = kv(s)
            t = turns[int(k["turn"])]
            t["fair"].append((i, int(k["observer"]), int(k["target"]), tup(k["pos"]), squad_of.get(int(k["observer"]))))
            if t["line"] is None:
                t["line"] = i
        elif s.startswith("[HIVECONTACT]"):
            k = kv(s)
            t = turns[int(k["turn"])]
            if "event" not in k:
                t["contacts"][int(k["target"])] = (tup(k["pos"]), k["cls"], int(k.get("age", 0)), int(k.get("observer", -1)))
        elif s.startswith("[HIVESQUADTURN]"):
            k = kv(s)
            t = turns[int(k["turn"])]
            t["squads"][int(k["squad"])] = k
    print("==", run)
    picked = None
    for turn in sorted(turns):
        t = turns[turn]
        seers = defaultdict(set)
        for i, o, tgt, p, q in t["fair"]:
            if q is not None:
                seers[tgt].add(q)
        if show > 0:
            print(f" turn {turn}: contacts {[(c, v[0], v[1], v[2]) for c, v in t['contacts'].items()]}")
            print(f"   seers by squad {dict((c, sorted(v)) for c, v in seers.items())}")
            for q, k in sorted(t["squads"].items()):
                print(f"   squad {q} task {k['task']} hold {k.get('hold')} alive {k['alive']} tuPct {k.get('tuPct')} shots {k.get('shots')} saw {k.get('saw')} objective {k.get('objective')}")
            show -= 1
    return L, turns, squad_of


if __name__ == "__main__":
    for run in sys.argv[1:]:
        L, turns, sq = scan(run)
        i0 = next(i for i, s in enumerate(L) if s.startswith("[HIVEFAIR]") or s.startswith("[HIVECONTACT]"))
        print(" first plan lines:")
        for s in L[i0 : i0 + 60]:
            if s.startswith(("[HIVEFAIR]", "[HIVECONTACT]", "[HIVETASK]", "[HIVEHOLD]", "[HIVEREVIEW]")):
                print("   ", s[:170])
