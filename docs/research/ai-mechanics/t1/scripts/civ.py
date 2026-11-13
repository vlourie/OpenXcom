"""Hostile attacks at civilians in d0_cases.tsv: the gap to the nearest seen player unit, per scenario, per battle seed.

  py -3.13 civ.py <d0_cases.tsv> <out dir>"""
import gzip
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TSV, OUT = Path(sys.argv[1]), Path(sys.argv[2])
lines = TSV.read_text(encoding="utf-8-sig").splitlines()
cols = lines[0].split("\t")
rows = [dict(zip(cols, l.split("\t"))) for l in lines[1:]]
civ = [r for r in rows if r["af"] == "2"]
gap = Counter()
scen = Counter()
scen_any = Counter()
for r in civ:
    alts = [a.split(":") for a in r["alts"].split(";") if a]
    pl = [int(a[1]) for a in alts if a[4] == "f0"]
    s = r["battle"].split("_")[1]
    if not pl:
        gap["no player seen"] += 1
        continue
    g = min(pl) - int(r["adist"])
    gap["<=0" if g <= 0 else "1-3" if g <= 3 else "4-8" if g <= 8 else ">8"] += 1
    scen_any[s] += 1
    if g <= 3:
        scen[s] += 1
print("civilian-aimed hostile attacks:", len(civ))
print("gap to nearest seen player unit (tiles farther than the civilian):", dict(gap))
print("per scenario, a player unit seen (any gap / <=3):", {s: (scen_any[s], scen[s]) for s in sorted(scen_any)})
print("by battle:", dict(Counter(r["battle"] for r in civ)))
# civilians killed by hostiles, player units lost, per scenario with civilians
for d in sorted(OUT.iterdir()):
    if not d.name.startswith("D0_"):
        continue
    kc = kp = 0
    types = Counter()
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AICASUALTY] "):
                k = dict(w.split("=", 1) for w in body.split()[1:] if "=" in w)
                if k.get("kfaction") == "1" and k.get("vfaction") == "2":
                    kc += 1
                    types[k.get("type")] += 1
                if k.get("vfaction") == "0":
                    kp += 1
    if kc:
        print(f"{d.name}: civilians killed by hostiles {kc} {dict(types)}; player units out {kp}")
