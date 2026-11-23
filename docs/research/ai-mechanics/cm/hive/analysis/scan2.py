"""HIVE COMMAND gate, second pass over the D0 logs (read only): are the players a real force (armed, hurt by the enemy), is the outcome open, how much of the enemy is out of contact at the start of its turns. Usage: scan2.py <sv/res/out> <scen.tsv> <out.tsv>"""
import csv
import gzip
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
root, scen, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
missions = {r["id"]: r["mission"] for r in csv.DictReader(open(scen, encoding="utf-8-sig"), delimiter="\t")}
kv = re.compile(r"(\w+)=([^ ]*)")
rows = []
for d in sorted(root.glob("scpa_D_*")):
    _, _, sc, seed = d.name.split("_")
    f = d / "openxcom.log.gz"
    if not f.exists():
        continue
    armed = hp = players = 0
    alive = defaultdict(int)
    free = defaultdict(int)
    pfall = []
    hfall = defaultdict(int)
    res = {}
    pseen = set()
    for line in gzip.open(f, "rt", encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 3:
            continue
        m = p[2]
        if m.startswith("[AISTATE] aistart "):
            k = dict(kv.findall(m))
            t = int(k["turn"])
            if k.get("faction") == "0" and t == 1 and k["unit"] not in pseen:
                pseen.add(k["unit"])
                players += 1
                hp += int(k["hp"].split("/")[1])
                hands = (k.get("rh", "-"), k.get("lh", "-"))
                armed += any(h != "-" and not h.startswith("INV_NULL") and "SHIELD" not in h for h in hands)
            elif k.get("faction") == "1" and t <= 4 and k.get("status") not in ("6", "7"):
                alive[t] += 1
                if k.get("sees", "-") == "-" and k.get("seenby", "0") == "0":
                    free[t] += 1
        elif m.startswith("[AICASUALTY]"):
            k = dict(kv.findall(m))
            if k.get("vfaction") == "0":
                pfall.append(int(k["turn"]))
            elif k.get("kfaction") == "0":
                hfall[int(k["turn"])] += 1
        elif m.startswith("[AIRESULT]"):
            res = dict(kv.findall(m))
    if not res:
        continue
    pfall.sort()
    rows.append({
        "sc": sc, "seed": seed, "mission": missions.get(sc, "?"), "players": players, "armed": armed, "php": hp, "phplost": res.get("phplost"),
        "turns": res.get("turn"), "liveS": res.get("livesoldiers"), "liveA": res.get("livealiens"), "hostile": res.get("hostile"), "hattacks": res.get("hattacks"),
        "a1": alive[1], "f1": free[1], "a2": alive[2], "f2": free[2], "a3": alive[3], "f3": free[3], "a4": alive[4], "f4": free[4],
        "k123": sum(hfall[t] for t in (1, 2, 3)), "pfall": ",".join(map(str, pfall[:10])),
    })
cols = list(rows[0].keys())
with open(out, "w", encoding="utf-8-sig", newline="") as fo:
    w = csv.DictWriter(fo, cols, delimiter="\t")
    w.writeheader()
    w.writerows(rows)
print("sc seed pl armed php lost turns liveS liveA host atk | alive/free t1 t2 t3 t4 | killedByPlayer t1-3 | player falls | mission")
for r in rows:
    print(r["sc"], r["seed"], r["players"], r["armed"], r["php"], r["phplost"], r["turns"], r["liveS"], r["liveA"], r["hostile"], r["hattacks"], "|", f'{r["a1"]}/{r["f1"]} {r["a2"]}/{r["f2"]} {r["a3"]}/{r["f3"]} {r["a4"]}/{r["f4"]}', "|", r["k123"], "|", r["pfall"], "|", r["mission"][4:26])
