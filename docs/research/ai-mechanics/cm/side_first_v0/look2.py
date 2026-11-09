"""SIDE-FIRST COMBAT: details of one battle: own units killed by own side, throws, vetoes by reason, director's time per turn, attacks of one weapon. args: zip label [weapon]"""
import json
import sys
from collections import Counter

sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0])
from battle_stats import KV, lines

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
W = sys.argv[3] if len(sys.argv) > 3 else None
ls = lines(sys.argv[1], sys.argv[2])
print("-- own killed by own")
for s in ls:
    if s.startswith("[AICASUALTY] "):
        d = dict(KV.findall(s))
        if d.get("vfaction") == "1" and d.get("kfaction") in ("1", "-1"):
            print(" ", s[13:170])
print("-- throws")
pend = None
th = Counter()
for s in ls:
    if s.startswith("[AIDECIDE] "):
        d = dict(KV.findall(s.split(" hu=")[0]))
        pend = d
    elif s.startswith("[AIEXEC] ") and pend:
        x = json.loads(s[9:])
        d, pend = pend, None
        if d.get("side") == "1" and d.get("act") == "6":
            th[d.get("weapon")] += 1
            print(f"  turn {d['turn']} unit {d['unit']} from {d['from']} to {d['to']} {d['weapon']} tu {d['tu']} spent {x.get('spent')} dmg {x.get('dmg')} fdmg {x.get('fdmg')} down {x.get('downed')} fdown {x.get('fdowned')}")
print(" ", dict(th))
print("-- vetoes")
v = Counter()
pendA = {}
us = []
for s in ls:
    if not s.startswith("[AISCD] "):
        continue
    j = json.loads(s[8:])
    e = j.get("ev")
    if e == "veto":
        v[(j["w"], "eff0" if j["eff"] == 0 else "eff>0", "ff0" if j["ff"] == 0 else "ff>0", "blind" if j["target"] == -1 else "unit")] += 1
    elif e == "turn_end":
        us.append((j["turn"], j["us"] // 1000, j["calls"], j["lines"], j["over"], j["acts"], j["clears"]))
    elif W and e == "act" and j.get("w") == W:
        pendA[j["actor"]] = j
    elif W and e == "result" and j.get("actor") in pendA and j["kind"] == "A":
        p = pendA.pop(j["actor"])
        print(f"  {W} t{p['turn']} actor {p['actor']} target {p['target']} d {p['d']:.1f} acc {p['acc']:.0f} pHit {p['pHit']:.2f} eff {p['eff']:.1f} rep {p['rep']} shot t{p['t']} cost {p['cost']} -> spent {j['spent']} hit {j['tHit']} dmg {j['tDmg']} stun {j['tStun']} own {j['ownLoss']}")
for k, n in v.most_common(14):
    print(" ", k, n)
print("-- time per turn (turn, ms, calls, lines, over, acts, clears)")
print(" ", us[:12], "max", max(us, key=lambda x: x[1]) if us else None)
