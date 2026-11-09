#!/bin/sh
# SIDE_TURN_ACTION_SCHEDULER stage 2: pack the logs of a prefix on rabota, bring the zip here, unpack into cm/res/all
# usage: fetch.sh <prefix>
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
P="$1"
ssh -i "$K" "$H" "C:\\OXCE_AIWorker\\python\\python.exe -I C:\\OXCE_AIWorker\\cmrun\\pack_logs.py C:\\OXCE_AIWorker\\cmrun $P C:\\OXCE_AIWorker\\cmrun\\res_$P.zip" 2>/dev/null | tr -d '\r'
scp -q -i "$K" "$H:C:/OXCE_AIWorker/cmrun/res_$P.zip" "$S/cm/res/res_$P.zip" 2>/dev/null
cd "$S/cm/res/all" && unzip -oq "../res_$P.zip" && ls out | grep "^${P}_"
