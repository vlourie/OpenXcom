"""Movement diagnosis: the state hashes of the two loads decision by decision up to the first different action (read only)."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
db = [kv(s) for s in read("hh7_HL_M3_s1") if s.startswith("[AIDECIDE]")]
dc = [kv(s) for s in read("hh8_HL_M3_s1") if s.startswith("[AIDECIDE]")]
HASH = ["hu", "hi", "ho", "hou", "hm", "hr", "hr0", "ha0", "ha"]
for n, (x, y) in enumerate(zip(db, dc)):
    bad = [f for f in HASH if x.get(f) != y.get(f)]
    if bad:
        print("first hash difference at decision", n, "unit", x["unit"], bad)
        break
else:
    print("no hash difference")
