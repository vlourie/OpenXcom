"""HIVE D2 CORRECTION, read only: the test of the closed exit on M3: every patrol result of the pocket's soldiers on turns 1-2 against the line where (4,18,0) is taken and left; a path out while it is taken would refute the explanation."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
run = sys.argv[1] if len(sys.argv) > 1 else "d23_DN_M3_s1"
L = read(run)
W = ("1000050", "1000027", "1000016", "1000028")
for i, s in enumerate(L):
    if s.startswith("[HIVEUA] event=PATROLEND"):
        k = kv(s)
        if k["unit"] in W and int(k["turn"]) <= 2:
            print(f"line {i} END t{k['turn']} {k['unit']} at {k['at']} tries {k['tries']} refused {k['refused']} taken {k['taken']} end {k['end']}")
    elif s.startswith("[AIEXEC]"):
        j = json.loads(s[9:])
        if str(j.get("unit")) in W:
            tr = j.get("trail") or []
            if j.get("walk") and i < 4000:
                print(f"line {i} WALK {j.get('unit')} rec {j.get('rec')} pos {j.get('pos')} spent {j.get('spent')} trail {str(tr)[:150]}")
    elif s.startswith("[AIPANIC]") and "side=0" in s and "turn=2" in s:
        print(f"line {i} {s[:50].strip()}")
    elif s.startswith("[HIVEREACH]"):
        k = kv(s)
        if k["unit"] in W and int(k["turn"]) <= 2:
            print(f"line {i} FIELD t{k['turn']} {k['unit']} at {k['at']} tiles {k['tiles']}")
