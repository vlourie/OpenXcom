"""FIRST CONTACT SURVIVAL V0, stage 5: the final category of every loss. B only where an alternative is proven: a flight into a cell with the killer's free line, the unit fell in that very cell, a safe reachable cell within its TU (the corrected probe on L4 s2, the rule's own [FCSACT] on L4 s1).
A candidate without such a proof goes to C with its reason. Usage: final.py <cat.tsv> <losses.tsv>"""
import csv
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
PROVEN = {("s2", "1000022"), ("s2", "1000035"), ("s2", "1000026"), ("s1", "1000001")}
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig"), delimiter="\t"))
for r in rows:
    seed = r["battle"].split("_")[-1]
    scen = r["battle"].split("_")[-2]
    r["scenario"] = scen
    r["seed"] = seed
    if r["cat"] == "A":
        r["cat_final"], r["reason"] = "A", "fell before any decision of its own"
    elif scen == "L4" and (seed, r["victim"]) in PROVEN:
        r["cat_final"], r["reason"] = "B", "flight into the killer's known line, a safe cell within its TU"
    elif r["cat"] == "Bc":
        r["cat_final"], r["reason"] = "C", "the killer known and had a line, but no alternative proven (or it would cancel an attack or an approach)"
    elif r["why"] in ("friend", "friend_self"):
        r["cat_final"], r["reason"] = "C", "a friend's shot (the direction is closed)"
    elif r["why"] == "wounds_status":
        r["cat_final"], r["reason"] = "C", "wounds or status"
    else:
        r["cat_final"], r["reason"] = "C", "the killer unknown, or it had to come or turn to see the unit"
cols = ["scenario", "seed", "turn", "side", "phase", "victim", "type", "how", "pos", "tu_at_loss", "killer", "kfaction", "dist", "weapon", "why", "win", "own_decisions", "last_mode", "last_act", "last_from", "last_to", "killer_seen_at_last", "killer_seen_before", "k_sees", "cat", "cat_final", "reason"]
with open(sys.argv[2], "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, cols, delimiter="\t", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
for sc in ("L4", "M1", "M10"):
    x = [r for r in rows if r["scenario"] == sc]
    y = [r for r in x if r["win"] == "1"]
    print(sc, "all", len(x), sorted(Counter(r["cat_final"] for r in x).items()), "| window", len(y), sorted(Counter(r["cat_final"] for r in y).items()))
    print("   window cause", Counter(r["why"] for r in y).most_common(), "| reasons C", Counter(r["reason"][:28] for r in y if r["cat_final"] == "C").most_common())
    print("   window last decision (acted):", Counter((r["last_mode"], r["last_act"]) for r in y if r["cat_final"] != "A").most_common(8))
