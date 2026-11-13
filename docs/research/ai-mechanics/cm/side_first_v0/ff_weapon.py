"""SIDE-FIRST COMBAT: friendly damage by weapon and arm over the final series; who decided the shot on XN (the director or the unit's think). args: zip prefix"""
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
P = sys.argv[2]
for m in ("M3", "M8", "L4", "L8"):
    for arm in ("D", "XN"):
        fw = Counter()
        how = Counter()
        n = Counter()
        for s_ in (1, 2, 3, 4):
            raw = gzip.open(io.BytesIO(z.read(f"out/{P}_{arm}_{m}_s{s_}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
            pend = None
            scd = set()
            for s in raw:
                s = s.split("\t")[-1]
                if s.startswith("[AISCD] "):
                    j = json.loads(s[8:])
                    if j.get("ev") == "act" and j.get("kind") == "A":
                        scd.add(str(j["actor"]))
                elif s.startswith("[AIDECIDE] "):
                    # the order in the log: the director's act, the previous record's [AIEXEC], then this action's [AIDECIDE]
                    pend = dict(KV.findall(s.split(" hu=")[0]))
                    pend["_scd"] = pend.get("unit") in scd
                    scd.discard(pend.get("unit"))
                elif s.startswith("[AIEXEC] ") and pend:
                    x = json.loads(s[9:])
                    d, pend = pend, None
                    if d.get("side") != "1":
                        continue
                    who = "director" if d["_scd"] and d.get("act") in ("7", "8", "9", "10") else "think"
                    if d.get("act") in ("7", "8", "9", "10") and (x.get("spent") or 0) > 0:
                        n[who] += 1
                    f = x.get("fdmg") or 0
                    if f:
                        act = d.get("act")
                        fw[(d.get("weapon"), act)] += f
                        how["attack:" + who if act in ("7", "8", "9", "10") else "other act " + str(act)] += f
        print(f"{m} {arm}: всего {sum(fw.values())}; {dict(how)}; выстрелов {dict(n)}; {fw.most_common(6)}")
