"""AI FORGE WP2: every engine line that differs between two runs, and every numeric field whose name looks like wall time in any engine line. Reads logs only. args: a b"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
a, b = sys.argv[1], sys.argv[2]


def engine(name):
    return [s for s in sic.read_log(rr.RES / f"res_fw{name}.zip", rr.label_of(name)) if s.startswith("[AI") and not s.startswith("[FORGE")]


x, y = engine(a), engine(b)
print("lines", len(x), len(y))
diff = [(i, p, q) for i, (p, q) in enumerate(zip(x, y)) if p != q]
print("differing lines", len(diff))
for i, p, q in diff[:10]:
    print(i, "A", p[:200])
    print(i, "B", q[:200])
TIME = re.compile(r"\b(\w*(?:_us|_ms|_ns|us|ms))=")
names = Counter()
for s in x + y:
    head = s.split(" ", 1)[0]
    for m in TIME.finditer(s):
        names[head + " " + m.group(1)] += 1
print("time-like fields", dict(names))
