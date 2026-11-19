"""HIVE D2 CORRECTION, read only: M3 turn 1, the pocket of 1000050 and 1000027. Every decision of the hostile side up to their first thinks, ON against OFF, in log order: who went where, and which units stand near the two when they think."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
RUNS = sys.argv[1:] or ["d21_DO_M3_s1", "d23_DN_M3_s1"]
WATCH = ("1000050", "1000027")


def tup(s):
    return tuple(int(x) for x in s.strip("()").split(","))


for run in RUNS:
    print("=====", run)
    L = read(run)
    where = {}
    first = {}
    n = 0
    for i, s in enumerate(L):
        if s.startswith("[HIVEREACH]"):
            k = kv(s)
            if k["turn"] == "1" and k["unit"] in WATCH:
                print(f"  line {i} FIELD unit {k['unit']} at {k['at']} tiles {k['tiles']}")
        if s.startswith("[HIVEUA] event=OFFER_REFUSED"):
            k = kv(s)
            if k["turn"] == "1":
                print(f"  line {i} REFUSED unit {k['unit']} offer {k['offer']} free {k['free']} expanded {k['expanded']}")
        if s.startswith("[HIVEUA] event=PATROLEND"):
            k = kv(s)
            if k["turn"] == "1" and k["unit"] in WATCH:
                print(f"  line {i} END unit {k['unit']} tries {k['tries']} end {k['end']}")
        if not s.startswith("[AIDECIDE]"):
            continue
        k = kv(s)
        if k["turn"] != "1":
            if int(k["turn"]) > 1:
                break
            continue
        if k.get("side") not in (None, "1", "HOSTILE", "hostile"):
            pass
        n += 1
        u = k["unit"]
        a = tup(k["from"])
        where[u] = k.get("to") if k["act"] == "2" else k["from"]
        mark = ""
        if u in WATCH and u not in first:
            first[u] = n
            mark = "  <== first think"
        near = abs(a[0] - 6) <= 8 and abs(a[1] - 15) <= 8
        if near or u in WATCH:
            print(f"  line {i} #{n} unit {u} from {k['from']} tu {k['tu']} mode {k['mode']} act {k['act']} to {k.get('to')}{mark}")
    print("  last known place on turn 1 of those within 8 tiles of (6,15):")
    for u, p in sorted(where.items()):
        t = tup(p)
        if abs(t[0] - 6) <= 8 and abs(t[1] - 15) <= 8:
            print("    ", u, p)
