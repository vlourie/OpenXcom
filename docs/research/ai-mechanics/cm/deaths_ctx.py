"""What a hostile was doing before it fell (D0 logs): its last decision (mode, act, did it see anyone), on whose turn it fell,
had it ever attacked, how many allies were near; and the patrol units that walked into contact and died before attacking.

  py -3.13 -I deaths_ctx.py <out dir> <prefix>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
MODE = {"0": "patrol", "1": "ambush", "2": "combat", "3": "escape"}
ACT = {0: "none", 2: "walk", 6: "throw", 7: "auto", 8: "snap", 9: "aimed", 10: "hit", 12: "launch", 15: "rethink"}

ctx = Counter()
by_mode = defaultdict(Counter)
killer_w = Counter()
noatt_how = Counter()
for d in sorted(OUT.glob(f"{PRE}_*")):
    last = {}
    natt = Counter()
    seen_v = set()
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k = dict(KV.findall(body))
                last[k["unit"]] = k
                if int(k["act"]) in ATT:
                    natt[k["unit"]] += 1
            elif body.startswith("[AICASUALTY] ") and " vfaction=1 " in body:
                k = dict(KV.findall(body))
                v = k["victim"]
                if v in seen_v:
                    continue
                seen_v.add(v)
                if k.get("kfaction") == "1":
                    ctx["by_own_side"] += 1
                own = k["side"] == "1"
                lk = last.get(v)
                mode = MODE.get(lk["mode"], lk["mode"]) if lk else "no_decision"
                act = ACT.get(int(lk["act"]), lk["act"]) if lk else "-"
                key = ("own_turn" if own else "player_turn")
                ctx[key] += 1
                by_mode[key][f"{mode}/{act}"] += 1
                if natt[v] == 0:
                    noatt_how[f"{key}:{mode}/{act}"] += 1
                if own:
                    killer_w["reaction_killer_" + k.get("ktype", "?")] += 1
print("hostile deaths:", dict(ctx))
for key, c in by_mode.items():
    print(f"{key}: last decision mode/act:", dict(c.most_common(10)))
print("died without a single attack, by last decision:", dict(noatt_how.most_common(12)))
print("own-turn killers:", dict(killer_w.most_common(6)))
