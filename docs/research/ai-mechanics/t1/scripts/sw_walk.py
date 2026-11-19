"""Switches followed by a non-attack decision: the [AITARGET] record, the switch and the decision, plus the unit's trail notes
if the decision line carries them. Counts by the gap between the nearest's and the new target's distance.

  py -3.13 sw_walk.py <out dir> <prefix> [examples]"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
NEX = int(sys.argv[3]) if len(sys.argv) > 3 else 6
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
shown = 0
gap_walk, gap_att = Counter(), Counter()
for d in sorted(OUT.glob(f"{PRE}_*")):
    rec, sw = {}, {}
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AITARGET] "):
                rec[dict(KV.findall(body))["unit"]] = body
            elif body.startswith("[AITARGETSET] "):
                sw[dict(KV.findall(body))["unit"]] = body
            elif body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k = dict(KV.findall(body))
                s = sw.pop(k["unit"], None)
                r = rec.get(k["unit"])
                if not s or not r:
                    continue
                kr = dict(KV.findall(r))
                c = {x.split(":")[0]: x.split(":") for x in kr["cands"].split(";") if x}
                g = int(c[kr["best"]][2]) - int(c[kr["near"]][2])
                g = "<=2" if g <= 2 else "3-6" if g <= 6 else ">6"
                if int(k["act"]) in ATT:
                    gap_att[g] += 1
                    continue
                gap_walk[g] += 1
                if shown < NEX:
                    shown += 1
                    print(d.name)
                    print(" ", r[:400])
                    print(" ", s)
                    print(" ", body[:330])
print("distance gap new - nearest: attacks", dict(gap_att), "non-attacks", dict(gap_walk))
