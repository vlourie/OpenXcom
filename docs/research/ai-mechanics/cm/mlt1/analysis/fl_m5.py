"""MISSION_DIRECTOR_V0: the checks of a battle with orders: decisions per unit and turn, TU paid, the orders' shots against TU and the unit's turn; repeat identity of two runs.

  py -3.13 -I fl_m5.py <battle dir> [<repeat dir>]"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
TAGS = ("[AIDECIDE] ", "[AISTATE] ", "[AICASUALTY] ", "[AIRESULT] ")
TIME = re.compile(r" v?ms=\d+")


def body(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            yield raw.rstrip("\n").split("\t", 2)[-1]


rows = list(body(sys.argv[1]))
if len(sys.argv) > 2:
    a = [TIME.sub("", s) for s in rows if s.startswith(TAGS)]
    b = [TIME.sub("", s) for s in body(sys.argv[2]) if s.startswith(TAGS)]
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    print(f"repeat: lines {len(a)} / {len(b)}, " + ("the same" if first is None and len(a) == len(b) else f"DIFFERENT from {first}"))
decs = defaultdict(int)
over = 0
paid = Counter()
tu_bad = 0
dec = None
maxn = 0
for s in rows:
    if s.startswith("[AIDECIDE] "):
        dec = dict(KV.findall(s.split(" hu=")[0]))
        if dec["side"] != "1":
            dec = None
            continue
        decs[(dec["turn"], dec["unit"])] += 1
        maxn = max(maxn, int(dec["n"]))
    elif s.startswith("[AIEXEC] ") and dec:
        x = json.loads(s[9:])
        if str(x["unit"]) == dec["unit"]:
            sp = x.get("spent") or 0
            if sp > int(dec["tu"]):
                tu_bad += 1
            if int(dec["act"]) in (7, 8, 9) and int(dec["mode"]) == 0:
                paid["paid" if sp > 0 else "no TU, not fired"] += 1
        dec = None
print(f"hostile decisions per unit-turn: max {max(decs.values())}, max n {maxn}; spent over the TU at the decision: {tu_bad}; patrol-mode shots: {dict(paid)}")
print("result lines:", sum(s.startswith('[AIRESULT]') for s in rows), "crash markers:", sum(("FATAL" in s or "Segmentation" in s or "[ERROR]" in s) for s in rows))
