"""COORDINATED_ENGAGEMENT_V1: the functional gates and the engagement metrics of a series B (commander on) against A (D0).

Each hostile unit-turn as in ce_profile.py: useful (attacked with effect), wasted, exposed (no attack, ended in sight), hidden;
the player's next turn (AIAFTER). From B's [AIPROBE] ce lines: groups (turn, id, target, members, excluded with reasons) and
orders (FIRE / JOIN / HOLD / FREE). A group-turn is joint when two or more of its members attacked with effect in that hostile
turn; confirmed when one of those was held (HOLD) by the commander in the turn before - a joint attack the order had a hand
in, not two shots that happened to fall in one turn. Checks: a HOLD whose decision in the log is an attack; JOIN/HOLD counting
an attack of a member that was not yet made (turn order); orders to units outside the group's members.

  py -3.13 -I ce_check.py <out dir> <prefix A> <prefix B>     (labels <prefix>_<arm>_<scen>_s<k>)"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PA, PB = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}


def battle(d):
    last_dec = {}
    ut = defaultdict(lambda: {"att": 0, "eff": 0, "dmg": 0, "spotted": 0, "decides": 0})
    after = {}
    groups = {}  # (turn, gid) -> dict
    orders = []  # dicts, in log order
    fired = set()  # (turn, gid, unit) FIRE lines seen so far
    order_viol = 0
    pending_hold = {}  # unit -> order dict waiting for its AIDECIDE
    hold_attack = 0
    res = {}
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] "):
                k = dict(KV.findall(body))
                last_dec[k["unit"]] = k
                if k.get("side") == "1":
                    ut[(int(k["turn"]), k["unit"])]["decides"] += 1
                    o = pending_hold.pop(k["unit"], None)
                    if o and int(k["act"]) in ATT:
                        hold_attack += 1
            elif body.startswith("[AIEXEC] "):
                e = json.loads(body[len("[AIEXEC] "):])
                u = str(e["unit"])
                k = last_dec.pop(u, None)
                if not k or k.get("side") != "1":
                    continue
                s = ut[(int(k["turn"]), u)]
                if "pos" in e:
                    s["spotted"] = e.get("spotted", 0)
                if int(k["act"]) in ATT:
                    s["att"] += 1
                    if e.get("dmg", 0) + e.get("stunned", 0) // 2 > 0 or e.get("downed", 0):
                        s["eff"] += 1
                        s["dmg"] += e.get("dmg", 0)
            elif body.startswith("[AIAFTER] "):
                a = json.loads(body[len("[AIAFTER] "):])
                if a.get("side") == 1:
                    after[(a["turn"], str(a["unit"]))] = a
            elif body.startswith("[AIPROBE] ce group "):
                k = dict(KV.findall(body))
                ex = [] if k["excluded"] == "-" else [x.split(":") for x in k["excluded"].split(",")]
                groups[(int(k["turn"]), k["id"])] = {"target": k["target"].split("@")[0],
                                                     "members": [] if k["members"] == "-" else k["members"].split(","),
                                                     "excluded": ex}
            elif body.startswith("[AIPROBE] ce turn="):
                k = dict(KV.findall(body))
                t, g, u = int(k["turn"]), k["group"], k["unit"]
                o = {"turn": t, "group": g, "unit": u, "order": k["order"], "kind": k.get("kind", ""), "why": k.get("why", ""),
                     "tu": int(k.get("tu", 0)), "attacked": [] if k.get("attacked", "-") == "-" else k["attacked"].split(",")}
                orders.append(o)
                if o["order"] == "FIRE" and k.get("act") != "2":
                    fired.add((t, g, u))
                for x in o["attacked"]:
                    if (t, g, x) not in fired:
                        order_viol += 1
                if o["order"] == "HOLD":
                    pending_hold[u] = o
            elif body.startswith("[AIRESULT] "):
                res = dict(KV.findall(body))
    return ut, after, groups, orders, order_viol, hold_attack, res


def cat(s):
    return "useful" if s["eff"] else "wasted" if s["att"] else "exposed" if s["spotted"] else "hidden"


def series(pre):
    tot = {"cat": Counter(), "fell": Counter(), "dmg": 0, "decides": 0, "max_decides": 0, "battles": 0, "results": Counter(),
           "phplost": 0, "pdead": 0, "hdead": 0, "turns": 0}
    eng = Counter()
    hold_out = Counter()
    excl = Counter()
    per = {}
    for d in sorted(OUT.glob(f"{pre}_*")):
        if not (d / "openxcom.log.gz").exists():
            continue
        ut, after, groups, orders, viol, hold_attack, res = battle(d)
        tot["battles"] += 1
        tot["results"][res.get("how", "none")] += 1
        for key in ("phplost", "pdead", "hdead"):
            tot[key] += float(res.get(key, 0) or 0)
        tot["turns"] += int(res.get("turn", 0) or 0)
        for (t, u), s in ut.items():
            c = cat(s)
            tot["cat"][c] += 1
            a = after.get((t, u))
            if a and (a.get("dead") or a.get("down")):
                tot["fell"][c] += 1
            tot["dmg"] += s["dmg"]
            tot["decides"] += s["decides"]
            tot["max_decides"] = max(tot["max_decides"], s["decides"])
        eng["order_viol"] += viol
        eng["hold_on_attack"] += hold_attack
        held = defaultdict(set)  # turn -> units held
        for o in orders:
            eng["order." + o["order"] + ("." + o["kind"] if o["kind"] else "") + ("." + o["why"] if o["why"] else "")] += 1
            g = groups.get((o["turn"], o["group"]))
            if g is None or o["unit"] not in g["members"]:
                eng["order_outside_group"] += 1
            if o["order"] == "HOLD":
                if o["unit"] not in held[o["turn"]]:
                    eng["hold_tu_kept"] += o["tu"]
                held[o["turn"]].add(o["unit"])
        joint_turns = {}
        for (t, gid), g in groups.items():
            eng["groups"] += 1
            if len(g["members"]) >= 2:
                eng["groups_2plus"] += 1
            for _, why in g["excluded"]:
                excl[why] += 1
            m = g["members"]
            attackers = [u for u in m if ut.get((t, u), {}).get("att")]
            useful = [u for u in m if ut.get((t, u), {}).get("eff")]
            if len(m) >= 2:
                eng["gt_attackers"] += len(attackers)
                eng["gt_useful"] += len(useful)
                eng["gt_exposed_noattack"] += sum(1 for u in m if (t, u) in ut and cat(ut[(t, u)]) == "exposed")
                if len(useful) >= 2:
                    eng["joint"] += 1
                    joint_turns[(t, gid)] = useful
                    if any(u in held.get(t - 1, ()) for u in useful):
                        eng["confirmed"] += 1
                        eng["confirmed_useful_attacks"] += len(useful)
        for t, us in held.items():
            for u in us:
                a = after.get((t, u))
                nxt = ut.get((t + 1, u))
                in_joint = any(u in us2 for (t2, _), us2 in joint_turns.items() if t2 == t + 1)
                if a and (a.get("dead") or a.get("down")):
                    hold_out["fell_after_hold"] += 1
                elif u in held.get(t + 1, ()):
                    hold_out["held_again"] += 1
                elif nxt and nxt["eff"] and in_joint:
                    hold_out["joint_attack_next"] += 1
                elif nxt and nxt["eff"]:
                    hold_out["useful_alone_next"] += 1
                elif nxt and nxt["att"]:
                    hold_out["wasted_next"] += 1
                elif nxt and nxt["spotted"]:
                    hold_out["exposed_next"] += 1
                else:
                    hold_out["no_attack_next"] += 1
        per[d.name] = (res.get("phplost"), res.get("pdead"), res.get("hdead"), res.get("turn"))
    return tot, eng, hold_out, excl, per


A = series(PA)
B = series(PB)
for name, (tot, eng, hold_out, excl, _) in (("A " + PA, A), ("B " + PB, B)):
    c = tot["cat"]
    print(f"== {name}: battles {tot['battles']} results {dict(tot['results'])} turns {tot['turns']}")
    print(f"   phplost {tot['phplost']:.0f} pdead {tot['pdead']:.0f} hdead {tot['hdead']:.0f}  dmg by hostile attacks {tot['dmg']}")
    print("   unit-turns: " + "  ".join(f"{k} {c[k]} (fell {tot['fell'][k]})" for k in ("useful", "wasted", "exposed", "hidden")))
    print(f"   decisions {tot['decides']}, most in one unit-turn {tot['max_decides']}")
    if eng:
        print("   engagement:", dict(sorted(eng.items())))
        print("   HOLD outcomes:", dict(hold_out))
        print("   excluded:", dict(excl))
ta, tb = A[0], B[0]
ua, ub = ta["cat"]["useful"], tb["cat"]["useful"]
ea, eb = ta["cat"]["exposed"], tb["cat"]["exposed"]
eng = B[1]
print("== gates")
print(f"   confirmed joint engagements {eng['confirmed']} (need >= 20): {'PASS' if eng['confirmed'] >= 20 else 'FAIL'}")
print(f"   useful attacks B/A {ub}/{ua} = {ub / max(1, ua):.2f} (need >= 0.90): {'PASS' if ub >= 0.9 * ua else 'FAIL'}")
print(f"   exposed without attack B/A {eb}/{ea} (need B < A): {'PASS' if eb < ea else 'FAIL'}")
print(f"   HOLD on an attack {eng['hold_on_attack']}, turn-order violations {eng['order_viol']}, orders outside the group "
      f"{eng['order_outside_group']} (need 0): {'PASS' if not (eng['hold_on_attack'] or eng['order_viol'] or eng['order_outside_group']) else 'FAIL'}")
print(f"   decisions B/A {tb['decides']}/{ta['decides']} (need <= 1.10), max per unit-turn {tb['max_decides']}/{ta['max_decides']}: "
      f"{'PASS' if tb['decides'] <= 1.1 * ta['decides'] else 'FAIL'}")
print(f"   results B {dict(tb['results'])} A {dict(ta['results'])}")
