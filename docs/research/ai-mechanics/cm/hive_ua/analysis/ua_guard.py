"""UNIFIED ARMY CONTROL V0, read only: guards. A soldier on a ranked node keeps to it without a task (scout=false); the task's map-wide rungs lift that. Who, how often, what became of them; flood time. Writes guard.txt next to this file. Usage: ua_guard.py"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
SC = [("M6 s1", "ua4_UO_M6_s1", "ua1_UN_M6_s1"), ("M3 s1", "ua6_UO_M3_s1", "ua2_UN_M3_s1"), ("M8 s1", "ua8_UO_M8_s1", "ua3_UN_M8_s1")]
ATT = set(range(4, 21))
out = open(HERE / "guard.txt", "w", encoding="utf-8-sig")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.write(s + "\n")


def decs(L):
    d = defaultdict(list)
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1" and int(k["turn"]) <= 8:
                d[k["unit"]].append(k)
    return d


for name, off, on in SC:
    p("=====", name)
    A, B = read(off), read(on)
    a, b = decs(A), decs(B)
    types = {}
    for s in A:
        if s.startswith("[AISTATE]") and " faction=1 " in s:
            k = kv(s)
            types.setdefault(k["unit"], k["type"])
    guards = []
    for u, ds in a.items():
        turns = {x["turn"] for x in ds}
        still = {x["turn"] for x in ds if x["act"] == "0"} - {x["turn"] for x in ds if x["act"] != "0"}
        if len(turns) >= 2 and len(still) * 2 >= len(turns):
            guards.append((u, len(turns), len(still)))
    p(f"  soldiers standing at least half their turns without headquarters: {len(guards)}")
    down = {s for s in (kv(x)["victim"] for x in A if x.startswith("[AICASUALTY]"))}
    downb = {s for s in (kv(x)["victim"] for x in B if x.startswith("[AICASUALTY]"))}
    for u, n, st in guards:
        ds = b.get(u, [])
        moved = len({x["from"] for x in ds})
        ch = [kv(s) for s in B if s.startswith("[HIVEUA] event=CHOICE") and "unit=" + u + " " in s]
        p(f"   {u} {types.get(u)}: OFF turns {n}, standing {st}, attacks {sum(int(x['act']) in ATT for x in a[u])}, fell {u in down}; ON turns {len({x['turn'] for x in ds})}, places {moved}, attacks {sum(int(x['act']) in ATT for x in ds)}, fell {u in downb}, rungs {dict(Counter(k['rung'] for k in ch))}")
    ch = [kv(s) for s in B if s.startswith("[HIVEUA] event=CHOICE") and "changed=1" in s]
    p(f"  changed choices by rung {sorted(Counter(k['rung'] for k in ch).items())}; map-wide rungs (1,3) {sum(k['rung'] in ('1', '3') for k in ch)} of {len(ch)}")
    t = [kv(s) for s in B if s.startswith("[HIVEPERF]") and "phase=turn" in s]
    p(f"  floods by turn {[(k['turn'], k['floods'], k['floodUs']) for k in t]}")
    for run, L in ((off, A), (on, B)):
        r = [s for s in L if s.startswith("[AIRESULT]")]
        p(f"  {run} battle ms {kv(r[-1]).get('ms')}")
L = read("ra1_AN_M6_s1")
p("RA M6 s1 ms", kv([s for s in L if s.startswith("[AIRESULT]")][-1]).get("ms"), "phases", Counter(kv(s).get("phase") for s in L if s.startswith("[HIVEPERF]")))
out.close()
