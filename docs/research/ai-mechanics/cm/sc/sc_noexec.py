"""Hostile attack decisions ([AIDECIDE] side=1, act in ATT) whose execution record ([AIEXEC] of the unit next) spent no time
units and did not walk - the engine declined the shot; counted per log, to compare S with the control.

  py -3.13 -I sc_noexec.py <out dir> <label> [<label> ...]"""
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
    att = no = 0
    with gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] "):
                d = dict(KV.findall(body.split(" hu=")[0]))
                pend = d if d["side"] == "1" and int(d["act"]) in ATT else None
                att += pend is not None
            elif body.startswith("[AIEXEC] ") and pend is not None:
                x = json.loads(body[9:])
                if str(x["unit"]) == pend["unit"]:
                    no += not x["walk"] and not x["spent"]
                    pend = None
    print(f"{label}: hostile attack decisions {att}, executed with no time units spent {no}")
