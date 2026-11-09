"""Contact coordination, feasibility: the members of a squad unit by unit, turn by turn: where each decided first and last, the modes, the field size, attacks; and the orders of the active run (read only)."""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))


def show(run, members, last=6):
    print("==", run)
    L = read(run)
    dec = defaultdict(lambda: defaultdict(list))
    reach = defaultdict(dict)
    orders = defaultdict(list)
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1" and int(k["unit"]) in members:
                dec[int(k["unit"])][int(k["turn"])].append(k)
        elif s.startswith("[HIVEREACH]"):
            k = kv(s)
            if int(k["unit"]) in members:
                reach[int(k["unit"])][int(k["turn"])] = k
        elif s.startswith("[HIVEORD]"):
            k = kv(s)
            if k.get("unit", "").isdigit() and int(k["unit"]) in members:
                orders[int(k["unit"])].append(s[:230])
    for u in sorted(members):
        print(" unit", u)
        for t in range(1, last + 1):
            ds = dec[u].get(t, [])
            r = reach[u].get(t, {})
            if not ds:
                print(f"   t{t} no decisions; field {r.get('tiles')} at {r.get('at')}")
                continue
            m = Counter((d["mode"], d["act"]) for d in ds)
            print(f"   t{t} {ds[0]['from']} -> {ds[-1]['from']} tu {ds[0]['tu']}->{ds[-1]['tu']} field {r.get('tiles')} first to {ds[0]['to']} modes {dict(m)}")
        if orders[u]:
            for s in orders[u][:6]:
                print("     ", s)


if __name__ == "__main__":
    M = {1000007, 1000015, 1000021, 1000028, 1000037, 1000038}
    show("hh2_JS_M6_s1", M, 5)
    show("hh3_JA_M6_s1", M, 5)
