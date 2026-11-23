"""SIDE-FIRST COMBAT: the new arms in the stand's run_cm.py. XO - exe SD, flag off (must repeat D); XS - shadow (must repeat D too); XN - on; arm D is the D0 exe. arg: run_cm.py"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
new = '''        # SIDE-FIRST COMBAT AI (MASTER GO Vitali 06.11, at most 40 runs): exe SD (D0 + SideCombatDirector); XO - off, XS - shadow (both must repeat D), XN - on
        "XO": ("env_SD.txt", [], COMMON_D0), "XS": ("env_SD.txt", ["OXCE_AI_SCD=1"], COMMON_D0), "XN": ("env_SD.txt", ["OXCE_AI_SCD=2"], COMMON_D0),
}
TURNS = 60
'''
old = "}\nTURNS = 60\n"
if '"XO"' not in s:
    assert s.count(old) == 1
    s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
print("ok")
