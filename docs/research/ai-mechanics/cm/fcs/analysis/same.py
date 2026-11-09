"""FIRST CONTACT SURVIVAL: two battles line by line, up to the end of the shorter one: the decisions (with the state and RNG hashes), execution, casualties, events, states. The probe's own lines do not count.
Usage: same.py <dir a> <dir b>"""
import gzip
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TAGS = ("[AIDECIDE]", "[AIEXEC]", "[AICASUALTY]", "[AIEVENT]", "[AISTATE]")


def lines(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [s for s in (ln.rstrip("\n").split("\t")[-1] for ln in f) if s.startswith(TAGS)]


a, b = lines(sys.argv[1]), lines(sys.argv[2])
n = min(len(a), len(b))
for i in range(n):
    if a[i] != b[i]:
        print(f"DIFFER at line {i} of {len(a)}/{len(b)}\n  a: {a[i][:300]}\n  b: {b[i][:300]}")
        sys.exit(1)
print(f"IDENTICAL over {n} lines (a {len(a)}, b {len(b)}); decisions {sum(s.startswith('[AIDECIDE]') for s in a[:n])}")
