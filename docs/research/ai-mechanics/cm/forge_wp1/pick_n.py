"""AI FORGE WP1: event N for R6: the first decide fingerprint after the enemy's first psi action, taken from R5."""
import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_, f, _ = rr.split(sic.read_log(*rr.source_of("R5")))
psi = next(s for s in f if " ev=boundary " in s and "kind=psi.1" in s)
p = int(re.search(r"n=(\d+)", psi).group(1))
print("psi", psi[:200])
for s in f:
    n = int(re.search(r"n=(\d+)", s).group(1))
    if n > p and " ev=fp " in s and " at=decide " in s:
        print("N", n)
        print(s[:400])
        break
