"""FIRST CONTACT SURVIVAL, stage 2: the shadow probe's [FCSLOS] lines against the losses of the first contact window of the same battle (read only).
For every hostile decision of turn 1: exposed where it stands? does the chosen cell have lines of fire? a safe reachable cell, at what cost?
For every lost unit of the window: its last decision, did the probe see the killer's line, was there a safe cell within its TU.
And the units alive at the next player turn: under the player's eyes or not, with a safe cell at hand or not.
Usage: los.py <out tsv> <battle dir>..."""
import csv
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATTACK = {"6", "7", "8", "9"}


def kind(act):
    return "attack" if act in ATTACK else "walk" if act == "2" else "other"


tot = Counter()
out = []
for d in sys.argv[2:]:
    name = Path(d).name
    dec, cas, st2 = [], {}, {}
    last = None
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.rstrip("\n").split("\t")[-1]
            if s.startswith("[AIDECIDE] "):
                k = dict(KV.findall(s))
                last = None
                if k["side"] == "1" and k["turn"] == "1":
                    dec.append(k)
                    last = k
            elif s.startswith("[FCSLOS] "):
                k = dict(KV.findall(s))
                if last and k["unit"] == last["unit"]:  # the probe prints right after the unit's own decision line
                    last["los"] = k
            elif s.startswith("[AICASUALTY] "):
                k = dict(KV.findall(s))
                if k.get("vfaction") == "1":
                    cas.setdefault(k["victim"], k)
            elif s.startswith("[AISTATE] pstart"):
                k = dict(KV.findall(s))
                if k.get("turn") == "2" and k.get("faction") == "1":
                    st2[k["unit"]] = k
    have = [k for k in dec if "los" in k]
    print(f"== {name}: hostile decisions of turn 1: {len(dec)}, with the probe {len(have)}, known median {sorted(int(k['los']['known']) for k in have)[len(have) // 2] if have else '-'}")
    c = Counter()
    for k in have:
        l = k["los"]
        key = (kind(k["act"]), "now_exposed" if l["now"] != "-" else "now_clear", "dest_exposed" if l["dest"] != "-" else "dest_clear", "safe_exists" if int(l["safe"]) else "no_safe")
        c[key] += 1
        tot[key] += 1
    for key, n in sorted(c.items(), key=lambda a: -a[1]):
        print("  ", n, *key)
    lastdec = {}
    for k in have:
        lastdec[k["unit"]] = k
    g = Counter()
    for u, k in lastdec.items():
        st = st2.get(u)
        if st:
            g[("last_" + kind(k["act"]), "seen_at_pstart" if int(st.get("seenby", "0")) else "unseen_at_pstart", "safe_existed" if int(k["los"]["safe"]) else "no_safe")] += 1
    print("   alive at the next player turn, by the last decision:")
    for key, n in sorted(g.items(), key=lambda a: -a[1]):
        print("    ", n, *key)
    for v, ca in cas.items():
        t, side = int(ca["turn"]), ca["side"]
        if not (t == 1 or (t == 2 and side == "0")):
            continue
        ds = [k for k in have if k["unit"] == v]
        if not ds:
            continue
        k = ds[-1]
        l = k["los"]
        kill = ca.get("killer", "-1")
        out.append(dict(battle=name, turn=t, side=side, unit=v, type=ca.get("type", "")[4:18], act=k["act"], mode=k["mode"], at=k["from"], to=k["to"], tu=l["tu"], lost_at=ca.get("pos"), killer=kill, dist=ca.get("dist"),
                        killer_line_now=int(kill in l["now"].split(",")), killer_line_dest=int(kill in l["dest"].split(",")), known=l["known"], cells=l["cells"], safe=l["safe"], cheapest=l["best"].split(";")[0], decisions=len(ds)))
print()
print("all:")
for key, n in sorted(tot.items(), key=lambda a: -a[1]):
    print("  ", n, *key)
print()
if out:
    with open(sys.argv[1], "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(out[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(out)
    for r in out:
        print(r["battle"][-5:], "t" + str(r["turn"]), "s" + r["side"], r["unit"], r["type"], "a" + r["act"], "m" + r["mode"], r["at"], ">", r["to"], "tu" + r["tu"], "lost", r["lost_at"], "by", r["killer"], "d" + str(r["dist"]), "lineNow" + str(r["killer_line_now"]), "lineDest" + str(r["killer_line_dest"]), "known" + r["known"], "cells" + r["cells"], "safe" + r["safe"], r["cheapest"])
