"""RESTORE COMBAT AUTONOMY: the stage's scripts from those of CONTACT_COORDINATION (hive/cc), its arms in cm/st/run_cm.py, env file (exe RA). Run once before the build; run again is harmless."""
import re
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
T = S / "cm" / "st"
C = S / "hive" / "cc"
R = S / "hive" / "ra"


def conv(name, new, pairs):
    text = (C / name).read_bytes().decode("utf-8")
    for a, b in pairs:
        if a not in text:
            raise SystemExit(f"{name}: no {a[:60]}")
        text = text.replace(a, b)
    (R / new).write_bytes(text.encode("utf-8"))


conv("build_cc.sh", "build_ra.sh", [
    ("CONTACT_COORDINATION_V0: exe from the isolated tree hive/cc/tree (a copy of hive/tree + patch_cc.py)", "RESTORE COMBAT AUTONOMY: exe from the isolated tree hive/ra/tree (a copy of hive/cc/tree + patch_ra.py)"),
    ('W="$S/hive/cc"', 'W="$S/hive/ra"'), ("b-c", "b-a"), ("ninja-c.log", "ninja-a.log"), ("sh build_cc.sh", "sh build_ra.sh"),
])
conv("run_cc.sh", "run_ra.sh", [
    ("CONTACT_COORDINATION_V0: one run of the declared list (hive/cc/GATES_AND_RUN_LIST.md)", "RESTORE COMBAT AUTONOMY: one run of the declared list (hive/ra/GATES_AND_RUN_LIST.md)"),
    ("sh run_cc.sh <no> <arm> <scen> <seed>   or   sh run_cc.sh <no> LOAD", "sh run_ra.sh <no> <arm> <scen> <seed>   or   sh run_ra.sh <no> LOAD"),
    ('P="cc$1"', 'P="ra$1"'), ('D="$S/hive/cc/runs_done.txt"', 'D="$S/hive/ra/runs_done.txt"'), ("load_cc.ps1", "load_ra_unused.ps1"),
])
run = (R / "run_ra.sh").read_bytes().decode("utf-8")
run2 = re.sub(r'-ge \d+ \] && \{ echo "the limit of \d+ is spent"', '-ge 6 ] && { echo "the limit of 6 is spent"', run)
if '-ge 6 ]' not in run2:
    raise SystemExit("run_ra.sh: no limit line")
(R / "run_ra.sh").write_bytes(run2.encode("utf-8"))

# arms
path = T / "run_cm.py"
text = path.read_bytes().decode("utf-8")
if '"AN":' in text:
    print("arms are there")
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r"ARMS = \{.*?\n\}|ARMS = \{.*?\}\s*\n", text, re.S)
    block = m.group(0)
    close = block.rstrip().rfind("}")
    on = '"OXCE_AI_HIVE=2", "OXCE_AI_HIVE_CONTACT=1"'
    add = (
        "        # RESTORE COMBAT AUTONOMY (GO Vitali 05.11, at most 6 short runs): exe RA; AO - no headquarters, AF - the flag off, AN - on, AV - on, with the battle save on turn 3" + nl
        + '        "AO": ("env_RA.txt", [], COMMON_D0),' + nl
        + f'        "AF": ("env_RA.txt", [{on}], COMMON_D0), "AN": ("env_RA.txt", [{on}, "OXCE_AI_HIVE_AUTONOMY=1"], COMMON_D0),' + nl
        + f'        "AV": ("env_RA.txt", [{on}, "OXCE_AI_HIVE_AUTONOMY=1", "OXCE_AI_HIVE_SAVE_TURN=3"], COMMON_D0),' + nl
    )
    head = block[:close].rstrip()
    if not head.endswith(","):
        head += ","
    path.write_bytes(text.replace(block, head + nl + add + block[close:]).encode("utf-8"))
    print("arms added")

# env
env = (T / "env_CC.txt").read_bytes().decode("utf-8").replace("/exe/CC/", "/exe/RA/")
(T / "env_RA.txt").write_bytes(env.encode("utf-8"))
print("written")
