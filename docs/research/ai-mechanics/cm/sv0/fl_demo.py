"""STRIKE-V0 demonstration: one order of a battle with the order on, unit by unit against the same battle of D0.

  py -3.13 -I fl_demo.py <out dir> <D0 label> <on label> [order id]   (default: the battle's first order)

The chain SIDE CONTEXT -> SHARED TARGET -> ORDER -> LEGAL SHOT -> REAL RESULT: the order line (who it went to, each one's shot
type, TU cost and expected damage by the rules), then for every member its whole turn in D0 and with the order (decisions as
act/TU spent/damage, attacks, damage, TU left), the order shots and what the engine did with them, the target's casualty."""
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
ACT = {0: "none", 2: "walk", 3: "turn", 7: "auto", 8: "snap", 9: "aimed", 6: "throw", 10: "hit", 12: "launch"}


def read(d):
    ev = []
    pend = None
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
        elif body.startswith("[AICASUALTY] "):
            s = dict(KV.findall(body))
            s["kind"] = "cas"
            ev.append(s)
    return ev


def turn_of(ev, t, u):
    rows, att, dmg, left = [], 0, 0, None
    for e in ev:
        if e["kind"] == "dec" and e.get("side") == "1" and int(e["turn"]) == t and e["unit"] == u:
            x = e.get("x") or {}
            a = int(e["act"])
            rows.append(f"{ACT.get(a, a)}/{x.get('spent')}/{x.get('dmg')}")
            left = x.get("tu", left)
            if a in ATT and (x.get("spent") or 0) > 0 and not x.get("walk"):
                att += 1
                dmg += x.get("dmg") or 0
    return att, dmg, left, rows


def main():
    out = Path(sys.argv[1])
    dev, ev = read(out / sys.argv[2]), read(out / sys.argv[3])
    orders = [e for e in ev if e["kind"] == "strike.order"]
    o = next((e for e in orders if len(sys.argv) > 4 and e["order"] == sys.argv[4]), orders[0] if orders else None)
    if not o:
        print("no order")
        return
    t = int(o["turn"])
    print(f"ORDER {o['order']} turn {t} by unit {o['by']}: target {o['target']} at {o['tpos']} hp {o['thp']},"
          f" {o['shooters']} units with a legal useful shot now, expected damage sum {float(o['sum']):.1f}")
    members = []
    for m in o["members"].split(","):
        u, typ, cost, dm = m.split(":")
        members.append(u)
        print(f"  member {u}: {ACT.get(int(typ), typ)} cost {cost} TU, expected {float(dm):.1f} hp per attack")
    for e in ev:
        if e["kind"] == "strike.join" and e["order"] == o["order"]:
            members.append(e["unit"])
            print(f"  joined later: {e['unit']}")
    for e in ev:
        if e["kind"] == "strike.exec" and e["order"] == o["order"]:
            print(f"  ORDER SHOT unit {e['unit']} n{e['n']}: {ACT.get(int(e['type']), e['type'])} at {e['target']} (hp then"
                  f" {e['thp']}) instead of {ACT.get(int(e['d0act']), e['d0act'])} (mode {e['mode']}), TU {e['tu']}")
        if e["kind"] == "strike.close" and e["order"] == o["order"]:
            print(f"  order closed: {e['why']}")
    print(f"members' turn {t} (decisions act/TU spent/damage):")
    tot = [0, 0, 0, 0]
    for u in members:
        a = turn_of(dev, t, u)
        b = turn_of(ev, t, u)
        tot[0] += a[0]
        tot[1] += a[1]
        tot[2] += b[0]
        tot[3] += b[1]
        print(f"  {u}  D0: attacks {a[0]} dmg {a[1]} TU left {a[2]} [{' '.join(a[3])}]")
        print(f"  {' ' * len(u)}  on: attacks {b[0]} dmg {b[1]} TU left {b[2]} [{' '.join(b[3])}]")
    print(f"  members together  D0: attacks {tot[0]} dmg {tot[1]}  |  on: attacks {tot[2]} dmg {tot[3]}")
    for name, lst in (("D0", dev), ("on", ev)):
        cs = [e for e in lst if e["kind"] == "cas" and e.get("victim") == o["target"]]
        print(f"  target {o['target']} in {name}: " + (", ".join(f"{c['how']} turn {c['turn']} by {c['killer']}" for c in cs)
                                                  if cs else "not down"))


main()
