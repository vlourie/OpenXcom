"""TACTICAL FLANKING stage 1: screen the D0 battles for an episode the task asks for - only the probe logs, no new battles.

Per battle and hostile turn t, per player unit E the hostile side has spotted at the start of the turn (AISTATE aistart:
the player unit's spotted == 0 - the side's honest knowledge): the hostile group around E = able hostile units (health
>= 2/3, not a turret) within R tiles and +-1 level of E holding a weapon that did damage to a player unit somewhere in this
battle (a "useful" weapon). Then over turn t and the player turn t+1: the group's attacks at E executed and with damage,
damage to E, the group's units down (in turn t and in turn t+1), their walks that ended spotted with no attack that turn.

A row is an episode candidate when the group has 3-4 units with useful weapons and the turn went badly for it (>= 2 down
or no damage at E). Sorted by the group's losses.

  py -3.13 -I fl_screen.py <out dir> <prefix> [R]"""
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
R = float(sys.argv[3]) if len(sys.argv) > 3 else 15
P = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")


def pos(s):
    m = P.match(s)
    return tuple(int(v) for v in m.groups())


rows = []
for d in sorted(Path(sys.argv[1]).glob(f"{sys.argv[2]}_*")):
    snap = defaultdict(dict)     # turn -> unit -> state (aistart)
    dec = []                     # (turn, side, unit, act, aim, weapon, exec)
    down = {}                    # unit -> (turn, side)
    useful = set()
    pend = None
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        body = raw.rstrip("\n").split("\t", 2)[-1]
        if body.startswith("[AISTATE] aistart "):
            s = dict(KV.findall(body))
            snap[int(s["turn"])][s["unit"]] = s
        elif body.startswith("[AIDECIDE] "):
            s = dict(KV.findall(body.split(" hu=")[0]))
            pend = s
        elif body.startswith("[AIEXEC] ") and pend:
            x = json.loads(body[9:])
            if str(x["unit"]) == pend["unit"]:
                act = int(pend["act"])
                att = act in ATT and (x.get("spent") or 0) > 0 and not x.get("walk")
                dec.append((int(pend["turn"]), pend["side"], pend["unit"], att, pend["aim"], pend["weapon"],
                            x.get("dmg") or 0, bool(x.get("walk")), x.get("spotted") or 0))
                if att and pend["side"] == "1" and (x.get("dmg") or 0) > 0:
                    useful.add(pend["weapon"])
            pend = None
        elif body.startswith("[AICASUALTY] "):
            s = dict(KV.findall(body))
            down.setdefault(s["victim"], (int(s["turn"]), s["side"]))
    for t in sorted(snap):
        if t > 20:
            break
        units = snap[t]
        hostile = {k: v for k, v in units.items() if v["faction"] == "1"}
        for e, ev in units.items():
            if ev["faction"] != "0" or ev["spotted"] != "0" or ev["status"] in ("6", "7"):
                continue
            ep = pos(ev["pos"])
            grp = []
            for k, v in hostile.items():
                hp, hmax = (int(x) for x in v["hp"].split("/"))
                if "TURRET" in v["type"] or hp * 3 < hmax * 2 or v["status"] == "7":
                    continue
                hands = [h.split(":")[0] for h in (v.get("rh", "-"), v.get("lh", "-")) if h != "-"]
                if not any(h in useful for h in hands + [v["weapon"]]):
                    continue
                p = pos(v["pos"])
                if abs(p[2] - ep[2]) <= 1 and ((p[0] - ep[0]) ** 2 + (p[1] - ep[1]) ** 2) ** 0.5 <= R:
                    grp.append(k)
            if not 3 <= len(grp) <= 4:
                continue
            g = set(grp)
            att_e = [x for x in dec if x[0] == t and x[1] == "1" and x[2] in g and x[3] and x[4] == e]
            att_any = [x for x in dec if x[0] == t and x[1] == "1" and x[2] in g and x[3]]
            lost = [k for k in grp if k in down and down[k][0] in (t, t + 1) and not (down[k][0] == t + 1 and down[k][1] == "1")]
            exposed = {x[2] for x in dec if x[0] == t and x[1] == "1" and x[2] in g and x[7] and x[8] > 0} - {x[2] for x in att_any}
            rows.append((len(lost), d.name, t, e, ev["type"], ev["pos"], len(grp), ",".join(grp), len(att_e),
                         sum(1 for x in att_e if x[6] > 0), sum(x[6] for x in att_e), len(att_any),
                         sum(1 for x in att_any if x[6] > 0), len(exposed), ",".join(sorted(lost))))
rows.sort(key=lambda r: (-r[0], -r[13], r[1], r[2]))
print(f"R={R}; rows {len(rows)} (group of 3-4 able hostile units with a useful weapon around a known player unit)")
print("lost battle turn E type pos | grp members | attE hitE dmgE attAll hitAll exposed-no-attack | lost units")
for r in rows[:60]:
    print(f"{r[0]} {r[1]} t{r[2]} E={r[3]} {r[4][:12]} {r[5]} | {r[6]} {r[7]} | {r[8]} {r[9]} {r[10]} {r[11]} {r[12]} {r[13]} | {r[14]}")
