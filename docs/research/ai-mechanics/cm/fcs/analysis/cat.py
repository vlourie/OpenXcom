"""FIRST CONTACT SURVIVAL, stage 1: categories A/B/C of every hostile loss, by scenario, with the first contact window of each battle (read only).
Window: from the first turn of the battle with a hostile loss by the player's hand through the end of the player's next turn.
A   never got a decision of its own before the fall.
Bc  a candidate for B: acted, the killer known at its last decision, and either the killer already saw it at the start of the phase or it fell to reaction on its own action. An alternative cell is NOT yet proven.
C   the rest: the killer unknown, or had to come or turn to see it; a friend's shot; wounds and status.
Usage: cat.py <out tsv> <x.tsv>..."""
import csv
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
EXPL = ("GRENADE", "ROCKET", "MISSILE", "BOMB", "EXPLOS", "MINE", "CHARGE", "MORTAR")


def category(r):
    if int(r["own_decisions"]) == 0:
        return "A"
    if r["cause"] in ("friendly", "turn_start_wounds_or_fire", "no_killer"):
        return "C"
    known = r["killer_seen_at_last"] == "1" or r["killer_seen_before"] == "1"
    if not known:
        return "C"
    if r["side"] == "0":
        return "Bc" if r.get("k_sees") == "1" else "C"
    return "Bc" if r["cause"] == "reaction" and r["actor_is_victim"] == "1" else "C"


def why(r):
    if r["cause"] == "friendly":
        return "friend_self" if r["actor_is_victim"] == "1" else "friend"
    if any(x in r["weapon"].upper() for x in EXPL):
        return "explosive"
    if r["cause"] == "turn_start_wounds_or_fire":
        return "wounds_status"
    if r["cause"] == "no_killer":
        return "no_killer"
    if r["side"] == "1":
        return r["cause"]
    return "player_turn_fire"


rows = []
for p in sys.argv[2:]:
    rows += list(csv.DictReader(open(p, encoding="utf-8-sig"), delimiter="\t"))
first = {}
for r in rows:
    first.setdefault((r["battle"], r["victim"]), r)
units = list(first.values())
t0 = {}
for r in units:
    if r["kfaction"] == "0":
        t0[r["battle"]] = min(t0.get(r["battle"], 999), int(r["turn"]))
for r in units:
    r["cat"] = category(r)
    r["why"] = why(r)
    t = int(r["turn"])
    b = t0.get(r["battle"], 999)
    r["win"] = int(b <= t and (t == b or (t == b + 1 and r["side"] == "0")))
cols = list(rows[0].keys()) + ["why", "win"]
with open(sys.argv[1], "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, cols, delimiter="\t", extrasaction="ignore")
    w.writeheader()
    w.writerows(units)


def scen(b):
    return b.split("_")[-2]


for sc in sorted({scen(r["battle"]) for r in units}):
    x = [r for r in units if scen(r["battle"]) == sc]
    print(f"== {sc}: battles {len({r['battle'] for r in x})}, units lost {len(x)}; categories {sorted(Counter(r['cat'] for r in x).items())}")
    print("   all, cause:", Counter(r["why"] for r in x).most_common())
    y = [r for r in x if r["win"]]
    print(f"   window: {len(y)}; categories {sorted(Counter(r['cat'] for r in y).items())}; cause {Counter(r['why'] for r in y).most_common()}")
    for b in sorted({r["battle"] for r in x}):
        z = [r for r in x if r["battle"] == b and r["win"]]
        print(f"     {b}: first hostile loss by the player t{t0.get(b)}; window {len(z)}: {sorted(Counter(r['cat'] for r in z).items())}")
print()
print("Bc in the window, by battle and phase:")
g = defaultdict(list)
for r in units:
    if r["win"] and r["cat"] == "Bc":
        g[(r["battle"], r["turn"], r["side"])].append(r)
for k in sorted(g, key=lambda a: (a[0], int(a[1]), a[2])):
    print(" ", k[0][-9:], "t" + k[1], "side" + k[2], "n=" + str(len(g[k])))
    for r in g[k]:
        print("    ", r["victim"], r["type"][4:14], "at", r["pos"], "tuL" + r["tu_at_loss"], "by", r["killer"], "from", r.get("k_pos"), "d" + r["dist"], r["weapon"][:20], "| m" + r["last_mode"], "a" + r["last_act"], r["last_from"], ">", r["last_to"], "tu" + r["last_tu"], "seen" + r["last_seen_n"], "dec" + r["own_decisions"], r["cause"][:8])
