"""HIVE COMBAT INTENT V0: the stage's scripts from those of RESTORE COMBAT AUTONOMY (hive/ra), its arms in cm/st/run_cm.py, env file (exe CI). Run once before the build; run again is harmless."""
import re
from pathlib import Path

S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
T = S / "cm" / "st"
R = S / "hive" / "ra"
I = S / "hive" / "ci"


def conv(name, new, pairs):
    text = (R / name).read_bytes().decode("utf-8")
    for a, b in pairs:
        if a not in text:
            raise SystemExit(f"{name}: no {a[:60]}")
        text = text.replace(a, b)
    (I / new).write_bytes(text.encode("utf-8"))


conv("build_ra.sh", "build_ci.sh", [
    ("RESTORE COMBAT AUTONOMY: exe from the isolated tree hive/ra/tree (a copy of hive/cc/tree + patch_ra.py)", "HIVE COMBAT INTENT V0: exe from the isolated tree hive/ci/tree (a copy of hive/ra/tree + patch_ci.py)"),
    ('W="$S/hive/ra"', 'W="$S/hive/ci"'), ("b-a", "b-i"), ("ninja-a.log", "ninja-i.log"), ("sh build_ra.sh", "sh build_ci.sh"),
])
conv("run_ra.sh", "run_ci.sh", [
    ("RESTORE COMBAT AUTONOMY: one run of the declared list (hive/ra/GATES_AND_RUN_LIST.md)", "HIVE COMBAT INTENT V0: one run of the declared list (hive/ci/GATES_AND_RUN_LIST.md)"),
    ("sh run_ra.sh <no> <arm> <scen> <seed>   or   sh run_ra.sh <no> LOAD", "sh run_ci.sh <no> <arm> <scen> <seed>   or   sh run_ci.sh <no> LOAD"),
    ('P="ra$1"', 'P="ci$1"'), ('D="$S/hive/ra/runs_done.txt"', 'D="$S/hive/ci/runs_done.txt"'), ("-ge 6 ]", "-ge 8 ]"), ("the limit of 6", "the limit of 8"),
    ("load_ra_unused.ps1", "load_ci_unused.ps1"),
])
conv("up_ra.sh", "up_ci.sh", [
    ("RESTORE COMBAT AUTONOMY: exe RA (hive/ra/tree), its BUILD_INFO and ra.diff", "HIVE COMBAT INTENT V0: exe CI (hive/ci/tree), its BUILD_INFO and ci.diff"),
    ('"$T/exe/RA"', '"$T/exe/CI"'), ('hive/ra/b-a/bin/$X" "$T/exe/RA/$X"', 'hive/ci/b-i/bin/$X" "$T/exe/CI/$X"'), ("hive/ra/make_ra.py", "hive/ci/make_ci.py"),
    ('grep EXE "$T/env_RA.txt"', 'grep EXE "$T/env_CI.txt"'),
    (': > "$S/hive/ra/ra.diff"', ': > "$S/hive/ci/ci.diff"'),
    ('diff -u "$S/hive/cc/tree/src/Battlescape/$f" "$S/hive/ra/tree/src/Battlescape/$f" >> "$S/hive/ra/ra.diff"', 'diff -u "$S/hive/ra/tree/src/Battlescape/$f" "$S/hive/ci/tree/src/Battlescape/$f" >> "$S/hive/ci/ci.diff"'),
    ('cd "$S/hive/cc/tree/src"', 'cd "$S/hive/ra/tree/src"'), ('cmp -s "$f" "$S/hive/ra/tree/src/$f" || echo "differs from CC: $f"', 'cmp -s "$f" "$S/hive/ci/tree/src/$f" || echo "differs from RA: $f"'),
    ('sha256sum "$S/hive/ra/ra.diff"', 'sha256sum "$S/hive/ci/ci.diff"'), ('cat "$S/hive/ra/tree/GIT_COMMIT.txt"', 'cat "$S/hive/ci/tree/GIT_COMMIT.txt"'),
    ('sha256sum "$T/exe/RA/$X"', 'sha256sum "$T/exe/CI/$X"'), ("build_label=cmrun-RA", "build_label=cmrun-CI"),
    ("CC + RESTORE COMBAT AUTONOMY (OXCE_AI_HIVE_AUTONOMY=1 over OXCE_AI_HIVE=2 and OXCE_AI_HIVE_CONTACT=1)", "RA + COMBAT INTENT V0 (OXCE_AI_HIVE_INTENT=1 shadow, 2 active, over OXCE_AI_HIVE=2, OXCE_AI_HIVE_CONTACT=1, OXCE_AI_HIVE_AUTONOMY=1)"),
    ("cmrun\\\\exe\\\\RA mkdir C:\\\\OXCE_AIWorker\\\\cmrun\\\\exe\\\\RA", "cmrun\\\\exe\\\\CI mkdir C:\\\\OXCE_AIWorker\\\\cmrun\\\\exe\\\\CI"),
    ('scp -q -i "$K" "$T/exe/RA/$X" "$T/exe/RA/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/RA/"', 'scp -q -i "$K" "$T/exe/CI/$X" "$T/exe/CI/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/CI/"'),
    ('"exe/RA/$X" exe/D0/BUILD_INFO.txt exe/RA/BUILD_INFO.txt', '"exe/CI/$X" exe/D0/BUILD_INFO.txt exe/CI/BUILD_INFO.txt'), ("env_D0.txt env_RA.txt", "env_D0.txt env_CI.txt"),
    ('"$S/hive/ra/ra.diff" "$T/run_cm.py" "$T/env_RA.txt"', '"$S/hive/ci/ci.diff" "$T/run_cm.py" "$T/env_CI.txt"'),
    ('"$T/exe/RA/BUILD_INFO.txt"', '"$T/exe/CI/BUILD_INFO.txt"'),
])
bad = [w for w in ("/RA", "env_RA", "ra.diff", "hive/ra/b-a", "RA/") if w in (I / "up_ci.sh").read_text(encoding="utf-8").replace("hive/ra/tree", "")]
if bad:
    raise SystemExit(f"up_ci.sh: left {bad}")

