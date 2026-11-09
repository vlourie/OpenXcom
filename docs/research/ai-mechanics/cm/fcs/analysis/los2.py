"""FIRST CONTACT SURVIVAL, stage 2: the corrected probe's [FCSLOS] lines of hostile turn 1 against the same battle's losses (read only).
By mode: walkers' start and chosen cell exposed or not, safe cells by the line itself and by the AI's own answer, the cheapest safe cell against the TU.
Then every lost unit of the window that decided on turn 1, with what the probe knew.
Usage: los2.py <out tsv> <battle dir>..."""
import csv
import gzip
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATTACK = {"6", "7", "8", "9"}
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
                if last and k["unit"] == last["unit"]:
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
    cells = sum(int(k["los"]["cells"]) for k in have)
    safe = sum(int(k["los"]["safe"]) for k in have)
    old = sum(int(k["los"]["safeOld"]) for k in have)
    print(f"== {name}: decisions {len(dec)}, with the probe {len(have)}; reachable cells over them {cells}: safe by the line {safe} ({safe / max(cells, 1):.0%}), by the AI's own answer {old} ({old / max(cells, 1):.0%})")
    c = Counter()
    for k in have:
        l = k["los"]
        cost = int(l["best"].split(";")[0].split(":")[1]) if int(l["safe"]) else None
        kind = "attack" if k["act"] in ATTACK else "walk" if k["act"] == "2" else "other"
        if kind == "attack":
            key = (f"m{k['mode']}", kind, "now_exposed" if l["now"] != "-" else "now_clear", "safe" if cost is not None else "no_safe")
        else:
            key = (f"m{k['mode']}", kind, "now_exposed" if l["now"] != "-" else "now_clear", "dest_exposed" if l["dest"] != "-" else "dest_clear", "safe" if cost is not None else "no_safe")
        c[key] += 1
    for key, n in sorted(c.items(), key=lambda a: -a[1]):
        print("  ", n, *key)
    lastdec = {}
    for k in have:
        lastdec[k["unit"]] = k
    g = Counter()
    for u, k in lastdec.items():
        st = st2.get(u)
        if st:
            g[(f"m{k['mode']}", "a" + k["act"], "dest_exposed" if k["los"]["dest"] != "-" else "dest_clear", "seen_at_pstart" if int(st.get("seenby", "0")) else "unseen_at_pstart")] += 1
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
        out.append(dict(battle=name, turn=t, side=side, unit=v, type=ca.get("type", "")[8:18], act=k["act"], mode=k["mode"], at=k["from"], to=k["to"], tu=l["tu"], lost_at=ca.get("pos"), killer=kill, dist=ca.get("dist"),
                        killer_line_now=int(kill in l["now"].split(",")), killer_line_dest=int(kill in l["dest"].split(",")), n_now=0 if l["now"] == "-" else len(l["now"].split(",")), n_dest=0 if l["dest"] == "-" else len(l["dest"].split(",")),
                        known=l["known"], cells=l["cells"], safe=l["safe"], safe_old=l["safeOld"], cheapest=l["best"].split(";")[0], decisions=len(ds)))
print()
if out:
    with open(sys.argv[1], "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(out[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(out)
    for r in out:
        print(r["battle"][-5:], "t" + str(r["turn"]), "s" + r["side"], r["unit"], r["type"], "a" + r["act"], "m" + r["mode"], r["at"], ">", r["to"], "tu" + r["tu"], "lost", r["lost_at"], "by", r["killer"], "d" + str(r["dist"]), "kNow" + str(r["killer_line_now"]), "kDest" + str(r["killer_line_dest"]), "nNow" + str(r["n_now"]), "nDest" + str(r["n_dest"]), "k" + r["known"], "cells" + r["cells"], "safe" + r["safe"], "old" + r["safe_old"], r["cheapest"])
