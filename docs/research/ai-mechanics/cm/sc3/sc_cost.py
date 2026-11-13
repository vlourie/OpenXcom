"""SIDE_TURN_ACTION_SCHEDULER stage 2: the scheduler's own cost per pick ([AISCHED] us=, the attack tests and the choice) and
the record hash without the timer field - the timed run must repeat the untimed one.

  py -3.13 -I sc_cost.py <out dir> <untimed label> <timed label>"""
import gzip
import hashlib
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(sys.argv[1])
US = re.compile(r"^\[AISCHED\] us=(\d+) ")
TAGS = ("[AIDECIDE] ", "[AIEXEC] ", "[AISCHED] ", "[AICASUALTY] ")


def scan(label):
    h, us = hashlib.md5(), []
    with gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if not body.startswith(TAGS):
                continue
            m = US.match(body)
            if m:
                us.append(int(m.group(1)))
                body = "[AISCHED] " + body[m.end():]
            h.update(body.encode("utf-8"))
    return h.hexdigest(), us


a, _ = scan(sys.argv[2])
b, us = scan(sys.argv[3])
print(f"{sys.argv[2]} {a}\n{sys.argv[3]} {b} {'IDENTICAL' if a == b else 'DIFFERENT'}")
us.sort()
n = len(us)
if n:
    print(f"  picks {n}, total {sum(us) / 1000:.1f} ms, mean {sum(us) / n:.0f} us, median {us[n // 2]} us, "
          f"p95 {us[int(n * 0.95)]} us, max {us[-1]} us")
