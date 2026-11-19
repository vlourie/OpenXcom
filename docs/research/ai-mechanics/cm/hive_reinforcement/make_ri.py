"""REINFORCEMENT INTELLIGENCE V0: the stage's scripts from those of CONTACT_COORDINATION (hive/cc), its arms in cm/st/run_cm.py, env files and load runner (exe RI). Run once before the build; run again is harmless."""
import re
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
T = S / "cm" / "st"
C = S / "hive" / "cc"
R = S / "hive" / "ri"


def conv(name, new, pairs):
    text = (C / name).read_bytes().decode("utf-8")
    for a, b in pairs:
        if a not in text:
            raise SystemExit(f"{name}: no {a[:60]}")
        text = text.replace(a, b)
    (R / new).write_bytes(text.encode("utf-8"))


conv("build_cc.sh", "build_ri.sh", [
    ("CONTACT_COORDINATION_V0: exe from the isolated tree hive/cc/tree (a copy of hive/tree + patch_cc.py)", "REINFORCEMENT INTELLIGENCE V0: exe from the isolated tree hive/ri/tree (a copy of hive/cc/tree + patch_ri.py)"),
    ('W="$S/hive/cc"', 'W="$S/hive/ri"'), ("b-c", "b-r"), ("ninja-c.log", "ninja-r.log"), ("sh build_cc.sh", "sh build_ri.sh"),
])
conv("run_cc.sh", "run_ri.sh", [
    ("CONTACT_COORDINATION_V0: one run of the declared list (hive/cc/GATES_AND_RUN_LIST.md)", "REINFORCEMENT INTELLIGENCE V0: one run of the declared list (hive/ri/GATES_AND_RUN_LIST.md)"),
    ("sh run_cc.sh <no> <arm> <scen> <seed>   or   sh run_cc.sh <no> LOAD", "sh run_ri.sh <no> <arm> <scen> <seed>   or   sh run_ri.sh <no> LOAD"),
    ('P="cc$1"', 'P="ri$1"'), ('D="$S/hive/cc/runs_done.txt"', 'D="$S/hive/ri/runs_done.txt"'), ("load_cc.ps1", "load_ri.ps1"),
])

# arms
path = T / "run_cm.py"
text = path.read_bytes().decode("utf-8")
if '"RN":' in text:
    print("arms are there")
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r"ARMS = \{.*?\n\}|ARMS = \{.*?\}\s*\n", text, re.S)
    block = m.group(0)
    close = block.rstrip().rfind("}")
    on = '"OXCE_AI_HIVE=2", "OXCE_AI_HIVE_CONTACT=1"'
    add = (
        "        # REINFORCEMENT INTELLIGENCE V0 (GO Vitali 05.11, at most 8 short runs): exe RI; RF - the gate off, RN - on, RV - on, with the battle save on turn 3" + nl
        + f'        "RF": ("env_RI.txt", [{on}], COMMON_D0), "RN": ("env_RI.txt", [{on}, "OXCE_AI_HIVE_REINF=1"], COMMON_D0),' + nl
        + f'        "RV": ("env_RI.txt", [{on}, "OXCE_AI_HIVE_REINF=1", "OXCE_AI_HIVE_SAVE_TURN=3"], COMMON_D0),' + nl
    )
    head = block[:close].rstrip()
    if not head.endswith(","):
        head += ","
    path.write_bytes(text.replace(block, head + nl + add + block[close:]).encode("utf-8"))
    print("arms added")

# env
env = (T / "env_CC.txt").read_bytes().decode("utf-8").replace("/exe/CC/", "/exe/RI/")
(T / "env_RI.txt").write_bytes(env.encode("utf-8"))
envl = (T / "env_CL.txt").read_bytes().decode("utf-8").replace("/exe/CC/", "/exe/RI/")
nl = "\r\n" if "\r\n" in envl else "\n"
if "OXCE_AI_HIVE_REINF" not in envl:
    envl = envl.rstrip("\r\n") + nl + "OXCE_AI_HIVE_REINF=1" + nl
(T / "env_RL.txt").write_bytes(envl.encode("utf-8"))

# load runner
py = (T / "load_cc.py").read_bytes().decode("utf-8")
py = py.replace("env_CL.txt", "env_RL.txt").replace("_CL_M3_s1_w0", "_RL_M3_s1_w0").replace("CONTACT_COORDINATION_V0, run 7: the battle save of run 6", "REINFORCEMENT INTELLIGENCE V0, run 4: the battle save of run 3").replace("arm CL", "arm RL")
(T / "load_ri.py").write_bytes(py.encode("utf-8"))
ps = (T / "load_cc.ps1").read_bytes().decode("utf-8")
ps = ps.replace("load_cc.py", "load_ri.py").replace("CONTACT_COORDINATION_V0", "REINFORCEMENT INTELLIGENCE V0")
(T / "load_ri.ps1").write_bytes(ps.encode("utf-8"))
print("written; bom in ps1:", (T / "load_ri.ps1").read_bytes()[:3] == b"\xef\xbb\xbf")
print((T / "env_RL.txt").read_text(encoding="utf-8")[-160:])
