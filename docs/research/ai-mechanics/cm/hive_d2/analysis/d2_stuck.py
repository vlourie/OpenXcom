"""HIVE D2 CORRECTION, read only: a walk to a kept node that does nothing, turn after turn. Whose node it was (offer or the soldier's own), since when, who stands on it, how far along the soldier is, and when it ends."""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def main(run):
    L = read(run)
    print("=====", run)
    origin = {}
    seq = []
    last_at = {}
    for i, s in enumerate(L):
        if s.startswith("[HIVEUA] event=PATROLEND"):
            e = kv(s)
            if e["end"] != "none":
                origin[(e["unit"], e["end"])] = ("offer" if int(e["taken"]) else "own", e["turn"], i)
        elif s.startswith("[AIDECIDE]"):
            seq.append((i, kv(s)))
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            if seq and str(j.get("unit")) == seq[-1][1]["unit"]:
                k = seq[-1][1]
                seq[-1] = (seq[-1][0], k, j)
    ranges = defaultdict(list)
    place = defaultdict(list)  # turn -> where everyone is, in order
    for row in seq:
        if len(row) < 3:
            continue
        i, k, j = row
        if k.get("side") != "1":
            continue
        p = j.get("pos")
        place[k["unit"]].append((i, int(k["turn"]), tuple(p) if p else None))
        if k["act"] == "2" and j.get("spent", 0) == 0 and not (j.get("trail") or []):
            ranges[(k["unit"], k.get("to"))].append((int(k["turn"]), i, k["from"], k["tu"]))
    print(" no-reason empty walks by soldier and node:")
    for (u, to), v in sorted(ranges.items(), key=lambda x: -len(x[1])):
        o = origin.get((u, to))
        ts = sorted({x[0] for x in v})
        tgt = tuple(int(a) for a in to.strip("()").split(","))
        i0 = v[0][1]
        on = []
        for w, w_pl in place.items():
            before = [x for x in w_pl if x[0] <= i0 and x[2]]
            if before and before[-1][2] == tgt and w != u:
                on.append(w)
        print("  ", u, "->", to, "n", len(v), "turns", ts, "from", sorted({x[2] for x in v}), "node of", o, "standing on it at the first:", on)
    keys = [s for s in L if "STALE" in s[:40] or "stale" in s[:40]]
    print(" stale lines", len(keys), keys[0][:160] if keys else "")


for r in sys.argv[1:] or ["d23_DN_M3_s1", "d26_DN_M6_s1", "d21_DO_M3_s1", "us2_QN_M3_s1"]:
    main(r)
