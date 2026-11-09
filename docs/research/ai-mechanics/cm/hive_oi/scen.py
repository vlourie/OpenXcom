"""OPERATIONAL INTELLIGENCE: how general is the melee finding: over the D0 archive of 24 scenarios and 2 seeds: per scenario the melee weapons held by the AI side in the engine's list, the number of melee chains of 100 TU or more on a target that did not go down, their mean damage. Read only.
Usage: scen.py <archive dir>"""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
root = Path(sys.argv[1])
KV = re.compile(r"(\w+)=([^ ]*)")
files = []
for z in sorted(root.glob("res_*.zip")):
    zf = zipfile.ZipFile(z)
    files += [(zf, n) for n in zf.namelist() if n.endswith("openxcom.log.gz")]
print("logs", len(files))
tab = defaultdict(lambda: defaultdict(list))
seen = defaultdict(Counter)
for zf, name in files:
    if "_D_" not in name:
        continue
    m = re.search(r"_([ML]\d+)_", name)
    scen = m.group(1) if m else name
    weapon = {}
    side = {}
    cur = {}
    try:
        with gzip.open(io.BytesIO(zf.read(name)), "rt", encoding="utf-8", errors="replace") as h:
            for ln in h:
                s = ln.rstrip("\n").split("\t")[-1]
                if s.startswith("[AIDECIDE]"):
                    k = dict(KV.findall(s))
                    cur = k
                elif s.startswith("[AIREC]"):
                    try:
                        j = json.loads(s[8:])
                    except ValueError:
                        continue
                    weapon[j["rec"]] = cur.get("weapon")
                    side[j["rec"]] = cur.get("side")
                elif s.startswith("[AICAND] acts="):
                    try:
                        for a in json.loads(s.split(" list=", 1)[1]):
                            if a.get("k") == "a" and a.get("t") == 10 and a.get("tu", 99) <= 20:
                                seen[scen][a["w"]] += 1
                    except (IndexError, ValueError):
                        pass
                elif s.startswith("[AIEXEC]"):
                    try:
                        j = json.loads(s[9:])
                    except ValueError:
                        continue
                    r = j["rec"]
                    if side.get(r) == "1" and j.get("dmg", 0) > 0 and j.get("spent", 0) >= 100 and not j.get("downed"):
                        w = weapon.get(r) or ""
                        if not any(x in w for x in ("RIFLE", "GUN", "PISTOL", "CANNON", "SNIPER", "LAUNCHER", "BLASTER", "HEAVY", "MINIGUN", "GRENADE", "CLIP", "TOXIGUN", "SHOTGUN", "CARBINE")):
                            tab[scen][w].append(j["dmg"])
    except OSError:
        continue
print("scenario: melee weapons cheap enough to chain (list entries); chains >=100 TU on a target that stayed up: n, mean")
for scen in sorted(set(seen) | set(tab)):
    w = ", ".join(f"{x[4:16]}" for x, _ in seen[scen].most_common(5))
    c = "; ".join(f"{x[4:16]} {len(v)} chains mean {sum(v) // len(v)}" for x, v in tab[scen].items())
    print(f"  {scen}: {w} || {c}")
