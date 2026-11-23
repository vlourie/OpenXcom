"""OPERATIONAL INTELLIGENCE: what a D0 battle log holds: line kinds, one sample each. Read only."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import OUT, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
print("runs:", sorted(p.name for p in OUT.iterdir() if p.is_dir())[:80])
for run in sys.argv[1:]:
    L = read(run)
    c = Counter()
    sample = {}
    for s in L:
        k = s.split(" ", 1)[0] if s.startswith("[") else "other"
        c[k] += 1
        sample.setdefault(k, s)
    print("=====", run, len(L))
    for k, n in c.most_common():
        print(f"{n:6d} {k}  {sample[k][:420]}")
