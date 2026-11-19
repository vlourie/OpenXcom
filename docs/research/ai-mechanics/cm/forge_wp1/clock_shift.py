"""AI FORGE WP1: the virtual clock between two replays: is the shift the same at every fingerprint and dump? args: run run ..."""
import re
import sys
from collections import Counter

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = re.compile(r" C=(\d+)")
for a, b in zip(sys.argv[1::2], sys.argv[2::2]):
    _, fa, da = rr.split(sic.read_log(*rr.source_of(a)))
    _, fb, db = rr.split(sic.read_log(*rr.source_of(b)))
    shifts = Counter()
    first = None
    for x, y in zip(fa, fb):
        if " ev=fp " in x:
            cx, cy = int(C.search(x).group(1)), int(C.search(y).group(1))
            if first is None:
                first = (cx, cy)
            shifts[cx - cy] += 1
    for n in set(da) & set(db):
        cx, cy = int(C.search(da[n][0]).group(1)), int(C.search(db[n][0]).group(1))
        shifts[cx - cy] += 1
    print(a, b, "first clock", first, "shifts at fingerprints and dumps", dict(shifts))
