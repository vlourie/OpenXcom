"""Where the hostile side's engagements fail (D0/cm0 logs): each hostile unit-turn is one of
  useful   - attacked and hurt or downed a player unit (AIEXEC dmg/stunned/downed of its attack actions)
  wasted   - attacked, no effect
  exposed  - no attack, ended its turn seen by a player unit (spotted > 0)
  hidden   - no attack, ended unseen
and what the player's next turn did to it (AIAFTER: dead/down, hp lost). Per hostile turn: how many useful attackers it
brought, and how the player HP it took splits between turns of 1, 2, 3+ useful attackers on the same target.

  py -3.13 -I ce_profile.py <out dir> <prefix>"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}

cat = Counter()
fate = defaultdict(Counter)  # category -> dead, hp_lost, n_after
dmg_by = Counter()
grp = Counter()  # useful attackers on one target in a turn -> count of (turn, target)
grp_dmg = Counter()
turns_useful = Counter()
exposed_mode = Counter()
exposed_mates = Counter()
battles = 0
for d in sorted(OUT.glob(f"{PRE}_*")):
    battles += 1
    last_dec = {}
    ut = defaultdict(lambda: {"att": 0, "eff": 0, "dmg": 0, "spotted": 0, "mode": None, "aims": set(), "pos": None})
    tgt = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # turn -> aim -> [useful attackers, dmg]
    after = {}
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] "):
                k = dict(KV.findall(body))
                last_dec[k["unit"]] = k
            elif body.startswith("[AIEXEC] "):
                e = json.loads(body[len("[AIEXEC] "):])
                u = str(e["unit"])
                k = last_dec.pop(u, None)
                if not k or k.get("side") != "1":
                    continue
                t = int(k["turn"])
                s = ut[(t, u)]
                s["mode"] = k["mode"]
                if "pos" in e:
                    s["spotted"] = e.get("spotted", 0)
                    s["pos"] = tuple(e["pos"])
                if int(k["act"]) in ATT:
                    s["att"] += 1
                    hit = e.get("dmg", 0) + e.get("stunned", 0) // 2
                    if hit > 0 or e.get("downed", 0):
                        s["eff"] += 1
                        s["dmg"] += e.get("dmg", 0)
                        s["aims"].add(k.get("aim", "?"))
            elif body.startswith("[AIAFTER] "):
                a = json.loads(body[len("[AIAFTER] "):])
                if a.get("side") == 1:
                    after[(a["turn"], str(a["unit"]))] = a
    for (t, u), s in ut.items():
        c = "useful" if s["eff"] else "wasted" if s["att"] else "exposed" if s["spotted"] else "hidden"
        cat[c] += 1
        dmg_by[c] += s["dmg"]
        a = after.get((t, u))
        if a:
            fate[c]["n"] += 1
            fate[c]["dead"] += a.get("dead", 0) or a.get("down", 0)
            fate[c]["hp_lost"] += a.get("hp_lost", 0)
        if c == "exposed":
            exposed_mode[{"0": "patrol", "1": "ambush", "2": "combat", "3": "escape"}.get(s["mode"], s["mode"])] += 1
            p = s["pos"]
            mates = sum(1 for (t2, u2), s2 in ut.items() if t2 == t and u2 != u and s2["eff"] and s2["pos"]
                        and max(abs(s2["pos"][0] - p[0]), abs(s2["pos"][1] - p[1])) <= 8)
            mb = "0" if mates == 0 else "1" if mates == 1 else "2+"
            exposed_mates[mb] += 1
            if a:
                exposed_mates["fell_" + mb] += a.get("dead", 0) or a.get("down", 0)
        for aim in s["aims"]:
            tgt[t][aim][0] += 1
            tgt[t][aim][1] += s["dmg"] // max(1, len(s["aims"]))
    for t, aims in tgt.items():
        turns_useful[sum(1 for x in ut if x[0] == t and ut[x]["eff"])] += 1
        for aim, (n, dm) in aims.items():
            b = "1" if n == 1 else "2" if n == 2 else "3+"
            grp[b] += 1
            grp_dmg[b] += dm
tot = sum(cat.values())
print(f"battles {battles}, hostile unit-turns with a decision {tot}")
print("category       share  dmg dealt   next player turn: fell  hp lost/unit")
for c in ("useful", "wasted", "exposed", "hidden"):
    fa = fate[c]
    n = max(1, fa["n"])
    print(f"  {c:8s} {cat[c]:6d} {100 * cat[c] / tot:4.0f}%  {dmg_by[c]:8d}   {fa['n']:6d}  {100 * fa['dead'] / n:4.1f}%  {fa['hp_lost'] / n:6.1f}")
print("exposed by mode:", dict(exposed_mode))
print("exposed: useful attackers of the same turn within 8 tiles:", dict(exposed_mates))
print("(turn, target) by useful attackers on it:", dict(grp), " dmg:", dict(grp_dmg))
print("hostile turns by useful attackers:", dict(sorted(turns_useful.items())))
