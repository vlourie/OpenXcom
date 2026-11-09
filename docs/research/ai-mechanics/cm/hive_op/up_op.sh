#!/bin/sh
# HIVE COORDINATED OPERATION V0: exe OP (hive/op/tree), its BUILD_INFO and op.diff, the runner and env file to rabota (C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/OP"
cp "$S/hive/op/b-o/bin/$X" "$T/exe/OP/$X"
py -3.13 -I "$S/hive/op/make_op.py"
grep EXE "$T/env_OP.txt"
: > "$S/hive/op/op.diff"
for f in HiveCommand.h HiveCommand.cpp AIModule.h AIModule.cpp; do
	diff -u "$S/hive/ci/tree/src/Battlescape/$f" "$S/hive/op/tree/src/Battlescape/$f" >> "$S/hive/op/op.diff" || true
done
( cd "$S/hive/ci/tree/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/hive/op/tree/src/$f" || echo "differs from CI: $f"; done )
d=$(sha256sum "$S/hive/op/op.diff" | cut -d' ' -f1)
c=$(cat "$S/hive/op/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/OP/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-OP\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "CI + COORDINATED OPERATION V0 (OXCE_AI_HIVE_OP=1 shadow, 2 active, over OXCE_AI_HIVE=1)" "$d" "$h" > "$T/exe/OP/BUILD_INFO.txt"
cut -c1-120 "$T/exe/OP/BUILD_INFO.txt"
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\OP mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\OP" 2>/dev/null
scp -q -i "$K" "$T/exe/OP/$X" "$T/exe/OP/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/OP/" 2>/dev/null
( cd "$T" && sha256sum "exe/D0/$X" "exe/OP/$X" exe/D0/BUILD_INFO.txt exe/OP/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_OP.txt > SHA256SUMS.txt )
scp -q -i "$K" "$S/hive/op/op.diff" "$T/run_cm.py" "$T/env_OP.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3 | cut -c1-200
