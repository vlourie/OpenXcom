"""STRIKE-V0, the checks the per-shot table does not show.

  py -3.13 -I fl_sv2.py <out dir> <D0 prefix> <shadow prefix> <on prefix>

A. The shadow run equals D0 decision for decision, so at every would-be shot the rest of that unit-turn in the shadow log is
   exactly what happens without the order: the decision it would have replaced, whether the unit attacks later in the turn
   anyway (a shot that is not additional), the damage of those attacks, what the replaced walk itself cost.
B. The battles with the order on: shots per order, focus on one target, friendly damage, TU against the cost, the rules' estimate
   against the result, order shots against the same battles' other attacks, the side's attacks and moves against D0, decisions
   per unit-turn and decisions that spent nothing (loops), error lines, the target on a hostile unit's seen list (FAIR)."""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
FIRE = {7, 8, 9}
ATT = {6, 7, 8, 9, 10, 12, 13, 14}


def read(d):
    ev = []
    pend = None
    res = None
    errors = 0
    snap = defaultdict(dict)
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        parts = raw.rstrip("\n").split("\t", 2)
        body = parts[-1]
        if len(parts) == 3 and parts[1] in ("[ERROR]", "[FATAL]"):
            errors += 1
        if body.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(body.split(" hu=")[0]))
            pend["kind"] = "dec"
            ev.append(pend)
        elif body.startswith("[AIEXEC] ") and pend:
            x = json.loads(body[9:])
            if str(x["unit"]) == pend["unit"]:
                pend["x"] = x
            pend = None
        elif body.startswith("[AISTRIKE] "):
            s = dict(KV.findall(body[11:]))
            s["kind"] = "strike." + s.get("kind", "?")
            ev.append(s)
        elif body.startswith("[AIEVENT] ") and "what=reaction" in body:
            s = dict(KV.findall(body))
            s["kind"] = "react"
            ev.append(s)
        elif body.startswith("[AICASUALTY] "):
            s = dict(KV.findall(body))
            s["kind"] = "cas"
            ev.append(s)
        elif body.startswith("[AISTATE] aistart "):
            s = dict(KV.findall(body))
            snap[int(s["turn"])][s["unit"]] = s
        elif body.startswith("[AIRESULT] "):
            res = dict(KV.findall(body))
    return ev, res, errors, snap


def is_attack(e):
    x = e.get("x") or {}
    return int(e["act"]) in ATT and (x.get("spent") or 0) > 0 and not x.get("walk")


def useful(x):
    return (x.get("dmg") or 0) > 0 or (x.get("stunned") or 0) > 0 or (x.get("downed") or 0) > 0


def reactions_after(ev, i):
    n = 0
    for y in ev[i + 1:]:
        if y["kind"] == "dec":
            break
        if y["kind"] == "react" and int(y["unit"]) < 1000000:
            n += 1
    return n


def bucket(v):
    return "<2" if v < 2 else "2-5" if v < 5 else "5-15" if v < 15 else ">=15"


def part_a(out, ps):
    c = Counter()
    later_dmg = 0
    later_tu = walk_spent = walk_lost = walk_react = 0
    act_ok = Counter()
    n_battles = 0
    per_battle = Counter()
    for d in sorted(out.glob(f"{ps}_*")):
        ev, _, _, _ = read(d)
        n_battles += 1
        for i, e in enumerate(ev):
            if e["kind"] == "strike.opp" and e.get("cls") == "allowed" and e.get("shot") == "ok":
                act_ok[f"act{e['act']} mode{e['mode']}"] += 1
            if e["kind"] != "strike.exec":
                continue
            t, u = int(e["turn"]), e["unit"]
            per_battle[d.name] += 1
            c["would-be shots"] += 1
            c[f"replaces act{e['d0act']} mode{e['mode']}"] += 1
            j = next((k for k in range(i + 1, len(ev)) if ev[k]["kind"] == "dec" and ev[k]["unit"] == u), None)
            if j is None:
                continue
            x0 = ev[j].get("x") or {}
            walk_spent += x0.get("spent") or 0
            walk_lost += x0.get("hp_lost") or 0
            walk_react += reactions_after(ev, j)
            if x0.get("down"):
                c["the replaced walk: unit went down"] += 1
            att = dmg = 0
            good = False
            left = None
            for y in ev[j:]:
                if y["kind"] == "dec" and y.get("side") == "1" and y["unit"] == u and int(y["turn"]) == t:
                    xx = y.get("x") or {}
                    left = xx.get("tu", left)
                    if is_attack(y):
                        att += 1
                        dmg += xx.get("dmg") or 0
                        good = good or useful(xx)
            later_dmg += dmg
            later_tu += left or 0
            if att == 0:
                c["D0: no attack later in the turn (additional)"] += 1
                if (left or 0) >= int(e["cost"]):
                    c["  of them TU for the shot still unused at the end of the walks"] += 1
            else:
                c["D0: attacks later in the turn anyway (not additional)"] += 1
                if good:
                    c["  of them a useful attack, which the order could cost"] += 1
    print("A. shadow = D0: what the would-be shots would have replaced")
    for k, v in c.most_common():
        print(f"  {k:62s} {v}")
    print(f"  the D0 attacks later in those unit-turns dealt in all         {later_dmg}")
    print(f"  the replaced walks: TU spent {walk_spent}, unit hp lost {walk_lost}, reactions {walk_react}")
    print("  allowed by class and shot ok, all decisions: " + ", ".join(f"{k}={v}" for k, v in act_ok.most_common()))


