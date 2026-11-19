"""SIDE-FIRST COMBAT: the cases fair_check.py flagged, with the record lines around them; and the same weapon's time units in D. args: zip"""
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


def read(label):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    return [s.split("\t")[-1] for s in raw]


# 1. the canister gun: decisions' tu, the next tu of the same unit, with and without the director
for label in ("sfF_XN_M3_s2", "sfF_D_M3_s2"):
    pend = None
    c = Counter()
    ex = []
    for s in read(label):
        if s.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(s.split(" hu=")[0]))
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            d, pend = pend, None
            if d.get("side") == "1" and d.get("weapon") == "STR_CANISTER_GUN" and d.get("act") in ("8", "9") and (x.get("spent") or 0) > 0:
                c[(d["act"], x["spent"])] += 1
                if len(ex) < 2:
                    ex.append((d["unit"], d["turn"], d["tu"], x["tu"], x["spent"], x.get("hp_lost"), json.dumps(x.get("trail"))[:220]))
    print(label, "canister (act, spent): n", sorted(c.items())[:24])
    for e in ex:
        print("  ", e)

# 2. the P walk that spent 80 for 50, and the act without a result
ls = read("sfF_XN_L4_s4")
for i, s in enumerate(ls):
    if s.startswith("[AISCD] ") and '"ev":"act"' in s and '"kind":"P"' in s and '"walkTu":50' in s:
        print("L4 s4 --")
        n = 0
        for t in ls[i:i + 40]:
            if t.startswith(("[AISCD]", "[AIEXEC]", "[AIDECIDE]")):
                print("  ", t[:260])
                n += 1
                if n > 6:
                    break
        break
prev = None
for i, s in enumerate(ls):
    if s.startswith("[AISCD] "):
        j = json.loads(s[8:])
        if j.get("ev") == "act":
            if prev is not None:
                print("act without result:", json.dumps(prev)[:200], "then", json.dumps(j)[:200])
            prev = j
        elif j.get("ev") == "result":
            prev = None

# 3. attacks on a target that went out
ls = read("sfF_XN_L8_s4")
out = {}
for s in ls:
    if s.startswith("[AISCD] "):
        j = json.loads(s[8:])
        if j.get("ev") == "result" and j.get("tOut"):
            out[j["target"]] = j["turn"]
            print("L8 s4 out:", json.dumps(j)[:200])
        if j.get("ev") == "act" and j.get("kind") == "A" and j["target"] in out:
            print("L8 s4 attack after out:", json.dumps(j)[:260])
    elif s.startswith("[AICASUALTY]") or (s.startswith("[AISTATE] aistart") and False):
        d = dict(KV.findall(s))
        if d.get("vfaction") == "0":
            print("  casualty", s[13:120])
