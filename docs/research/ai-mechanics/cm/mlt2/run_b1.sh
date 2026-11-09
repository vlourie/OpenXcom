#!/bin/sh
# MISSION-LEVEL TACTICS STAGE 2, battle 1 of 8 (declared before the launch): shadow PL on L4_s1, limit 12 turns. The gate: the plan of 2 or more fighters.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_launch.ps1 -Scen L4 -Jobs 1 -Tag p1 -Arms PL -Seeds 1 -Prefix p1 -Turns 12" 2>/dev/null | tr -d '\r' | cut -c1-160
sh "$S/md2/wait_run2.sh" p1 p1 2>&1 | tail -8
