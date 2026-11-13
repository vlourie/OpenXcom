"""SIDE_TURN_ACTION_SCHEDULER stage 2: the hostile side's wall time per decision (log timestamps, 1 s resolution): the sum over
hostile turns of (last - first [AIDECIDE] side=1) divided by the hostile decisions of those turns.

  py -3.13 -I sc_speed.py <out dir> <label> [<label> ...]"""
import gzip
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(sys.argv[1])
TS = re.compile(r"^\[(\d\d-\d\d-\d{4}_\d\d-\d\d-\d\d)\]")
for label in sys.argv[2:]:
    turns = {}
    with gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            if "[AIDECIDE] " not in raw or " side=1 " not in raw:
                continue
            m = TS.match(raw)
            t = int(re.search(r" turn=(\d+)", raw).group(1))
            ts = datetime.strptime(m.group(1), "%d-%m-%Y_%H-%M-%S").timestamp()
            a, b, n = turns.get(t, (ts, ts, 0))
            turns[t] = (min(a, ts), max(b, ts), n + 1)
    sec = sum(b - a for a, b, _ in turns.values())
    n = sum(x[2] for x in turns.values())
    sched = 0
    with gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        sched = sum(1 for raw in f if "[AISCHED] " in raw)
    print(f"{label}: hostile turns {len(turns)}, decisions {n}, hostile wall time {sec:.0f} s, {1000 * sec / max(n, 1):.1f} ms/decision, "
          f"[AISCHED] picks {sched}")
    for k in sorted(turns)[:2]:
        a, b, n = turns[k]
        print(f"    turn {k}: decisions {n}, {b - a:.0f} s, {1000 * (b - a) / max(n, 1):.1f} ms/decision")
