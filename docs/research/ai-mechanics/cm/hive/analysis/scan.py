"""HIVE COMMAND gate: per scenario of the D0 logs (scpa_D_*), read only: units, length, outcome, how fast the side falls, how much of it is out of contact (where a task can matter). Usage: scan.py <sv/res/out> <scen.tsv> <out.tsv>"""
import csv
import gzip
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
root, scen, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
missions = {r["id"]: (r["mission"], r["race"]) for r in csv.DictReader(open(scen, encoding="utf-8-sig"), delimiter="\t")}
kv = re.compile(r"(\w+)=([^ ]*)")
rows = []
for d in sorted(root.glob("scpa_D_*")):
    _, _, sc, seed = d.name.split("_")
    f = d / "openxcom.log.gz"
    if not f.exists():
        continue
    t1 = set()
    dec = defaultdict(lambda: defaultdict(int))
    free = defaultdict(int)
    freeunits = defaultdict(set)
    acted = defaultdict(set)
    fall = defaultdict(int)
    ff = 0
    first_seen = None
    res = {}
    for line in gzip.open(f, "rt", encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 3:
            continue
        m = p[2]
        if m.startswith("[AIDECIDE]"):
            k = dict(kv.findall(m))
            if k.get("side") != "1":
                continue
            t = int(k["turn"])
            u = int(k["unit"])
            mode = k["mode"]
            dec[t][mode] += 1
            acted[t].add(u)
            seen = k.get("seen", "-")
            if seen not in ("-", "") and first_seen is None:
                first_seen = t
            if mode == "0" and seen in ("-", ""):
                free[t] += 1
                freeunits[t].add(u)
        elif m.startswith("[AISTATE] pstart turn=1 "):
            k = dict(kv.findall(m))
            if k.get("faction") == "1":
                t1.add(k["unit"])
        elif m.startswith("[AICASUALTY]"):
            k = dict(kv.findall(m))
            if k.get("vfaction") == "1":
                fall[int(k["turn"])] += 1
                if k.get("kfaction") == "1":
                    ff += 1
        elif m.startswith("[AIRESULT]"):
            res = dict(kv.findall(m))
    if not res:
        continue
    h = int(res.get("hostile", 0))
    a = lambda n: sum(fall[t] for t in fall if t <= n)
    row = {
        "sc": sc, "seed": seed, "mission": missions.get(sc, ("?", "?"))[0], "race": missions.get(sc, ("?", "?"))[1],
        "hostile": h, "player": res.get("player"), "turns": res.get("turn"), "liveS": res.get("livesoldiers"), "liveA": res.get("livealiens"), "aborted": res.get("aborted"),
        "pdead": res.get("pdead"), "hdead": res.get("hdead"), "ff": ff, "fall1": a(1), "fall2": a(2), "fall3": a(3), "contact": first_seen,
    }
    for t in (1, 2, 3):
        row[f"act{t}"] = len(acted[t])
        row[f"free{t}"] = len(freeunits[t])
        row[f"pat{t}"] = dec[t]["0"]
        row[f"com{t}"] = dec[t]["2"]
        row[f"esc{t}"] = dec[t]["3"]
    rows.append(row)
cols = list(rows[0].keys())
with open(out, "w", encoding="utf-8-sig", newline="") as fo:
    w = csv.DictWriter(fo, cols, delimiter="\t")
    w.writeheader()
    w.writerows(rows)
print("sc seed hostile player turns liveS liveA hdead ff fall1/2/3 contact act1 free1 act2 free2 act3 free3 mission")
for r in rows:
    print(r["sc"], r["seed"], r["hostile"], r["player"], r["turns"], r["liveS"], r["liveA"], r["hdead"], r["ff"], f'{r["fall1"]}/{r["fall2"]}/{r["fall3"]}', r["contact"], r["act1"], r["free1"], r["act2"], r["free2"], r["act3"], r["free3"], r["mission"])
