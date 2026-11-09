"""SIDE-FIRST COMBAT: the order of [AISCD] act, [AIDECIDE], [AIEXEC], [AISCD] result around the director's attacks; how many attacks pair with a record. args: zip label"""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
z = zipfile.ZipFile(sys.argv[1])
raw = gzip.open(io.BytesIO(z.read(f"out/{sys.argv[2]}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
ls = [s.split("\t")[-1] for s in raw]
ev = [(i, s) for i, s in enumerate(ls) if s.startswith(("[AISCD] ", "[AIDECIDE] ", "[AIEXEC] "))]
shown = 0
c = Counter()
for n, (i, s) in enumerate(ev):
    if s.startswith("[AISCD] ") and '"ev":"act"' in s and '"kind":"A"' in s:
        j = json.loads(s[8:])
        c["A"] += 1
        nxt = ev[n + 1][1] if n + 1 < len(ev) else ""
        prv = ev[n - 1][1] if n else ""
        c["next " + nxt[:9]] += 1
        c["prev " + prv[:9]] += 1
        if nxt.startswith("[AIDECIDE]"):
            d = dict(KV.findall(nxt.split(" hu=")[0]))
            c["next decide same unit" if d.get("unit") == str(j["actor"]) else "next decide other unit"] += 1
            c["next decide act " + str(d.get("act"))] += 1
        if prv.startswith("[AIDECIDE]"):
            d = dict(KV.findall(prv.split(" hu=")[0]))
            c["prev decide same unit" if d.get("unit") == str(j["actor"]) else "prev decide other unit"] += 1
            c["prev decide act " + str(d.get("act"))] += 1
        if shown < 3:
            shown += 1
            print("--")
            for _, t in ev[max(0, n - 2):n + 5]:
                print("  ", t[:200])
print(dict(c))
