"""OPERATIONAL INTELLIGENCE, step 1: armour wear from the only logs that hold it: [HIVEINTENT] event=EFFECTNOTE of the CI runs (each hit of a noted shot: side, armour before and after, damage). Shows sample lines, then per weapon and side: hits, HP damage, armour worn, armour reached. Read only.
Usage: wear.py <run> [<run> ...]"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
shown = 0
for run in sys.argv[1:]:
    L = read(run)
    for s in L:
        if "EFFECTNOTE" in s and shown < 4:
            print(s[:400])
            shown += 1
    n = sum("EFFECTNOTE" in s for s in L)
    print(run, "EFFECTNOTE lines", n)
    keys = defaultdict(int)
    for s in L:
        if "EFFECTNOTE" in s:
            for k in kv(s):
                keys[k] += 1
    print("  keys", dict(keys))
