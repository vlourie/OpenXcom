"""SIDE-FIRST COMBAT: the first hostile turn unit by unit, D against XN (same start, same side): decisions, TU spent, actions by type, per unit type; the units whose TU stayed unused; psi units. args: zip prefix mission

Unit type from [AISTATE] (aistart turn=1); start TU likewise."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
ACT = {2: "walk", 6: "throw", 7: "auto", 8: "snap", 9: "aim", 10: "hit", 13: "psi", 14: "mc", 0: "none", 15: "rethink"}


def read(z, label):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    return [s.split("\t")[-1] for s in raw]


def turn1(z, label):
    typ, tu0, tu_end = {}, {}, {}
    u = defaultdict(Counter)
    pend = None
    src = defaultdict(Counter)
    for s in read(z, label):
        if s.startswith("[AISTATE] "):
            kind = s.split(" ", 2)[1]
            d = dict(KV.findall(s))
            if d.get("faction") != "1" or "unit" not in d:
                continue
            if kind == "aistart" and d.get("turn") == "1":
                typ[d["unit"]] = d.get("type")
                tu0[d["unit"]] = int(d["tu"])
            elif kind == "pstart" and d.get("turn") == "2":
                tu_end[d["unit"]] = int(d["tu"])
        elif s.startswith("[AIREC] "):
            j = json.loads(s[8:])
            if j.get("turn") == 1 and j.get("side") == 1:
                src[str(j["unit"])][str((j.get("base") or {}).get("src"))] += 1
        elif s.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(s.split(" hu=")[0]))
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            d, pend = pend, None
            if d.get("side") == "1" and d.get("turn") == "1" and str(x.get("unit")) == d.get("unit"):
                c = u[d["unit"]]
                c["dec"] += 1
                c[ACT.get(int(d["act"]), d["act"])] += 1
                c["spent"] += x.get("spent") or 0
                c["dmg"] += x.get("dmg") or 0
    return typ, tu0, tu_end, u, src


z = zipfile.ZipFile(sys.argv[1])
P, M = sys.argv[2], sys.argv[3]
for s in (1, 2, 3, 4):
    print(f"\n== {M} s{s}: тип юнита: юнитов; решений, ОВ потрачено, из ОВ начала; действия")
    for arm in ("D", "XN"):
        typ, tu0, tu_end, u, src = turn1(z, f"{P}_{arm}_{M}_s{s}")
        by = defaultdict(Counter)
        for i, t in typ.items():
            b = by[t]
            b["units"] += 1
            b["tu0"] += tu0[i]
            b.update(u[i])
        for t, b in sorted(by.items(), key=lambda kv: -kv[1]["units"]):
            acts = " ".join(f"{k}:{v}" for k, v in sorted(b.items()) if k not in ("units", "tu0", "dec", "spent", "dmg"))
            print(f"  {arm:<3}{t:<34} {b['units']:>3}; реш {b['dec']:>4}, ОВ {b['spent']:>6} из {b['tu0']:>6} ({100 * b['spent'] / max(1, b['tu0']):.0f} %), урон {b['dmg']:>5}; {acts}")
