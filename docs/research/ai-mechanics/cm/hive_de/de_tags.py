"""DECISION ENGINE FOUNDATION, read only: what one D0 log holds - tags and a sample line of each, and the keys of the AIREC record."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
L = read(sys.argv[1] if len(sys.argv) > 1 else "scpa_D_M3_s1")
c = Counter()
ex = {}
for s in L:
    if s.startswith("["):
        t = s.split("]")[0] + "]"
        c[t] += 1
        ex.setdefault(t, s[:330])
for t, n in c.most_common():
    print(n, ex[t])
for s in L:
    if s.startswith("[AIREC]") and '"side":1' in s[:200]:
        j = json.loads(s[8:])
        if j.get("turn", 0) >= 2 and j.get("state", {}).get("tu", 0) > 30:
            print(json.dumps({k: (v if k not in ("state",) else "...") for k, v in j.items()}, ensure_ascii=False)[:1800])
            break
