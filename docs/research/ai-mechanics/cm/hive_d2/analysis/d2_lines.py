"""HIVE D2 CORRECTION, read only: the log lines the report cites for 1000050 and 1000016, and where 1000021 of M6 walked."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
L = read("d23_DN_M3_s1")
print("--- 1000016, turn 1")
for i, s in enumerate(L):
    if "1000016" in s[:200] and i < 3000 and s.startswith(("[AIDECIDE]", "[AIEXEC]")):
        print(i, s[:170])
print("--- 1000016, the roll of its fight at the exit")
for i, s in enumerate(L[:1100]):
    if s.startswith("[AIREC]") and '"unit":1000016' in s.replace(" ", ""):
        print(i, s[:420])
print("--- 1000050: patrol ends and fields, turns 1 and 2")
for i, s in enumerate(L):
    if "1000050" in s[:200] and i < 4200 and s.startswith(("[HIVEUA] event=PATROLEND", "[HIVEREACH]", "[AIDECIDE]")):
        print(i, s[:190])
print("--- M6 1000021 by turn")
M = read("d26_DN_M6_s1")
for i, s in enumerate(M):
    if s.startswith("[AIDECIDE]"):
        k = kv(s)
        if k.get("unit") == "1000021":
            print(i, k["turn"], k["from"], "m" + k["mode"], "a" + k["act"], k.get("to"), "tu", k["tu"])
print("--- M6 OFF 1000021")
for i, s in enumerate(read("d25_DO_M6_s1")):
    if s.startswith("[AIDECIDE]"):
        k = kv(s)
        if k.get("unit") == "1000021":
            print(i, k["turn"], k["from"], "m" + k["mode"], "a" + k["act"], k.get("to"), "tu", k["tu"])
