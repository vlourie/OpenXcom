"""AI-IF: why the alternatives in cases.tsv are not useful - melee (no target in reach / too weak / stopped by the armour),
the grenade (the largest roll through the under armour), the other hand's items, the targets and distances.

  py -3.13 -I if_why.py <cases.tsv>"""
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
lines = Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines()
head = lines[0].split("\t")
rows = [dict(zip(head, l.split("\t"))) for l in lines[1:]]
melee = Counter()
gren = Counter()
hand = Counter()
targets = Counter()
dist = Counter()
ev = Counter()
tu = Counter()
for r in rows:
    targets[(r["battle"], r["target"], r["tfac"])] += 1
    d = int(r["dist"])
    dist["adjacent" if d <= 1 else "2-5" if d <= 5 else "6-10" if d <= 10 else ">10"] += 1
    ev[r["ev10"]] += 1
    t = int(r["tu"])
    tu["<20" if t < 20 else "20-39" if t < 40 else "40-59" if t < 60 else ">=60"] += 1
    if r["melee"] != "-":
        best = "unreachable"
        for e in r["melee"].split(";"):
            typ, hit, who, walk, e10, through = e.rsplit(":", 5)
            if who == "-1":
                k = "unreachable"
            elif int(through) <= 0:
                k = "armour_stops" + ("_adjacent" if walk == "0" else "_reach")
            elif int(e10) < 5:
                k = "too_weak" + ("_adjacent" if walk == "0" else "_reach")
            else:
                k = "useful" + ("_adjacent" if walk == "0" else "_reach")
            rank = ["unreachable", "armour_stops_reach", "armour_stops_adjacent", "too_weak_reach", "too_weak_adjacent", "useful_reach",
                    "useful_adjacent"]
            if rank.index(k) > rank.index(best):
                best = k
        melee[best] += 1
    if r["gren"] != "-":
        typ, need, have, eff, valid, through = r["gren"].rsplit(":", 5)
        gren[("through" if int(through) > 0 else "stopped") + "/" + ("tu" if int(have) >= int(need) else "no_tu") + "/" +
             ("eff" if int(eff) > 0 else "no_eff") + "/" + ("valid" if valid == "1" else "invalid")] += 1
    if r["hand"] != "-":
        hand[r["hand"].split(":")[0] + (" notfire" if r["hand"].endswith(":notfire") else " ev10=" + r["hand"].split(":")[-3])] += 1
print("cases", len(rows))
print("melee best reason:", dict(melee.most_common()))
print("grenade through/tu/efficacy/valid:", dict(gren.most_common()))
print("other hand:", dict(hand.most_common()))
print("distance:", dict(dist))
print("current shot ev10:", dict(sorted(ev.items(), key=lambda x: int(x[0]))))
print("tu at the shot:", dict(tu))
print("distinct targets:", len(targets), "top:", targets.most_common(8))
print("target faction:", dict(Counter(r["tfac"] for r in rows)))
print("alt/pos rows:")
for r in rows:
    if r["primary"] != "none":
        print("  ", r["battle"], "turn", r["turn"], "unit", r["unit"], r["weapon"], "target", r["target"], "alt", r["alt"], "pos", r["pos"],
              "melee", r["melee"], "fx_damage", r["fx_damage"])
print("damage-like effect rows:")
for r in rows:
    if r["fx_damage"] == "1":
        print("  ", r["battle"], "turn", r["turn"], "unit", r["unit"], r["weapon"], "target", r["target"], "ev10", r["ev10"])
