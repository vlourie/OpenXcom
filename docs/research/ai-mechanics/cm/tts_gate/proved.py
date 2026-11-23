"""NATURAL GATE: the class the engine itself proves. Same B and T, same cells and stance: lof 0 while a comrade stands on the lane, lof 1 once it has left, in the same side turn.
Then the GO's conditions one by one; refuted = the comrade left and the engine still said lof 0. Args: cands.jsonl"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ATT = {5, 6, 7, 8, 9, 10, 11, 12}
RES = [json.loads(s) for s in Path(sys.argv[1]).open(encoding="utf-8")]
F = Counter()
rows = []
per_b = Counter()
for r in RES:
    for c in r["cands"]:
        s = c["shot"]
        for f in c["flips"]:
            if not (f["after"] and f["turn"] == c["turn"]):
                continue
            left = [x for x in f["comrades"] if x["out"] or x["now"] != x["was"]]
            if not left:
                continue
            F["0 same-turn opening"] += 1
            walked = [x for x in left if not x["out"]]
            if not walked:
                F["x only by a comrade falling, not walking"] += 1
                break
            F["1 a comrade walked off"] += 1
            if f["tu"] < s["tu"]:
                F["x B has no TU for a shot by then"] += 1
                break
            F["2 B still has TU for the shot at the opening"] += 1
            if not c["hurtT"]:
                F["x this weapon never wounded this T in the battle"] += 1
                break
            F["3 weapon wounded T in the battle"] += 1
            if c["other_lof"]:
                F["x B had another shot with a line at the block"] += 1
                break
            F["4 B had no other shot with a line"] += 1
            d = f["did"]
            later = [x for x in c["b_later"] if x["n"] >= f["n"] or True]
            shot_t = any(x["t"] in ATT and x["u"] == c["T"]["id"] for x in [c["b_this"]] + c["b_later"])
            F["5a B fired at T anyway" if shot_t else "5b B did not fire at T in the turn"] += 1
            rows.append(f"{r['name']} t{c['turn']} B{c['B']['id']}{tuple(c['B']['pos'])} tu{c['B']['tu']}>{f['tu']} T{c['T']['id']}{tuple(c['T']['pos'])} d{s['d']} {s['w']} {s['tu']}TU p{s['p']} hurtT {c['hurtT']} | walked {[(x['id'], x['was'], x['now']) for x in walked]} | own {c['own']} fit {c['own_fit']} | B then t{d['t']} u{d['u']} sp{d['spent']} dmg{d['dmg']} f{d['fdmg']} | later {[(x['t'], x['u'], x['spent'], x['dmg']) for x in c['b_later']][:6]}")
            break
for k in sorted(F):
    print(f"{F[k]:5d}  {k}")
print()
for s in rows:
    print(s)
