"""COORDINATED_ENGAGEMENT_V2, step 1 (GO Vitali 30.10): how many dangerous solo exposures of the enemy a commander could
reach at all - from logs already recorded (D0 control), no battles. Each condition is checked on the same unit-turn and the
funnel is the running intersection, never independent subtractions.

Exposed unit-turn (hostile U, turn t): no attack of its own, the last action ended in sight of the player (AIEXEC spotted).
  spotters  - player units whose sees list at the next player turn's start (pstart t+1) holds U (truth, only to name them);
  task      - the exposing action is a walk (act 2) of PATROL or COMBAT (ESCAPE, AMBUSH and attacks are left alone);
  able      - U at aistart t: hp >= 2/3, a ranged weapon (one any unit of the logs fired with: act 7/8/9);
  hidden    - where U stood before that walk nobody saw it (the previous action's spotted 0, or aistart seenby 0): a HOLD there
              keeps it out of sight;
  known     - a spotter of U was known to the hostile side when the turn began (in some hostile unit's sees at aistart t) -
              the danger of the path can be seen with the side's own knowledge (FAIR); otherwise it is the unknown ambush;
  ally      - another able hostile unit, alive at aistart t, within R tiles (2d) and dz <= 1 of that known spotter E;
  joint     - both can engage E legally: the ally sees E at aistart t or t+1 or attacked E's tile at t or t+1, and U's exposure
              tile is within 20 tiles of E (E saw U there).
Also the real turn t+1 of the control: did the ally and U attack with effect (the joint attack the HOLD would aim at).

  py -3.13 -I ce_reach.py <out dir> <prefix> [max turn t]"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
TMAX = int(sys.argv[3]) if len(sys.argv) > 3 else 999
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
SHOT = {7, 8, 9}
RADII = (12, 20)


def pos(t):
    return tuple(int(x) for x in t.strip("()").split(","))


def d2(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def parse(path):
    st = defaultdict(dict)  # (when, turn) -> unit -> state
    decs = []  # (decide dict, exec dict) of side 1 and 0, log order
    last = {}
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AISTATE] aistart ") or body.startswith("[AISTATE] pstart "):
                when = body.split(" ", 2)[1]
                k = dict(KV.findall(body))
                hp, hpmax = (int(x) for x in k["hp"].split("/"))
                st[(when, int(k["turn"]))][k["unit"]] = {
                    "f": k["faction"], "status": k["status"], "pos": pos(k["pos"]), "hp": hp, "hpmax": hpmax,
                    "weapon": k["weapon"], "sees": set() if k["sees"] == "-" else set(k["sees"].split(",")),
                    "seenby": int(k["seenby"])}
            elif body.startswith("[AIDECIDE] "):
                k = dict(KV.findall(body))
                last[k["unit"]] = k
            elif body.startswith("[AIEXEC] "):
                e = json.loads(body[len("[AIEXEC] "):])
                k = last.pop(str(e["unit"]), None)
                if k:
                    decs.append((k, e))
    return st, decs


ranged = set()
battles = []
for d in sorted(OUT.glob(f"{PRE}_*")):
    p = d / "openxcom.log.gz"
    if p.exists():
        st, decs = parse(p)
        battles.append((d.name, st, decs))
        for k, e in decs:
            if int(k["act"]) in SHOT:
                ranged.add(k.get("weapon", "-"))
ranged.discard("-")

funnel = Counter()
modes = Counter()
per_battle = Counter()
cases = []
for name, st, decs in battles:
    ut = defaultdict(list)
    attacks = defaultdict(list)  # turn -> (unit, target tile, effective)
    for k, e in decs:
        if k.get("side") != "1":
            continue
        t = int(k["turn"])
        ut[(t, k["unit"])].append((k, e))
        if int(k["act"]) in ATT:
            eff = e.get("dmg", 0) + e.get("stunned", 0) // 2 > 0 or e.get("downed", 0)
            attacks[t].append((k["unit"], pos(k["to"]) if k.get("to") else None, bool(eff)))
    for (t, u), seq in ut.items():
        if t > TMAX:
            continue
        if any(int(k["act"]) in ATT for k, _ in seq):
            continue
        k, e = seq[-1]
        if not e.get("spotted"):
            continue
        funnel["0 exposed"] += 1
        a0 = st.get(("aistart", t), {})
        p1 = st.get(("pstart", t + 1), {})
        me = a0.get(u)
        spot = [pid for pid, s in p1.items() if s["f"] == "0" and u in s["sees"]]
        modes[("patrol", "ambush", "combat", "escape")[int(k["mode"])] + "/" + k["act"] if k["mode"] in "0123" else k["mode"]] += 1
        if not (int(k["act"]) == 2 and k["mode"] in ("0", "2")):
            continue
        funnel["1 task patrol/combat walk"] += 1
        if not me or me["hp"] * 3 < me["hpmax"] * 2 or me["weapon"] not in ranged:
            continue
        funnel["2 able"] += 1
        prev = [x for x in seq[:-1] if "pos" in x[1]]
        hid = (prev[-1][1].get("spotted", 0) == 0) if prev else me["seenby"] == 0
        if not hid:
            continue
        funnel["3 hidden before the walk"] += 1
        knownE = {pid for s in a0.values() if s["f"] == "1" and s["status"] == "0" for pid in s["sees"]}
        ks = [pid for pid in spot if pid in knownE and pid in a0]
        if not ks:
            continue
        funnel["4 spotter known (FAIR)"] += 1
        epos = tuple(e["pos"]) if "pos" in e else me["pos"]
        a1 = st.get(("aistart", t + 1), {})
        hit = {r: False for r in RADII}
        join_real = False
        for E in ks:
            ep = a0[E]["pos"]
            if d2(epos, ep) > 20:
                continue
            for aid, s in a0.items():
                if aid == u or s["f"] != "1" or s["status"] != "0" or s["hp"] * 3 < s["hpmax"] * 2 or s["weapon"] not in ranged:
                    continue
                if abs(s["pos"][2] - ep[2]) > 1:
                    continue
                dist = d2(s["pos"], ep)
                can = E in s["sees"] or E in a1.get(aid, {}).get("sees", set()) or any(
                    au == aid and at == ep for tt in (t, t + 1) for au, at, _ in attacks[tt])
                if not can:
                    continue
                for r in RADII:
                    if dist <= r:
                        hit[r] = True
                if any(au == aid and eff for au, _, eff in attacks[t + 1]) and any(au == u and eff for au, _, eff in attacks[t + 1]):
                    join_real = True
        for r in RADII:
            if hit[r]:
                funnel[f"5 ally + joint possible (R={r})"] += 1
        if hit[RADII[0]]:
            per_battle[name] += 1
            cases.append((name, t, u))
            if join_real:
                funnel["6 R=12: control t+1 - U and the ally both useful"] += 1

print(f"series {PRE}, battles {len(battles)}, hostile turns t <= {TMAX}; ranged weapons {len(ranged)}")
for k in sorted(funnel):
    print(f"  {funnel[k]:5d}  {k}")
print("  exposed by last decision:", dict(modes.most_common()))
print("  candidates (R=12) per battle:", dict(sorted(per_battle.items())))
print("  first cases:", cases[:12])
