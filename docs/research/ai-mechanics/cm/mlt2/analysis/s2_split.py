"""STAGE 2, the 17 against 21-26 of stage 1: in the M1 logs the hostile shots' breaking hits on module objects by source and by facility cell, and the module tiles lost in all
(read only). Then for the given L4 battles the module tiles lost in all, the cost in time. Usage: s2_split.py <stage 1 out dir> <stage 2 out dir>"""
import collections
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")


def lines(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for ln in f:
            yield ln.rstrip("\n").split("\t")[-1]


def split(d):
    plans = []  # (log order) fighters from the plan's turn on
    fighters = set()
    cell_of_plan = None
    src = collections.Counter()
    facs = {}
    first = {}
    last = None
    for s in lines(d):
        if not s.startswith("[AIMISSION]"):
            if s.startswith("[AIRESULT]"):
                res = dict(KV.findall(s))
            continue
        k = dict(KV.findall(s))
        w = k.get("what")
        if w == "fac":
            facs[k["at"]] = k["type"]
        elif w == "plan":
            fighters = set(f.split(">")[0] for f in k["fighters"].split(";"))
            cell_of_plan = k.get("cell") or cell_of_plan
        elif w == "objective":
            cell_of_plan = k.get("cell") or cell_of_plan
        elif w == "hit" and k.get("side") == "1" and k.get("module") == "1" and k.get("part") == "3" and int(k["tdmg"]) >= int(k["partarmor"]):
            x, y = k["tile"].split(",")[:2]
            c = f"{int(x) // 10},{int(y) // 10}"
            src[(k["unit"] in fighters, c)] += 1
        elif w == "grid":
            cells = dict(re.findall(r"(\d+,\d+)=(\d+/\d+)", s))
            if not first:
                first = cells
            last = cells
    t0 = sum(int(v.split("/")[1]) for v in (first or {}).values())
    t1 = sum(int(v.split("/")[0]) for v in (last or {}).values())
    return src, facs, t0, t1, res


a, b = Path(sys.argv[1]), Path(sys.argv[2])
for name in sys.argv[3:]:
    d = (b if name.startswith("p") else a) / name
    src, facs, t0, t1, res = split(d)
    order = sum(v for (o, c), v in src.items() if o)
    proto = sum(v for (o, c), v in src.items() if not o)
    print(f'{name}: broke by shots: plan fighters {order}, the rest {proto}, total {order + proto}; module tiles {t0} > {t1} (lost {t0 - t1}) turn {res.get("turn")} ms {res.get("ms")} vms {res.get("vms")}')
    print("   ", {("order " if o else "proto ") + c + " " + facs.get(c, "?")[4:]: v for (o, c), v in sorted(src.items())})
