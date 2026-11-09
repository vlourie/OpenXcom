"""Hostile own-side casualties (kfaction == vfaction == 1) in casualty files, by weapon and the terrain mark; and whether
the rec.gz has blast records.  usage: ff_cas.py <casualties.txt> ..."""
import collections
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
tot = collections.Counter()
per = collections.Counter()
weap = collections.Counter()
for p in sys.argv[1:]:
    seen = set()
    for l in Path(p).read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if "[AICASUALTY]" not in l:
            continue
        d = dict(KV.findall(l.split("[AICASUALTY]", 1)[1]))
        if d.get("vfaction") != "1":
            continue
        if d["victim"] in seen:
            continue
        seen.add(d["victim"])
        tot["hostile_victims"] += 1
        if d.get("kfaction") == "1":
            key = "self" if d.get("killer") == d.get("victim") else "own"
            tot[key] += 1
            tot["ff_terrain" + d.get("terrain", "?")] += 1
            per[Path(p).name.split(".")[0]] += 1
            weap[(d.get("weapon"), d.get("terrain"))] += 1
    rec = Path(str(p).replace(".casualties.txt", ".rec.gz"))
    if rec.exists() and not tot["blast_checked"]:
        with gzip.open(rec, "rt", encoding="utf-8", errors="replace") as f:
            tot["blast_records_in_first_rec"] = sum(1 for l in f if "[AIBLAST]" in l)
        tot["blast_checked"] = 1
for k in sorted(tot):
    print(f"{k}\t{tot[k]}")
print("\n== by battle")
for k, v in per.most_common():
    print(f"{k}\t{v}")
print("\n== by weapon, terrain")
for k, v in weap.most_common(30):
    print(f"{k}\t{v}")
