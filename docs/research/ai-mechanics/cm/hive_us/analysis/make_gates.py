"""us_gates.py from the gates of V0: the same measures on the new runs; M6 OFF of this build, M3 and M8 OFF of V0 (the OFF path differs only by a timer). No new measure in it."""
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/hive")
t = (S / "ua" / "ua_gates.py").read_text(encoding="utf-8")
old = 'SC = [("M6 s1", "ua4_UO_M6_s1", "ua5_US_M6_s1", "ua1_UN_M6_s1", "ra1_AN_M6_s1"), ("M3 s1", "ua6_UO_M3_s1", "ua7_US_M3_s1", "ua2_UN_M3_s1", None), ("M8 s1", "ua8_UO_M8_s1", "ua9_US_M8_s1", "ua3_UN_M8_s1", None)]'
new = 'SC = [("M6 s1", "us4_QO_M6_s1", "us5_QS_M6_s1", "us1_QN_M6_s1", "ra1_AN_M6_s1"), ("M3 s1", "ua6_UO_M3_s1", "ua7_US_M3_s1", "us2_QN_M3_s1", None), ("M8 s1", "ua8_UO_M8_s1", "ua9_US_M8_s1", "us3_QN_M8_s1", None)]'
assert old in t
t = t.replace(old, new).replace('"""UNIFIED ARMY CONTROL V0, read only: gates T6, T9, F1-F8', '"""UNIFIED ARMY SAFETY, read only: the same measures as V0, gates T6, T9, F1-F8')
# the fields of this build: "changed" is written by event=RESULT/DECIDED, CHOICE has no changed field if older
(S / "us" / "us_gates.py").write_text(t, encoding="utf-8")
print("ok")
