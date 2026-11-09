"""E2 target switches: every [AITARGETSET] (setupAttack took the clearly better target), whether the unit's decision right after
it was an attack at that target, whether the switched target went out by that shooter the same turn, and its faction.

  py -3.13 switches.py <out dir> <prefix>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
c = Counter()
acts = Counter()
per = Counter()
for d in sorted(OUT.glob(f"{PRE}_*")):
    fac = {}
    pend = {}
    sw = []
    outs = set()
    recs = 0
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AISTATE] "):
                k = dict(KV.findall(body))
                if "unit" in k and "faction" in k:
                    fac[k["unit"]] = k["faction"]
            elif body.startswith("[AITARGET] "):
                recs += 1
                k = dict(KV.findall(body))
                c["picks"] += 1
                c["pick_flag"] += k["pick"] == "1"
            elif body.startswith("[AITARGETSET] "):
                k = dict(KV.findall(body))
                pend[k["unit"]] = k
            elif body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k = dict(KV.findall(body))
                p = pend.pop(k["unit"], None)
                if p:
                    att = int(k["act"]) in ATT
                    acts[k["act"]] += 1
                    sw.append((k["turn"], k["unit"], p["to"], att and k.get("aim") == p["to"], att))
            elif body.startswith("[AICASUALTY] "):
                k = dict(KV.findall(body))
                outs.add((k["turn"], k.get("killer"), k["victim"]))
    per[d.name.split("_")[1]] += len(sw)
    for t, u, v, at, att in sw:
        c["switch"] += 1
        c["attack"] += att
        c["attack_at_new"] += at
        c["new_civilian"] += fac.get(v) == "2"
        c["new_player"] += fac.get(v) == "0"
        c["out_by_shooter_same_turn"] += at and (t, u, v) in outs
        c["attack_at_new_player"] += at and fac.get(v) == "0"
        c["out_player"] += at and fac.get(v) == "0" and (t, u, v) in outs
        c["attack_at_new_civilian"] += at and fac.get(v) == "2"
        c["out_civilian"] += at and fac.get(v) == "2" and (t, u, v) in outs
print("records and switches:", dict(c))
print("decision right after a switch (act):", dict(acts))
print("switches per scenario:", dict(sorted(per.items())))