def part_b(out, pd, pn):
    sh = Counter()
    by_est = defaultdict(Counter)
    orders = Counter()
    tu_diff = Counter()
    other = Counter()
    d0 = Counter()
    res_rows = []
    top = []
    fair_ok = fair_no = 0
    aux = Counter()
    killed = []
    for nd in sorted(out.glob(f"{pn}_*")):
        dd = out / nd.name.replace(f"{pn}_", f"{pd}_", 1)
        ev, res, err, snap = read(nd)
        dev, dres, derr, _ = read(dd)
        sh["error lines on"] += err
        sh["error lines D0"] += derr
        res_rows.append((nd.name, dres, res))
        seen = defaultdict(set)
        fired = Counter()
        hit_units = defaultdict(set)
        order_target = {e["order"]: e["target"] for e in ev if e["kind"] == "strike.order"}
        for o in order_target:
            orders["orders"] += 1
        marked = set()
        for i, e in enumerate(ev):
            if e["kind"] == "dec" and e.get("side") == "1":
                seen[int(e["turn"])].update(x for x in e.get("seen", "-").split(",") if x != "-")
            if e["kind"] != "strike.exec":
                continue
            t, u = int(e["turn"]), e["unit"]
            j = next((k for k in range(i + 1, len(ev)) if ev[k]["kind"] == "dec" and ev[k]["unit"] == u), None)
            dec = ev[j]
            marked.add(j)
            x = dec.get("x") or {}
            if int(dec["act"]) != int(e["type"]):
                sh["next decision is not the ordered shot"] += 1
            if int(dec["tu"]) != int(e["tu"]):
                sh["decision's TU differs from the check's"] += 1
            seen[t].update(s for s in dec.get("seen", "-").split(",") if s != "-")
            if e["target"] in seen[t]:
                fair_ok += 1
            else:
                fair_no += 1
            tv = snap.get(t, {}).get(e["target"], {})
            aux["vehicle target" if tv.get("weapon", "").startswith("AUX_") else "infantry target"] += 1
            spent = x.get("spent") or 0
            cost = int(e["cost"])
            tu_diff[spent - cost] += 1
            if spent < cost:
                sh["spent below the cost"] += 1
            if x.get("tu") is not None and x["tu"] != int(dec["tu"]) - spent:
                sh["TU after differs from TU before minus spent"] += 1
            sh["shots"] += 1
            sh["TU"] += spent
            sh["dmg"] += x.get("dmg") or 0
            sh["friendly dmg"] += x.get("fdmg") or 0
            sh["friendly downed"] += x.get("fdowned") or 0
            sh["useful"] += useful(x)
            sh["reactions"] += reactions_after(ev, j)
            sh["hp lost"] += x.get("hp_lost") or 0
            sh["est"] += float(e["dmg"])
            b = bucket(float(e["dmg"]))
            by_est[b]["shots"] += 1
            by_est[b]["useful"] += useful(x)
            by_est[b]["dmg"] += x.get("dmg") or 0
            by_est[b]["est"] += float(e["dmg"])
            fired[e["order"]] += 1
            if useful(x):
                hit_units[e["order"]].add(u)
            if x.get("downed"):
                cas = [y for y in ev[j:j + 40] if y["kind"] == "cas" and y.get("killer") == u]
                killed.append(f"{nd.name} t{t} u{u} target{e['target']} -> " + ",".join(f"{c['victim']}:{c['how']}" for c in cas))
        for o in order_target:
            orders[f"{min(fired[o], 3)}{'+' if fired[o] >= 3 else ''} shots by order"] += 1
            if len(hit_units[o]) >= 2:
                orders["two or more units did damage by order"] += 1
        for name, lst, skip, tot in (("on", ev, marked, other), ("D0", dev, set(), d0)):
            per = Counter()
            for k, e in enumerate(lst):
                if e["kind"] != "dec" or e.get("side") != "1":
                    continue
                x = e.get("x") or {}
                per[(int(e["turn"]), e["unit"])] += 1
                tot["decisions"] += 1
                tot["spent nothing"] += not (x.get("spent") or 0)
                if k in skip or not is_attack(e):
                    continue
                tot["attacks"] += 1
                tot["TU"] += x.get("spent") or 0
                tot["dmg"] += x.get("dmg") or 0
                tot["useful"] += useful(x)
                tot["reactions"] += reactions_after(lst, k)
                tot["hp lost"] += x.get("hp_lost") or 0
                tot["friendly dmg"] += x.get("fdmg") or 0
            if per:
                u, m = per.most_common(1)[0]
                top.append((nd.name, name, m, u))
    n = sh["shots"]
    print("\nB. the battles with the order on")
    print("  orders: " + ", ".join(f"{k}={v}" for k, v in sorted(orders.items())))
    print(f"  order shots {n}: useful {sh['useful']} ({100 * sh['useful'] / n:.1f}%), damage {sh['dmg']} ({sh['dmg'] / n:.1f} per shot),"
          f" TU {sh['TU']} ({sh['TU'] / n:.1f} per shot, {sh['TU'] / max(1, sh['dmg']):.1f} per hp)")
    print(f"  estimate by the rules in all {sh['est']:.0f} against damage {sh['dmg']}")
    print(f"  friendly damage {sh['friendly dmg']}, friendly downed {sh['friendly downed']}; reactions {sh['reactions']}, shooters' hp lost {sh['hp lost']}")
    print("  " + ", ".join(f"{k}={v}" for k, v in aux.most_common()))
    print("  by estimate: " + "; ".join(f"{b}: shots {c['shots']} useful {c['useful']} dmg {c['dmg']} est {c['est']:.0f}" for b, c in sorted(by_est.items())))
    print("  spent minus cost (turning): " + ", ".join(f"{k}:{v}" for k, v in sorted(tu_diff.items())))
    for k in ("next decision is not the ordered shot", "decision's TU differs from the check's", "spent below the cost",
              "TU after differs from TU before minus spent", "error lines on", "error lines D0"):
        print(f"  {k}: {sh[k]}")
    print(f"  FAIR, independent of the code's own check: target on the seen list of a hostile decision of that turn {fair_ok}, not found there {fair_no}")
    for name, c in (("other attacks, on", other), ("attacks, D0", d0)):
        a = max(1, c["attacks"])
        print(f"  {name}: {c['attacks']}, useful {c['useful']} ({100 * c['useful'] / a:.1f}%), damage {c['dmg']} ({c['dmg'] / a:.1f} per attack),"
              f" TU {c['TU'] / a:.1f} per attack, {c['TU'] / max(1, c['dmg']):.1f} per hp, reactions {c['reactions']} ({100 * c['reactions'] / a:.1f}%),"
              f" hp lost {c['hp lost']}, friendly {c['friendly dmg']}; decisions {c['decisions']}, spent nothing {c['spent nothing']} ({100 * c['spent nothing'] / max(1, c['decisions']):.1f}%)")
    print("  order shots that downed someone: ")
    for s in killed:
        print("    " + s)
    print("  most decisions in one unit-turn: " + "; ".join(f"{a[len(pn) + 1:] if b == 'on' else a[len(pn) + 1:]} {b} {m}" for a, b, m, u in top))
    print("  battle results D0 -> on")
    keys = ("pdead", "phplost", "hdead", "hattacks", "hmoves", "turn")
    s = {k: [0, 0] for k in keys}
    for name, a, b in res_rows:
        print(f"    {name[len(pn) + 1:]:10s} " + " ".join(f"{k} {a[k]}->{b[k]}" for k in keys))
        for k in keys:
            s[k][0] += int(a[k])
            s[k][1] += int(b[k])
    print("    together   " + " ".join(f"{k} {v[0]}->{v[1]}" for k, v in s.items()))


out = Path(sys.argv[1])
part_a(out, sys.argv[3])
part_b(out, sys.argv[2], sys.argv[4])
