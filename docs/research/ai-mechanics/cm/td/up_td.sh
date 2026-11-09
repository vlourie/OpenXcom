#!/bin/sh
# AI_TACTICAL_DIRECTOR_V1: exe TD (td/tree: HEAD + al.diff + al3.diff + the director, DEV), the runner with arms O/T, env_TD and
# the launcher to the work machine (rabota, C:/OXCE_AIWorker/cmrun); then prep (sums)
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/TD"
cp "$S/td/b-tddev/bin/$X" "$T/exe/TD/$X"
( cd "$S/td" && { diff -u ../ce/AIModule.d0.cpp tree/src/Battlescape/AIModule.cpp > td.diff || true; }; diff -u ../ce/AIModule.d0.h tree/src/Battlescape/AIModule.h >> td.diff || true )
d=$(sha256sum "$S/td/td.diff" | cut -d' ' -f1)
c=$(cat "$S/td/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/TD/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-TD\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "DEV HEAD + al.diff + al3.diff + AI_TACTICAL_DIRECTOR_V1 (AIModule.cpp/.h), flag OXCE_AI_TACTICAL_DIRECTOR" "$d" "$h" > "$T/exe/TD/BUILD_INFO.txt"
( cd "$T" && sha256sum "exe/CM/$X" "exe/SR/$X" "exe/D0/$X" "exe/CE/$X" "exe/TD/$X" exe/*/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_CM.txt env_SR.txt env_D0.txt env_CE.txt env_TD.txt make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
grep -E "TD|run_cm|launch" "$T/SHA256SUMS.txt"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force C:\\OXCE_AIWorker\\cmrun\\exe\\TD | Out-Null\""
scp -q -i "$K" "$T/exe/TD/$X" "$T/exe/TD/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/TD/"
scp -q -i "$K" "$S/td/td.diff" "$T/run_cm.py" "$T/env_TD.txt" "$T/cm_launch.ps1" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" | tr -d '\r' | head -3
