"""AI_TACTICAL_DIRECTOR_V1: which battles of the D0 control (seed 1) have hostile turns where the side knows player units but
most of its units see none - where a group would have to close in rather than shoot at once. From [AISTATE] before lines of
turns 2..9: per battle, hostile unit-turns that see nobody while their side knows someone, and those that see someone.

  py -3.13 -I td_pick.py <out dir> <prefix>"""
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, P = Path(sys.argv[1]), sys.argv[2]
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
rows = []
for d in sorted(OUT.glob(f"{P}_*_s1")):
    f = d / "openxcom.log.gz"
    if not f.exists():
        continue
    blind = see = 0
    with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if not body.startswith("[AISTATE] aistart "):
                continue
            k = dict(KV.findall(body))
            t = int(k["turn"])
            if t < 2 or t > 9 or k["faction"] != "1" or k["status"] != "0" or k.get("weapon", "-") == "-":
                continue
            if k["sees"] != "-":
                see += 1
            elif int(k.get("known", "0")) > 0:
                blind += 1
    rows.append((blind, see, d.name))
for blind, see, name in sorted(rows, reverse=True):
    print(f"{name}: blind-but-known {blind}, seeing {see}")
