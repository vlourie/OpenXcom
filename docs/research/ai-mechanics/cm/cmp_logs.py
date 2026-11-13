"""Correctness of a flag-off arm: for each battle of series B, is the record of the same battle in series A the same - the
[AIDECIDE], [AISTATE] and [AICASUALTY] lines in order and [AIRESULT] without its timings (ms, vms).

  py -3.13 -I cmp_logs.py <out dir> <prefix A> <prefix B>     (labels <prefix>_<arm>_<scen>_s<k>; the arm part is ignored)"""
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PA, PB = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
TAGS = ("[AIDECIDE] ", "[AISTATE] ", "[AICASUALTY] ", "[AIRESULT] ")
TIME = re.compile(r" v?ms=\d+")


def lines(d):
    out = []
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith(TAGS):
                out.append(TIME.sub("", body))
    return out


def key(name, pre):
    return name[len(pre) + 1:].split("_", 1)[1]


a = {key(d.name, PA): d for d in OUT.glob(f"{PA}_*")}
same = diff = 0
for d in sorted(OUT.glob(f"{PB}_*")):
    k = key(d.name, PB)
    if k not in a:
        print("no pair", d.name)
        continue
    la, lb = lines(a[k]), lines(d)
    if la == lb:
        same += 1
        continue
    diff += 1
    i = next((i for i, (x, y) in enumerate(zip(la, lb)) if x != y), min(len(la), len(lb)))
    print(f"DIFF {k}: lines {len(la)}/{len(lb)}, first at {i}:\n  A {la[i][:200] if i < len(la) else '-'}\n  B {lb[i][:200] if i < len(lb) else '-'}")
print(f"identical {same}, different {diff}")
