"""CONTACT_COORDINATION_V0: the side plan's time per run, from HIVEPERF (read only). Usage: plantime.py <run> ..."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

for r in sys.argv[1:]:
    v = [int(kv(s)["us"]) for s in read(r) if s.startswith("[HIVEPERF]") and "phase=plan" in s]
    print(r, "plan us", v[:9], "max", max(v) if v else None)
