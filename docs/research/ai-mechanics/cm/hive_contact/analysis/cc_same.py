"""CONTACT_COORDINATION_V0: two battles with different turn limits, the same up to the shorter one's end? As hh_same.py over the AI tags; the longer run's own panic record of the next turn is the only line taken out, and it is counted (read only).
Usage: cc_same.py <out dir shorter> <out dir longer> <last turn>"""
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TAGS = ("[AIDECIDE]", "[AIEXEC]", "[AISTATE]", "[AICASUALTY]", "[AIREC]", "[AIPANIC]", "[AIAFTER]", "[AIPOSTWALK]", "[AIEVENT]")
timing = re.compile(r" (?:\w*us|\w*ms|\w*_ns|t|ms)=[-0-9.]+")
cfg = re.compile(r'"cfg":"[0-9a-f]+",')
panic = re.compile(r"\[AIPANIC\] turn=(\d+)")


def read(d, last):
    out, taken = [], 0
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.rstrip("\n").split("\t")[-1]
            if s.startswith(TAGS):
                m = panic.match(s)
                if m and int(m.group(1)) > last:
                    taken += 1
                    continue
                out.append(cfg.sub("", timing.sub("", s)))
    return out, taken


last = int(sys.argv[3])
a, ta = read(sys.argv[1], last)
b, tb = read(sys.argv[2], last)
print(Path(sys.argv[1]).name, len(a), "taken out", ta, "|", Path(sys.argv[2]).name, len(b), "taken out", tb)
n = min(len(a), len(b))
for i in range(n):
    if a[i] != b[i]:
        print("FIRST DIFFERENCE at", i, "of", n)
        print(" A", a[i][:260])
        print(" B", b[i][:260])
        sys.exit(1)
print("SAME over", n, "lines; left over A", len(a) - n, "B", len(b) - n)
