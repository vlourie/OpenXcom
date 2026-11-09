"""TACTICAL AI 2.0, scenario analysis (logs only): the focus-fire trigger of fl_trigger.py counted once per unit-turn.

A hostile unit-turn (t, u) is a 'possible shooter' when at its FIRST decision of t the engine offers it a fire option
(auto/snap/aimed, lof 1, TU within its TU) at a known player infantry that at least two other hostiles can also shoot
from their start cells (the fl_trigger.py trigger). Per such unit-turn: did it attack anyone in t (dmg > 0 or not),
the AI mode of its first decision (0 patrol, 1 ambush, 2 combat, 3 escape), whether it went down in its own turn t,
and the 'capable' proxy of fl_focus.py (its weapon hurt player infantry somewhere in this battle).

  py -3.13 -I fl_focus2.py <out dir> <prefix>"""
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
MODE = {"0": "patrol", "1": "ambush", "2": "combat", "3": "escape"}
cls = Counter()
by_mode = defaultdict(Counter)
lost = Counter()
for d in sorted(Path(sys.argv[1]).glob(f"{sys.argv[2]}_*")):
    snap = defaultdict(dict)
    acts, first, mode1 = {}, {}, {}
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
            if pend.get("side") == "1":
                mode1.setdefault((int(pend["turn"]), pend["unit"]), pend.get("mode", "?"))
        elif body.startswith("[AIEXEC] ") and pend:
            x = json.loads(body[9:])
            if str(x["unit"]) == pend["unit"] and pend["side"] == "1":
                if int(pend["act"]) in ATT and (x.get("spent") or 0) > 0 and not x.get("walk"):
                    dec.append((int(pend["turn"]), pend["unit"], pend["aim"], x.get("dmg") or 0, pend.get("weapon", "-")))
            pend = None
        elif body.startswith("[AICASUALTY] "):
            s = dict(KV.findall(body))
            down.setdefault(s["victim"], (int(s["turn"]), s["side"]))
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
    units = set()
    for (t, e), g in shooters.items():
        if len(g) >= 3:
            units |= {(t, u) for u in g}
    for (t, u) in units:
        mine = [dm for (tt, uu, aim, dm, w) in dec if tt == t and uu == u]
        c = ("hit" if any(mine) else "miss") if mine else "none"
        cap = snap[t][u].get("weapon", "-") in hurt
        key = c + ("_cap" if cap else "")
        cls[key] += 1
        by_mode[MODE.get(mode1.get((t, u)), "?")][c] += 1
        if cap:
            by_mode[MODE.get(mode1.get((t, u)), "?")][c + "_cap"] += 1
        if u in down and down[u] == (t, "1"):
            lost[c] += 1
n = sum(cls.values())
print(f"possible-shooter unit-turns {n}")
for c in ("hit", "miss", "none"):
    a, b = cls[c] + cls[c + "_cap"], cls[c + "_cap"]
    print(f"  {c:5s} {a:5d} ({100 * a / n:4.1f}%)  of them with a 'capable' weapon {b:5d}; went down in own turn {lost[c]}")
print("first-decision mode x outcome:")
for m, cc in sorted(by_mode.items()):
    print(f"  {m:7s} " + " ".join(f"{c}={cc[c]} (capable {cc[c + '_cap']})" for c in ("hit", "miss", "none")))
