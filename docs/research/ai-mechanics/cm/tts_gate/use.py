"""NATURAL GATE, phase A: does a line get used. For B's same-turn openings against the base rate of the side: when a soldier's list holds a firearm shot with a line and TU, how often the decision is an attack.
Also how the indirect line evidence stands against the engine, where the log can test it. Args: cands.jsonl, zip of the D0 logs."""
import gzip
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gate_lib as G

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ATT = {5, 6, 7, 8, 9, 10, 11, 12}
RES = [json.loads(s) for s in Path(sys.argv[1]).open(encoding="utf-8")]
o = Counter()
ev = Counter()
for r in RES:
    for c in r["cands"]:
        s = c["shot"]
        a = c["A"][0]
        for f in c["flips"]:
            if f["after"] and f["turn"] == c["turn"] and any(not x["out"] and x["now"] != x["was"] for x in f["comrades"]) and f["tu"] >= f["shot"]["tu"]:
                d = f["did"]
                o["openings with TU"] += 1
                o["attack any" if d["t"] in ATT else "no attack"] += 1
                if d["t"] in ATT and d["u"] == c["T"]["id"]:
                    o["attack T"] += 1
                    o["attack T dmg"] += d["dmg"] or 0
                    o["attack T fdmg"] += d["fdmg"] or 0
                break
        # the indirect evidence, where B came back to its cell after the comrade left
        tight = [x for x in c["A"] if x["dB"] >= 1 and x["dT"] >= 1 and x["dist"] <= 1.0]
        if len(tight) == 1 and tight[0]["lofT"] == 1 and tight[0]["dB"] <= 3:
            u = tight[0]["id"]
            yes = any(f["after"] and any(x["id"] == u and (x["out"] or x["now"] != x["was"]) for x in f["comrades"]) for f in c["flips"])
            no = any(u in x["gone"] for x in c.get("still", []))
            ev["indirect evidence"] += 1
            if yes or no:
                ev["testable"] += 1
                ev["opened" if yes else "stayed closed"] += 1
print(dict(o))
print(dict(ev))
base = Counter()
with zipfile.ZipFile(sys.argv[2]) as z:
    for n in sorted(x for x in z.namelist() if x.endswith("openxcom.log.gz")):
        L = [s.rstrip("\n").split("\t")[-1] for s in gzip.open(io.BytesIO(z.read(n)), "rt", encoding="utf-8", errors="replace")]
        b = G.Battle(L)
        for d in b.dec:
            if d["side"] != 1 or not d["acts"]:
                continue
            s = G.shots_by_target(b.acts(d["acts"]))
            if any(x["lof"] and x["tu"] <= d["tu"] for x in s.values()):
                base["decisions with a shot in hand"] += 1
                base["attack" if d["t"] in ATT else "no attack"] += 1
print(dict(base))
