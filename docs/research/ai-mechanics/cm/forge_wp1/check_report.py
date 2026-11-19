"""AI FORGE WP1: the monitor's counters and every run's exit code, as the records say, to check the report against."""
import json
import re
from pathlib import Path

F = Path(__file__).resolve().parent
c = json.loads((F / "WP1_COMPARE.json").read_text(encoding="utf-8-sig"))
for k, v in c["monitor"].items():
    print(k, {x: y for x, y in v.items() if x not in ("first_violations", "first_notes", "mark_by", "clear_by", "marks_by", "clears_by")})
for p in sorted((F / "res").glob("run_fg*.txt")):
    print(p.name, re.findall(r"code=-?\d+", p.read_text(encoding="utf-8", errors="replace")))
