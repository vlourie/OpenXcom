"""UNIFIED ARMY SAFETY: the stage's scripts from those of UNIFIED ARMY CONTROL V0 (hive/ua), its arms in cm/st/run_cm.py, env file (exe US). Run again is harmless."""
import re
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
T = S / "cm" / "st"
C = S / "hive" / "ua"
U = S / "hive" / "us"


def conv(name, new, pairs):
    text = (C / name).read_bytes().decode("utf-8")
    for a, b in pairs:
        if a not in text:
            raise SystemExit(f"{name}: no {a[:60]}")
        text = text.replace(a, b)
    (U / new).write_bytes(text.encode("utf-8"))


conv("build_ua.sh", "build_us.sh", [
    ("UNIFIED ARMY CONTROL V0: exe from the isolated tree hive/ua/tree (a copy of hive/ra/tree + patch_ua.py)", "UNIFIED ARMY SAFETY: exe from the isolated tree hive/us/tree (a copy of hive/ua/tree + patch_us.py)"),
    ('W="$S/hive/ua"', 'W="$S/hive/us"'), ("b-u", "b-s"), ("ninja-u.log", "ninja-s.log"), ("sh build_ua.sh", "sh build_us.sh"),
])
conv("run_ua.sh", "run_us.sh", [
    ("UNIFIED ARMY CONTROL V0: one run of the declared list (HIVE_UNIFIED_ARMY_CONTROL_V0_DESIGN.md)", "UNIFIED ARMY SAFETY: one run of the declared list (HIVE_UNIFIED_ARMY_SAFETY_PLAN.md)"),
    ("sh run_ua.sh <no> <arm> <scen> <seed>   or   sh run_ua.sh <no> LOAD <save label> <save file>", "sh run_us.sh <no> <arm> <scen> <seed>"),
    ('P="ua$1"', 'P="us$1"'), ('D="$S/hive/ua/runs_done.txt"', 'D="$S/hive/us/runs_done.txt"'), ("-ge 12 ]", "-ge 6 ]"), ("the limit of 12", "the limit of 6"),
])
conv("up_ua.sh", "up_us.sh", [
    ("UNIFIED ARMY CONTROL V0: exe UA (hive/ua/tree), its BUILD_INFO and ua.diff", "UNIFIED ARMY SAFETY: exe US (hive/us/tree), its BUILD_INFO and us.diff"),
    ('"$T/exe/UA"', '"$T/exe/US"'), ('hive/ua/b-u/bin/$X" "$T/exe/UA/$X"', 'hive/us/b-s/bin/$X" "$T/exe/US/$X"'), ("hive/ua/make_ua.py", "hive/us/make_us.py"),
    ('grep EXE "$T/env_UA.txt"', 'grep EXE "$T/env_US.txt"'),
    (': > "$S/hive/ua/ua.diff"', ': > "$S/hive/us/us.diff"'),
    ('diff -u "$S/hive/ra/tree/src/$f" "$S/hive/ua/tree/src/$f" >> "$S/hive/ua/ua.diff"', 'diff -u "$S/hive/ua/tree/src/$f" "$S/hive/us/tree/src/$f" >> "$S/hive/us/us.diff"'),
    ('cd "$S/hive/ra/tree/src"', 'cd "$S/hive/ua/tree/src"'),
    ('cmp -s "$f" "$S/hive/ua/tree/src/$f" || echo "differs from RA: $f"', 'cmp -s "$f" "$S/hive/us/tree/src/$f" || echo "differs from UA: $f"'),
    ('sha256sum "$S/hive/ua/ua.diff"', 'sha256sum "$S/hive/us/us.diff"'), ('cat "$S/hive/ua/tree/GIT_COMMIT.txt"', 'cat "$S/hive/us/tree/GIT_COMMIT.txt"'),
    ('sha256sum "$T/exe/UA/$X"', 'sha256sum "$T/exe/US/$X"'), ("build_label=cmrun-UA", "build_label=cmrun-US"),
    ("RA minus orders and stand + UNIFIED ARMY CONTROL V0 (OXCE_AI_HIVE=1 shadow, 2 active)", "UA + UNIFIED ARMY SAFETY: no map-wide step over scout=false, timings (OXCE_AI_HIVE=1 shadow, 2 active)"),
    ('"$T/exe/UA/BUILD_INFO.txt"', '"$T/exe/US/BUILD_INFO.txt"'),
    ("cmrun\\\\exe\\\\UA mkdir C:\\\\OXCE_AIWorker\\\\cmrun\\\\exe\\\\UA", "cmrun\\\\exe\\\\US mkdir C:\\\\OXCE_AIWorker\\\\cmrun\\\\exe\\\\US"),
    ('scp -q -i "$K" "$T/exe/UA/$X"', 'scp -q -i "$K" "$T/exe/US/$X"'), ('"$H:C:/OXCE_AIWorker/cmrun/exe/UA/"', '"$H:C:/OXCE_AIWorker/cmrun/exe/US/"'),
    ('"exe/UA/$X" exe/D0/BUILD_INFO.txt exe/UA/BUILD_INFO.txt', '"exe/US/$X" exe/D0/BUILD_INFO.txt exe/US/BUILD_INFO.txt'), ("env_D0.txt env_UA.txt", "env_D0.txt env_US.txt"),
    ('"$S/hive/ua/ua.diff" "$T/run_cm.py" "$T/env_UA.txt"', '"$S/hive/us/us.diff" "$T/run_cm.py" "$T/env_US.txt"'),
])
left = (U / "up_us.sh").read_text(encoding="utf-8")
bad = [w for w in ("/UA", "env_UA", "ua.diff", "b-u") if w in left]
if bad:
    raise SystemExit(f"up_us.sh: left {bad}")

# arms
path = T / "run_cm.py"
text = path.read_bytes().decode("utf-8")
if '"QN":' in text:
    print("arms are there")
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r"ARMS = \{.*?\n\}|ARMS = \{.*?\}\s*\n", text, re.S)
    block = m.group(0)
    close = block.rstrip().rfind("}")
    if '"QO"' in block or '"QS"' in block:
        raise SystemExit("arm names taken")
    add = (
        "        # HIVE UNIFIED ARMY SAFETY (GO Vitali 05.11, at most 6 short runs): exe US; QO - no headquarters, QS - shadow, QN - active" + nl
        + '        "QO": ("env_US.txt", [], COMMON_D0), "QS": ("env_US.txt", ["OXCE_AI_HIVE=1"], COMMON_D0), "QN": ("env_US.txt", ["OXCE_AI_HIVE=2"], COMMON_D0),' + nl
    )
    head = block[:close].rstrip()
    if not head.endswith(","):
        head += ","
    path.write_bytes(text.replace(block, head + nl + add + block[close:]).encode("utf-8"))
    print("arms added")

env = (T / "env_UA.txt").read_bytes().decode("utf-8").replace("/exe/UA/", "/exe/US/")
(T / "env_US.txt").write_bytes(env.encode("utf-8"))
print("written")
