"""AI-T2 step 1: the D0 attacks at the nearest target whose expected effect is 0 (E1 record = D0 decisions), and for each the
other recorded targets with a line of fire and their expected effect in HP (absolute, no maximum health). Counts by the
alternative's faction and by the HP threshold; the same split for the attacks that did put the target out.

  py -3.13 t2_repro.py <out dir> <prefix> [examples tsv]"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
EX = Path(sys.argv[3]) if len(sys.argv) > 3 else None
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
THR = (1, 3, 5, 10)
c = Counter()
alt = Counter()
fac_best = Counter()
weap = Counter()
rows = []
for d in sorted(OUT.glob(f"{PRE}_*")):
    pend = {}
    shots = []
    outs = set()
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AITARGET] "):
                k = dict(KV.findall(body))
                if k["model"] != "1":
                    continue
                cands = {}
                for x in k["cands"].split(";"):
                    if x:
                        i, fac, dist, ev, hp, sc = x.split(":")
                        cands[i] = (int(fac), int(dist), int(ev), int(sc))
                pend[k["unit"]] = (k, cands)
            elif body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k = dict(KV.findall(body))
                p = pend.pop(k["unit"], None)
                if not p:
                    continue
                r, cands = p
                near = r["near"]
                if int(k["act"]) in ATT and k.get("aim") == near and cands[near][3] == 0:
                    shots.append((k["turn"], k["unit"], near, r["weapon"], cands, k["act"]))
            elif body.startswith("[AICASUALTY] "):
                k = dict(KV.findall(body))
                outs.add((k["turn"], k.get("killer"), k["victim"]))
    seen = set()
    for t, u, v, w, cands, act in shots:
        if (t, u, v) in seen:
            continue
        seen.add((t, u, v))
        c["useless_attacks"] += 1
        c["target_out_anyway"] += (t, u, v) in outs
        weap[w] += 1
        others = {i: x for i, x in cands.items() if i != v}
        c["with_other_target_lof"] += bool(others)
        best = max(others.items(), key=lambda kv: (kv[1][2], -kv[1][1]), default=None)
        for th in THR:
            ok = [i for i, x in others.items() if x[2] >= th]
            alt[f"alt_ev>={th}"] += bool(ok)
            alt[f"alt_ev>={th}_player"] += any(others[i][0] == 0 for i in ok)
            alt[f"alt_ev>={th}_civilian_only"] += bool(ok) and all(others[i][0] == 2 for i in ok)
        if best and best[1][2] >= 1:
            fac_best[best[1][0]] += 1
        rows.append((d.name, t, u, w, v, cands[v][1], best[0] if best else "-", best[1][0] if best else "-",
                     best[1][1] if best else "-", best[1][2] if best else "-", act))
print("D0 attacks at the nearest with expected effect 0:", dict(c))
print("alternatives (another seen target with a line of fire, expected HP this turn):", dict(alt))
print("faction of the best alternative with ev>=1 (0 player, 2 civilian):", dict(fac_best))
print("weapons:", dict(weap.most_common(12)))
if EX:
    with open(EX, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("battle\tturn\tunit\tweapon\tnear\tnear_dist\tbest\tbest_faction\tbest_dist\tbest_ev\tact\n")
        for r in rows:
            f.write("\t".join(map(str, r)) + "\n")
