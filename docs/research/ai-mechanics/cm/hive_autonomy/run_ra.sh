#!/bin/sh
# RESTORE COMBAT AUTONOMY: one run of the declared list (hive/ra/GATES_AND_RUN_LIST.md) on rabota; the logs land in hive/res.
# sh run_ra.sh <no> <arm> <scen> <seed>   or   sh run_ra.sh <no> LOAD <save label> <save file>
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
R="C:/OXCE_AIWorker/cmrun"
P="ra$1"
D="$S/hive/ra/runs_done.txt"
grep -q "^$1 " "$D" 2>/dev/null && { echo "run $1 already done"; exit 1; }
[ "$(wc -l < "$D" 2>/dev/null || echo 0)" -ge 6 ] && { echo "the limit of 6 is spent"; exit 1; }
st=$(ssh -i "$K" "$H" "powershell -NoProfile -Command (Get-ScheduledTask oxce_cmrun).State" 2>/dev/null | tr -d '\r')
echo "task before: $st"
[ "$st" = "Running" ] && { echo "someone's run is going, not starting"; exit 1; }
if [ "$2" = "LOAD" ]; then
	echo "$1 LOAD $3 $4 turns=8" >> "$D"
	ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\load_ra_unused.ps1 -Label $3 -Save $4 -Prefix $P -Turns 8" 2>/dev/null | tr -d '\r' | cut -c1-200
else
	echo "$1 $2 $3 s$4 turns=8" >> "$D"
	ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_launch.ps1 -Scen $3 -Jobs 1 -Tag $P -Arms $2 -Seeds $4 -Prefix $P -Turns 8" 2>/dev/null | tr -d '\r' | cut -c1-200
fi
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
