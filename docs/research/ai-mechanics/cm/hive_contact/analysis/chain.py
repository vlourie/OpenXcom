"""CONTACT_COORDINATION_V0: the chain of one run: per squad and turn, role, the orders, what each unit did; what each kind of order came to; the guards' distance to what they saw (read only). Usage: chain.py <run> [squad ...]"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))


def main():
    run = sys.argv[1]
    squads = {int(x) for x in sys.argv[2:]}
    L = read(run)
    dec = defaultdict(lambda: defaultdict(list))
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                dec[int(k["turn"])][int(k["unit"])].append(k)
    for s in L:
        if not s.startswith("[HIVECC]"):
            continue
        k = kv(s)
        if k.get("squad", "-") != "-" and int(k["squad"]) in squads and k["event"] in ("ASSIGN", "ORDER", "EXEC", "FEEDBACK", "REINFORCE_CHECK") and int(k["turn"]) <= 5:
            print(" ", s[len("[HIVECC] "):][:190])
    print("== what each kind of order came to: attack in the same turn or the next")
    res = defaultdict(Counter)
    tu_left = defaultdict(list)
    for s in L:
        if s.startswith("[HIVECC]") and "event=ORDER" in s:
            k = kv(s)
            t, u = int(k["turn"]), int(k["unit"])
            key = (k["role"], k["kind"])
            res[key]["n"] += 1
            same = any(int(d["act"]) in ATT for d in dec[t].get(u, []))
            nxt = any(int(d["act"]) in ATT for d in dec[t + 1].get(u, []))
            res[key]["attack_same"] += same
            res[key]["attack_next"] += nxt and not same
            res[key]["none"] += not (same or nxt)
            ds = dec[t].get(u, [])
            if ds:
                tu_left[key].append(int(ds[-1]["tu"]) * 100 // max(1, int(ds[0]["tu"])))
    for key, c in sorted(res.items()):
        v = sorted(tu_left[key])
        print("  ", key, dict(c), "last decision's TU, % of first, median", v[len(v) // 2] if v else None)
    print("== orders that arrived and then")
    arr = Counter()
    for s in L:
        if s.startswith("[HIVEORD]") and "state=COMPLETED" in s and "note=arrived" in s:
            k = kv(s)
            t, u = int(k["turn"]), int(k["unit"])
            same = any(int(d["act"]) in ATT for d in dec[t].get(u, []))
            nxt = any(int(d["act"]) in ATT for d in dec[t + 1].get(u, []))
            arr[(k["why"], "attack" if same or nxt else "none")] += 1
    print("  ", arr.most_common())
    print("== guards at the moment they took a contact: their anchor and the contact")
    holds = {}
    contacts = defaultdict(dict)
    for s in L:
        if s.startswith("[HIVEHOLD]"):
            k = kv(s)
            holds[int(k["squad"])] = (k["anchor"], k["why"])
        elif s.startswith("[HIVECONTACT]"):
            k = kv(s)
            if "event" not in k:
                contacts[int(k["turn"])][k["target"]] = k["pos"]
        elif s.startswith("[HIVECC]") and "event=ASSIGN" in s:
            k = kv(s)
            if k["hold"] == "guard_sector" and k["to"] == "ENGAGE":
                p = tup(contacts[int(k["turn"])].get(k["contact"], "(0,0,0)"))
                a = tup(holds[int(k["squad"])][0])
                print(f"   t{k['turn']} squad {k['squad']} anchor {a} contact {k['contact']} {p} distance {max(abs(a[0]-p[0]), abs(a[1]-p[1]))} why {k['why']}")


if __name__ == "__main__":
    main()
