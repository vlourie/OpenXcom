"""HIVE hardening: are two battles the same? Every decision, its execution, the state and the casualties, line by line, over the shorter one (a battle may be cut by its turn limit).
Usage: hh_same.py <out dir A> <out dir B>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TAGS = ("[AIDECIDE]", "[AIEXEC]", "[AISTATE]", "[AICASUALTY]", "[AIREC]", "[AIPANIC]", "[AIAFTER]", "[AIPOSTWALK]", "[AIEVENT]")
timing = re.compile(r" (?:\w*us|\w*ms|\w*_ns|t|ms)=[-0-9.]+")
cfg = re.compile(r'"cfg":"[0-9a-f]+",')  # the hash of the flags: they differ between the arms by design


def read(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        out = []
        for ln in f:
            s = ln.rstrip("\n").split("\t")[-1]
            if s.startswith(TAGS):
                out.append(cfg.sub("", timing.sub("", s)))
        return out


a, b = read(sys.argv[1]), read(sys.argv[2])
print(Path(sys.argv[1]).name, len(a), "|", Path(sys.argv[2]).name, len(b))
print("counts A", Counter(s.split(" ")[0] for s in a).most_common(9))
n = min(len(a), len(b))
for i in range(n):
    if a[i] != b[i]:
        print("FIRST DIFFERENCE at", i, "of", n)
        print(" A", a[i][:300])
        print(" B", b[i][:300])
        sys.exit(1)
print("SAME over", n, "lines; left over A", len(a) - n, "B", len(b) - n)
