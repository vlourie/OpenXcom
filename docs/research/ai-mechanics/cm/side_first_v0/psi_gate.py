"""SIDE-FIRST COMBAT V0.1: the L8 gate. Psi and capture by seed: chosen, carried out (time units spent), what they did to the target by the log; psi actions per battle turn; morale, stun and wounds the player lost in hostile turns.
args: zip:prefix:arm ... [--mission=L8]"""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
PSI = {"13": "psi", "14": "mc"}


def battle(z, label, show=0):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    c = Counter()
    pend = None
    start = {}
    fac = {}
    psi_on = []
    turns = 0
    for s in raw:
        s = s.split("\t")[-1]
        if s.startswith("[AISTATE] "):
            kind = s.split(" ", 2)[1]
            d = dict(KV.findall(s))
            if "unit" not in d:
                continue
            u = d["unit"]
            was = fac.get(u)
            fac[u] = d.get("faction")
            if was == "0" and d.get("faction") == "1":
                c["faction_0_to_1"] += 1
            if d.get("faction") != "0" or "hp" not in d:
                continue
            state = dict(morale=int(d["morale"]), stun=int(d["stun"]), wounds=int(d.get("wounds") or 0), hp=int(d["hp"].split("/")[0]))
            if kind == "aistart":
                start[(int(d["turn"]), u)] = state
            elif kind == "pstart":
                b = start.get((int(d["turn"]) - 1, u))
                if b:
                    c["morale_lost"] += max(0, b["morale"] - state["morale"])
                    c["morale_gained"] += max(0, state["morale"] - b["morale"])
                    c["stun_added"] += max(0, state["stun"] - b["stun"])
                    c["wounds_added"] += max(0, state["wounds"] - b["wounds"])
                    c["unit_turns"] += 1
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            pend = d if d.get("side") == "1" and d.get("act") in PSI else None
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            k = PSI[pend["act"]]
            spent = x.get("spent") or 0
            c[k + "_chosen"] += 1
            c[k + "_done"] += 1 if spent > 0 else 0
            c["psi_tu"] += spent
            c[k + "_stun"] += x.get("stunned") or 0
            c[k + "_dmg"] += x.get("dmg") or 0
            c[k + "_downed"] += x.get("downed") or 0
            if show and len(psi_on) < show:
                psi_on.append((pend.get("turn"), pend.get("unit"), k, pend.get("aim"), spent, x.get("dmg"), x.get("stunned"), x.get("downed"), x.get("hp_lost")))
            pend = None
        elif s.startswith("[AIRESULT] "):
            d = dict(KV.findall(s))
            turns = int(d.get("turn") or 0)
    c["turns"] = turns
    return c, psi_on


mission = "L8"
args = []
for a in sys.argv[1:]:
    if a.startswith("--mission="):
        mission = a.split("=")[1]
    else:
        args.append(a)
for a in args:
    zp, prefix, arm = a.rsplit(":", 2)
    z = zipfile.ZipFile(zp)
    tot = Counter()
    for s_ in (1, 2, 3, 4):
        c, ex = battle(z, f"{prefix}_{arm}_{mission}_s{s_}", 3)
        tot.update(c)
        print(f"  {prefix} {arm} s{s_}: ходов {c['turns']}, пси выбрано {c['psi_chosen']} исполнено {c['psi_done']}, захват выбрано {c['mc_chosen']} исполнено {c['mc_done']}, ОВ {c['psi_tu']}; перешло на сторону врага {c['faction_0_to_1']}; пример {ex[:2]}")
    done = tot["psi_done"] + tot["mc_done"]
    print(f"{prefix} {arm} {mission}: пси {tot['psi_chosen']}/{tot['psi_done']} (выбрано/исполнено), захват {tot['mc_chosen']}/{tot['mc_done']}, ходов {tot['turns']}; выбрано на ход {(tot['psi_chosen'] + tot['mc_chosen']) / max(1, tot['turns']):.2f}, исполнено на ход {done / max(1, tot['turns']):.2f}; ОВ {tot['psi_tu']}; захвачено бойцов {tot['faction_0_to_1']}; юнит-ходов игрока {tot['unit_turns']}, мораль -{tot['morale_lost']} +{tot['morale_gained']} оглушение +{tot['stun_added']} раны +{tot['wounds_added']}")
