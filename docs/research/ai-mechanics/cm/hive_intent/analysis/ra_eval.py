"""RESTORE COMBAT AUTONOMY: runs side by side on the metrics declared in GATES_AND_RUN_LIST.md, turns 1..8. Combat capability, not orders: artificial escapes, units that lost the chance to act, attacks and damage, cells walked towards the squad's objective, the guard's sector, losses by turn, squads after the next turn, TU. Read only. Run chain.py on the same runs first.
Usage: ra_eval.py <run> ..."""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
ATT = set(range(4, 21))
LAST = 8
HOLD_RADIUS = 8
NOT_GUARD = {"nothing_known", "nothing_reachable"}
P = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")


def xyz(s):
    m = P.search(s or "")
    return tuple(int(x) for x in m.groups()) if m else None


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def ana(run):
    L = read(run)
    R = Counter()
    objective = {}
    anchor = {}
    role = {}
    last_order = {}
    answer = {}
    dec = []
    dmg = Counter()
    fdmg = Counter()
    down = defaultdict(set)
    members = {}
    react = 0
    turn = 0
    res = ""
    for s in L:
        if s.startswith("[HIVECC]"):
            k = kv(s)
            if k["event"] == "ASSIGN":
                role[k["squad"]] = k["to"]
            elif k["event"] == "AUTONOMY":
                answer[k["unit"]] = k["answer"]
                R["answer_" + k["answer"]] += 1
                R["from_" + k["from"]] += 1
        elif s.startswith("[HIVETASK]"):
            k = kv(s)
            objective[k["squad"]] = xyz(k.get("objective"))
        elif s.startswith("[HIVEHOLD]"):
            k = kv(s)
            if k.get("event") == "entered":
                anchor[k["squad"]] = xyz(k.get("anchor"))
        elif s.startswith("[HIVESQUAD]"):
            k = kv(s)
            if "members" not in k or "id" not in k:
                continue
            members[k["id"]] = {m.rstrip("SAL") for m in k["members"].split(",")}
            if xyz(k.get("anchor")) and k["id"] not in anchor:
                anchor[k["id"]] = xyz(k["anchor"])
        elif s.startswith("[HIVEORD]"):
            k = kv(s)
            last_order[k["unit"]] = k
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            turn = int(k["turn"])
            if k["side"] == "1" and turn <= LAST:
                o = last_order.get(k["unit"], {})
                sq = o.get("squad", "")
                dec.append(dict(k, answer=answer.pop(k["unit"], ""), order=dict(o), squad=sq, role=role.get(sq, "MAINTAIN"), obj=objective.get(sq), anchor=anchor.get(sq)))
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            if not j.get("walk") and int(j.get("unit", 0)) >= 1000000 and turn <= LAST:
                dmg[turn] += j.get("dmg", 0)
                fdmg[turn] += j.get("fdmg", 0)
        elif s.startswith("[AICASUALTY]"):
            k = kv(s)
            if int(k["turn"]) <= LAST + 1:
                down[k.get("vfaction")].add((k["victim"], int(k["turn"])))
        elif s.startswith("[AIEVENT]") and "what=reaction" in s:
            k = kv(s)
            if k.get("side") == "0" and int(k["unit"]) >= 1000000:
                react += 1
        elif s.startswith("[AIRESULT]"):
            res = s
    # the table has the same decisions in the same order; n repeats inside a unit's turn, (turn, unit, n) is no key
    p = HERE / f"decisions_{run}.tsv"
    tsv = list(csv.DictReader(open(p, encoding="utf-8-sig"), delimiter="\t"))
    if len(tsv) != len(dec):
        raise SystemExit(f"{run}: table {len(tsv)} decisions {len(dec)}")
    for k, d in zip(dec, tsv):
        if (k["turn"], k["unit"], k["tu"]) != (d["turn"], d["unit"], d["tu"]):
            raise SystemExit(f"{run}: table out of step at {k['turn']} {k['unit']}")
        k["row"] = d
    byturn = defaultdict(list)
    for k in dec:
        byturn[(int(k["turn"]), k["unit"])].append(k)
    T = Counter()
    closing = Counter()
    guard = Counter()
    tu = Counter()
    for k in dec:
        c = k["row"]
        a = k["answer"]
        name = c.get("cls", "")
        act = int(k["act"])
        T["decisions"] += 1
        T["attacks"] += act in ATT
        if act in ATT:
            T["attacks_" + (k["role"] if k["role"] != "MAINTAIN" else k["order"].get("task", "NONE"))] += 1
        T["walks"] += act == 2
        T["esc_all"] += k["mode"] == "3"
        T["esc_walk"] += k["mode"] == "3" and act == 2
        T["esc_dice"] += name.startswith("esc_dice")
        T["esc_kept"] += name.startswith("esc_kept")
        T["esc_kept_walk"] += name == "esc_kept_walk"
        is_art = name.startswith("art_esc") and a != "FREE"
        T["ART_ESC"] += is_art
        T["ART_ESC_walk"] += name == "art_esc_walk" and a != "FREE"
        T["free_fallback"] += name.startswith("art_esc") and a == "FREE"
        T["free_fallback_walk"] += name == "art_esc_walk" and a == "FREE"
        T["stand_mode0"] += name == "held_patrol_stand" and a != "FREE"
        T["answer_stand_decisions"] += a == "STAND"
        T["answer_free_decisions"] += a == "FREE"
        T["answer_free_walk"] += a == "FREE" and act == 2
        T["answer_free_attack"] += a == "FREE" and act in ATT
    ordered = sorted(byturn)
    for (t, u) in ordered:
        ds = byturn[(t, u)]
        names = [k["row"]["cls"] for k in ds]
        T["unit_turns"] += 1
        art = any(n.startswith("art_esc") and k["answer"] != "FREE" for n, k in zip(names, ds))
        T["ut_art"] += art
        T["ut_art_ends_idle"] += art and ds[-1]["act"] == "0"
        T["ut_idle_end"] += ds[-1]["act"] == "0"
        T["tu_idle_end"] += int(ds[-1]["tu"]) if ds[-1]["act"] == "0" else 0
        # TU: never rise inside a turn
        tus = [int(k["tu"]) for k in ds]
        tu["rises"] += sum(b > a for a, b in zip(tus, tus[1:]))
        tu[f"start_{u}"] = max(tu[f"start_{u}"], tus[0])
        nxt = byturn.get((t + 1, u))
        a, b = xyz(ds[0]["from"]), xyz(nxt[0]["from"]) if nxt else None
        if not b:
            continue
        k0 = ds[0]
        o = k0["order"]
        is_guard = o.get("task") == "HOLD" and o.get("why") not in NOT_GUARD and k0["role"] == "MAINTAIN"
        if is_guard and k0["anchor"]:
            guard["unit_turns"] += 1
            d = cheb(b, k0["anchor"])
            guard["in_radius"] += d <= HOLD_RADIUS
            guard["moved"] += a != b
            guard["cells"] += cheb(a, b)
        elif k0["obj"] and (k0["role"] in ("ENGAGE", "REINFORCE") or o.get("task") == "SEARCH"):
            label = k0["role"] if k0["role"] != "MAINTAIN" else "SEARCH"
            closing[label + "_ut"] += 1
            delta = cheb(a, k0["obj"]) - cheb(b, k0["obj"])
            closing[label + "_net"] += delta
            closing[label + "_toward"] += max(delta, 0)
            closing[label + "_away"] += max(-delta, 0)
            closing[label + "_walked"] += cheb(a, b)
    by_turn = {}
    for fac, name in (("1", "own"), ("0", "enemy")):
        seen = {}
        for v, t in sorted(down[fac], key=lambda x: x[1]):
            seen.setdefault(v, t)
        by_turn[name] = [sum(t <= x for t in seen.values()) for x in (2, 4, 6, 8)]
    # squads after the next turn: who of each squad still stands at turn 3 and at the end
    own_down = {}
    for v, t in sorted(down["1"], key=lambda x: x[1]):
        own_down.setdefault(v, t)
    squads = {}
    for sid, m in sorted(members.items(), key=lambda x: int(x[0])):
        squads[sid] = (len(m), sum(1 for u in m if own_down.get(u, 99) > 3), sum(1 for u in m if own_down.get(u, 99) > LAST))
    start = {k[6:]: v for k, v in tu.items() if k.startswith("start_")}
    return dict(run=run, T=T, closing=closing, guard=guard, react=react, dmg=sum(dmg.values()), fdmg=sum(fdmg.values()), by_turn=by_turn, squads=squads, rises=tu["rises"], start=start, res=res, tail=R)


