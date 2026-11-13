"""SIDE-FIRST COMBAT V0.1: the order units were given decisions in the first hostile turn, as runs: unit x count; a star marks the director's action, the journal's switches and handbacks are not logged one by one.
args: zip label"""
import gzip
import io
import json
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
z = zipfile.ZipFile(sys.argv[1])
raw = gzip.open(io.BytesIO(z.read(f"out/{sys.argv[2]}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
runs = []
scd = set()
for s in raw:
    s = s.split("\t")[-1]
    if s.startswith("[AISCD] "):
        j = json.loads(s[8:])
        if j.get("ev") == "act" and j.get("turn") == 1:
            scd.add(str(j["actor"]))
        if j.get("ev") == "turn_end" and j.get("turn") == 1:
            print({k: j[k] for k in ("calls", "acts", "attacks", "walks", "thinks", "consults", "special", "vetoes", "switches", "backs")})
    elif s.startswith("[AIDECIDE] "):
        d = dict(KV.findall(s.split(" hu=")[0]))
        if d.get("side") != "1" or d.get("turn") != "1":
            continue
        u = d["unit"]
        mark = "*" if u in scd else ""
        scd.discard(u)
        short = u[-3:] if len(u) == 7 else "p" + u
        if runs and runs[-1][0] == short:
            runs[-1][1] += mark or "."
        else:
            runs.append([short, mark or "."])
print(" ".join(f"{a}{b}" for a, b in runs))
