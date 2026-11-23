"""Does the expected effect model hold? For every recorded attack at the nearest target (E1 = D0 decisions): did that shooter put
that target out the same turn ([AICASUALTY] killer=unit victim=near), grouped by the model's score of the nearest.
Also the same for the attacks where the model valued the nearest highly - a calibration of the score against the outcome.

  py -3.13 verify_ev.py <out dir> <prefix>"""
import gzip
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
bins = defaultdict(lambda: [0, 0, 0])  # attacks, the target out by this shooter this turn, of them stunned
weap = defaultdict(lambda: [0, 0, 0])
for d in sorted(OUT.glob(f"{PRE}_*")):
    pend = {}
    shots = []  # (turn, unit, near, score bin, weapon)
    outs = set()
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AITARGET] "):
                k = dict(KV.findall(body))
                if k["model"] != "1":
                    continue
                c = {x.split(":")[0]: int(x.split(":")[5]) for x in k["cands"].split(";") if x}
                pend[k["unit"]] = (k["near"], c[k["near"]], k["weapon"])
            elif body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k = dict(KV.findall(body))
                p = pend.pop(k["unit"], None)
                if p and int(k["act"]) in ATT and k.get("aim") == p[0]:
                    sc = p[1]
                    b = "0" if sc == 0 else "1-49" if sc < 50 else "50-199" if sc < 200 else "200-499" if sc < 500 else "500+"
                    shots.append((k["turn"], k["unit"], p[0], b, p[2]))
            elif body.startswith("[AICASUALTY] "):
                k = dict(KV.findall(body))
                outs.add((k["turn"], k.get("killer"), k["victim"], k.get("how")))
    for t, u, v, b, w in set(shots):
        hit = [h for (tt, kk, vv, h) in outs if tt == t and kk == u and vv == v]
        bins[b][0] += 1
        bins[b][1] += bool(hit)
        bins[b][2] += any(h != "dead" for h in hit)
        if b == "0":
            weap[w][0] += 1
            weap[w][1] += bool(hit)
            weap[w][2] += any(h != "dead" for h in hit)
print("score of the nearest (x1000) -> distinct (turn, shooter, target) attacks, target out by the shooter that turn, of them not dead")
for b in ("0", "1-49", "50-199", "200-499", "500+"):
    a, o, s = bins[b]
    print(f"  {b:8s} {a:5d} {o:5d} ({100 * o / max(1, a):.0f}%) not dead {s}")
print("score 0, by weapon (attacks, out, not dead):", {w: tuple(v) for w, v in sorted(weap.items(), key=lambda x: -x[1][0])[:15]})
