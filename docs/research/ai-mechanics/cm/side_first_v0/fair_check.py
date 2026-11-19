"""SIDE-FIRST COMBAT: was the director's action legal and did the engine do it? From the logs of battles with the director on. args: zip label [zip label ...]

Per battle: every act has its result (none lost, the last one of a battle may be open); an attack's time units within cost + the turn, and the walk within walkTu plus what the engine adds on the way (stops are less);
no unit's time units grow inside a hostile turn ([AIREC] state.tu, by decisions of the same turn); no attack at a target the side did not see: the act's tAt against [AISTATE]; rng_touched none; shots at a target already out (the act after the target's own out result)."""
import json
import sys
from collections import Counter

sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0])
from battle_stats import lines

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
bad_total = 0
args = sys.argv[1:]
for zp, label in zip(args[0::2], args[1::2]):
    c = Counter()
    last = {}
    tus = {}
    outs = {}
    over = []
    pend = None
    for s in lines(zp, label):
        if s.startswith("[AIREC] "):
            j = json.loads(s[8:])
            if j.get("side") == 1:
                k = (j["turn"], j["unit"])
                tu = j["state"]["tu"]
                if k in tus and tu > tus[k]:
                    c["tu_grew"] += 1
                tus[k] = tu
        elif s.startswith("[AISCD] "):
            j = json.loads(s[8:])
            e = j.get("ev")
            if e == "act":
                c["act"] += 1
                if pend is not None:
                    c["act_without_result"] += 1
                pend = j
                if j["kind"] == "A":
                    if outs.get(j["target"]) is not None and outs[j["target"]] <= j["turn"]:
                        c["attack_on_out"] += 1
            elif e == "result":
                c["result"] += 1
                p, pend = pend, None
                if p is None:
                    c["result_without_act"] += 1
                    continue
                if j["kind"] == "A":
                    # a blade strikes on while the time units last (MeleeAttackBState, getAIMeleeHitCount): its limit is what the unit had
                    lim = p["tu"] if p["t"] == 10 else p["cost"] + p["turnTu"]
                    c["attack"] += 1
                    if j["spent"] > lim + 2:
                        c["attack_tu_over"] += 1
                        over.append(("A", p["w"], p["t"], lim, j["spent"]))
                    if j["spent"] < p["cost"]:
                        c["attack_tu_short"] += 1
                        over.append(("A-short", p["w"], p["t"], lim, j["spent"]))
                    if j.get("tOut"):
                        outs[j["target"]] = j["turn"]
                elif j["kind"] in ("M", "P", "C"):
                    c["walk"] += 1
                    if j["spent"] > p["walkTu"] + 8:
                        c["walk_tu_over"] += 1
                        over.append((j["kind"], p["walkTu"], j["spent"]))
                    if not j["moved"]:
                        c["walk_not_moved"] += 1
                    if j["at"] != p["to"]:
                        c["walk_stopped_short"] += 1
                elif j["kind"] == "T":
                    c["special"] += 1
            elif e == "rng_touched":
                c["rng_touched"] += 1
    print(label, dict(sorted(c.items())))
    if over:
        print("  examples", over[:6])
    for k in ("tu_grew", "attack_on_out", "attack_tu_over", "walk_tu_over", "rng_touched", "result_without_act"):
        bad_total += c[k]
print("BAD", bad_total)
