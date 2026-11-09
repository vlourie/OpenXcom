"""CONTACT_COORDINATION_V0: from the hardening's runner files, the arms of this stage in cm/st/run_cm.py, its env files and the load runner (exe CC). Usage: make_cc.py"""
import re
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
T = S / "cm" / "st"
H = S / "hive"

# arms
path = T / "run_cm.py"
text = path.read_bytes().decode("utf-8")
if '"CO":' in text:
    print("arms are there")
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r"ARMS = \{.*?\n\}|ARMS = \{.*?\}\s*\n", text, re.S)
    block = m.group(0)
    close = block.rstrip().rfind("}")
    add = (
        '        # CONTACT_COORDINATION_V0 (GO Vitali 05.11, at most 8 short runs): exe CC; CO - off, CB - HIVE without the contact flag, CC - with it, CV - with it and a save at turn 3' + nl
        + '        "CO": ("env_CC.txt", [], COMMON_D0), "CB": ("env_CC.txt", ["OXCE_AI_HIVE=2"], COMMON_D0),' + nl
        + '        "CC": ("env_CC.txt", ["OXCE_AI_HIVE=2", "OXCE_AI_HIVE_CONTACT=1"], COMMON_D0),' + nl
        + '        "CV": ("env_CC.txt", ["OXCE_AI_HIVE=2", "OXCE_AI_HIVE_CONTACT=1", "OXCE_AI_HIVE_SAVE_TURN=3"], COMMON_D0),' + nl
    )
    head = block[:close].rstrip()
    if not head.endswith(","):
        head += ","
    path.write_bytes(text.replace(block, head + nl + add + block[close:]).encode("utf-8"))
    print("arms added")

# env
env = (T / "env_HH.txt").read_bytes().decode("utf-8").replace("/exe/HH/", "/exe/CC/")
(T / "env_CC.txt").write_bytes(env.encode("utf-8"))
envl = (T / "env_HL.txt").read_bytes().decode("utf-8").replace("/exe/HH/", "/exe/CC/")
nl = "\r\n" if "\r\n" in envl else "\n"
if "OXCE_AI_HIVE_CONTACT" not in envl:
    envl = envl.rstrip("\r\n") + nl + "OXCE_AI_HIVE_CONTACT=1" + nl
(T / "env_CL.txt").write_bytes(envl.encode("utf-8"))

# load runner
py = (H / "load_hh.py").read_bytes().decode("utf-8")
py = py.replace("env_HL.txt", "env_CL.txt").replace('_HL_M3_s1_w0', '_CL_M3_s1_w0').replace("--turns 9", "--turns 8").replace("default=9", "default=8")
py = py.replace("HIVE hardening, runs 7 and 8: the battle save of run 6", "CONTACT_COORDINATION_V0, run 7: the battle save of run 6").replace("arm HL", "arm CL")
(T / "load_cc.py").write_bytes(py.encode("utf-8"))
ps = (H / "load_hh.ps1").read_bytes().decode("utf-8")
ps = ps.replace("load_hh.py", "load_cc.py").replace("[int]$Turns = 9", "[int]$Turns = 8").replace("HIVE hardening", "CONTACT_COORDINATION_V0")
(T / "load_cc.ps1").write_bytes(ps.encode("utf-8"))
print("env and load runner written; bom in ps1:", (T / "load_cc.ps1").read_bytes()[:3] == b"\xef\xbb\xbf")
