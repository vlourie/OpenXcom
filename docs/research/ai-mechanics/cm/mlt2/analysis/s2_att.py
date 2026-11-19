"""STAGE 2: the hostile attack decisions split into shots at modules in patrol mode and all others, and every case of TU spent over the TU at the decision (read only).
Usage: s2_att.py <out dir> <battle>..."""
import collections
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
for name in sys.argv[2:]:
    with gzip.open(Path(sys.argv[1]) / name / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        rows = [ln.rstrip("\n").split("\t")[-1] for ln in f]
    dec = None
    att = collections.Counter()
    over = []
    for s in rows:
        if s.startswith("[AIDECIDE] "):
            k = dict(KV.findall(s))
            dec = k if k.get("side") == "1" else None
            if dec and int(k["act"]) in (6, 7, 8, 9, 10, 11, 12):
                att["module shot" if k["mode"] == "0" else "other"] += 1
        elif s.startswith("[AIEXEC] ") and dec:
            x = json.loads(s[9:])
            if str(x["unit"]) == dec["unit"]:
                sp = x.get("spent") or 0
                if sp > int(dec["tu"]):
                    over.append(f't{dec["turn"]} {dec["unit"]} m{dec["mode"]} a{dec["act"]} tu{dec["tu"]} sp{sp} {x.get("how") or x.get("result") or ""}')
            dec = None
    print(name, dict(att), "over:", over)
