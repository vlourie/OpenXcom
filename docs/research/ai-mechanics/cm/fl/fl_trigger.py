"""TACTICAL FLANKING stage 1: how often the plan's trigger happens in the D0 battles and what D0 did then - logs only.

Trigger (hostile turn t, known player infantry E): at least 3 hostile units have, at their FIRST decision of the turn (so
from where they started, before anyone moved), an engine fire option at E - auto/snap/aimed, line of fire (lof=1), TU
cost within their TU ([AICAND] acts of that [AIREC]). E is infantry (its [AISTATE] weapon is not AUX_*) and known to the
hostile side (aistart spotted == 0). The same unit's lof at later decisions is not used (it may have moved).

Per trigger: the shooters, how many of them fired at E that turn in D0, damage to E, whether E went down that turn, and
how many of the shooters went down in turn t (own turn) - plus, for scale, the D0 turn's total fire at E by anyone.

  py -3.13 -I fl_trigger.py <out dir> <prefix>"""
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
FIRE = {7, 8, 9}
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
rows = []
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
                    dec.append((int(pend["turn"]), pend["unit"], pend["aim"], x.get("dmg") or 0))
            pend = None
        elif body.startswith("[AICASUALTY] "):
            s = dict(KV.findall(body))
            down.setdefault(s["victim"], (int(s["turn"]), s["side"]))
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
        fired = {u for (tt, u, aim, dm) in dec if tt == t and aim == e and u in g}
        dmg = sum(dm for (tt, u, aim, dm) in dec if tt == t and aim == e)
        allfire = sum(1 for (tt, u, aim, dm) in dec if tt == t and aim == e)
        other = sum(1 for (tt, u, aim, dm) in dec if tt == t and u in g and aim != e)
        e_down = e in down and down[e][0] == t and down[e][1] == "1"
        lost = sum(1 for u in g if u in down and down[u] == (t, "1"))
        rows.append((d.name, t, e, len(g), len(fired), other, allfire, dmg, e_down, lost))
print(f"triggers {len(rows)} in {len(set(r[0] for r in rows))} battles")
print("battle turn E | shooters fired_at_E shooters_attacked_other all_attacks_at_E dmg_E E_down | shooters_lost_own_turn")
for r in rows:
    print(f"{r[0]} t{r[1]} E={r[2]} | {r[3]} {r[4]} {r[5]} {r[6]} {r[7]} {int(r[8])} | {r[9]}")
n = len(rows) or 1
print(f"mean shooters {sum(r[3] for r in rows) / n:.2f}; mean fired at E {sum(r[4] for r in rows) / n:.2f}; "
      f"share of shooters that fired at E {sum(r[4] for r in rows) / max(1, sum(r[3] for r in rows)):.2f}; "
      f"E down in the turn {sum(r[8] for r in rows)}/{len(rows)}; triggers where <=1 shooter fired at E "
      f"{sum(1 for r in rows if r[4] <= 1)}")
