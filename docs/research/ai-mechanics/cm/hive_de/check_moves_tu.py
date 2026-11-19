"""Guard for R-709: a script that reads the [AICAND] moves list has to drop the tiles with a negative cost, they are not reachable.
Usage: check_moves_tu.py <folder or script>... Prints the scripts without the filter, exit code 1 if there are any."""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
READS = re.compile(r"AICAND\\?\]\s*moves=")
FILTER = re.compile(r">=\s*0\b|<\s*0\b|:-1")
bad = 0
seen = 0
for a in sys.argv[1:]:
    p = Path(a)
    for f in sorted(p.glob("*.py")) if p.is_dir() else [p]:
        s = f.read_text(encoding="utf-8-sig", errors="replace")
        if f.name == Path(__file__).name or not READS.search(s):
            continue
        seen += 1
        if not FILTER.search(s):
            print("no negative-cost filter:", f)
            bad += 1
print("scripts that read moves:", seen, "without the filter:", bad)
sys.exit(1 if bad else 0)
