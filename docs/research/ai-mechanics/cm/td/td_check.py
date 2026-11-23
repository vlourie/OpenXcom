"""AI_TACTICAL_DIRECTOR_V1: what the director did in a series (B, flag on) and how it went against the same battles of the D0
control (A), both up to the same turn.

From B's [AIPROBE] td lines: plans (contacts, able units, groups and roles), the unit's own choice (std) and the director's
order in each think; each order is joined to the unit's next AIDECIDE / AIEXEC (was it carried out, what it did). Joint
engagement: a group-turn in which two or more members attacked with effect; planned when one of those attacks came from a
FIRE / JOIN order (or the shot after FIREWALK / JOINWALK) or the attacker was sent by MANEUVER / WAIT / SUPPORT in the group's
turn before. Checks: an order that replaced an attack the unit chose (must be 0), orders per unit-turn (loop guard), WAIT that
never ended in an attack, support that kept its time units and its reaction shots, contacts the plan used that were not
seen (age > 1).

  py -3.13 -I td_check.py <out dir> <prefix A> <prefix B> [max turn]     (labels <prefix>_<arm>_<scen>_s<k>)"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PA, PB = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
TMAX = int(sys.argv[4]) if len(sys.argv) > 4 else 999
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
CHANGE = {"FIRE", "FIREWALK", "JOIN", "JOINWALK", "SUPPORT", "MANEUVER", "WAIT", "HOLD"}


def battle(d):
    last_dec = {}
    ut = defaultdict(lambda: {"att": 0, "eff": 0, "dmg": 0, "spotted": 0, "decides": 0, "aims": set(), "eff_aims": set()})
    after_p = Counter()  # turn -> player hp lost in the hostile turn
    cas = Counter()
    plans, groups, orders = [], {}, []
    pending = {}  # unit -> order waiting for its decision / exec
    reactions = []
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIPROBE] td plan "):
                plans.append(dict(KV.findall(body)))
            elif body.startswith("[AIPROBE] td group "):
                k = dict(KV.findall(body))
                mem = []
                for m in k.get("members", "").split(","):
                    p = m.split(":")
                    mem.append((p[0], p[1] if len(p) > 1 else "-"))
                groups[(int(k["turn"]), k["id"])] = {"phase": k["phase"], "target": k["target"].split("@")[0],
                                                     "age": int(k["target"].split("/")[-1]), "members": mem}
            elif body.startswith("[AIPROBE] td turn="):
                k = dict(KV.findall(body))
                o = {"turn": int(k["turn"]), "group": k["group"], "unit": k["unit"], "role": k["role"], "order": k["order"],
                     "why": k.get("why", ""), "std": k["std"], "tu": int(k["tu"]), "dec": None, "exe": None}
                orders.append(o)
                pending[k["unit"]] = o
            elif body.startswith("[AIDECIDE] "):
                k = dict(KV.findall(body))
                last_dec[k["unit"]] = k
                if k.get("side") == "1":
                    ut[(int(k["turn"]), k["unit"])]["decides"] += 1
                    o = pending.get(k["unit"])
                    if o and o["dec"] is None:
                        o["dec"] = k
            elif body.startswith("[AIEXEC] "):
                e = json.loads(body[len("[AIEXEC] "):])
                u = str(e["unit"])
                k = last_dec.pop(u, None)
                o = pending.pop(u, None)
                if o and o["dec"] is not None:
                    o["exe"] = e
                if not k or k.get("side") != "1":
                    continue
                s = ut[(int(k["turn"]), u)]
                if "pos" in e:
                    s["spotted"] = e.get("spotted", 0)
                if int(k["act"]) in ATT:
                    s["att"] += 1
                    s["aims"].add(k.get("aim", "-"))
                    if e.get("dmg", 0) + e.get("stunned", 0) // 2 > 0 or e.get("downed", 0):
                        s["eff"] += 1
                        s["dmg"] += e.get("dmg", 0)
                        s["eff_aims"].add(k.get("aim", "-"))
            elif body.startswith("[AIAFTER] "):
                a = json.loads(body[len("[AIAFTER] "):])
                if a.get("side") == 0:
                    after_p[a["turn"]] += a.get("hp_lost", 0)
            elif body.startswith("[AICASUALTY] "):
                k = dict(KV.findall(body))
                cas[(int(k["turn"]), k["vfaction"])] += 1
            elif body.startswith("[AIEVENT] ") and " what=reaction " in body:
                k = dict(KV.findall(body))
                reactions.append((int(k["turn"]), k["side"], k["unit"]))
    return ut, after_p, cas, plans, groups, orders, reactions


def cat(s):
    return "useful" if s["eff"] else "wasted" if s["att"] else "exposed" if s["spotted"] else "hidden"


def series(pre):
    out = {}
    for d in sorted(OUT.glob(f"{pre}_*")):
        if (d / "openxcom.log.gz").exists():
            key = "_".join(d.name.split("_")[2:])
            out[key] = battle(d)
    return out


A, B = series(PA), series(PB)
keys = sorted(set(A) & set(B))
print(f"pairs {len(keys)}: {keys}; turns <= {TMAX}")
tot = {x: Counter() for x in "AB"}
for x, S in (("A", A), ("B", B)):
    for key in keys:
        ut, after_p, cas, *_ = S[key]
        for (t, u), s in ut.items():
            if t <= TMAX:
                tot[x][cat(s)] += 1
                tot[x]["useful_on_player"] += any(a.isdigit() and int(a) < 1000000 for a in s["eff_aims"])
                tot[x]["decides"] += s["decides"]
                tot[x]["max_decides"] = max(tot[x]["max_decides"], s["decides"])
                tot[x]["dmg"] += s["dmg"]
        tot[x]["php_lost"] += sum(v for t, v in after_p.items() if t <= TMAX)
        tot[x]["pdead"] += sum(v for (t, f), v in cas.items() if t <= TMAX and f == "0")
        tot[x]["hdead"] += sum(v for (t, f), v in cas.items() if t <= TMAX and f == "1")
for x in "AB":
    c = tot[x]
    print(f"== {x} {PA if x == 'A' else PB}: useful {c['useful']} wasted {c['wasted']} exposed {c['exposed']} hidden {c['hidden']}; "
          f"dmg by hostile attacks {c['dmg']}; player hp lost {c['php_lost']}, player down {c['pdead']}, hostile down {c['hdead']}; "
          f"decisions {c['decides']} (max {c['max_decides']} per unit-turn); unit-turns with an effective attack on a player unit "
          f"{c['useful_on_player']}")

ordc, chg, done, roles, phases, why_free = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
joint = Counter()
support = Counter()
replaced_attack = 0
per_ut = Counter()
stale = 0
plans_n = plans_g = 0
for key in keys:
    ut, after_p, cas, plans, groups, orders, reactions = B[key]
    for p in plans:
        if int(p["turn"]) <= TMAX:
            plans_n += 1
            plans_g += int(p["groups"]) > 0
    for (t, gid), g in groups.items():
        if t > TMAX:
            continue
        phases[g["phase"]] += 1
        stale += g["age"] > 1
        for _, r in g["members"]:
            roles[r] += 1
    sent = defaultdict(set)  # (turn, group) -> units the director moved (MANEUVER / WAIT / SUPPORT)
    planned_att = defaultdict(set)  # (turn, group) -> units whose attack came from an order
    sup_units = defaultdict(set)  # turn -> support units
    for o in orders:
        if o["turn"] > TMAX:
            continue
        ordc[o["order"]] += 1
        per_ut[(key, o["turn"], o["unit"])] +=o["order"] in CHANGE and o["order"] != "HOLD"
        std_act = int(o["std"].split("/")[1].split("@")[0])
        if std_act in ATT and o["order"] != "KEEP":
            replaced_attack += 1
        if o["order"] == "FREE":
            why_free[o["why"]] += 1
        if o["order"] in CHANGE:
            chg[o["std"].split("@")[0] + ">" + o["order"]] += 1
        dec, exe = o["dec"], o["exe"]
        if o["order"] in ("FIRE", "JOIN"):
            ok = bool(exe and exe.get("spent", 0) > 0)
            eff = bool(exe and (exe.get("dmg", 0) + exe.get("stunned", 0) // 2 > 0 or exe.get("downed", 0)))
            done[o["order"] + (".paid" if ok else ".notpaid")] += 1
            done[o["order"] + (".useful" if eff else ".nouse")] += 1
            if ok:
                planned_att[(o["turn"], o["group"])].add(o["unit"])
        elif o["order"] in ("FIREWALK", "JOINWALK"):
            done[o["order"] + (".moved" if exe and exe.get("walk") else ".stuck")] += 1
            s = ut.get((o["turn"], o["unit"]), {})
            done[o["order"] + (".turn_useful" if s.get("eff") else ".turn_wasted" if s.get("att") else
                               ".turn_exposed" if s.get("spotted") else ".turn_hidden")] += 1
            planned_att[(o["turn"], o["group"])].add(o["unit"])  # the shot after the walk, if any, counts as ordered
        elif o["order"] in ("MANEUVER", "WAIT", "SUPPORT", "HOLD"):
            sent[(o["turn"], o["group"])].add(o["unit"])
            if exe and "pos" in exe:
                done[o["order"] + (".hidden" if exe.get("spotted", 0) == 0 else ".seen")] += 1
            if o["order"] == "SUPPORT":
                sup_units[o["turn"]].add(o["unit"])
                if exe and "tu" in exe:
                    support["kept_tu"] += 1 if exe["tu"] > 0 else 0
                support["orders"] += 1
    for t, side, u in reactions:
        if side == "0" and u in sup_units.get(t, set()):
            support["reaction_shots"] += 1
        if side == "0":
            support["reactions_all_hostile"] += 1
    # joint engagements
    for (t, gid), g in groups.items():
        if t > TMAX or g["phase"] == "LIMIT":
            continue
        m = [u for u, _ in g["members"]]
        useful = [u for u in m if ut.get((t, u), {}).get("eff")]
        on_target = [u for u in m if g["target"] in ut.get((t, u), {}).get("eff_aims", ())]
        on_player = [u for u in m if any(a.isdigit() and int(a) < 1000000 for a in ut.get((t, u), {}).get("eff_aims", ()))]
        prev_sent_all = set()
        for (t2, g2), us in sent.items():
            if t2 == t - 1:
                prev_sent_all |= us
        for name, lst in (("target", on_target), ("player", on_player)):
            if len(lst) >= 2:
                joint["joint_on_" + name] += 1
                if any(u in planned_att[(t, gid)] or u in prev_sent_all for u in lst):
                    joint["planned_on_" + name] += 1
                    if name == "target":
                        print(f"   planned joint on the target: {key} t={t} group {gid} {g['phase']} target {g['target']} members "
                              f"{g['members']} hit it {sorted(lst)} ordered {sorted(planned_att[(t, gid)] & set(lst))} sent before "
                              f"{sorted(prev_sent_all & set(lst))}")
        if len(useful) >= 2:
            joint["joint"] += 1
            prev_sent = set()
            for (t2, g2), us in sent.items():
                if t2 == t - 1:
                    prev_sent |= us
            if any(u in planned_att[(t, gid)] or u in prev_sent for u in useful):
                joint["planned"] += 1
                joint["planned_useful_attacks"] += len(useful)
        # the prototype: an APPROACH group of turn t, its members sent (closing in / waiting / covering) and not exposed, then a
        # group of turn t+1 on the same target whose attacks with effect come from two or more of them
        if g["phase"] == "APPROACH":
            joint["approach"] += 1
            sent_ok = [u for u in sent[(t, gid)] if (t, u) in ut and cat(ut[(t, u)]) != "exposed"]
            joint["approach_sent_hidden"] += len(sent_ok)
            joint["approach_sent_exposed"] += len([u for u in sent[(t, gid)] if (t, u) in ut and cat(ut[(t, u)]) == "exposed"])
            nxt = [g2 for (t2, _), g2 in groups.items() if t2 == t + 1 and g2["target"] == g["target"]]
            if nxt:
                joint["approach_followed"] += 1
                hit = [u for u in sent_ok if any(a.isdigit() and int(a) < 1000000 for a in ut.get((t + 1, u), {}).get("eff_aims", ()))]
                att = [u for u in sent_ok if ut.get((t + 1, u), {}).get("att")]
                joint["approach_next_attackers"] += len(att)
                joint["approach_next_useful"] += len(hit)
                if len(hit) >= 2:
                    joint["approach_to_joint_strike"] += 1
                    print(f"   prototype: {key} t={t} group {gid} target {g['target']} sent {sorted(sent_ok)} -> t+1 useful {sorted(hit)}")
        attackers = [u for u in m if ut.get((t, u), {}).get("att")]
        joint["members"] += len(m)
        joint["members_attacked"] += len(attackers)
        joint["members_exposed_noattack"] += sum(1 for u in m if (t, u) in ut and cat(ut[(t, u)]) == "exposed")

print(f"== plans {plans_n}, with groups {plans_g}; groups by phase {dict(phases)}; roles {dict(roles)}; group targets older than "
      f"a turn {stale}")
print("   orders:", dict(ordc.most_common()))
print("   FREE why:", dict(why_free.most_common()))
print("   own choice > order:", dict(chg.most_common(14)))
print("   carried out:", dict(sorted(done.items())))
print("   support:", dict(support))
print("   engagement:", dict(joint))
print(f"   orders replacing an attack the unit chose {replaced_attack} (need 0); most changing orders in one unit-turn "
      f"{max(per_ut.values()) if per_ut else 0}")
