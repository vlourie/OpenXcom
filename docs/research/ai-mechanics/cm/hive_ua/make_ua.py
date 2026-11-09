"""UNIFIED ARMY CONTROL V0: the stage's scripts from those of COMBAT INTENT V0 (hive/ci), its arms in cm/st/run_cm.py, env file (exe UA). Run again is harmless."""
import re
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
T = S / "cm" / "st"
C = S / "hive" / "ci"
U = S / "hive" / "ua"


def conv(name, new, pairs):
    text = (C / name).read_bytes().decode("utf-8")
    for a, b in pairs:
        if a not in text:
            raise SystemExit(f"{name}: no {a[:60]}")
        text = text.replace(a, b)
    (U / new).write_bytes(text.encode("utf-8"))


conv("build_ci.sh", "build_ua.sh", [
    ("HIVE COMBAT INTENT V0: exe from the isolated tree hive/ci/tree (a copy of hive/ra/tree + patch_ci.py)", "UNIFIED ARMY CONTROL V0: exe from the isolated tree hive/ua/tree (a copy of hive/ra/tree + patch_ua.py)"),
    ('W="$S/hive/ci"', 'W="$S/hive/ua"'), ("b-i", "b-u"), ("ninja-i.log", "ninja-u.log"), ("sh build_ci.sh", "sh build_ua.sh"),
])
conv("run_ci.sh", "run_ua.sh", [
    ("HIVE COMBAT INTENT V0: one run of the declared list (hive/ci/GATES_AND_RUN_LIST.md)", "UNIFIED ARMY CONTROL V0: one run of the declared list (HIVE_UNIFIED_ARMY_CONTROL_V0_DESIGN.md)"),
    ("sh run_ci.sh <no> <arm> <scen> <seed>   or   sh run_ci.sh <no> LOAD", "sh run_ua.sh <no> <arm> <scen> <seed>   or   sh run_ua.sh <no> LOAD"),
    ('P="ci$1"', 'P="ua$1"'), ('D="$S/hive/ci/runs_done.txt"', 'D="$S/hive/ua/runs_done.txt"'), ("-ge 8 ]", "-ge 12 ]"), ("the limit of 8", "the limit of 12"),
    ("load_ci_unused.ps1", "load_ua.ps1"),
])
conv("up_ci.sh", "up_ua.sh", [
    ("HIVE COMBAT INTENT V0: exe CI (hive/ci/tree), its BUILD_INFO and ci.diff", "UNIFIED ARMY CONTROL V0: exe UA (hive/ua/tree), its BUILD_INFO and ua.diff"),
    ('"$T/exe/CI"', '"$T/exe/UA"'), ('hive/ci/b-i/bin/$X" "$T/exe/CI/$X"', 'hive/ua/b-u/bin/$X" "$T/exe/UA/$X"'), ("hive/ci/make_ci.py", "hive/ua/make_ua.py"),
    ('grep EXE "$T/env_CI.txt"', 'grep EXE "$T/env_UA.txt"'),
    (': > "$S/hive/ci/ci.diff"', ': > "$S/hive/ua/ua.diff"'),
    ("for f in HiveCommand.h HiveCommand.cpp AIModule.h AIModule.cpp; do", "for f in Battlescape/HiveCommand.h Battlescape/HiveCommand.cpp Battlescape/AIModule.h Battlescape/AIModule.cpp Savegame/SavedBattleGame.h Savegame/SavedBattleGame.cpp; do"),
    ('diff -u "$S/hive/ra/tree/src/Battlescape/$f" "$S/hive/ci/tree/src/Battlescape/$f" >> "$S/hive/ci/ci.diff"', 'diff -u "$S/hive/ra/tree/src/$f" "$S/hive/ua/tree/src/$f" >> "$S/hive/ua/ua.diff"'),
    ('cmp -s "$f" "$S/hive/ci/tree/src/$f"', 'cmp -s "$f" "$S/hive/ua/tree/src/$f"'),
    ('sha256sum "$S/hive/ci/ci.diff"', 'sha256sum "$S/hive/ua/ua.diff"'), ('cat "$S/hive/ci/tree/GIT_COMMIT.txt"', 'cat "$S/hive/ua/tree/GIT_COMMIT.txt"'),
    ('sha256sum "$T/exe/CI/$X"', 'sha256sum "$T/exe/UA/$X"'), ("build_label=cmrun-CI", "build_label=cmrun-UA"),
    ("RA + COMBAT INTENT V0 (OXCE_AI_HIVE_INTENT=1 shadow, 2 active, over OXCE_AI_HIVE=2, OXCE_AI_HIVE_CONTACT=1, OXCE_AI_HIVE_AUTONOMY=1)", "RA minus orders and stand + UNIFIED ARMY CONTROL V0 (OXCE_AI_HIVE=1 shadow, 2 active)"),
    ('"$T/exe/CI/BUILD_INFO.txt"', '"$T/exe/UA/BUILD_INFO.txt"'),
    ("cmrun\\\\exe\\\\CI mkdir C:\\\\OXCE_AIWorker\\\\cmrun\\\\exe\\\\CI", "cmrun\\\\exe\\\\UA mkdir C:\\\\OXCE_AIWorker\\\\cmrun\\\\exe\\\\UA"),
    ('scp -q -i "$K" "$T/exe/CI/$X"', 'scp -q -i "$K" "$T/exe/UA/$X"'), ('"$H:C:/OXCE_AIWorker/cmrun/exe/CI/"', '"$H:C:/OXCE_AIWorker/cmrun/exe/UA/"'),
    ('"exe/CI/$X" exe/D0/BUILD_INFO.txt exe/CI/BUILD_INFO.txt', '"exe/UA/$X" exe/D0/BUILD_INFO.txt exe/UA/BUILD_INFO.txt'), ("env_D0.txt env_CI.txt", "env_D0.txt env_UA.txt"),
    ('"$S/hive/ci/ci.diff" "$T/run_cm.py" "$T/env_CI.txt"', '"$S/hive/ua/ua.diff" "$T/run_cm.py" "$T/env_UA.txt"'),
])
left = (U / "up_ua.sh").read_text(encoding="utf-8")
bad = [w for w in ("/CI", "env_CI", "ci.diff", "hive/ci", "b-i") if w in left]
if bad:
    raise SystemExit(f"up_ua.sh: left {bad}")

