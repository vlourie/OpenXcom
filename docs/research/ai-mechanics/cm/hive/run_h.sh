#!/bin/sh
# HIVE COMMAND CORE V0: one run of the declared list (GATES_AND_RUN_LIST.md) on rabota, limit 12 turns; the logs land in hive/res. sh run_h.sh <no> <arm> <scen> <seed>
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
R="C:/OXCE_AIWorker/cmrun"
P="hv$1"
grep -q "^$1 " "$S/hive/runs_done.txt" 2>/dev/null && { echo "run $1 already done"; exit 1; }
[ "$(wc -l < "$S/hive/runs_done.txt" 2>/dev/null || echo 0)" -ge 12 ] && { echo "the limit of 12 is spent"; exit 1; }
echo "$1 $2 $3 s$4 turns=12" >> "$S/hive/runs_done.txt"
st=$(ssh -i "$K" "$H" "powershell -NoProfile -Command (Get-ScheduledTask oxce_cmrun).State" 2>/dev/null | tr -d '\r')
echo "task before: $st"
[ "$st" = "Running" ] && { echo "someone's run is going, not starting"; sed -i '$ d' "$S/hive/runs_done.txt"; exit 1; }
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_launch.ps1 -Scen $3 -Jobs 1 -Tag $P -Arms $2 -Seeds $4 -Prefix $P -Turns 12" 2>/dev/null | tr -d '\r' | cut -c1-160
n=0
while [ $n -lt 80 ]; do
	sleep 15
	n=$((n+1))
	st=$(ssh -i "$K" "$H" "powershell -NoProfile -Command (Get-ScheduledTask oxce_cmrun).State" 2>/dev/null | tr -d '\r')
	[ "$st" = "Ready" ] && break
done
echo "state: $st after $((n*15)) s"
ssh -i "$K" "$H" "C:\\OXCE_AIWorker\\python\\python.exe -I $R/pack_logs.py $R $P $R/res_$P.zip" 2>/dev/null | tr -d '\r' | tail -1 | cut -c1-200
mkdir -p "$S/hive/res"
scp -q -i "$K" "$H:$R/res_$P.zip" "$S/hive/res/" 2>/dev/null
scp -q -i "$K" "$H:$R/logs/run_$P.txt" "$S/hive/res/" 2>/dev/null
( cd "$S/hive/res" && unzip -oq "res_$P.zip" && ls out | grep "^$P" | head -5 )
tail -2 "$S/hive/res/run_$P.txt" | cut -c1-200
