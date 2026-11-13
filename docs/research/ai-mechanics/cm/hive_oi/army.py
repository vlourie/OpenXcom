"""OPERATIONAL INTELLIGENCE, step 1: what the AI side and the player really have in one battle, from the D0 log. Read only.
Usage: army.py <run>"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import ATT, Battle, acts_of  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ACT = {6: "throw", 7: "auto", 8: "snap", 9: "aimed", 10: "melee", 11: "?"}
b = Battle(sys.argv[1])
print("=====", b.run, "seed", b.seed, "result", {k: b.result.get(k) for k in ("mission", "how", "turn", "pdead", "hdead", "hostile", "player", "pattacks", "hattacks")} if b.result else None)
print("-- player's units (first state)")
for u, k in sorted(b.units.items(), key=lambda x: int(x[0])):
    if k.get("faction") == "0":
        print(f"  {u} {k.get('type')} tu={k.get('tumax')} hp={k.get('hp')} morale={k.get('morale')} rh={k.get('rh')} lh={k.get('lh')} spare={k.get('spare')} ammo={k.get('ammo')} pos={k.get('pos')}")
print("-- AI side by type")
by = defaultdict(list)
for u, k in b.units.items():
    if k.get("faction") == "1":
        by[k.get("type")].append(k)
for t, v in sorted(by.items(), key=lambda x: -len(x[1])):
    w = Counter(f"{x.get('rh')}|{x.get('lh')}" for x in v)
    print(f"  {t} n={len(v)} tu={sorted(set(x.get('tumax') for x in v))} hp={sorted(set(x.get('hp').split('/')[-1] for x in v))} hands={dict(w)}")
print("-- what each AI fighter could do, from the engine's own list of actions at its first decision")
first = {}
for d in b.decisions:
    first.setdefault(d["unit"], d)
opts = Counter()
carriers = defaultdict(set)
cost = defaultdict(set)
for u, d in first.items():
    seen = set()
    for a in acts_of(d):
        if a.get("k") == "a":
            key = (a["w"], ACT.get(a["t"], a["t"]))
            seen.add(key)
            cost[key].add(a["tu"])
    for key in seen:
        opts[key] += 1
        carriers[key].add(u)
for key, n in opts.most_common():
    print(f"  {key[0]:32s} {key[1]:6s} fighters={n:3d} tu={sorted(cost[key])[:6]}")
print("-- what the AI side did")
done = Counter()
dmg = Counter()
hit = Counter()
for d in b.attacks:
    key = (d["weapon"] if int(d["act"]) != 6 else "THROW", int(d["act"]))
    done[key] += 1
    e = d.get("exec") or {}
    dmg[key] += e.get("dmg", 0)
    hit[key] += e.get("dmg", 0) > 0
for key, n in done.most_common():
    print(f"  {key[0]:32s} act {key[1]:3d} n={n:4d} with_damage={hit[key]:3d} dmg={dmg[key]}")
print("-- who killed and stunned player's units, first line per victim and how")
seen = set()
for c in b.casualties:
    if not c.get("victim", "x").startswith("1000") and (c["victim"], c.get("how")) not in seen and len(c["victim"]) < 7:
        seen.add((c["victim"], c.get("how")))
        print(f"  turn {c.get('turn')} {c['victim']} {c.get('how')} by {c.get('killer')} ({c.get('ktype')}) {c.get('weapon')} side={c.get('hit')} dist={c.get('dist')}")
print("-- AI losses by turn, killer's weapon")
lost = Counter()
for c in b.casualties:
    if c.get("vfaction") == "1" and c.get("how") == "dead":
        lost[c.get("weapon")] += 1
print("  ", lost.most_common(12))
