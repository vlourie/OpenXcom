#!/bin/sh
# MISSION-LEVEL TACTICS STAGE 2: one series of the declared list, limit 12 turns. sh run_x.sh <arms> <seed> <prefix>
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_launch.ps1 -Scen L4 -Jobs 2 -Tag $3 -Arms $1 -Seeds $2 -Prefix $3 -Turns 12" 2>/dev/null | tr -d '\r' | cut -c1-160
sh "$S/md2/wait_run2.sh" $3 $3 2>&1 | tail -8
