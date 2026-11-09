"""REINFORCEMENT INTELLIGENCE V0: one run against its base on the metrics declared in GATES_AND_RUN_LIST.md, turns 1..last. Usage: ri_eval.py <run> <base> [last]. Read only."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))


def ana(run, last):
    L = read(run)
    R = Counter()
    orders = {}
    dec = defaultdict(lambda: defaultdict(list))
    rec2dec = {}
    assigns = []
    novi = []
    results = Counter()
    ends = Counter()
    elig = Counter()
    pending = {}
    dmg = defaultdict(Counter)
    turn = 0
    fell = {}
    downed_soldiers = set()
    own_out = set()
    ff = 0
    tasks = set()
    for s in L:
        if s.startswith("[HIVECC]"):
            k = kv(s)
            e = k["event"]
            if int(k.get("turn", 0)) > last:
                continue
            if e == "ORDER" and k["role"] == "REINFORCE":
                orders[(int(k["turn"]), int(k["unit"]))] = k
            elif e == "ASSIGN":
                if k["to"] == "REINFORCE":
                    assigns.append(k)
                elif k["from"] == "REINFORCE":
                    ends[k["why"]] += 1
            elif e == "NO_VIABLE_REINFORCEMENT":
                novi.append(k)
            elif e == "HELP_RESULT":
                results[k["kind"] + (":" + k["why"] if "why" in k else "")] += 1
            elif e == "ELIGIBILITY":
                for p in k.get("units", "").split(","):
                    if ":" in p:
                        elig[p.split(":")[1]] += 1
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            turn = int(k["turn"])
            if k["side"] == "1" and turn <= last:
                dec[turn][int(k["unit"])].append(k)
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            if j.get("walk") or int(j.get("unit", 0)) < 1000000 or turn > last:
                continue
            d = dmg[(turn, int(j["unit"]))]
            d["dmg"] += j.get("dmg", 0)
            d["fdmg"] += j.get("fdmg", 0)
        elif s.startswith("[AICASUALTY]"):
            k = kv(s)
            t = int(k["turn"])
            if t > last:
                continue
            if k.get("vfaction") == "1":
                own_out.add(k["victim"])
                fell.setdefault(int(k["victim"]), t)
            else:
                downed_soldiers.add(k["victim"])
        elif s.startswith("[HIVETASK]"):
            k = kv(s)
            if k.get("kind") == "sector_node" and int(k["turn"]) <= last:
                tasks.add((k["squad"], k["key"]))
    # helpers
    attacks_c = attacks_o = stood = 0
    first = {}
    helper_units = defaultdict(set)
    hdmg = 0
    kinds = Counter()
    for (t, u), o in orders.items():
        kinds[o["kind"]] += 1
        ds = dec[t].get(u, [])
        helper_units[t].add(u)
        c = o["contact"]
        for d in ds:
            if int(d["act"]) in ATT:
                if d["aim"] == c:
                    attacks_c += 1
                else:
                    attacks_o += 1
        if not any(int(d["act"]) in ATT or d["act"] == "2" for d in ds):
            stood += 1
        hdmg += dmg[(t, u)]["dmg"]
    # delay per assignment, retargets apart
    delays = []
    fresh = [a for a in assigns if not a["why"].startswith("contact_not_in_sight")]
    for a in fresh:
        t0, sq, c = int(a["turn"]), a["squad"], a["contact"]
        delay = None
        for t in range(t0, min(t0 + REINFORCE_SPAN, last) + 1):
            for (tt, u), o in orders.items():
                if tt == t and o["squad"] == sq and o["contact"] == c and any(int(d["act"]) in ATT and d["aim"] == c for d in dec[t].get(u, [])):
                    delay = t - t0 if delay is None else min(delay, t - t0)
        delays.append(delay)
    # lost helpers: on the order's turn or in the enemy's next phase (its turn number is the next one)
    lost = sum(1 for u, t in fell.items() if u in helper_units.get(t, ()) or u in helper_units.get(t - 1, ()))
    a_all = sum(int(d["act"]) in ATT for t in dec for ds in dec[t].values() for d in ds)
    d_all = sum(v["dmg"] for v in dmg.values())
    f_all = sum(v["fdmg"] for v in dmg.values())
    o_att = a_all - attacks_c - attacks_o
    o_dmg = d_all - hdmg
    # the TU left on unit-turns that end with nothing
    lastd = {}
    for t in dec:
        for u, ds in dec[t].items():
            lastd[(t, u)] = ds[-1]
    idle = [d for d in lastd.values() if d["act"] == "0"]
    res = [s for s in L if s.startswith("[AIRESULT]")]
    return dict(run=run, fresh=len(fresh), retarget=len(assigns) - len(fresh), novi=len(novi), novi_checked=sum(int(k.get("checked", 0)) > 0 for k in novi), kinds=dict(kinds), helper_turns=sum(kinds.values()),
                att_contact=attacks_c, att_other=attacks_o, stood=stood, delays=delays, helper_dmg=hdmg, lost=lost, other_att=o_att, other_dmg=o_dmg,
                search_objectives=len(tasks), side_att=a_all, side_dmg=d_all, friendly=f_all, soldiers_out=len(downed_soldiers), own_out=len(own_out), deciding_last=len(dec.get(last, {})), idle_turns=len(idle), idle_tu=sum(int(d["tu"]) for d in idle),
                unit_turns=len(lastd), results=dict(results), ends=dict(ends), elig=dict(elig), airesult=res[-1][:150] if res else "")


REINFORCE_SPAN = 3


def main():
    run, base = sys.argv[1], sys.argv[2]
    last = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    a, b = ana(run, last), ana(base, last)
    for key in a:
        va, vb = a[key], b[key]
        print(f"{key:18s} {str(va):60s} | {vb}")


if __name__ == "__main__":
    main()
