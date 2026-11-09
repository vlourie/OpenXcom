#!/bin/sh
# STAGE_RALLY_V1: exe SR (cm/tree with the rally patch, DEV) and the runner with arms A0/A/B to the work machine (rabota)
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/SR"
cp "$S/cm/b-cmdev/bin/$X" "$T/exe/SR/$X"
( cd "$S/cm" && diff -u base/AIModule.cpp tree/src/Battlescape/AIModule.cpp > sr.diff || true )
h=$(sha256sum "$T/exe/SR/$X" | cut -d' ' -f1)
d=$(sha256sum "$S/cm/sr.diff" | cut -d' ' -f1)
printf 'build_label=cmrun-SR\ngit_commit=%s\nnote=DEV (OXCE_AI_DEV=ON, Release) HEAD + STAGE_RALLY_V1 (AIModule.cpp only), flag OXCE_AI_STAGE_RALLY (1 scouts, 2 every patrol)\npatch_sha256=%s\nexe_sha256=%s\n' "$(cat "$S/cm/tree/GIT_COMMIT.txt")" "$d" "$h" > "$T/exe/SR/BUILD_INFO.txt"
( cd "$T" && sha256sum "exe/CM/$X" "exe/SR/$X" exe/CM/BUILD_INFO.txt exe/SR/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_CM.txt env_SR.txt cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
grep -E "SR|run_cm" "$T/SHA256SUMS.txt"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force C:\\OXCE_AIWorker\\cmrun\\exe\\SR | Out-Null\""
scp -q -i "$K" "$T/exe/SR/$X" "$T/exe/SR/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/SR/"
scp -q -i "$K" "$S/cm/sr.diff" "$T/run_cm.py" "$T/env_SR.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" | tr -d '\r' | head -3
