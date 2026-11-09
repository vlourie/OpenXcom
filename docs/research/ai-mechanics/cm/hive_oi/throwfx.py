"""OPERATIONAL INTELLIGENCE, step 1: what the AI's grenades did: for each AI turn with throws, HP of each player's unit at aistart(t) and pstart(t+1), direct damage logged by [AIEXEC] for that unit and turn. Damage not explained by direct hits is due to blast or reaction side effects. Also the same table for all turns, to see how much of the side's total damage comes unexplained. Read only.
Usage: throwfx.py <run>"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import Battle, kv, pos  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
b = Battle(sys.argv[1])
pstart = defaultdict(dict)
for s in b.L:
    if s.startswith("[AISTATE] pstart"):
        k = kv(s)
        pstart[int(k["turn"])][k["unit"]] = k


def hp(k):
    return int(k["hp"].split("/")[0])


def stun(k):
    return int(str(k.get("stun", "0")).split("/")[0])


direct = defaultdict(lambda: defaultdict(int))
for d in b.attacks:
    if int(d["act"]) != 6:
        e = d.get("exec") or {}
        direct[int(d["turn"])][d["target"]] += e.get("dmg", 0)
throws = defaultdict(list)
for d in b.attacks:
    if int(d["act"]) == 6:
        throws[int(d["turn"])].append(d)
print("====", b.run)
tot_all = tot_dir = 0
turns = sorted(b.state)
for t in turns:
    lines = []
    for u, k in sorted(b.state[t].items()):
        if k.get("faction") != "0":
            continue
        n = pstart.get(t + 1, {}).get(u)
        if not n:
            continue
        lost = hp(k) - hp(n)
        tot_all += max(lost, 0)
        tot_dir += direct[t].get(u, 0)
        if lost or stun(k) != stun(n):
            lines.append(f"   {u} hp {hp(k)}->{hp(n)} (lost {lost}) stun {stun(k)}->{stun(n)} direct {direct[t].get(u, 0)} pos {k['pos']}")
    if t in throws:
        print(f"-- turn {t}: {len(throws[t])} throws: " + " ".join(f"{d['unit']}>{d['to']}" for d in throws[t]))
        print("\n".join(lines) if lines else "   no HP or stun change")
print("all turns: HP lost by player's units", tot_all, "logged as direct", tot_dir)
