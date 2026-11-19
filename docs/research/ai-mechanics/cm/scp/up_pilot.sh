#!/bin/sh
# SIDE_TURN_ACTION_SCHEDULER combat pilot: exe S2 (the stage 2 scheduler v4 from the stage 2 archive, no COVER code), env_S2,
# the runner with arm N to rabota (C:/OXCE_AIWorker/cmrun); then prep (sums). Arm A is D (exe D0, env_D0) as uploaded before.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
( cd "$T" && sha256sum "exe/D0/$X" "exe/TD/$X" "exe/SC/$X" "exe/S2/$X" exe/D0/BUILD_INFO.txt exe/TD/BUILD_INFO.txt exe/SC/BUILD_INFO.txt exe/S2/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py cm_load.py env_D0.txt env_TD.txt env_SC.txt env_S2.txt env_SL.txt env_QL.txt make_cfg.py cm_launch.ps1 cm_load.ps1 cm_prep.ps1 > SHA256SUMS.txt )
grep -E "S2|D0|run_cm" "$T/SHA256SUMS.txt"
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\S2 mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\S2" 2>/dev/null
scp -q -i "$K" "$T/exe/S2/$X" "$T/exe/S2/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/S2/" 2>/dev/null
scp -q -i "$K" "$T/run_cm.py" "$T/env_S2.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3
