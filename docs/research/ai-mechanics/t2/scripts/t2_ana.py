"""AI-T2 analysis of the [AIT2] / [AIT2FX] / [AIT2SET] lines.

record (F1, decisions = D0): every hostile firearm shot judged by t2Retarget, the shot that followed and what it changed.
  - useless shots, the ones executed, their real effect on the target ([AIT2FX] of the attack decision right after);
  - the not-useless shots (special effects / modelled damage) and their real effect, for the calibration;
  - useless with a useful lawful alternative (switch would happen), by the alternative's faction.
switch (F2): the same, plus [AIT2SET]: switched, the shot executed at the new target, its real effect, and the decision kinds.

An effect: health down, stun up, fatal wounds up, armour down on any side, fire set, morale down, energy down, or the status
changed (out). TU alone is not counted (the target's own reaction fire spends it). later=1 - the next decision came after a
turn change: turn-start regeneration and bleeding are mixed in, counted separately.

  py -3.13 t2_ana.py <out dir> <prefix> [per-battle tsv]"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
TSV = Path(sys.argv[3]) if len(sys.argv) > 3 else None
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
SHOT = {7, 8, 9}
ATT = {6, 7, 8, 9, 10, 12, 13, 14}


def effect(fx):
    if fx is None:
        return None
    d = [int(x) for x in fx["d"].split(",")]
    hp, stun, mor, tu, en, wnd, fire, *arm = d
    a, b = fx["st"].split(">")
    return hp < 0 or stun > 0 or wnd > 0 or any(x < 0 for x in arm) or fire > 0 or mor < 0 or en < 0 or a != b


c = Counter()
why = Counter()
fx_by = defaultdict(Counter)
per = []
acts_after_switch = Counter()
for d in sorted(OUT.glob(f"{PRE}_*")):
    b = Counter()
    pend = {}
    last_attack = None  # (key) of the last hostile attack decision, waiting for its [AIT2FX]
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIT2] "):
                k = dict(KV.findall(body))
                pend[k["unit"]] = {"t2": k, "set": None}
            elif body.startswith("[AIT2SET] "):
                k = dict(KV.findall(body))
                if k["unit"] in pend:
                    pend[k["unit"]]["set"] = k
            elif body.startswith("[AIT2FX] "):
                k = dict(KV.findall(body))
                if last_attack and last_attack["unit"] == k["unit"]:
                    last_attack["fx"] = k
                    cls = last_attack["cls"]
                    e = effect(k)
                    lat = "later" if k["later"] == "1" else "now"
                    fx_by[cls][f"{lat}_n"] += 1
                    fx_by[cls][f"{lat}_effect"] += e
                    if k["st"].split(">")[0] != k["st"].split(">")[1]:
                        fx_by[cls][f"{lat}_status"] += 1
                    hp = int(k["d"].split(",")[0])
                    fx_by[cls][f"{lat}_hp_lost"] += -hp if hp < 0 else 0
                last_attack = None
            elif body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k = dict(KV.findall(body))
                p = pend.pop(k["unit"], None)
                act = int(k["act"])
                if not p:
                    if act in SHOT or act == 10:
                        last_attack = {"unit": k["unit"], "cls": "other_attack"}
                    continue
                t2, s = p["t2"], p["set"]
                c["judged"] += 1
                b["judged"] += 1
                useless = t2["useless"] == "1"
                shot = act in SHOT and k.get("aim") == (s["to"] if s else t2["target"])
                if not useless:
                    why[t2["why"] if t2["why"] != "-" else ("modelled_ev>=0.5")] += 1
                    cls = "not_useless_" + ("model" if t2["why"] == "-" else "special")
                else:
                    c["useless"] += 1
                    b["useless"] += 1
                    c["useless_with_alt"] += t2["best"] != "-1"
                    b["useless_with_alt"] += t2["best"] != "-1"
                    c[f"useless_alt_fac{t2['bfac']}"] += t2["best"] != "-1"
                    c["useless_any_other_target"] += t2["n"] != "0"
                    cls = "useless_kept"
                if s:
                    c["switched"] += 1
                    b["switched"] += 1
                    acts_after_switch[act] += 1
                    c["switch_attack"] += act in ATT
                    c["switch_shot_new"] += shot
                    c["switch_none"] += act == 0
                    c["switch_set_act_rethink"] += s["act"] == "15"
                    cls = "switched_new_target" if shot else "switched_other"
                if act in SHOT or act == 10:
                    c[f"{cls}_executed"] += 1
                    last_attack = {"unit": k["unit"], "cls": cls}
                else:
                    c[f"{cls}_no_attack"] += 1
            elif body.startswith("[AIDECIDE] "):
                pass
    per.append((d.name, b["judged"], b["useless"], b["useless_with_alt"], b["switched"]))
print("judged shots and switches:", dict(sorted(c.items())))
print("why not useless:", dict(why.most_common()))
print("real effect of the executed attack, by class (now = before the turn ended):")
for cls, v in sorted(fx_by.items()):
    n, e = v["now_n"], v["now_effect"]
    print(f"  {cls:24s} now {e}/{n} with effect ({100 * e / max(1, n):.0f}%), status {v['now_status']}, hp lost {v['now_hp_lost']}; "
          f"later {v['later_effect']}/{v['later_n']}")
if acts_after_switch:
    print("decision right after a switch (act):", dict(acts_after_switch))
if TSV:
    with open(TSV, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("battle\tjudged\tuseless\tuseless_with_alt\tswitched\n")
        for r in per:
            f.write("\t".join(map(str, r)) + "\n")
