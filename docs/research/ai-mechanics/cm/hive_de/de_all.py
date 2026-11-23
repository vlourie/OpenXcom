"""DECISION ENGINE FOUNDATION, read only, over the 48 D0 battles: for each group-choice class, how often and how much.
A friendly damage: by act and weapon, and what share comes with a blast line; own-side damage against damage to the player.
B lost unit-turns: a soldier with time units and no walk spent, whole turn; what the same soldier's side did.
C spotted-for-sniper: units with sniper chance, decisions by the sniper source, spotter use."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
A = Path("E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip")
KV = re.compile(r"(\w+)=([^ ]*)")


def kv(s):
    return dict(KV.findall(s))


zf = zipfile.ZipFile(A)
ROW = []
tot = Counter()
src = Counter()
fdw = Counter()
lostu = Counter()
for n in sorted(x for x in zf.namelist() if x.endswith("openxcom.log.gz")):
    name = n.split("/")[-2].replace("scpa_D_", "")
    L = [x.rstrip("\n").split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(n)), "rt", encoding="utf-8", errors="replace")]
    seq = []
    blasts = 0
    res = ""
    for i, s in enumerate(L):
        if s.startswith("[AIDECIDE]"):
            seq.append({"i": i, "k": kv(s)})
        elif s.startswith("[AIREC]"):
            if seq and '"base"' in s:
                try:
                    j = json.loads(s[8:])
                    seq[-1]["src"] = (j.get("base") or {}).get("src")
                except json.JSONDecodeError:
                    pass
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            if seq and str(j.get("unit")) == seq[-1]["k"]["unit"]:
                seq[-1]["ex"] = j
        elif s.startswith("[AIRESULT]"):
            res = kv(s)
    H = [d for d in seq if d["k"].get("side") == "1"]
    dm = fd = fdn = att = spent = 0
    ut = defaultdict(list)
    for d in H:
        ut[(int(d["k"]["turn"]), d["k"]["unit"])].append(d)
        ex = d.get("ex") or {}
        dm += ex.get("dmg", 0)
        fd += ex.get("fdmg", 0)
        fdn += ex.get("fdowned", 0)
        spent += ex.get("spent", 0)
        act = int(d["k"].get("act", 0))
        src[d.get("src")] += 1
        if ex.get("fdmg", 0):
            fdw[("walk" if act == 2 else "attack", d["k"].get("weapon", "-"))] += ex["fdmg"]
    lost = [(k, v) for k, v in ut.items() if sum(x.get("ex", {}).get("spent", 0) for x in v) == 0 and int(v[0]["k"]["tu"]) > 0]
    ltu = sum(int(v[0]["k"]["tu"]) for _, v in lost)
    ttu = sum(int(v[0]["k"]["tu"]) for v in ut.values())
    ROW.append((name, len(ut), dm, fd, fdn, len(lost), ltu, ttu, res.get("hdead", ""), res.get("pdead", "")))
    tot["dmg"] += dm
    tot["fdmg"] += fd
    tot["fdowned"] += fdn
    tot["ut"] += len(ut)
    tot["lost"] += len(lost)
    tot["ltu"] += ltu
    tot["ttu"] += ttu
print("battle unit_turns dmg fdmg fdowned lost_ut lost_tu all_tu hdead pdead")
for r in ROW:
    print(*r)
print(dict(tot))
print("sources:", src.most_common(25))
print("fdmg by walk/attack and weapon:", fdw.most_common(25))
w = sum(v for k, v in fdw.items() if k[0] == "walk")
print("fdmg during walks", w, "during attacks", sum(fdw.values()) - w)
