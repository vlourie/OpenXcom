"""UNIFIED ARMY SAFETY, read only: the order of journal lines on M6: the guards' fields against everyone who stood on or walked off the lift column (20,15,*) and the corridor. Usage: us_order.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def near(p):
    x, y, z = p.strip("()").split(",")
    return x == "20" and y == "15"


for run in ("us1_QN_M6_s1", "us5_QS_M6_s1"):
    print("==", run)
    L = read(run)
    for i, s in enumerate(L):
        if s.startswith("[HIVEREACH]"):
            k = kv(s)
            if int(k["turn"]) <= 3 and k["unit"] in ("1000021", "1000038", "1000039"):
                print(i, "field", k["unit"], "t", k["turn"], "tiles", k["tiles"])
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            if int(k["turn"]) <= 3 and k["side"] == "1" and (near(k["from"]) or near(k["to"])):
                print(i, "t", k["turn"], "unit", k["unit"], k["from"], "->", k["to"], "m" + k["mode"], "a" + k["act"])
    # the changed choice just before the unit walked off the column, on turn 3
    for s in L:
        if s.startswith("[HIVEUA] event=CHOICE") and " unit=1000033 " in s:
            k = kv(s)
            if k["turn"] == "3":
                print("  choice 1000033 t3 at", k["at"], "free", k["free"], "chosen", k["chosen"], "changed", k["changed"], "scout", k["scout"], "linked", k["chosen_linked"])
