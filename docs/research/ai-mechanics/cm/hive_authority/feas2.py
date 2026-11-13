"""AUTHORITY CONTRACT, part 3, second pass on the same 48 D0 battles, read only: unit types of the player's side, so that vehicles (the case of the closed operation) stand apart from people; share of those put out in the player's turn who were out of every player's sight at its start; AI combat-mode walks split by charge; TU of the operation's fighters against the plan in run 4."""
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
S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
KV = re.compile(r"(\w+)=([^ ]*)")
POS = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")


def kv(s):
    return dict(KV.findall(s))


def tup(p):
    m = POS.match(p or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def d2(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


zf = zipfile.ZipFile(A)
names = sorted(n for n in zf.namelist() if n.endswith("log.gz") and "scpa_D_" in n)
types = Counter()
weapons = Counter()
veh = defaultdict(Counter)
dist = defaultdict(Counter)
how = Counter()
kill_by = Counter()
for n in names:
    L = [x.split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(n)), "rt", encoding="utf-8", errors="replace").read().split("\n")]
    ps = defaultdict(dict)
    ais = defaultdict(dict)
    out = set()
    for s in L:
        if s.startswith("[AISTATE] pstart"):
            k = kv(s)
            ps[int(k["turn"])][k["unit"]] = k
        elif s.startswith("[AISTATE] aistart"):
            k = kv(s)
            ais[int(k["turn"])][k["unit"]] = k
        elif s.startswith("[AICASUALTY]"):
            k = kv(s)
            if k.get("how") in ("dead", "stun"):
                out.add((k["victim"], int(k["turn"]), int(k.get("side", -1))))
                if k.get("side") == "0" and k.get("vfaction") == "1":
                    how[k.get("how")] += 1
                    kill_by["own side's blast or fire, or none named" if k.get("kfaction") != "0" else "player's unit"] += 1
    for t, P in ps.items():
        if t not in ais:
            continue
        for k in P.values():
            if k["faction"] == "0":
                types[k.get("type")] += 1
                weapons[k.get("type") + " " + k.get("weapon", "")] += 1
                if int(k["status"]) < 6 and int(k.get("seenby", 0)) > 0:
                    v = "vehicle" if k.get("weapon", "").startswith(("AUX_TANK", "AUX_WOLVERIN")) else "person"
                    veh[v]["seen"] += 1
                    if (k["unit"], t, 0) in out or k["unit"] not in ais[t]:
                        veh[v]["down"] += 1
                        continue
                    b = ais[t][k["unit"]]
                    move = d2(tup(k["pos"]), tup(b["pos"]))
                    veh[v]["moved3"] += move >= 3
                    veh[v]["dirchg"] += b.get("dir") != k.get("dir")
                    veh[v]["still_seen"] += int(b.get("seenby", 0)) > 0
                    veh[v]["n"] += 1
print("player's unit types at pstart:", types.most_common(14))
print("weapon by type:", weapons.most_common(12))
print("target over the player's turn:", {a: dict(b) for a, b in veh.items()})
print("AI units put out in the player's turn: how", how.most_common(), "by", kill_by.most_common())
with gzip.open(S / "hive/res/out/op4_OA_M3_s1/openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
    L = [x.rstrip("\n").split("\t")[-1] for x in f]
for s in L:
    if s.startswith("[AISTATE] aistart turn=4 ") and any(f"unit={u} " in s for u in ("1000000", "1000005")):
        k = kv(s)
        print("run 4, aistart:", k["unit"], k["pos"], "tu", k["tu"], "tumax", k.get("tumax"))
    if s.startswith("[HIVEOP] event=ASSIGN"):
        print("run 4,", s[9:170])
    if s.startswith("[AISTATE] pstart turn=5 ") and any(f"unit={u} " in s for u in ("1000000", "1000005")):
        k = kv(s)
        print("run 4, pstart:", k["unit"], k["pos"], "tu", k["tu"])
