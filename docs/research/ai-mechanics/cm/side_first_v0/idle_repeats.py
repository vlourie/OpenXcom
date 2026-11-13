"""SIDE-FIRST COMBAT V0.1: the records that spent no time units and repeat the unit's previous spent-nothing record: which actions, whether the unit moved or anything got hurt, the longest run, and whether the record stands under a director's act or under the unit's own think. args: zip:prefix:arm:mission ..."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")


def battle(z, label, tot):
    ls = [s.split("\t")[-1] for s in gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()]
    cur = None
    prev = {}
    run = Counter()
    last_pos = {}
    scd = None
    for s in ls:
        if s.startswith("[AISCD] "):
            j = json.loads(s[8:])
            if j.get("ev") == "act":
                scd = j["actor"]
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            cur = d if d.get("side") == "1" else None
            if cur:
                cur["director"] = scd == int(d["unit"])
            scd = None
        elif s.startswith("[AIEXEC] ") and cur:
            x = json.loads(s[9:])
            d, cur = cur, None
            if str(x.get("unit")) != d["unit"]:
                continue
            act = d.get("act")
            if act in ("0", "1", None):
                continue
            sig = (d["turn"], d["unit"], d.get("from"), act, d.get("to"))
            spent = x.get("spent") or 0
            if spent == 0:
                tot["spent0"] += 1
                tot["spent0_act_" + act] += 1
                if prev.get(d["unit"]) == sig:
                    tot["rep"] += 1
                    tot["rep_act_" + act] += 1
                    tot["rep_director" if d["director"] else "rep_think"] += 1
                    tot["rep_hurt"] += 1 if (x.get("dmg") or x.get("stunned") or x.get("downed")) else 0
                    tot["rep_moved"] += 1 if d.get("from") != "(%d,%d,%d)" % tuple(x["pos"]) else 0
                    run[sig] += 1
                prev[d["unit"]] = sig
            else:
                prev[d["unit"]] = None
    if run:
        tot["run_max"] = max(tot["run_max"], max(run.values()) + 1)


for a in sys.argv[1:]:
    zp, prefix, arm, mission = a.rsplit(":", 3)
    z = zipfile.ZipFile(zp)
    tot = Counter()
    for s_ in (1, 2, 3, 4):
        battle(z, f"{prefix}_{arm}_{mission}_s{s_}", tot)
    print(prefix, arm, mission, dict(sorted(tot.items())))
