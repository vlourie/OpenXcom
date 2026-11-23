#!/bin/sh
# commander stage: the cmrun package for the work machine (rabota) - exe CM from HEAD, stand scripts of HEAD, the C1 saves
# and scenarios, runner and scripts; then cm_prep.ps1 there (stand2's scenario/missions and envrun.py copied, sums checked)
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/CM" "$T/saves" "$T/stand"
cp "$S/cm/b-cmdev/bin/$X" "$T/exe/CM/$X"
h=$(sha256sum "$T/exe/CM/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-CM\ngit_commit=%s\nnote=DEV (OXCE_AI_DEV=ON, Release) from clean HEAD, git archive in cm/tree\nexe_sha256=%s\n' "$(cat "$S/cm/tree/GIT_COMMIT.txt")" "$h" > "$T/exe/CM/BUILD_INFO.txt"
cp "$S/c1/station/saves/"*.sav "$T/saves/"
cp "$S/c1/station/scen.tsv" "$T/scen.tsv"
# stand2's stand-adapted copies (as C1/AS, same sums as rabota's stand2); tools/ of HEAD is the local variant
cp "$S/c1/ai_arena.py" "$S/c1/ai_probe.py" "$T/stand/"
rm -f "$T/cmrun.py"
( cd "$T" && sha256sum "exe/CM/$X" exe/CM/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_CM.txt cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
cat "$T/SHA256SUMS.txt"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force C:\\OXCE_AIWorker\\cmrun\\exe\\CM,C:\\OXCE_AIWorker\\cmrun\\saves,C:\\OXCE_AIWorker\\cmrun\\stand | Out-Null\""
scp -q -i "$K" "$T/exe/CM/$X" "$T/exe/CM/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/CM/"
scp -q -i "$K" "$T/saves/"*.sav "$H:C:/OXCE_AIWorker/cmrun/saves/"
scp -q -i "$K" "$T/stand/ai_arena.py" "$T/stand/ai_probe.py" "$H:C:/OXCE_AIWorker/cmrun/stand/"
scp -q -i "$K" "$T/run_cm.py" "$T/env_CM.txt" "$T/scen.tsv" "$T/cm_launch.ps1" "$T/cm_prep.ps1" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" | tr -d '\r'
