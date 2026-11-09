"""HIVE COMMAND CORE V0: the three arms in the runner cm/st/run_cm.py. Usage: patch_arms.py <run_cm.py>"""
import re
import sys

path = sys.argv[1]
raw = open(path, "rb").read()
text = raw.decode("utf-8")
if '"HO":' in text:
    print("already there")
    sys.exit(0)
nl = "\r\n" if "\r\n" in text else "\n"
m = re.search(r"ARMS = \{.*?\n\}|ARMS = \{.*?\}\s*\n", text, re.S)
block = m.group(0)
close = block.rstrip().rfind("}")
add = (
    '        # HIVE COMMAND CORE V0 (GO Vitali 05.11, at most 12 short battles): exe HV (D0 + HiveCommand); HO - off (must repeat D),' + nl
    + '        # HS - shadow (must repeat D too), HA - active' + nl
    + '        "HO": ("env_HV.txt", [], COMMON_D0), "HS": ("env_HV.txt", ["OXCE_AI_HIVE=1"], COMMON_D0),' + nl
    + '        "HA": ("env_HV.txt", ["OXCE_AI_HIVE=2"], COMMON_D0),' + nl
)
head = block[:close].rstrip()
if not head.endswith(","):
    head += ","
new = head + nl + add + block[close:]
open(path, "wb").write(text.replace(block, new).encode("utf-8"))
print("arms added")
