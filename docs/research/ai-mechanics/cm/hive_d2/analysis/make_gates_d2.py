"""d2_gates.py from the gates of SAFETY: the same measures on the new runs; M6 shadow of the SAFETY build (no M6 shadow in this list), marked as such in the report."""
import re
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/hive")
t = (S / "us" / "us_gates.py").read_text(encoding="utf-8")
new = 'SC = [("M6 s1", "d25_DO_M6_s1", "us5_QS_M6_s1", "d26_DN_M6_s1", "ra1_AN_M6_s1"), ("M3 s1", "d21_DO_M3_s1", "d22_DS_M3_s1", "d23_DN_M3_s1", None)]'
t, n = re.subn(r"^SC = \[.*$", new, t, count=1, flags=re.M)
assert n == 1
t = t.replace('"""UNIFIED ARMY SAFETY, read only:', '"""HIVE D2 CORRECTION, read only:', 1)
(S / "d2" / "d2_gates.py").write_text(t, encoding="utf-8")
print("ok")
