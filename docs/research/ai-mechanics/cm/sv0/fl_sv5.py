"""STRIKE-V0: the TU reserve. In the shadow run (= D0): how the walks the order would replace ended. In the battles with the order on:
what the order shots left of the unit's TU against its TU at the start of its turn (the AI's reserve, BattlescapeGame::checkReservedTU,
is 1/3, 2/5 or 1/2 of the base TU by the unit's reserve mode; the start TU stands for the base here), the same for the other attacks.

  py -3.13 -I fl_sv5.py <out dir> <shadow prefix> <on prefix>"""
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}


def lines(d):
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        yield raw.rstrip("\n").split("\t", 2)[-1]


out, ps, pn = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
how = Counter()
for d in sorted(out.glob(f"{ps}_*")):
    want = None
    pend = None
    for s in lines(d):
        if s.startswith("[AISTRIKE] kind=exec "):
            want = dict(KV.findall(s))["unit"]
        elif s.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(s.split(" hu=")[0]))
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            if str(x["unit"]) == pend["unit"] and pend["unit"] == want:
                t = (x.get("trail") or ["(no trail)"])[-1].split(" ")[0]
                how[("spent 0, " if not x.get("spent") else "moved, ") + t] += 1
                want = None
            pend = None
print("the replaced walks in the shadow run, how they ended: " + ", ".join(f"{k}={v}" for k, v in how.most_common()))


def band(after, start):
    f = after / max(1, start)
    return "below 1/3" if f < 1 / 3 else "1/3-2/5" if f < 0.4 else "2/5-1/2" if f < 0.5 else "1/2 or more"


order = Counter()
other = Counter()
for d in sorted(out.glob(f"{pn}_*")):
    start = {}
    pend = None
    is_order = False
    for s in lines(d):
        if s.startswith("[AISTRIKE] kind=exec "):
            is_order = True
        elif s.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(s.split(" hu=")[0]))
            if pend["side"] == "1":
                start.setdefault((pend["turn"], pend["unit"]), int(pend["tu"]))
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            if str(x["unit"]) == pend["unit"] and pend["side"] == "1" and int(pend["act"]) in ATT and (x.get("spent") or 0) > 0 and not x.get("walk"):
                k = (pend["turn"], pend["unit"])
                (order if is_order else other)[band(x["tu"], start[k])] += 1
            if str(x["unit"]) == pend["unit"]:
                is_order = False
            pend = None
for name, c in (("order shots", order), ("other attacks", other)):
    n = sum(c.values())
    print(f"TU left after {name} ({n}), of the start TU: " + ", ".join(f"{k}={v} ({100 * v / n:.0f}%)" for k, v in sorted(c.items())))
