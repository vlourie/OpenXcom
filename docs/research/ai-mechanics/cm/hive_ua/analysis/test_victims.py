"""Guard of R-674: losses counted from [AICASUALTY] must be units, never lines. On the run where lines reached 221, lib.victims stays within the side's size and near [AIRESULT]. Usage: test_victims.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
sys.path.insert(0, str(Path(__file__).parent))
from lib import kv, read, victims  # noqa: E402

for run in ("ua6_UO_M3_s1", "ua2_UN_M3_s1", "ua4_UO_M6_s1", "ua1_UN_M6_s1", "ua8_UO_M8_s1", "ua3_UN_M8_s1"):
    L = read(run)
    r = kv([s for s in L if s.startswith("[AIRESULT]")][-1])
    lines = sum(s.startswith("[AICASUALTY]") and " vfaction=1 " in s for s in L)
    n = len(victims(L).get("1", ()))
    gone = int(r["hdead"]) + int(r["hout"])
    assert n <= int(r["hostile"]), (run, n, r["hostile"])
    assert gone <= n, (run, gone, n)
    print(run, "lines", lines, "victims", n, "hdead+hout", gone, "hostile", r["hostile"])
print("ok")
