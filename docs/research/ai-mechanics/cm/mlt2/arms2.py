"""MISSION-LEVEL TACTICS STAGE 2: the arms PO (off), PL (shadow), PN (orders) of exe M2 in run_cm.py. Once only."""
import pathlib
import sys

p = pathlib.Path(sys.argv[1]) / "cm" / "st" / "run_cm.py"
b = p.read_bytes().decode("utf-8")
old = '"MN": ("env_MD.txt", ["OXCE_AI_MDIR=2"], COMMON_D0)}'
nl = "\r\n" if "\r\n" in b else "\n"
new = ('"MN": ("env_MD.txt", ["OXCE_AI_MDIR=2"], COMMON_D0),' + nl +
       '        "PO": ("env_M2.txt", [], COMMON_D0), "PL": ("env_M2.txt", ["OXCE_AI_MDIR=1"], COMMON_D0),' + nl +
       '        "PN": ("env_M2.txt", ["OXCE_AI_MDIR=2"], COMMON_D0)}')
if b.count(old) != 1:
    raise SystemExit(f"{b.count(old)} matches")
p.write_bytes(b.replace(old, new).encode("utf-8"))
print("ok")
