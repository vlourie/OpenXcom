"""AI_TACTICAL_DIRECTOR_V1: casualties per battle up to a turn, by victim faction ([AICASUALTY] vfaction), for several series.

  py -3.13 -I td_cas.py <out dir> <max turn> <prefix>..."""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, TMAX = Path(sys.argv[1]), int(sys.argv[2])
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
keys = set()
res = {}
for p in sys.argv[3:]:
    for d in sorted(OUT.glob(f"{p}_*")):
        f = d / "openxcom.log.gz"
        if not f.exists():
            continue
        key = "_".join(d.name.split("_")[2:])
        c = Counter()
        with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                body = raw.rstrip("\n").split("\t", 2)[-1]
                if body.startswith("[AICASUALTY] "):
                    k = dict(KV.findall(body))
                    if int(k["turn"]) <= TMAX:
                        c[k["vfaction"]] += 1
        res[(p, key)] = c
        keys.add(key)
for key in sorted(keys):
    print(key, "  ".join(f"{p}: p{res[(p, key)]['0']} h{res[(p, key)]['1']} n{res[(p, key)]['2']}" for p in sys.argv[3:] if (p, key) in res))
