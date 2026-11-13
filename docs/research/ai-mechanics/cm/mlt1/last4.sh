#!/bin/sh
# MISSION_DIRECTOR_V0: the last 4 of the 12 battles, stop moments named before the launch: OFF and a repeat of the orders on M1_s1 (natural end, at most turn 12),
# shadow and orders on M1_s2 (natural end, at most turn 18).
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_launch.ps1 -Scen M1 -Jobs 2 -Tag mlz -Arms MO,MN -Seeds 1 -Prefix mlz -Turns 12" 2>/dev/null | tr -d '\r' | cut -c1-160
sh "$S/md/wait_run.sh" mlz mlz 2>&1 | tail -8
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_launch.ps1 -Scen M1 -Jobs 2 -Tag mly -Arms ML,MN -Seeds 2 -Prefix mly -Turns 18" 2>/dev/null | tr -d '\r' | cut -c1-160
sh "$S/md/wait_run.sh" mly mly 2>&1 | tail -8
