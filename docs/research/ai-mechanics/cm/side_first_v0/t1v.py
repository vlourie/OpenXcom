"""SIDE-FIRST COMBAT V0.1: the first hostile turn by unit type of one battle, with the battle's totals. args: zip label"""
import re
import runpy
import sys
import zipfile
from collections import Counter, defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0])
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
argv = sys.argv
sys.argv = ["t1_units", argv[1], "x", "x"]
sys.stdout.flush()
src = open(__file__.rsplit("t1v.py", 1)[0] + "t1_units.py", encoding="utf-8").read().split("z = zipfile.ZipFile")[0]
ns = {}
exec(src, ns)
z = zipfile.ZipFile(argv[1])
typ, tu0, tu_end, u, _ = ns["turn1"](z, argv[2])
by = defaultdict(Counter)
for i, t in typ.items():
    b = by[t]
    b["units"] += 1
    b["tu0"] += tu0[i]
    b.update(u[i])
for t, b in sorted(by.items(), key=lambda kv: -kv[1]["units"]):
    acts = " ".join(f"{k}:{v}" for k, v in sorted(b.items()) if k not in ("units", "tu0", "dec", "spent", "dmg"))
    print(f"  {t:<34} {b['units']:>3}; реш {b['dec']:>4}, ОВ {b['spent']:>6} из {b['tu0']:>6} ({100 * b['spent'] / max(1, b['tu0']):.0f} %), урон {b['dmg']:>5}; {acts}")
for s in ns["read"](z, argv[2]):
    if s.startswith("[AIRESULT] "):
        print(" ", s[:220])
