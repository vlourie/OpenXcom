"""Print the log lines of one soldier in one turn, in order, cut to a width. Read only.
Usage: around.py <run> <unit> <turn> [width]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
run, unit, turn = sys.argv[1:4]
width = int(sys.argv[4]) if len(sys.argv) > 4 else 400
cur = None
on = False
for s in read(run):
    if s.startswith("[AIDECIDE]"):
        k = kv(s)
        cur = k["turn"]
        on = k["unit"] == unit
    if cur != turn:
        continue
    if f"unit={unit}" in s or f'"unit":{unit}' in s or (on and s.startswith(("[AIREC]", "[AIEXEC]"))):
        print(s[:width])
