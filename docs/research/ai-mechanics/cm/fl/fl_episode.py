"""TACTICAL FLANKING stage 1: one hostile turn of a D0 battle, from the probe log alone.

1) the snapshot at the start of the hostile turn (aistart): every hostile unit (position, TU, health, morale, weapon and
   hands, whom it sees, how many player units see it) and every player unit (position, TU, health, kneel, weapon, turns
   since the hostile side spotted it - the honest knowledge: 0 = seen this turn);
2) the hostile turn in order: each decision (mode, action, target cell, aimed unit, weapon, the player units the side has
   spotted this turn), what it did (AIEXEC: where it ended, TU spent, damage, spotted by how many), the reactions it drew
   and the casualties;
3) the next player turn: the player's attacks and the casualties among the hostile units.

  py -3.13 -I fl_episode.py <log.gz> <turn> [units=all|id,id,...]"""
import gzip
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ACT = {0: "none", 1: "turn", 2: "walk", 3: "kneel", 4: "prime", 6: "throw", 7: "auto", 8: "snap", 9: "aimed", 10: "hit",
       11: "use", 12: "launch", 13: "mind", 14: "panic"}
MODE = {0: "patrol", 1: "ambush", 2: "combat", 3: "escape"}
T = int(sys.argv[2])
only = None if len(sys.argv) < 4 or sys.argv[3] == "all" else set(sys.argv[3].split(","))

pend = None
for raw in gzip.open(sys.argv[1], "rt", encoding="utf-8", errors="replace"):
    body = raw.rstrip("\n").split("\t", 2)[-1]
    if body.startswith("[AISTATE] aistart ") or body.startswith("[AISTATE] pstart "):
        d = dict(KV.findall(body))
        kind = body.split(" ", 2)[1]
        if int(d["turn"]) != T or kind != "aistart":
            continue
        if d["faction"] == "1":
            print(f"H {d['unit']:>8} {d['type']:<24} pos={d['pos']} dir={d['dir']} tu={d['tu']}/{d['tumax']} hp={d['hp']} "
                  f"mor={d['morale']} st={d['status']} w={d['weapon']} rh={d['rh']} lh={d['lh']} ammo={d['ammo']} "
                  f"sees={d['sees']} seenby={d['seenby']} known={d['known']} near={d['near']}")
        elif d["faction"] == "0":
            print(f"P {d['unit']:>8} {d['type']:<24} pos={d['pos']} dir={d['dir']} tu={d['tu']}/{d['tumax']} hp={d['hp']} "
                  f"kneel={d['kneel']} st={d['status']} w={d['weapon']} rh={d['rh']} lh={d['lh']} spotted={d['spotted']} "
                  f"sees={d['sees']}")
        else:
            print(f"N {d['unit']:>8} {d['type']:<24} pos={d['pos']} hp={d['hp']}")
    elif body.startswith("[AIDECIDE] "):
        d = dict(KV.findall(body.split(" hu=")[0]))
        t = int(d["turn"])
        pend = None
        if not (t == T and d["side"] == "1" or t == T + 1 and d["side"] == "0"):
            continue
        if d["side"] == "1" and only and d["unit"] not in only:
            continue
        act = int(d["act"])
        if d["side"] == "0" and act not in (6, 7, 8, 9, 10, 12):
            continue
        pend = d
        print(f"  {'H' if d['side'] == '1' else 'p'}{t} D {d['unit']} n={d['n']} from={d['from']} tu={d['tu']} "
              f"{MODE.get(int(d['mode']), d['mode'])} {ACT.get(act, act)} to={d['to']} run={d['run']} aim={d['aim']} "
              f"w={d['weapon']} seen={d['seen']}")
    elif body.startswith("[AIEXEC] ") and pend:
        x = json.loads(body[9:])
        if str(x["unit"]) == pend["unit"]:
            tr = x.get("trail") or []
            tr = (tr[0][:110] + (f" (+{len(tr) - 1})" if len(tr) > 1 else "")) if tr else ""
            print(f"      -> pos={x.get('pos')} tu={x.get('tu')} spent={x.get('spent')} dmg={x.get('dmg')} downed={x.get('downed')} "
                  f"fdmg={x.get('fdmg')} hp_lost={x.get('hp_lost')} down={x.get('down')} seen={x.get('seen')} "
                  f"spotted={x.get('spotted')} {tr}")
        pend = None
    elif body.startswith("[AIEVENT] ") and " what=reaction " in body:
        d = dict(KV.findall(body))
        if int(d["turn"]) in (T, T + 1):
            print(f"      ~ reaction turn={d['turn']} side={d['side']} reactor={d['unit']} {body[10:160]}")
    elif body.startswith("[AICASUALTY] "):
        d = dict(KV.findall(body))
        if int(d["turn"]) in (T, T + 1):
            print(f"      X {d['turn']}/{d['side']} victim={d['victim']}({d['vfaction']}) {d['how']} at {d['pos']} by "
                  f"{d['killer']}({d['kfaction']}) {d['weapon']} dist={d['dist']}")
