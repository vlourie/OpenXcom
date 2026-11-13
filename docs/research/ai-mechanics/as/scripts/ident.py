"""Decision identity: every [AIDECIDE] and [AIRESULT] line of a new battle against the archived D0 battle of the same scenario and seed.

  py -3.13 ident.py <new out dir> <D0 out dir> <prefix> [<prefix> ...]"""
import gzip
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
NEW, OLD = Path(sys.argv[1]), Path(sys.argv[2])


def lines(p):
    out = []
    with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith(("[AIDECIDE] ", "[AIRESULT]", "[AICASUALTY] ")):
                # the wall time of the battle (ms=) is not a decision
                out.append(" ".join(w for w in body.split() if not w.startswith("ms=")))
    return out


same = diff = 0
for pre in sys.argv[3:]:
    for d in sorted(NEW.glob(f"{pre}_*")):
        old = OLD / ("D0" + d.name[len(pre):]) / "openxcom.log.gz"
        a, b = lines(d / "openxcom.log.gz"), lines(old)
        if a == b:
            same += 1
            print(f"{d.name}: IDENTICAL {len(a)} lines")
            continue
        diff += 1
        k = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        print(f"{d.name}: DIFFERS at line {k} of {len(a)}/{len(b)}")
        print("  new", a[k][:300] if k < len(a) else "-")
        print("  D0 ", b[k][:300] if k < len(b) else "-")
print(f"identical {same}, different {diff}")
