"""HIVE D2 CORRECTION: the stage's scripts from those of UNIFIED ARMY SAFETY (hive/us), its arms in cm/st/run_cm.py, env file (exe D2). Run again is harmless."""
import re
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
T = S / "cm" / "st"
C = S / "hive" / "us"
U = S / "hive" / "d2"


def conv(name, new, pairs):
    text = (C / name).read_bytes().decode("utf-8")
    for a, b in pairs:
        if a not in text:
            raise SystemExit(f"{name}: no {a[:60]}")
        text = text.replace(a, b)
    (U / new).write_bytes(text.encode("utf-8"))


conv("build_us.sh", "build_d2.sh", [
    ("UNIFIED ARMY SAFETY: exe from the isolated tree hive/us/tree (a copy of hive/ua/tree + patch_us.py)", "HIVE D2 CORRECTION: exe from the isolated tree hive/d2/tree (a copy of hive/us/tree + patch_d2.py)"),
    ('W="$S/hive/us"', 'W="$S/hive/d2"'), ("b-s", "b-d"), ("ninja-s.log", "ninja-d.log"), ("sh build_us.sh", "sh build_d2.sh"),
])
conv("run_us.sh", "run_d2.sh", [
    ("UNIFIED ARMY SAFETY: one run of the declared list (HIVE_UNIFIED_ARMY_SAFETY_PLAN.md)", "HIVE D2 CORRECTION: one run of the declared list (HIVE_UA_D2_CORRECTION_PLAN.md)"),
    ("sh run_us.sh", "sh run_d2.sh"),
    ('P="us$1"', 'P="d2$1"'), ('D="$S/hive/us/runs_done.txt"', 'D="$S/hive/d2/runs_done.txt"'),
])
conv("up_us.sh", "up_d2.sh", [
    ("UNIFIED ARMY SAFETY: exe US (hive/us/tree), its BUILD_INFO and us.diff", "HIVE D2 CORRECTION: exe D2 (hive/d2/tree), its BUILD_INFO and d2.diff"),
    ("hive/us/", "hive/d2/"), ("hive/ua/", "hive/us/"), ("us.diff", "d2.diff"), ("/US", "/D2"), ("\\US", "\\D2"), ("env_US", "env_D2"), ("cmrun-US", "cmrun-D2"),
    ("b-s/", "b-d/"), ("make_us.py", "make_d2.py"), ("differs from UA", "differs from US"),
    ("UA + UNIFIED ARMY SAFETY: no map-wide step over scout=false, timings (OXCE_AI_HIVE=1 shadow, 2 active)", "US + HIVE D2 CORRECTION: a refused offer costs no try, the kept node is not taken away, timings (OXCE_AI_HIVE=1 shadow, 2 active)"),
])
left = (U / "up_d2.sh").read_text(encoding="utf-8")
bad = [w for w in ("/US/", "env_US", "us.diff", "b-s", "hive/ua") if w in left]
if bad:
    raise SystemExit(f"up_d2.sh: left {bad}")

# arms
path = T / "run_cm.py"
text = path.read_bytes().decode("utf-8")
if '"DN":' in text:
    print("arms are there")
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r"ARMS = \{.*?\n\}|ARMS = \{.*?\}\s*\n", text, re.S)
    block = m.group(0)
    close = block.rstrip().rfind("}")
    if '"DO"' in block or '"DS"' in block:
        raise SystemExit("arm names taken")
    add = (
        "        # HIVE D2 CORRECTION (GO Vitali 05.11, at most 6 short runs): exe D2; DO - no headquarters, DS - shadow, DN - active" + nl
        + '        "DO": ("env_D2.txt", [], COMMON_D0), "DS": ("env_D2.txt", ["OXCE_AI_HIVE=1"], COMMON_D0), "DN": ("env_D2.txt", ["OXCE_AI_HIVE=2"], COMMON_D0),' + nl
    )
    head = block[:close].rstrip()
    if not head.endswith(","):
        head += ","
    path.write_bytes(text.replace(block, head + nl + add + block[close:]).encode("utf-8"))
    print("arms added")

env = (T / "env_US.txt").read_bytes().decode("utf-8").replace("/exe/US/", "/exe/D2/")
(T / "env_D2.txt").write_bytes(env.encode("utf-8"))
print("written")
