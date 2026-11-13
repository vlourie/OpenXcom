"""HIVE hardening: the four arms in the runner cm/st/run_cm.py. Usage: patch_arms_hh.py <run_cm.py>"""
import re
import sys

path = sys.argv[1]
raw = open(path, "rb").read()
text = raw.decode("utf-8")
if '"JO":' in text:
    print("already there")
    sys.exit(0)
nl = "\r\n" if "\r\n" in text else "\n"
m = re.search(r"ARMS = \{.*?\n\}|ARMS = \{.*?\}\s*\n", text, re.S)
block = m.group(0)
close = block.rstrip().rfind("}")
add = (
    '        # HIVE hardening (GO Vitali 05.11, at most 8 short runs): exe HH; JO - off, JS - shadow, JA - active, JV - active with a save at turn 5' + nl
    + '        "JO": ("env_HH.txt", [], COMMON_D0), "JS": ("env_HH.txt", ["OXCE_AI_HIVE=1"], COMMON_D0),' + nl
    + '        "JA": ("env_HH.txt", ["OXCE_AI_HIVE=2"], COMMON_D0),' + nl
    + '        "JV": ("env_HH.txt", ["OXCE_AI_HIVE=2", "OXCE_AI_HIVE_SAVE_TURN=5"], COMMON_D0),' + nl
)
head = block[:close].rstrip()
if not head.endswith(","):
    head += ","
new = head + nl + add + block[close:]
open(path, "wb").write(text.replace(block, new).encode("utf-8"))
print("arms added")
