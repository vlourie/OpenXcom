"""SIDE_TURN_ACTION_SCHEDULER stage 3, step 1: a battle turn by turn - per side turn the mover's decisions, executed walks and
attacks (the opportunities for reaction fire), the reactions of the other side (reactions per opportunity), the casualties by
faction, and the time units the hostile units keep at the end of their own turn (what they can react with in the player's).

  py -3.13 -I sc_turns.py <out dir> <label> [<label> ...]"""
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(sys.argv[1])
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}


def hostile(uid):
    return int(uid) >= 1000000


for label in sys.argv[2:]:
    st = defaultdict(lambda: defaultdict(int))
    keep = defaultdict(dict)  # (turn) -> hostile unit -> TU after its last execution in its own turn
    pend = None
    with gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] "):
                d = dict(KV.findall(body.split(" hu=")[0]))
                key = (int(d["turn"]), int(d["side"]))
                st[key]["dec"] += 1
                pend = (key, d)
            elif body.startswith("[AIEXEC] ") and pend:
                x = json.loads(body[9:])
                key, d = pend
                if str(x["unit"]) != d["unit"]:
                    continue
                if x["walk"]:
                    st[key]["walk"] += 1
                if int(d["act"]) in ATT and not x["walk"] and (x["spent"] or 0) > 0:
                    st[key]["att"] += 1
                if key[1] == 1:
                    keep[key[0]][d["unit"]] = x["tu"]
                pend = None
            elif body.startswith("[AIEVENT] ") and " what=reaction " in body:
                e = dict(KV.findall(body))
                key = (int(e["turn"]), int(e["side"]))
                st[key]["reac_h" if hostile(e["unit"]) else "reac_p"] += 1
            elif body.startswith("[AICASUALTY] "):
                e = dict(KV.findall(body))
                key = (int(e["turn"]), int(e["side"]))
                st[key]["dead_h" if e["vfaction"] == "1" else "dead_p" if e["vfaction"] == "0" else "dead_n"] += 1
    print(f"== {label}")
    print("  turn side   dec walk att | reactions by the other side (per 10 walks+attacks) | casualties P/H | hostile TU kept: units, mean")
    for key in sorted(st):
        if key[1] not in (0, 1):
            continue
        s = st[key]
        opp = s["walk"] + s["att"]
        r = s["reac_h"] if key[1] == 0 else s["reac_p"]
        kp = keep.get(key[0], {}) if key[1] == 1 else {}
        kt = f"{len(kp)}, {sum(kp.values()) / len(kp):.0f}" if kp else "-"
        print(f"  {key[0]:>4} {'P' if key[1] == 0 else 'H'}   {s['dec']:>5} {s['walk']:>4} {s['att']:>3} | {r:>4} ({10 * r / max(opp, 1):.2f}) "
              f"| {s['dead_p']}/{s['dead_h']} | {kt}")
