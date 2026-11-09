#!/bin/sh
# MISSION-LEVEL TACTICS STAGE 2: wait for the oxce_cmrun task on rabota to finish (at most 40 minutes), then fetch the series' logs here (md2/res).
#   sh wait_run2.sh <prefix> <tag>
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
R="C:/OXCE_AIWorker/cmrun"
n=0
while [ $n -lt 160 ]; do
	sleep 15
	n=$((n+1))
	st=$(ssh -i "$K" "$H" "powershell -NoProfile -Command (Get-ScheduledTask oxce_cmrun).State" 2>/dev/null | tr -d '\r')
	[ "$st" = "Ready" ] && break
done
echo "state: $st after $((n*15)) s"
ssh -i "$K" "$H" "C:\\OXCE_AIWorker\\python\\python.exe -I $R/pack_logs.py $R $1 $R/res_$1.zip" 2>/dev/null | tr -d '\r' | tail -2 | cut -c1-200
mkdir -p "$S/md2/res"
scp -q -i "$K" "$H:$R/res_$1.zip" "$S/md2/res/" 2>/dev/null
scp -q -i "$K" "$H:$R/logs/run_$2.txt" "$S/md2/res/" 2>/dev/null
( cd "$S/md2/res" && unzip -oq "res_$1.zip" && ls out | grep "^$1_" | head -20 )
tail -6 "$S/md2/res/run_$2.txt" | cut -c1-200
