"""HIVE COORDINATED OPERATION V0: arms OO, OS, OA and OG in the runner and the env file of exe OP. Run again - no change."""
import re
from pathlib import Path

T = Path(__file__).resolve().parents[2] / "cm" / "st"
path = T / "run_cm.py"
text = path.read_bytes().decode("utf-8")
if '"OA":' in text:
    print("arms are there")
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r"ARMS = \{.*?\n\}|ARMS = \{.*?\}\s*\n", text, re.S)
    block = m.group(0)
    close = block.rstrip().rfind("}")
    add = (
        "        # HIVE COORDINATED OPERATION V0 (GO Vitali 05.11, at most 6 short runs): exe OP; OO - off, OS - shadow from turn 4, OA - active from turn 4, OG - active from turn 1" + nl
        + '        "OO": ("env_OP.txt", [], COMMON_D0),' + nl
        + '        "OS": ("env_OP.txt", ["OXCE_AI_HIVE=1", "OXCE_AI_HIVE_OP=1", "OXCE_AI_HIVE_OP_FROM_TURN=4"], COMMON_D0),' + nl
        + '        "OA": ("env_OP.txt", ["OXCE_AI_HIVE=1", "OXCE_AI_HIVE_OP=2", "OXCE_AI_HIVE_OP_FROM_TURN=4"], COMMON_D0),' + nl
        + '        "OG": ("env_OP.txt", ["OXCE_AI_HIVE=1", "OXCE_AI_HIVE_OP=2"], COMMON_D0),' + nl
    )
    head = block[:close].rstrip()
    if not head.endswith(","):
        head += ","
    path.write_bytes(text.replace(block, head + nl + add + block[close:]).encode("utf-8"))
    print("arms added")
env = (T / "env_CI.txt").read_bytes().decode("utf-8").replace("/exe/CI/", "/exe/OP/")
(T / "env_OP.txt").write_bytes(env.encode("utf-8"))
print("written")
