"""UNIFIED ARMY CONTROL V0, read only: last figures for the result. Commanders and their tasks, panic behind RESULT's lost time units, patrol shuttles, the example of F8, the end of each battle. Writes final.txt next to this file. Usage: ua_final.py"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
SC = [("M6 s1", "ua4_UO_M6_s1", "ua1_UN_M6_s1"), ("M3 s1", "ua6_UO_M3_s1", "ua2_UN_M3_s1"), ("M8 s1", "ua8_UO_M8_s1", "ua3_UN_M8_s1")]
out = open(HERE / "final.txt", "w", encoding="utf-8-sig")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.write(s + "\n")


def shuttles(L):
    seq = defaultdict(list)
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1" and int(k["turn"]) <= 8 and k["mode"] == "0" and k["act"] == "2" and k["to"] != k["from"]:
                seq[k["unit"]].append(k["to"])
    n = tot = 0
    for v in seq.values():
        w = [a for a, b in zip(v, [None] + v) if a != b]
        tot += len(w)
        n += sum(w[i] == w[i - 2] for i in range(2, len(w)))
    return n, tot


for name, off, on in SC:
    p("=====", name)
    A, B = read(off), read(on)
    cmd = [kv(s) for s in B if s.startswith("[HIVECMD]")]
    p("  commanders", len(cmd), "kept", dict(Counter(k.get("kept") for k in cmd)), "why", dict(Counter(k.get("why") for k in cmd)), "task labels", dict(Counter(k.get("task") for k in cmd)))
    dec = {(kv(s)["turn"], kv(s)["unit"]) for s in B if s.startswith("[AIDECIDE]")}
    lost = [kv(s) for s in B if s.startswith("[HIVEUA] event=RESULT") and " tu=0 " in s and " moved=0 " in s]
    lost = [k for k in lost if (k["turn"], k["unit"]) not in dec]
    st = Counter()
    for k in lost:
        for s in B:
            if s.startswith("[AISTATE] aistart") and f"turn={k['turn']} " in s and f"unit={k['unit']} " in s:
                st[kv(s).get("status")] += 1
                break
    p("  no decision, time units gone:", len(lost), "status at the side's start", dict(st))
    p("  patrol shuttles A-B-A among distinct targets, OFF", shuttles(A), "ON", shuttles(B))
    for run, L in ((off, A), (on, B)):
        r = kv([s for s in L if s.startswith("[AIRESULT]")][-1])
        p(f"  {run}: " + " ".join(f"{x}={r.get(x)}" for x in ("how", "turn", "player", "pdead", "livesoldiers", "pwounded", "phplost", "hostile", "hdead", "hout", "hleft", "livealiens", "pmoves", "pattacks", "hmoves", "hattacks")))
    if name == "M8 s1":
        for s in B:
            if s.startswith("[HIVEUA]") and "turn=1 " in s and "unit=1000000 " in s and ("event=CHOICE" in s or "event=RESULT" in s):
                p("  ", s[:260])
        p("   OFF", [(k["n"], k["mode"], k["act"], k["from"], k["to"], k["tu"]) for k in (kv(s) for s in A if s.startswith("[AIDECIDE]") and "turn=1 " in s and "unit=1000000 " in s)][:4])
        p("   ON ", [(k["n"], k["mode"], k["act"], k["from"], k["to"], k["tu"]) for k in (kv(s) for s in B if s.startswith("[AIDECIDE]") and "turn=1 " in s and "unit=1000000 " in s)][:4])
out.close()
