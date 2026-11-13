#!/bin/sh
# CONTACT_COORDINATION_V0: exe CC (hive/cc/tree), its BUILD_INFO and cc.diff, the runner, env files and the load runner to rabota (C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/CC"
cp "$S/hive/cc/b-c/bin/$X" "$T/exe/CC/$X"
py -3.13 -I "$S/hive/cc/make_cc.py"
grep EXE "$T/env_CC.txt" "$T/env_CL.txt"
diff -u "$S/hive/tree/src/Battlescape/HiveCommand.cpp" "$S/hive/cc/tree/src/Battlescape/HiveCommand.cpp" > "$S/hive/cc/cc.diff" || true
( cd "$S/hive/tree/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/hive/cc/tree/src/$f" || echo "differs from HH: $f"; done )
d=$(sha256sum "$S/hive/cc/cc.diff" | cut -d' ' -f1)
c=$(cat "$S/hive/cc/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/CC/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-CC\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "HH + CONTACT_COORDINATION_V0 (OXCE_AI_HIVE_CONTACT=1 over OXCE_AI_HIVE=2)" "$d" "$h" > "$T/exe/CC/BUILD_INFO.txt"
cut -c1-120 "$T/exe/CC/BUILD_INFO.txt"
( cd "$T" && sha256sum "exe/D0/$X" "exe/HH/$X" "exe/CC/$X" exe/D0/BUILD_INFO.txt exe/HH/BUILD_INFO.txt exe/CC/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_HH.txt env_CC.txt env_CL.txt load_cc.py load_cc.ps1 > SHA256SUMS.txt )
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\CC mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\CC" 2>/dev/null
scp -q -i "$K" "$T/exe/CC/$X" "$T/exe/CC/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/CC/" 2>/dev/null
scp -q -i "$K" "$S/hive/cc/cc.diff" "$T/run_cm.py" "$T/env_CC.txt" "$T/env_CL.txt" "$T/load_cc.py" "$T/load_cc.ps1" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3 | cut -c1-200
