"""SIDE-FIRST COMBAT V0.1: the first hostile turn of the chrysalids (or a type), unit by unit: the think number and action of each decision in order, the time units, who acted in between.
args: zip label [type]"""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
z = zipfile.ZipFile(sys.argv[1])
want = sys.argv[3] if len(sys.argv) > 3 else "CHRYSSALID"
raw = gzip.open(io.BytesIO(z.read(f"out/{sys.argv[2]}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
typ = {}
seq = defaultdict(list)
order = []
pend = None
for s in raw:
    s = s.split("\t")[-1]
    if s.startswith("[AISTATE] "):
        d = dict(KV.findall(s))
        if d.get("unit") and d.get("type"):
            typ[d["unit"]] = d["type"]
    elif s.startswith("[AIDECIDE] "):
        d = dict(KV.findall(s.split(" hu=")[0]))
        pend = None
        if d.get("side") == "1" and d.get("turn") == "1":
            pend = d
            order.append(d["unit"])
    elif s.startswith("[AIEXEC] ") and pend:
        x = json.loads(s[9:])
        seq[pend["unit"]].append((len(order), pend.get("n"), pend.get("act"), pend.get("tu"), x.get("spent"), (x.get("trail") or [""])[0][:28] if x.get("trail") else ""))
        pend = None
idsorted = sorted(seq, key=int)
tot = Counter()
for u in idsorted:
    if want in typ.get(u, ""):
        tot["rounds"] += len(seq[u])
        print(u, typ[u], "реш", len(seq[u]), "ОВ", sum(q[4] or 0 for q in seq[u]))
        print("   ", " ".join(f"#{q[0]}:n{q[1]}a{q[2]}/{q[3]}-{q[4]}" for q in seq[u]))
print(tot, "решений всех юнитов в ход", len(order))
