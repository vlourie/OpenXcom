"""A hostile's fall crossed with its last decision and how alone it was (allies within 5 tiles, same level +-1), and whether
the side was already in contact (any hostile had seen a player unit before); also patrol walks after first contact - how
many hostile decisions are still random patrol while the side knows where the player is.

  py -3.13 -I alone_mode.py <out dir> <prefix>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
MODE = {"0": "patrol", "1": "ambush", "2": "combat", "3": "escape"}


def pos(t):
    return tuple(int(x) for x in t.strip("()").split(","))


cross = Counter()
dec = Counter()
for d in sorted(OUT.glob(f"{PRE}_*")):
    where, fac, dead, last, natt = {}, {}, set(), {}, Counter()
    contact = None
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AISTATE] "):
                k = dict(KV.findall(body))
                if "unit" in k and "pos" in k:
                    where[k["unit"]] = pos(k["pos"])
                    fac[k["unit"]] = k["faction"]
                    if k["faction"] == "1" and k.get("sees", "-") != "-" and contact is None:
                        contact = int(k.get("turn", "0") or 0)
            elif body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k = dict(KV.findall(body))
                u = k["unit"]
                last[u] = k
                if k.get("from"):
                    where[u] = pos(k["from"])
                if int(k["act"]) in ATT:
                    natt[u] += 1
                if k.get("seen", "-") not in ("-", "") and contact is None:
                    contact = int(k["turn"])
                m = MODE.get(k["mode"], k["mode"])
                after = contact is not None and int(k["turn"]) >= contact
                dec[("after_contact" if after else "before_contact", m)] += 1
            elif body.startswith("[AICASUALTY] ") and " vfaction=1 " in body:
                k = dict(KV.findall(body))
                v = k["victim"]
                if v in dead:
                    continue
                dead.add(v)
                p = pos(k["pos"])
                near = sum(1 for x, fa in fac.items() if fa == "1" and x != v and x not in dead and x in where
                           and max(abs(where[x][0] - p[0]), abs(where[x][1] - p[1])) <= 5 and abs(where[x][2] - p[2]) <= 1)
                lk = last.get(v)
                m = MODE.get(lk["mode"], lk["mode"]) + "/" + ("attack" if int(lk["act"]) in ATT else "walk" if lk["act"] == "2" else "other") if lk else "no_decision"
                cross[(m, "alone" if near == 0 else "1" if near == 1 else "2+", "attacked" if natt[v] else "never")] += 1
print("hostile falls: last decision, allies within 5, ever attacked:")
for k, v in sorted(cross.items(), key=lambda kv: -kv[1])[:16]:
    print(f"  {v:5d}  {k}")
print("hostile decisions by mode, before/after the side's first contact:")
for k, v in sorted(dec.items()):
    print(f"  {v:6d}  {k}")