# arms
path = T / "run_cm.py"
text = path.read_bytes().decode("utf-8")
if '"IA":' in text:
    print("arms are there")
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r"ARMS = \{.*?\n\}|ARMS = \{.*?\}\s*\n", text, re.S)
    block = m.group(0)
    close = block.rstrip().rfind("}")
    on = '"OXCE_AI_HIVE=2", "OXCE_AI_HIVE_CONTACT=1", "OXCE_AI_HIVE_AUTONOMY=1"'
    add = (
        "        # HIVE COMBAT INTENT V0 (GO Vitali 05.11, at most 8 short runs): exe CI; IO - no headquarters, IS - shadow, IA - active, IV - active, with the battle save on turn 3" + nl
        + '        "IO": ("env_CI.txt", [], COMMON_D0),' + nl
        + f'        "IS": ("env_CI.txt", [{on}, "OXCE_AI_HIVE_INTENT=1"], COMMON_D0), "IA": ("env_CI.txt", [{on}, "OXCE_AI_HIVE_INTENT=2"], COMMON_D0),' + nl
        + f'        "IV": ("env_CI.txt", [{on}, "OXCE_AI_HIVE_INTENT=2", "OXCE_AI_HIVE_SAVE_TURN=3"], COMMON_D0),' + nl
    )
    head = block[:close].rstrip()
    if not head.endswith(","):
        head += ","
    path.write_bytes(text.replace(block, head + nl + add + block[close:]).encode("utf-8"))
    print("arms added")

# env
env = (T / "env_RA.txt").read_bytes().decode("utf-8").replace("/exe/RA/", "/exe/CI/")
(T / "env_CI.txt").write_bytes(env.encode("utf-8"))
print("written")
