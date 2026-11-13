"""HIVE COMMAND CORE V0: the kinds of hive lines in a journal with their count and first samples (read only). Usage: tags.py <dir>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
lines = [ln.rstrip("\n").split("\t")[-1] for ln in gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace")]
kinds = Counter()
shown = Counter()
for s in lines:
    m = re.match(r"\[(HIVE\w*)\]", s)
    if not m:
        continue
    t = m.group(1)
    second = s.split(" ")[1].split("=")[0] if " " in s else ""
    key = t + ":" + (s.split(" ")[3].split("=")[0] if t == "HIVECMD" and len(s.split(" ")) > 3 else second)
    kinds[t] += 1
    shown[key] += 1
    if shown[key] <= 2 and t != "HIVEORD":
        print(s[:260])
print(kinds)
