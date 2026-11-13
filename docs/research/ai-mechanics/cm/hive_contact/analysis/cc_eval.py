"""CONTACT_COORDINATION_V0: the gates by the journal of an active run against the D0 behaviour of the same seed (read only).
Usage: cc_eval.py <active run> <off run> [last turn]"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
PLAYER_FACTION = "0"


def d2(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def side_dec(L):
    out = defaultdict(lambda: defaultdict(list))
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                out[int(k["turn"])][int(k["unit"])].append(k)
    return out


def damage(L):
    """Per enemy unit: (damage, kills, attacks with result) from the execution records, kept by turn through the decisions."""
    dmg = defaultdict(lambda: Counter())
    turn = 0
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            turn = int(k["turn"])
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[len("[AIEXEC] "):])
            except ValueError:
                continue
            if j.get("walk"):
                continue
            u = int(j["unit"])
            if u < 1000000:
                continue  # the player's bot: not this side
            dmg[(turn, u)]["dmg"] += j.get("dmg", 0)
            dmg[(turn, u)]["downed"] += j.get("downed", 0)
            dmg[(turn, u)]["stunned"] += j.get("stunned", 0)
            dmg[(turn, u)]["fdmg"] += j.get("fdmg", 0)
    return dmg


def casualties(L, last):
    c = Counter()
    for s in L:
        if s.startswith("[AICASUALTY]"):
            k = kv(s)
            if int(k["turn"]) <= last:
                c["enemy" if k.get("vfaction") == "1" else "player"] += 1
    return c


def main():
    run, off = sys.argv[1], sys.argv[2]
    last = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    L, O = read(run), read(off)
    print("==", run, "against", off, "lines", len(L), len(O))
    print(" errors", [s[:140] for s in L if "CRASH" in s or "Exception" in s or s.startswith("[HIVELOAD] parsed=0")][:3])
    cc = [(s, kv(s)) for s in L if s.startswith("[HIVECC]")]
    ev = Counter(k["event"] for s, k in cc)
    print(" events", dict(ev))
    dec, dec0 = side_dec(L), side_dec(O)
    dmg, dmg0 = damage(L), damage(O)

    print("== decisions (first 5 turns)")
    for s, k in cc:
        if k["event"] == "DECISION" and int(k["turn"]) <= 5:
            print("  ", s[len("[HIVECC] "):][:320])
    print("== assignments")
    rows = Counter()
    for s, k in cc:
        if k["event"] == "ASSIGN":
            rows[(k["from"], k["to"], k["why"])] += 1
    for r, n in rows.most_common():
        print("  ", r, n)
    print("   first ones:")
    for s, k in [x for x in cc if x[1]["event"] == "ASSIGN"][:14]:
        print("    t", k["turn"], "squad", k["squad"], k["from"], "->", k["to"], "contact", k["contact"], k["why"], "task", k["task"], k["hold"])
    print("== reinforce checks", [(k["turn"], k["squad"], k["contact"], k["dist"], k["able"]) for s, k in cc if k["event"] == "REINFORCE_CHECK"][:24])
    print("== orders by role and kind", Counter((k["role"], k["kind"]) for s, k in cc if k["event"] == "ORDER").most_common())

    # F2, F3: REINFORCE units
    order_units = defaultdict(dict)  # turn -> unit -> order line
    for s, k in cc:
        if k["event"] == "ORDER" and k["role"] == "REINFORCE":
            order_units[int(k["turn"])][int(k["unit"])] = k
    changed, atk, atk_rows = [], [], []
    for t, us in sorted(order_units.items()):
        for u, o in us.items():
            ds, d0 = dec[t].get(u, []), dec0[t].get(u, [])
            if o["kind"] in ("fire", "approach"):
                on = [d for d in ds if d["to"] == o["target"] and d["act"] == "2"]
                same0 = [d for d in d0 if d["to"] == o["target"] and d["act"] == "2"]
                if on and not same0:
                    changed.append((t, u, o["kind"], o["target"], [d["to"] for d in d0][:2]))
            for d in ds:
                if int(d["act"]) in ATT:
                    atk.append((t, u))
                    atk_rows.append((t, u, o["kind"], d["act"], d["aim"], d["from"], d["weapon"]))
    print("== F2 changed by the order (walk on the order's node; in the off run this unit-turn did not):", len(changed), "units-turns,", len({c[1] for c in changed}), "units")
    for c in changed[:12]:
        print("   ", c)
    print("== F3 attacks by units under a REINFORCE order, not in sight at the plan:", len(atk))
    for r in atk_rows[:16]:
        print("   ", r)

    # role tallies: attacks and damage by role per turn
    role_of = defaultdict(dict)
    for s, k in cc:
        if k["event"] == "EXEC":
            role_of[int(k["turn"])][int(k["unit"])] = k["role"]
    print("== attacks by role, from EXEC")
    tally = defaultdict(Counter)
    for s, k in cc:
        if k["event"] == "EXEC" and int(k["act"]) in ATT:
            tally[int(k["turn"])][k["role"]] += 1
    for t in sorted(tally)[:last]:
        print("   t", t, dict(tally[t]))

    # F4 MAINTAIN
    ctasks = [k for s, k in cc if k["event"] == "ASSIGN" and k["from"] == "MAINTAIN"]
    print("== F4 left MAINTAIN:", Counter((k["to"], k["why"]) for k in ctasks).most_common())
    bad = [s[:200] for s in L if s.startswith("[HIVETASK]") and "kind=contact" in s and "role=" not in s]
    print("   a contact as an objective without the decision:", len(bad), bad[:2])
    hold_rows = [(kv(s)["turn"], kv(s)["squad"], kv(s).get("why")) for s in L if s.startswith("[HIVETASK]") and "from=HOLD" in s]
    print("   left a hold:", Counter(x[2] for x in hold_rows).most_common(), hold_rows[:6])

    # F5
    ord_rows = [kv(s) for s in L if s.startswith("[HIVEORD]") and "state=" in s]
    blocked = Counter((k["unit"], k["target"]) for k in ord_rows if k["state"] == "BLOCKED")
    print("== F5 same unit and node blocked twice:", sum(1 for v in blocked.values() if v >= 2), "blocked in all", sum(blocked.values()))
    for t, us in sorted(order_units.items()):
        pass
    # cycles of REINFORCE units: back to the place it stood two turns ago, three turns running
    walk = defaultdict(dict)
    for t in dec:
        for u, ds in dec[t].items():
            walk[u][t] = tup(ds[0]["from"])
    cyc = []
    runits = {u for us in order_units.values() for u in us}
    for u in runits:
        ts = sorted(walk[u])
        run_ = 0
        for a, b in zip(ts, ts[2:]):
            if b == a + 2 and walk[u][a] == walk[u][b] and walk[u][a] != walk[u].get(a + 1):
                run_ += 1
                if run_ >= 2:
                    cyc.append(u)
            else:
                run_ = 0
    print("   units A-B-A-B over the turns:", sorted(set(cyc)))
    stay = Counter(k["why"] for k in (kv(s) for s in L if s.startswith("[HIVEORD]") and "kind=STAY" in s and "state=CREATED" in s))
    print("   stays by reason:", stay.most_common())

    # FAIR on the role contacts
    fair = {(kv(s)["turn"], kv(s)["target"]) for s in L if s.startswith("[HIVEFAIR]")}
    missing = [k for s, k in cc if k["event"] == "ORDER" and k.get("contact") and (k["turn"], k["contact"]) not in fair]
    print("== FAIR: orders on a contact with no observer record that turn:", len(missing), missing[:2])

    # tactical, descriptive
    print("== TACTICAL (descriptive). The units under a REINFORCE order in the first turn it was given, their turns 1-4, this run against off")
    if order_units:
        t0 = min(order_units)
        units = sorted(order_units[t0])
        def row(dc, dm):
            a, dd = 0, Counter()
            for t in range(t0, t0 + 4):
                for u in units:
                    a += sum(int(d["act"]) in ATT for d in dc[t].get(u, []))
                    dd.update(dm.get((t, u), Counter()))
            return a, dict(dd)
        print("   first turn", t0, "units", units)
        print("   on ", row(dec, dmg))
        print("   off", row(dec0, dmg0))
    def side(dc, dm):
        out = {}
        for t in sorted(dc):
            if t <= last:
                a = sum(int(d["act"]) in ATT for ds in dc[t].values() for d in ds)
                dd = sum(v["dmg"] for (tt, u), v in dm.items() if tt == t)
                alive = len(dc[t])
                out[t] = (alive, a, dd)
        return out
    print("   side per turn (units deciding, attacks, damage)")
    print("    on ", side(dec, dmg))
    print("    off", side(dec0, dmg0))
    print("   casualties to turn", last, "on", dict(casualties(L, last)), "off", dict(casualties(O, last)))
    plan = [int(kv(s)["us"]) for s in L if s.startswith("[HIVEPERF]") and "phase=plan" in s]
    print("== plan us, max", max(plan) if plan else None, "sum", sum(plan))
    print(" end", L[-1][:100])
    res = [s[:200] for s in L if s.startswith("[AIRESULT]")]
    print(" result", res[-1:] )


if __name__ == "__main__":
    main()
