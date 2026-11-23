"""The attacks on the contact in cc8's two useful assignments: did the unit see the contact at its first decision of the turn, and did it walk before the shot? Read only."""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
SPANS = {("1", 3): "448", ("0", 7): "470"}
L = read("cc8_CC_M6_s1")
dec = defaultdict(list)
units = defaultdict(set)
sees = {}
for s in L:
    if s.startswith("[AIDECIDE]"):
        k = kv(s)
        if k["side"] == "1":
            dec[(int(k["turn"]), k["unit"])].append(k)
    elif s.startswith("[AISTATE] aistart"):
        k = kv(s)
        sees[(int(k["turn"]), k["unit"])] = k.get("sees", "-")
    elif s.startswith("[HIVECC]") and "event=ORDER" in s and "role=REINFORCE" in s:
        k = kv(s)
        units[(k["squad"], int(k["turn"]))].add((k["unit"], k["kind"]))
for (sq, t), c in SPANS.items():
    for u, kind in sorted(units[(sq, t)]):
        ds = dec[(t, u)]
        hit = [i for i, d in enumerate(ds) if int(d["act"]) in ATT and d["aim"] == c]
        print("sq", sq, "t", t, "c", c, "unit", u, kind, "start sees", sees.get((t, u)), "hits at decisions", hit, "acts", [d["act"] for d in ds])
