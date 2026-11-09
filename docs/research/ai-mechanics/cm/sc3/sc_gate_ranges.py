"""Ranges of the reaction scores in [AICOVERGATE]: the covering unit's and the mover's, at the score gate and overall."""
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
for lab in sys.argv[2:]:
    u, m, ms = [], [], []
    with gzip.open(Path(sys.argv[1]) / lab / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AICOVERGATE] "):
                d = dict(KV.findall(body))
                if d["gate"] == "out":
                    continue
                u.append(int(d["uscore"]))
                m.append(int(d["mscore"]))
                if d["gate"] == "score":
                    ms.append(int(d["mscore"]))
    print(f"{lab}: B score {min(u)}-{max(u)}; mover score all {min(m)}-{max(m)}, at the score gate {min(ms)}-{max(ms)}")
