"""HIVE D2 CORRECTION, read only: who shuts the pocket on M3 turn 1. 1000016 at the exit in OFF and ON: the mode dice on the same tile; everyone who crosses (4,18,0) on turn 1 and 2; the first thinks of the two soldiers once it is free; each think of ON with no node at the end."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
EXIT = [4, 18, 0]
for run in sys.argv[1:] or ["d21_DO_M3_s1", "d23_DN_M3_s1", "us2_QN_M3_s1"]:
    print("=====", run)
    L = read(run)
    for i, s in enumerate(L):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["unit"] == "1000016" and k["turn"] in ("1", "2"):
                print(f"  line {i} t{k['turn']} 1000016 from {k['from']} tu {k['tu']} mode {k['mode']} act {k['act']} to {k.get('to')}")
        if s.startswith("[AIREC]"):
            j = json.loads(s[8:])
            if str(j.get("unit")) == "1000016" and j.get("turn") in (1, 2):
                b = j.get("base", {})
                r = b.get("reason", {})
                print(f"     rec {j.get('rec')} src {b.get('src')} odds {r.get('odds')} roll {r.get('roll')} keys {list(r.keys())[:10]}")
        if s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            tr = j.get("trail") or []
            if any(list(p)[:3] == EXIT for p in tr if isinstance(p, (list, tuple))) or j.get("pos") == EXIT:
                print(f"  line {i} crosses or ends on the exit: unit {j.get('unit')} rec {j.get('rec')} walk {j.get('walk')} end {j.get('pos')} spent {j.get('spent')}")
    ended = [(i, kv(s)) for i, s in enumerate(L) if s.startswith("[HIVEUA] event=PATROLEND")]
    for i, e in ended:
        if e["end"] == "none":
            print(f"  line {i} NO NODE t{e['turn']} unit {e['unit']} at {e['at']} tries {e['tries']} checked {e['free_checked']} refused {e['refused']} tu {e['tu']}")
