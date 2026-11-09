"""HIVE COMBAT INTENT V0: the four arms over the same turns: M6 s1 and M3 s1 ended sooner in the CI runs, so the totals up to 8 are not comparable. Joint attacks (two or more soldiers on one player unit in a turn, by the attack's tile), damage and losses up to the last turn of the CI run. Read only."""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
import json  # noqa: E402

ROWS = [("M6 s1", 5, ("cc3_CO_M6_s1", "cc8_CC_M6_s1", "ra1_AN_M6_s1", "ci5_IA_M6_s1")), ("M6 s2", 8, ("scpa_D_M6_s2", "cc5_CC_M6_s2", "ra2_AN_M6_s2", "ci6_IA_M6_s2")), ("M3 s1", 6, ("scpa_D_M3_s1", "cc6_CV_M3_s1", "ra3_AV_M3_s1", "ci7_IV_M3_s1"))]


def is_player(a):
    return a.isdigit() and int(a) < 1000000


for name, last, runs in ROWS:
    print("=====", name, "turns up to", last)
    for run in runs:
        L = read(run)
        dec = None
        recs = {}
        attacks = []
        ai = pl = 0
        for s in L:
            if s.startswith("[AIDECIDE]"):
                k = kv(s)
                dec = k if k["side"] == "1" and int(k["turn"]) <= last and int(k["act"]) in ATT else None
            elif s.startswith("[AIREC]") and dec is not None:
                try:
                    recs[json.loads(s[8:])["rec"]] = dec
                except ValueError:
                    pass
                dec = None
            elif s.startswith("[AIEXEC]"):
                try:
                    j = json.loads(s[9:])
                except ValueError:
                    continue
                if j["rec"] in recs:
                    attacks.append((recs[j["rec"]], j))
            elif s.startswith("[AICASUALTY]"):
                k = kv(s)
                # how=stun repeats for one unit turn after turn (60-72 lines for one unit on M3): only the dead are counted
                if int(k["turn"]) <= last and k.get("how") == "dead":
                    if k.get("vfaction") == "1":
                        ai += 1
                    elif is_player(k.get("victim", "x")):
                        pl += 1
        tally = defaultdict(lambda: defaultdict(int))
        for d, _ in attacks:
            if d["aim"] != "-1":
                tally[(d["turn"], d["to"])][d["aim"]] += 1
        who = defaultdict(set)
        dmg = defaultdict(int)
        for d, j in attacks:
            t = tally.get((d["turn"], d["to"]))
            aim = max(t, key=t.get) if t else d["aim"]
            who[(d["turn"], aim)].add(d["unit"])
            dmg[(d["turn"], aim)] += j.get("dmg", 0)
        joint = [k for k, v in who.items() if len(v) >= 2 and is_player(k[1])]
        print(f"  {run:14s} attacks {len(attacks):4d} with damage {sum(1 for _, j in attacks if j.get('dmg', 0) > 0):3d} dmg {sum(j.get('dmg', 0) for _, j in attacks):5d} | joint targets {len(joint):3d} fighters {sum(len(who[k]) for k in joint):3d} with damage {sum(1 for k in joint if dmg[k] > 0):3d} dmg {sum(dmg[k] for k in joint):5d} | losses AI {ai:3d} players {pl:2d}")
