"""SIDE-FIRST COMBAT: vetoes of a battle by target and weapon, beside the director's own attacks at the same target and what they did. args: zip label"""
import json
import sys
from collections import Counter, defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0])
from battle_stats import lines

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
veto = Counter()
vff = Counter()
acts = defaultdict(lambda: [0, 0.0, 0, 0])
pend = {}
appr = Counter()
for s in lines(sys.argv[1], sys.argv[2]):
    if not s.startswith("[AISCD] "):
        continue
    j = json.loads(s[8:])
    e = j.get("ev")
    if e == "veto":
        k = (j["target"], j["w"], "eff0" if j["eff"] == 0 else "eff>0", "ff0" if j["ff"] == 0 else "ff>0")
        veto[k] += 1
    elif e == "act" and j["kind"] == "A":
        pend[j["actor"]] = j
    elif e == "result" and j["kind"] == "A":
        p = pend.get(j["actor"], {})
        a = acts[(p.get("target"), p.get("w"))]
        a[0] += 1
        a[1] += j.get("eff", 0)
        a[2] += j.get("tDmg", 0)
        a[3] += j.get("tHit", 0)
print("vetoes (target, weapon, eff, ff): n")
for k, v in veto.most_common(40):
    print(" ", k, v)
print("director's attacks (target, weapon): n, eff sum, damage, hits")
for k, v in sorted(acts.items(), key=lambda x: str(x[0])):
    print(" ", k, v[0], round(v[1], 1), v[2], v[3])
