"""AI-IF analysis of the [AIIF] / [AIIFFX] lines (the record, decisions = D0).

A case: an [AIIF] (a strictly useless shot by T2's rule, written in setupAttack before projectileAction) followed by the same
unit's [AIDECIDE] that fires (act 7/8/9) at the same target. For each case, what else it had (non-exclusive flags), a primary
class by the cheapest useful alternative, and what the executed shot really did ([AIIFFX] of that decision) - on the target
and on the shooter (reaction fire during the shot).

Useful = ev >= 0.5 HP expected damage under the ruleset armour, as T2 (ev10 >= 5); melee and grenade also need a roll that gets
through the weakest ruleset armour (through > 0). Potential = an alternative whose honest verdict names a non-damage term.

  py -3.13 -I if_ana.py <out dir> <prefix> [cases tsv]"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
TSV = Path(sys.argv[3]) if len(sys.argv) > 3 else None
KV = re.compile(r"(\w+)=(\S+)")
SHOT = {7, 8, 9}
NOT_TERMS = {"-", "?", "not_direct", "no_ammo", "no_lof", ""}
ORDER = ("hand", "alt", "melee_now", "gren", "spec", "inv", "melee_reach", "pos")


def fire(text):
    """TYPE:ev10:who:why of hand/spec, or TYPE:notfire / -"""
    if text == "-" or text.endswith(":notfire"):
        return None
    t, ev, who, why = text.rsplit(":", 3)
    return {"type": t, "ev": int(ev), "who": who, "why": why}


def items(text):
    return [] if text == "-" else text.split(";")


def classify(r):
    f = {}
    alt = r["alt"].split(":")
    f["alt"] = int(alt[0]) >= 5
    f["alt_pot"] = alt[2] not in NOT_TERMS
    h = fire(r["hand"])
    f["hand"] = bool(h and h["ev"] >= 5)
    f["hand_pot"] = bool(h and h["why"] not in NOT_TERMS)
    f["hand_any"] = r["hand"] != "-"
    s = fire(r["spec"])
    f["spec"] = bool(s and s["ev"] >= 5)
    f["spec_pot"] = bool(s and s["why"] not in NOT_TERMS)
    f["inv"] = f["inv_pot"] = False
    f["inv_any"] = f["inv_melee"] = False
    f["inv_move"] = None
    for e in items(r["inv"]):
        p = e.split(":")
        f["inv_any"] = True
        if p[4] == "melee":
            f["inv_melee"] = True
            continue
        if p[4] == "noammo":
            continue
        if int(p[4]) >= 5:
            f["inv"] = True
            mv = int(p[2])
            f["inv_move"] = mv if f["inv_move"] is None else min(f["inv_move"], mv)
        if p[6] not in NOT_TERMS:
            f["inv_pot"] = True
    f["melee_now"] = f["melee_reach"] = False
    f["melee_any"] = r["melee"] != "-"
    f["melee_walk"] = None
    for e in items(r["melee"]):
        t, hit, who, walk, ev, through = e.rsplit(":", 5)
        if who == "-1" or int(ev) < 5 or int(through) <= 0:
            continue
        if int(walk) == 0:
            f["melee_now"] = True
        else:
            f["melee_reach"] = True
            w = int(walk)
            f["melee_walk"] = w if f["melee_walk"] is None else min(f["melee_walk"], w)
    f["gren"] = False
    f["gren_any"] = r["gren"] != "-"
    if f["gren_any"]:
        t, need, have, eff, valid, through = r["gren"].rsplit(":", 5)
        f["gren"] = valid == "1" and int(eff) > 0 and int(have) >= int(need) and int(through) > 0
        f["gren_parts"] = (int(have) >= int(need), int(eff) > 0, valid == "1", int(through) > 0)
    f["pos"] = not r["pos"].startswith("-")
    f["pos_walk"] = int(r["pos"].split(":")[2]) if f["pos"] else None
    f["primary"] = next((k for k in ORDER if f[k]), "none")
    return f


def effect(fx):
    d = [int(x) for x in fx["d"].split(",")]
    hp, stun, mor, tu, en, wnd, fire_, *arm = d
    a, b = fx["st"].split(">")
    return {"damage": hp < 0 or stun > 0 or wnd > 0 or a != b, "armour": any(x < 0 for x in arm), "fire": fire_ > 0,
            "morale": mor < 0, "energy": en < 0, "hp": -hp if hp < 0 else 0}


c = Counter()
prim = Counter()
flags = Counter()
by_weapon = defaultdict(Counter)
by_battle = defaultdict(Counter)
not_exec = Counter()
fx_sum = Counter()
gren_why = Counter()
none_kind = Counter()
rows = []
for d in sorted(OUT.glob(f"{PRE}_*")):
    pend = {}
    last = None
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIIF] "):
                k = dict(KV.findall(body))
                pend[k["unit"]] = k
                c["records"] += 1
            elif body.startswith("[AIIFFX] "):
                k = dict(KV.findall(body))
                if last and last["unit"] == k["unit"]:
                    e = effect(k)
                    last["fx"] = e
                    last["later"] = k["later"]
                    sh = [int(x) for x in k["self"].split(",")]
                    last["self_hp"] = -sh[0] if sh[0] < 0 else 0
                    a, b = k["sst"].split(">")
                    last["self_out"] = a != b
                last = None
            elif body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k = dict(KV.findall(body))
                act = int(k["act"])
                if act in SHOT or act in (6, 10, 12):
                    c["hostile_attacks"] += 1
                r = pend.pop(k["unit"], None)
                last = None
                if not r:
                    if act in SHOT or act in (6, 10, 12):
                        last = {"unit": k["unit"], "skip": True}
                    continue
                if not (act in SHOT and k.get("aim") == r["target"] and k.get("weapon", r["weapon"]) == r["weapon"]):
                    not_exec[act] += 1
                    continue
                r["battle"] = d.name
                r["act"] = act
                r["f"] = classify(r)
                rows.append(r)
                last = r
for r in rows:
    f = r["f"]
    c["cases"] += 1
    prim[f["primary"]] += 1
    by_weapon[r["weapon"]][f["primary"]] += 1
    by_battle[r["battle"]][f["primary"]] += 1
    for k, v in f.items():
        if v is True:
            flags[k] += 1
    if f.get("gren_any") and not f["gren"]:
        need, eff, valid, through = f["gren_parts"]
        gren_why["no_tu" if not need else "no_efficacy" if not eff else "invalid_throw" if not valid else "armour_stops"] += 1
    if f["primary"] == "none":
        none_kind["has_other_weapon_but_useless" if (f["hand_any"] or f["inv_any"] or f["melee_any"] or f["gren_any"] or r["spec"] != "-")
                  else "only_this_weapon"] += 1
        none_kind["other_targets_seen" if int(r["seen"]) > 1 else "single_target"] += 1
    fx = r.get("fx")
    if fx is None:
        fx_sum["no_fx"] += 1
        continue
    fx_sum["fx"] += 1
    for k in ("damage", "armour", "fire", "morale", "energy"):
        fx_sum[k] += fx[k]
    fx_sum["hp_lost"] += fx["hp"]
    fx_sum["self_hit"] += r["self_hp"] > 0
    fx_sum["self_hp_lost"] += r["self_hp"]
    fx_sum["self_out"] += r["self_out"]
print("totals:", dict(c))
print("recorded but no matching shot (act):", dict(not_exec))
print("primary class (cheapest useful alternative):", dict(prim.most_common()))
print("flags (non-exclusive):", dict(sorted(flags.items())))
print("grenade on the belt but no use:", dict(gren_why))
print("no alternative:", dict(none_kind))
print("executed shot's real effect:", dict(fx_sum))
print("by weapon:")
for w, v in sorted(by_weapon.items(), key=lambda x: -sum(x[1].values())):
    print(f"  {w:40s} {sum(v.values()):4d}  {dict(v.most_common())}")
print("by battle:")
for b, v in sorted(by_battle.items()):
    print(f"  {b:16s} {sum(v.values()):4d}  {dict(v.most_common())}")
if TSV:
    cols = ["battle", "turn", "unit", "tu", "en", "weapon", "target", "tfac", "dist", "ev10", "seen", "act", "alt", "hand", "inv",
            "spec", "melee", "gren", "pos", "tiles"]
    with open(TSV, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("\t".join(cols + ["primary", "fx_damage", "fx_energy", "self_hp"]) + "\n")
        for r in rows:
            fx = r.get("fx") or {}
            f.write("\t".join([str(r.get(k, "")) for k in cols] + [r["f"]["primary"], str(int(fx.get("damage", 0))),
                                                                 str(int(fx.get("energy", 0))), str(r.get("self_hp", ""))]) + "\n")
