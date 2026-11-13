"""[AITARGET] records (OXCE_AI_TARGET_EV=1): how often the nearest target is clearly worse than another legal one, and why.

  py -3.13 targets.py <out dir> <prefix> <examples tsv>
cands = id:faction:dist:ev:hpmax:score(x1000). Each record is one target pick in setupAttack of a hostile firearm unit; the
following [AIDECIDE] of the same unit tells the action (an attack at the nearest, or not)."""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE, EX = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
tot = Counter()
reason = Counter()
ratio = []
per = Counter()
ex = []
for d in sorted(OUT.glob(f"{PRE}_*")):
    pend = {}
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AITARGET] "):
                k = dict(KV.findall(body))
                c = [x.split(":") for x in k["cands"].split(";") if x]
                cand = {x[0]: dict(f=int(x[1]), dist=int(x[2]), ev=int(x[3]), hp=int(x[4]), sc=int(x[5])) for x in c}
                pend[k["unit"]] = (k, cand)
            elif body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k2 = dict(KV.findall(body))
                if k2["unit"] not in pend:
                    continue
                k, cand = pend.pop(k2["unit"])
                act = int(k2["act"])
                attack = act in ATT
                tot["picks"] += 1
                tot["multi"] += len(cand) > 1
                tot["melee"] += k["melee"] == "1"
                tot["unmodelled"] += k["model"] != "1"
                if k["model"] != "1":
                    reason[k["model"]] += 1
                if k["better"] != "1" or k["model"] != "1":
                    continue
                n, b = cand[k["near"]], cand[k["best"]]
                tot["better"] += 1
                tot["better_nomelee"] += k["melee"] == "0"
                tot["better_attack"] += attack
                tot["better_attack_at_near"] += attack and k2.get("aim") == k["near"]
                per[d.name.split("_")[1]] += 1
                ratio.append(b["sc"] / max(1, n["sc"]))
                why = []
                if n["f"] == 2 and b["f"] == 0:
                    why.append("civ->player")
                if n["sc"] == 0:
                    why.append("near_zero")
                if b["dist"] > n["dist"] and b["ev"] > n["ev"]:
                    why.append("farther_more_dmg")
                if b["hp"] < n["hp"]:
                    why.append("lower_hpmax")
                reason["+".join(why) or "other"] += 1
                if attack and k2.get("aim") == k["near"]:
                    ex.append((d.name, k2["turn"], k2["unit"], k["weapon"], k2["act"], k["near"], n, k["best"], b))
print("target picks with a record:", dict(tot))
print("unmodelled / why:", dict(reason))
ratio.sort()
if ratio:
    print(f"best/nearest score ratio: median {ratio[len(ratio) // 2]:.2f}, p25 {ratio[len(ratio) // 4]:.2f}, p75 {ratio[3 * len(ratio) // 4]:.2f}")
print("per scenario (clearly better alternative):", dict(sorted(per.items())))
EX.write_text("battle\tturn\tunit\tweapon\tact\tnear\tn_fac\tn_dist\tn_ev\tn_hpmax\tn_score\tbest\tb_fac\tb_dist\tb_ev\tb_hpmax\tb_score\n" + "".join(
    f"{a}\t{t}\t{u}\t{w}\t{ac}\t{ni}\t{n['f']}\t{n['dist']}\t{n['ev']}\t{n['hp']}\t{n['sc']}\t{bi}\t{b['f']}\t{b['dist']}\t{b['ev']}\t{b['hp']}\t{b['sc']}\n"
    for a, t, u, w, ac, ni, n, bi, b in ex), encoding="utf-8-sig")
print("examples (attack executed at the nearest while a clearly better legal target was seen):", len(ex))
