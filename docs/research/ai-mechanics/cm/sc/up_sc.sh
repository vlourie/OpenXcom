#!/bin/sh
# SIDE_TURN_ACTION_SCHEDULER stage 2: exe SC (sc/tree: HEAD + al.diff + al3.diff + the scheduler, DEV), the runner with arms Q/S,
# env_SC and the launcher to the work machine (rabota, C:/OXCE_AIWorker/cmrun); then prep (sums)
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/SC"
cp "$S/sc/b-scdev/bin/$X" "$T/exe/SC/$X"
D0="$S/td/tree/src/Battlescape"
N="$S/sc/tree/src/Battlescape"
( cd "$S/sc" && : > sc.diff && for f in AiProbe.h AiProbe.cpp BattlescapeGame.cpp; do diff -u --strip-trailing-cr "$D0/$f" "$N/$f" >> sc.diff || true; done )
cmp -s "$S/ce/AIModule.d0.cpp" "$N/AIModule.cpp" && cmp -s "$S/ce/AIModule.d0.h" "$N/AIModule.h" && echo "AIModule = D0"
d=$(sha256sum "$S/sc/sc.diff" | cut -d' ' -f1)
c=$(cat "$S/sc/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/SC/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-SC\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "DEV HEAD + al.diff + al3.diff + SIDE_TURN_ACTION_SCHEDULER stage 2 (AiProbe.cpp/.h, BattlescapeGame.cpp), flag OXCE_AI_SCHEDULER" "$d" "$h" > "$T/exe/SC/BUILD_INFO.txt"
( cd "$T" && sha256sum "exe/D0/$X" "exe/TD/$X" "exe/SC/$X" exe/D0/BUILD_INFO.txt exe/TD/BUILD_INFO.txt exe/SC/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_TD.txt env_SC.txt make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
grep -E "SC|run_cm" "$T/SHA256SUMS.txt"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force C:\\OXCE_AIWorker\\cmrun\\exe\\SC | Out-Null\""
scp -q -i "$K" "$T/exe/SC/$X" "$T/exe/SC/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/SC/"
scp -q -i "$K" "$S/sc/sc.diff" "$T/run_cm.py" "$T/env_SC.txt" "$T/cm_launch.ps1" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" | tr -d '\r' | head -3
