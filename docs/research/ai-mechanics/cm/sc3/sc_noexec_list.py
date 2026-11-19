"""The hostile attack decisions that spent no time units and did not walk (as sc_noexec.py), one line each: turn, unit, act,
target, weapon, from, the time units before and after - to see whether the declined shots of D0 are the same kind.

  py -3.13 -I sc_noexec_list.py <out dir> <label> [<label> ...]"""
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(sys.argv[1])
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
for label in sys.argv[2:]:
    pend = None
    print(f"== {label}")
    with gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] "):
                d = dict(KV.findall(body.split(" hu=")[0]))
                pend = d if d["side"] == "1" and int(d["act"]) in ATT else None
            elif body.startswith("[AIEXEC] ") and pend is not None:
                x = json.loads(body[9:])
                if str(x["unit"]) == pend["unit"]:
                    if not x["walk"] and not x["spent"]:
                        print(f"  turn {pend['turn']} unit {pend['unit']} n={pend['n']} act={pend['act']} aim={pend['aim']} "
                              f"to={pend['to']} from={pend['from']} weapon={pend.get('weapon')} tu={pend['tu']}->{x['tu']}")
                    pend = None
