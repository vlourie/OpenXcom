#!/bin/sh
# HIVE COMBAT INTENT V0: exe CI (hive/ci/tree), its BUILD_INFO and ci.diff, the runner and env file to rabota (C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/CI"
cp "$S/hive/ci/b-i/bin/$X" "$T/exe/CI/$X"
py -3.13 -I "$S/hive/ci/make_ci.py"
grep EXE "$T/env_CI.txt"
: > "$S/hive/ci/ci.diff"
for f in HiveCommand.h HiveCommand.cpp AIModule.h AIModule.cpp; do
	diff -u "$S/hive/ra/tree/src/Battlescape/$f" "$S/hive/ci/tree/src/Battlescape/$f" >> "$S/hive/ci/ci.diff" || true
done
( cd "$S/hive/ra/tree/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/hive/ci/tree/src/$f" || echo "differs from RA: $f"; done )
d=$(sha256sum "$S/hive/ci/ci.diff" | cut -d' ' -f1)
c=$(cat "$S/hive/ci/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/CI/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-CI\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "RA + COMBAT INTENT V0 (OXCE_AI_HIVE_INTENT=1 shadow, 2 active, over OXCE_AI_HIVE=2, OXCE_AI_HIVE_CONTACT=1, OXCE_AI_HIVE_AUTONOMY=1)" "$d" "$h" > "$T/exe/CI/BUILD_INFO.txt"
cut -c1-120 "$T/exe/CI/BUILD_INFO.txt"
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\CI mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\CI" 2>/dev/null
scp -q -i "$K" "$T/exe/CI/$X" "$T/exe/CI/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/CI/" 2>/dev/null
( cd "$T" && sha256sum "exe/D0/$X" "exe/CI/$X" exe/D0/BUILD_INFO.txt exe/CI/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_CI.txt > SHA256SUMS.txt )
scp -q -i "$K" "$S/hive/ci/ci.diff" "$T/run_cm.py" "$T/env_CI.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3 | cut -c1-200
