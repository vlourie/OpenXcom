"""MISSION-LEVEL TACTICS STAGE 2, step 1-2, no battles: from one L4 log - every building (modules by level and armor, target nodes, how far the nearest fighters start),
every hostile loss (where, by whom), the group's fighters' routes turn by turn, and the player's units seen in the first turn.

  py -3.13 -I s2_facts.py <battle dir>"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")


def xyz(s):
    return tuple(int(v) for v in s.strip("()").split(","))


rows = []
with gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
    for raw in f:
        rows.append(raw.rstrip("\n").split("\t", 2)[-1])

facs, tiles, nodes, units, cas, decs = {}, defaultdict(list), defaultdict(list), {}, [], []
pend = None
plans = []
for s in rows:
    if s.startswith("[AIMISSION] what=fac"):
        d = dict(KV.findall(s))
        facs[d["at"]] = d["type"].replace("STR_", "")
    elif s.startswith("[AIMISSION] what=mtile"):
        d = dict(KV.findall(s))
        p = xyz(d["at"])
        tiles[f"{p[0] // 10},{p[1] // 10}"].append((p, int(d["armor"])))
    elif s.startswith("[AIMISSION] what=node"):
        d = dict(KV.findall(s))
        nodes[d["grid"]].append(xyz(d["at"]))
    elif s.startswith("[AIMISSION] what=unit"):
        d = dict(KV.findall(s))
        units[d["id"]] = d
    elif s.startswith("[AIMISSION] what=plan"):
        plans.append(dict(KV.findall(s)))
    elif s.startswith("[AICASUALTY] "):
        cas.append(dict(KV.findall(s)))
    elif s.startswith("[AIDECIDE] "):
        pend = dict(KV.findall(s.split(" hu=")[0]))
    elif s.startswith("[AIEXEC] ") and pend:
        x = json.loads(s[9:])
        if str(x["unit"]) == pend["unit"]:
            pend["spent"] = x.get("spent") or 0
            pend["end"] = tuple(x.get("pos") or ())
            pend["xdmg"] = x.get("dmg") or 0
            pend["hp_lost"] = x.get("hp_lost") or 0
            pend["trail"] = (x.get("trail") or [""])[-1][:70]
            decs.append(pend)
        pend = None

fighters = {u: d for u, d in units.items() if d["protocol"] == "1"}
print("protocol fighters:", len(fighters), Counter(d["weapon"] for d in fighters.values()), "by reach", Counter(round(1.5 * float(d["power"]) * float(d["totile"])) for d in fighters.values()))
print("\n--- buildings: cell fac | modules | by z | armor range | breakable by rifle (60) / pistol (39) | nodes | nearest fighters' start distance")
for c in sorted(tiles, key=lambda k: len(tiles[k])):
    tl = tiles[c]
    zs = Counter(p[2] for p, _ in tl)
    arm = [a for _, a in tl]
    cx, cy = [int(v) * 10 + 5 for v in c.split(",")]
    near = sorted(round(((xyz(d["at"])[0] - cx) ** 2 + (xyz(d["at"])[1] - cy) ** 2) ** 0.5) for d in fighters.values())[:3]
    print(f"{c:4} {facs.get(c, '- (not a corner)'):30} {len(tl):3} z{dict(sorted(zs.items()))} a{min(arm)}-{max(arm)} br{sum(a <= 60 for a in arm)}/{sum(a <= 39 for a in arm)} nodes{len(nodes.get(c, []))} near{near}")
print("cells without modules:", sorted(c for c in facs if c not in tiles), [facs[c] for c in sorted(facs) if c not in tiles])

print("\n--- hostile losses: turn victim type how pos killer side weapon dist seenby")
hc = Counter()
for d in cas:
    if d.get("vfaction") == "1":
        k = "friendly" if d.get("kfaction") == "1" else "player" if d.get("kfaction") == "0" else "other"
        hc[(int(d["turn"]), k)] += 1
        print(f" t{d['turn']} {d['victim']} {d['type'].replace('STR_', '')} {d['how']} {d['pos']} {k} {d.get('killer')} {d.get('weapon')} d{d.get('dist')} seenby{d.get('seenby')} {'FIGHTER' if d['victim'] in fighters else ''}")
print("losses by turn and killer:", sorted(hc.items()))
print("\n--- plans:")
for p in plans:
    print(f" t{p['turn']} cell {p['cell']} {p['fighters']}")
print("\n--- fighters' decisions: unit turn from > to mode act tu spent end | last trail")
named = set()
for p in plans:
    for f in p["fighters"].split(";"):
        named.add(f.split(">")[0])
for u in sorted(named):
    print(f"{u} {units.get(u, {}).get('weapon', 'not in the dump: out before the side moved')} start {units.get(u, {}).get('at')}")
    for d in decs:
        if d["unit"] == u:
            print(f"  t{d['turn']} {d['from']} > {d['to']} m{d['mode']} a{d['act']} tu{d['tu']} sp{d['spent']} end{d['end']} dmg{d['xdmg']} lost{d['hp_lost']} | {d['trail']}")
print("\n--- player's positions at their first decision of turn 1 (analysis only, the plan must not read them):")
seen = {}
for d in decs:
    if d["side"] == "0" and d["turn"] == "1" and d["unit"] not in seen:
        seen[d["unit"]] = xyz(d["from"])
print(len(seen), Counter(f"{p[0] // 10},{p[1] // 10}" for p in seen.values()).most_common(20))
print("hostile starts by cell:", Counter(f"{xyz(d['at'])[0] // 10},{xyz(d['at'])[1] // 10}" for d in fighters.values()).most_common())
print("hostile fighter starts:", sorted((u, d["at"]) for u, d in fighters.items()))
