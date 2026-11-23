"""HIVE COMBAT INTENT V0: EFFECTNOTE: the rule armour against the worn armour at the refusals no_effect, and how the refused contacts ended. Read only.
Usage: effect_notes.py <run>"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
by = defaultdict(list)
for s in read(sys.argv[1]):
    if s.startswith("[HIVEINTENT] event=EFFECTNOTE"):
        k = kv(s)
        by[k["contact"]].append((int(k["turn"]), k["unit"], k["weapon"], k["rule"], k["now"]))
for c, rows in sorted(by.items()):
    first, last = rows[0], rows[-1]
    print("contact", c, "notes", len(rows), "weapons", sorted({r[2] for r in rows}))
    print("   rule f/r/b/l", first[3], "| now first", first[4], "turn", first[0], "| now last", last[4], "turn", last[0])