def main():
    rs = [ana(r) for r in sys.argv[1:]]
    print("runs", [r["run"] for r in rs])
    keys = sorted({k for r in rs for k in r["T"]})
    for k in keys:
        print(f"  {k:28}", *[f"{r['T'][k]:>8}" for r in rs])
    print("  reactions                   ", *[f"{r['react']:>8}" for r in rs])
    print("  damage dealt                ", *[f"{r['dmg']:>8}" for r in rs])
    print("  friendly damage             ", *[f"{r['fdmg']:>8}" for r in rs])
    print("  tu rises inside a turn      ", *[f"{r['rises']:>8}" for r in rs])
    for name in ("own", "enemy"):
        print(f"  down {name} by turns 2,4,6,8", *[r["by_turn"][name] for r in rs])
    print("closing on the objective (cells, Chebyshev, first decision of the turn to first of the next):")
    for k in sorted({k for r in rs for k in r["closing"]}):
        print(f"  {k:28}", *[f"{r['closing'][k]:>8}" for r in rs])
    print("guard's sector:")
    for k in ("unit_turns", "in_radius", "moved", "cells"):
        print(f"  {k:28}", *[f"{r['guard'][k]:>8}" for r in rs])
    print("squads, size / standing after turn 3 / at the end:")
    for r in rs:
        print("  ", r["run"], r["squads"])
    print("answers and where from:")
    for r in rs:
        print("  ", r["run"], dict(r["tail"]))
    print("results:")
    for r in rs:
        print("  ", r["run"], r["res"][:200])
    if len(rs) > 1:
        base = rs[0]["start"]
        for r in rs[1:]:
            print("  start TU above the first run's:", r["run"], sum(v > base.get(u, 10 ** 6) for u, v in r["start"].items()))


main()
