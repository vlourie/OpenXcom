"""Print the raw log lines around the first patrol-mode shots of one battle, cut for reading.

  py -3.13 -I log_ctx.py <battle dir> <how many shots> <lines after>"""
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
d, want, after = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
lines = [r.rstrip("\n").split("\t", 2)[-1] for r in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace")]
found = 0
for i, s in enumerate(lines):
    if s.startswith("[AIDECIDE] ") and " side=1 " in s and " mode=0 " in s and re.search(r" act=(7|8|9) ", s):
        found += 1
        print("-----")
        for t in lines[i - 1 : i + after]:
            print(re.sub(r" hu=.*", "", t)[:380])
        if found >= want:
            break
