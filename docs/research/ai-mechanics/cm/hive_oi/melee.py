"""OPERATIONAL INTELLIGENCE, step 1: the only melee fighters that reach tanks: each decision of a Chryssalid on M3: turn, cell, TU, mode, act, destination, attacks in the engine list, nearest player's tank and its arc. Then every casualty of player's tanks. Read only.
Usage: melee.py <run> <type substring>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import SIDE, Battle, acts_of, moves_of, pos, side_code  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
b = Battle(sys.argv[1])
want = sys.argv[2]
ids = [u for u, k in b.units.items() if k.get("faction") == "1" and want in k.get("type", "")]
print("units", ids)
dead = {}
for c in b.casualties:
    if c.get("victim") in ids and c.get("how") == "dead":
        dead[c["victim"]] = (c.get("turn"), c.get("killer"), c.get("weapon"), c.get("dist"), c.get("hit"))
print("deaths", dead)
TANK = ("444", "448", "470", "545")
for u in ids:
    print("--", u)
    for d in b.decisions:
        if d["unit"] != u:
            continue
        p = pos(d["from"])
        st = b.state.get(int(d["turn"]), {})
        near = []
        for t in TANK:
            k = st.get(t)
            if k and int(k.get("status", 0)) < 6:
                q = pos(k["pos"])
                dist = max(abs(q[0] - p[0]), abs(q[1] - p[1]))
                code = side_code(p, q, int(k["dir"]))
                near.append((dist, t, SIDE.get(code, "under"), k.get("spotted")))
        near.sort()
        n = near[0] if near else None
        m = moves_of(d)
        att = [a for a in acts_of(d) if a.get("k") == "a"]
        e = d.get("exec") or {}
        print(f"  t{d['turn']} {d['from']} tu {d['tu']} hp {d['hp']} mode {d['mode']} act {d['act']} to {d['to']} src {d.get('src')} seen {d.get('seen')} moves {len(m)} acts {len(att)} near {n} spent {e.get('spent')} dmg {e.get('dmg')}")
print("-- player's casualties")
for c in b.casualties:
    if c.get("victim") in TANK + ("454", "503", "520", "543") and c.get("how") == "dead":
        print("  ", {k: c.get(k) for k in ("turn", "victim", "killer", "ktype", "weapon", "hit", "dist", "pos")})
