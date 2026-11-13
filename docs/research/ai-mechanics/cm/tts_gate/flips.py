"""NATURAL GATE: the natural experiment in the D0 logs. The same B and T on the same cells and stance had no line while a comrade stood on the lane; the comrade left; the engine's line appeared. What did B do with it. Args: cands.jsonl"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ATT = {5, 6, 7, 8, 9, 10, 11, 12}
RES = [json.loads(s) for s in Path(sys.argv[1]).open(encoding="utf-8")]
n = Counter()
rows = []
ex = {}
for r in RES:
    for c in r["cands"]:
        fl = None
        for f in c["flips"]:
            if f["after"] and any(x["out"] or x["now"] != x["was"] for x in f["comrades"]):
                fl = f
                break
        if not fl:
            continue
        d = fl["did"]
        same = fl["turn"] == c["turn"]
        n["all"] += 1
        n["same_turn" if same else "next_turn"] += 1
        left = [x for x in fl["comrades"] if x["out"] or x["now"] != x["was"]]
        n["comrade_out" if all(x["out"] for x in left) else "comrade_walked"] += 1
        if fl["tu"] < fl["shot"]["tu"]:
            n["no_tu_for_shot"] += 1
        kind = "attack_T" if d["t"] in ATT and d["u"] == c["T"]["id"] else "attack_other" if d["t"] in ATT else "walk_or_other"
        n[kind] += 1
        n["dmg_" + kind] += d["dmg"] or 0
        n["fdmg_" + kind] += d["fdmg"] or 0
        if kind == "attack_T" and (d["dmg"] or 0) > 0:
            n["attack_T_hurt"] += 1
        rows.append(f"{r['name']} t{c['turn']}>{fl['turn']} B{c['B']['id']}{tuple(c['B']['pos'])} tu{c['B']['tu']}>{fl['tu']} T{c['T']['id']}{tuple(c['T']['pos'])} d{c['shot']['d']} {c['shot']['w']} | left {[(x['id'], x['was'], x['now'], x['out']) for x in left]} | {kind} t{d['t']} u{d['u']} sp{d['spent']} dmg{d['dmg']} f{d['fdmg']} others {fl['others']}")
print(dict(n))
for s in rows:
    print(s)
