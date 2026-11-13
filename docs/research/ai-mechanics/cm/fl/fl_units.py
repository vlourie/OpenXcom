"""TACTICAL FLANKING stage 1: per hostile unit, what one hostile turn T of a D0 battle came to.

Start (aistart T): position, TU, health, weapon, how many player units it sees and how many see it. Then over the hostile
turn: decisions, walks, attacks executed, damage, the reactions it drew (as the reacted-at unit is not logged: reactions
fired by the player while this unit acted), where it ended and how many player units saw it there; whether it went down in
its own turn or in the next player turn, and to whom.

  py -3.13 -I fl_units.py <log.gz> <turn>"""
import gzip
import json
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
T = int(sys.argv[2])
u = defaultdict(lambda: defaultdict(float))
start, order = {}, []
pend, actor = None, None
for raw in gzip.open(sys.argv[1], "rt", encoding="utf-8", errors="replace"):
    body = raw.rstrip("\n").split("\t", 2)[-1]
    if body.startswith("[AISTATE] aistart "):
        d = dict(KV.findall(body))
        if int(d["turn"]) == T and d["faction"] == "1":
            start[d["unit"]] = d
    elif body.startswith("[AIDECIDE] "):
        d = dict(KV.findall(body.split(" hu=")[0]))
        pend = None
        if int(d["turn"]) == T and d["side"] == "1":
            pend = d
            actor = d["unit"]
            if actor not in order:
                order.append(actor)
            s = u[actor]
            s["dec"] += 1
            s["mode_" + d["mode"]] += 1
    elif body.startswith("[AIEXEC] ") and pend:
        x = json.loads(body[9:])
        if str(x["unit"]) == pend["unit"]:
            s = u[pend["unit"]]
            act, spent, walk = int(pend["act"]), x.get("spent") or 0, bool(x.get("walk"))
            s["walk"] += walk
            if act in ATT and spent > 0 and not walk:
                s["att"] += 1
                s["dmg"] += x.get("dmg") or 0
            s["end_pos"] = x.get("pos")
            s["end_spot"] = x.get("spotted")
            s["end_seen"] = x.get("seen")
            s["tu_left"] = x.get("tu")
        pend = None
    elif body.startswith("[AIEVENT] ") and " what=reaction " in body:
        d = dict(KV.findall(body))
        if int(d["turn"]) == T and d["side"] == "1" and actor:
            u[actor]["react"] += 1
    elif body.startswith("[AICASUALTY] "):
        d = dict(KV.findall(body))
        if d["vfaction"] == "1" and int(d["turn"]) in (T, T + 1):
            ph = "own turn" if int(d["turn"]) == T and d["side"] == "1" else f"turn {d['turn']}/{d['side']}"
            u[d["victim"]]["down"] = f"{d['how']} {ph} by {d['killer']}({d['kfaction']}) {d['weapon']}"

print(f"{'unit':>8} {'type':<22} {'start':<12} tu   hp  weapon              sees seen| dec walk att dmg react  end          spot down")
for k in order + [x for x in start if x not in order]:
    d = start.get(k, {})
    s = u[k]
    sees = 0 if d.get("sees", "-") == "-" else len(d["sees"].split(","))
    print(f"{k:>8} {d.get('type', '?')[:22]:<22} {d.get('pos', '?'):<12} {d.get('tu', '?'):>3} {d.get('hp', '?'):>6} "
          f"{d.get('weapon', '?')[:19]:<19} {sees:>4} {d.get('seenby', '?'):>4}| {s['dec']:3.0f} {s['walk']:4.0f} {s['att']:3.0f} "
          f"{s['dmg']:3.0f} {s['react']:5.0f}  {str(s.get('end_pos', '-')):<12} {str(s.get('end_spot', '-')):>4} {s.get('down', '')}")