# arms
path = T / "run_cm.py"
text = path.read_bytes().decode("utf-8")
if '"UN":' in text:
    print("arms are there")
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r"ARMS = \{.*?\n\}|ARMS = \{.*?\}\s*\n", text, re.S)
    block = m.group(0)
    close = block.rstrip().rfind("}")
    add = (
        "        # HIVE UNIFIED ARMY CONTROL V0 (GO Vitali 05.11, at most 12 short runs): exe UA; UO - no headquarters, US - shadow, UN - active, UV - active, with the battle save on turn 3" + nl
        + '        "UO": ("env_UA.txt", [], COMMON_D0), "US": ("env_UA.txt", ["OXCE_AI_HIVE=1"], COMMON_D0), "UN": ("env_UA.txt", ["OXCE_AI_HIVE=2"], COMMON_D0),' + nl
        + '        "UV": ("env_UA.txt", ["OXCE_AI_HIVE=2", "OXCE_AI_HIVE_SAVE_TURN=3"], COMMON_D0),' + nl
    )
    head = block[:close].rstrip()
    if not head.endswith(","):
        head += ","
    path.write_bytes(text.replace(block, head + nl + add + block[close:]).encode("utf-8"))
    print("arms added")

# env
env = (T / "env_RA.txt").read_bytes().decode("utf-8").replace("/exe/RA/", "/exe/UA/")
(T / "env_UA.txt").write_bytes(env.encode("utf-8"))
print("written")
