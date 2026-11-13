"""TACTICAL AI 2.0, scenario analysis (logs only, no battles): in the focus-fire trigger turns of fl_trigger.py, what did
the possible shooters at E do instead, and was their weapon able to hurt player infantry in that battle at all.

Trigger as in fl_trigger.py: hostile turn t, known player infantry E (aistart spotted 0, weapon not AUX_*), at least 3
hostile units with an engine fire option at E (auto/snap/aimed, lof 1, TU within their TU) at their FIRST decision of t.

Per possible shooter in a trigger, the turn's own actions ([AIDECIDE] side 1 + [AIEXEC], TU spent, not a walk):
  at_E_hit / at_E_miss  - attacked E, the action's dmg > 0 / == 0
  other_hit / other_miss - attacked someone else (no attack at E), dmg > 0 / == 0
  none                  - no attack this turn (walked, patrolled, ran or stood)
'capable' (a proxy, not a rule calculation): the shooter's aistart weapon did dmg > 0 to anyone in an attack on player
infantry somewhere in this battle (any unit with that weapon). The log has no armour or damage roll, so 'capable' only
says the weapon type hurt the player's infantry here once; it is an upper bound on what a rule check would allow.

  py -3.13 -I fl_focus.py <out dir> <prefix>"""
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
tot = Counter()
cap_tot = Counter()
trig = 0
battles = set()
down_e = 0
e_dmg_turns = 0
per_battle = Counter()
for d in sorted(Path(sys.argv[1]).glob(f"{sys.argv[2]}_*")):
    snap = defaultdict(dict)
    acts, first = {}, {}
    dec = []
    down = {}
    pend = None
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        body = raw.rstrip("\n").split("\t", 2)[-1]
        if body.startswith("[AISTATE] aistart "):
            s = dict(KV.findall(body))
            snap[int(s["turn"])][s["unit"]] = s
        elif body.startswith("[AICAND] acts="):
            acts[body.split()[1].split("=")[1]] = body.split(" list=", 1)[1]
        elif body.startswith("[AIREC] "):
            r = json.loads(body[8:])
            k = (r["turn"], str(r["unit"]))
            if k not in first:
                first[k] = (r["state"]["tu"], r["cand"]["acts"])
        elif body.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(body.split(" hu=")[0]))
        elif body.startswith("[AIEXEC] ") and pend:
            x = json.loads(body[9:])
            if str(x["unit"]) == pend["unit"] and pend["side"] == "1":
                if int(pend["act"]) in ATT and (x.get("spent") or 0) > 0 and not x.get("walk"):
                    dec.append((int(pend["turn"]), pend["unit"], pend["aim"], x.get("dmg") or 0, pend.get("weapon", "-")))
            pend = None
        elif body.startswith("[AICASUALTY] "):
            s = dict(KV.findall(body))
            down.setdefault(s["victim"], (int(s["turn"]), s["side"]))
    # weapons that hurt player infantry in this battle (target known as infantry from any aistart of that turn)
    hurt = set()
    for (t, u, aim, dm, w) in dec:
        tv = snap.get(t, {}).get(aim)
        if dm > 0 and tv and tv["faction"] == "0" and not tv["weapon"].startswith("AUX_"):
            hurt.add(w)
    shooters = defaultdict(set)
    for (t, u), (tu, h) in first.items():
        if t not in snap or snap[t].get(u, {}).get("faction") != "1":
            continue
        a = acts.get(h, "[]")
        for x in (json.loads(a) if a.startswith("[") else []):
            e = str(x.get("u"))
            ev = snap[t].get(e)
            if (x.get("k") == "a" and x.get("t") in FIRE and x.get("lof") == 1 and (x.get("tu") or 999) <= tu and ev
                    and ev["faction"] == "0" and ev["spotted"] == "0" and not ev["weapon"].startswith("AUX_")):
                shooters[(t, e)].add(u)
    for (t, e), g in sorted(shooters.items()):
        if len(g) < 3:
            continue
        trig += 1
        battles.add(d.name)
        per_battle[d.name.split("_", 2)[2]] += 1
        if e in down and down[e][0] == t and down[e][1] == "1":
            down_e += 1
        if any(dm > 0 for (tt, u, aim, dm, w) in dec if tt == t and aim == e):
            e_dmg_turns += 1
        for u in g:
            mine = [(aim, dm) for (tt, uu, aim, dm, w) in dec if tt == t and uu == u]
            atE = [dm for (aim, dm) in mine if aim == e]
            oth = [dm for (aim, dm) in mine if aim != e]
            if atE:
                c = "at_E_hit" if any(atE) else "at_E_miss"
            elif oth:
                c = "other_hit" if any(oth) else "other_miss"
            else:
                c = "none"
            tot[c] += 1
            if snap[t][u].get("weapon", "-") in hurt:
                cap_tot[c] += 1
print(f"triggers {trig} in {len(battles)} battles; E down in the turn {down_e}; E damaged by anyone in the turn {e_dmg_turns}")
print("per scenario:", " ".join(f"{k}:{v}" for k, v in sorted(per_battle.items())))
order = ["at_E_hit", "at_E_miss", "other_hit", "other_miss", "none"]
n = sum(tot.values()) or 1
m = sum(cap_tot.values()) or 1
print(f"possible shooters {sum(tot.values())}; with a 'capable' weapon {sum(cap_tot.values())}")
for c in order:
    print(f"  {c:11s} all {tot[c]:5d} ({100 * tot[c] / n:4.1f}%)   capable {cap_tot[c]:5d} ({100 * cap_tot[c] / m:4.1f}%)")
