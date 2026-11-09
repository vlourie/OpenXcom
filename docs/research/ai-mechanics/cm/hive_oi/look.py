"""OPERATIONAL INTELLIGENCE: full sample lines of an AI side attack in a D0 log. Read only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
L = read(sys.argv[1])
n = 0
for i, s in enumerate(L):
    if s.startswith("[AIDECIDE]"):
        k = kv(s)
        if k["side"] == "1" and k["act"] in ("8", "9", "7", "6") and int(k["turn"]) == 2:
            n += 1
            if n in (1, 6):
                for t in L[i - 2 : i + 7]:
                    print(t[:2600])
                    print("-")
                print("=====")
for s in L:
    if s.startswith("[AISTATE]") and "faction=1" in s:
        print(s[:500])
        break
for s in L:
    if s.startswith("[AIPROBE]"):
        print(s[:300])
