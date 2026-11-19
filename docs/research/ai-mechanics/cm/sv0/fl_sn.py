"""STRIKE-V0, functional analysis of the battles with the order on (OXCE_AI_STRIKE=2) against the same battles of D0.

  py -3.13 -I fl_sn.py <out dir> <D0 prefix> <on prefix>

Per battle: the orders (kind=order: target, units it went to), the order shots handed out (kind=exec status=shot) and what
the engine then did with each - the unit's next decision must be that shot (AIDECIDE act 7/8/9) and its AIEXEC must show TU
spent with no walk (executed); useful - damage, stun or a down on the player side; the reactions (AIEVENT what=reaction of
player units) and the shooter's own losses (hp_lost, AICASUALTY in that turn) after it. Up to the first order shot the battle
is D0's own: the first shot's unit is compared with D0 for the rest of its turn (attacks, damage, TU spent and left). Checks:
TU never grows within a unit-turn, at most one order shot per unit-turn, decisions per unit-turn against D0's maximum, the
battle ended (AIRESULT)."""
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
    """The hostile decisions with their results, in log order, and the [AISTRIKE] lines, reactions, casualties, result."""
    ev = []
    pend = None
    res = None
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        body = raw.rstrip("\n").split("\t", 2)[-1]
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
        elif body.startswith("[AIRESULT] "):
            res = dict(KV.findall(body))
    return ev, res


def unit_turn(ev, t, u, n0):
    """The unit's decisions in turn t from decision number n0 on: attacks executed, damage, TU spent, TU left, own hp lost."""
    att = dmg = spent = lost = 0
    left = None
    acts = []
    for e in ev:
        if e["kind"] == "dec" and e.get("side") == "1" and int(e["turn"]) == t and e["unit"] == u and int(e["n"]) >= n0:
            x = e.get("x") or {}
            acts.append(int(e["act"]))
            spent += x.get("spent") or 0
            lost += x.get("hp_lost") or 0
            left = x.get("tu", left)
            if int(e["act"]) in ATT and (x.get("spent") or 0) > 0 and not x.get("walk"):
                att += 1
                dmg += (x.get("dmg") or 0)
    return {"att": att, "dmg": dmg, "spent": spent, "left": left, "lost": lost, "acts": acts}


def checks(ev):
    tu_up = 0
    per = Counter()
    last = {}
    for e in ev:
        if e["kind"] != "dec" or e.get("side") != "1":
            continue
        k = (int(e["turn"]), e["unit"])
        per[k] += 1
        tu = int(e["tu"])
        if k in last and tu > last[k]:
            tu_up += 1
        x = e.get("x") or {}
        last[k] = x.get("tu", tu)
    return tu_up, (max(per.values()) if per else 0)


def main():
    out, pd, pn = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    tot = Counter()
    for nd in sorted(out.glob(f"{pn}_*")):
        dd = out / nd.name.replace(f"{pn}_", f"{pd}_", 1)
        ev, res = read(nd)
        dev, dres = read(dd)
        print(f"== {nd.name}  result {res.get('how') if res else 'NONE'} turn={res.get('turn') if res else '-'}"
              f"  (D0: turn={dres.get('turn')} pdead={dres.get('pdead')} phplost={dres.get('phplost')} hdead={dres.get('hdead')};"
              f" on: pdead={res.get('pdead') if res else '-'} phplost={res.get('phplost') if res else '-'}"
              f" hdead={res.get('hdead') if res else '-'})")
        if not res:
            tot["no result"] += 1
        orders = [e for e in ev if e["kind"] == "strike.order"]
        tot["orders"] += len(orders)
        tot["orders >=2 units"] += sum(1 for o in orders if int(o["shooters"]) >= 2)
        tot["joins"] += sum(1 for e in ev if e["kind"] == "strike.join")
        execs = [i for i, e in enumerate(ev) if e["kind"] == "strike.exec" and e.get("status") == "shot"]
        tot["order shots handed out"] += len(execs)
        seen_ut = Counter()
        first = None
        for i in execs:
            e = ev[i]
            t, u = int(e["turn"]), e["unit"]
            seen_ut[(t, u)] += 1
            # the unit's decision right after the exec line is the one the order changed
            j = next((k for k in range(i + 1, len(ev)) if ev[k]["kind"] == "dec" and ev[k]["unit"] == u), None)
            dec = ev[j] if j is not None else None
            x = (dec or {}).get("x") or {}
            executed = bool(dec) and int(dec["act"]) in FIRE and (x.get("spent") or 0) > 0 and not x.get("walk")
            useful = executed and ((x.get("dmg") or 0) > 0 or (x.get("stunned") or 0) > 0 or (x.get("downed") or 0) > 0)
            # reactions by player units and casualties of the shooter until the side's next decision
            j = j + 1 if j is not None else i + 1
            react = 0
            for y in ev[j:]:
                if y["kind"] == "dec":
                    break
                if y["kind"] == "react" and int(y["unit"]) < 1000000:
                    react += 1
            died = any(y["kind"] == "cas" and y.get("victim") == u and int(y["turn"]) == t for y in ev[j:])
            tot["executed"] += executed
            tot["useful"] += useful
            tot["reactions after"] += react
            tot["shooter hp lost (that action)"] += x.get("hp_lost") or 0
            tot["shooter down later in its turn"] += died
            tot["TU of order shots"] += x.get("spent") or 0
            tot["dmg by order shots"] += x.get("dmg") or 0
            tot["downs by order shots"] += x.get("downed") or 0
            print(f"  exec t{t} u{u} n{e['n']} order{e['order']} target{e['target']} type{e['type']} cost{e['cost']}"
                  f" est{float(e['dmg']):.1f} d0act{e['d0act']} mode{e['mode']} -> act{dec['act'] if dec else '-'}"
                  f" spent{x.get('spent')} dmg{x.get('dmg')} stun{x.get('stunned')} down{x.get('downed')}"
                  f" hp_lost{x.get('hp_lost')} react{react} died{int(died)} {'EXEC' if executed else 'NOT-EXEC'}"
                  f"{' USEFUL' if useful else ''}")
            if first is None:
                first = (t, u, int(e["n"]))
        tot["unit-turns with >1 order shot"] += sum(1 for c in seen_ut.values() if c > 1)
        if first:
            t, u, n = first
            a, b = unit_turn(dev, t, u, n), unit_turn(ev, t, u, n)
            tot["first: D0 att"] += a["att"]
            tot["first: on att"] += b["att"]
            tot["first: D0 dmg"] += a["dmg"]
            tot["first: on dmg"] += b["dmg"]
            print(f"  first order shot t{t} u{u} n{n}, rest of that unit-turn  D0: attacks {a['att']} dmg {a['dmg']}"
                  f" spent {a['spent']} TU left {a['left']} acts {a['acts']}  |  on: attacks {b['att']} dmg {b['dmg']}"
                  f" spent {b['spent']} TU left {b['left']} acts {b['acts']}")
        up, mx = checks(ev)
        dup, dmx = checks(dev)
        tot["TU grew within a unit-turn (on)"] += up
        tot["TU grew within a unit-turn (D0)"] += dup
        print(f"  checks: TU grew within a unit-turn on {up} / D0 {dup}; max decisions per unit-turn on {mx} / D0 {dmx}")
    print("== totals")
    for k, v in tot.items():
        print(f"  {k:40s} {v}")


main()
