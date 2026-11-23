#!/bin/sh
# SIDE-FIRST COMBAT: one series on rabota under the own task oxce_cmrun, the budget of 40 runs kept in runs_done.txt. sh run_sfc.sh <prefix> <arms> <pairs M6:1,L2:2> <turns> [jobs]
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
W="$S/sfc"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
R='C:\OXCE_AIWorker\cmrun'
P=$1; ARMS=$2; PAIRS=$3; TURNS=$4; JOBS=${5:-19}
na=$(echo "$ARMS" | tr ',' '\n' | wc -l)
np=$(echo "$PAIRS" | tr ',' '\n' | wc -l)
n=$((na*np))
done=$(cat "$W/runs_done.txt" 2>/dev/null || echo 0)
if [ $((done+n)) -gt 58 ]; then echo "budget: $done + $n > 58"; exit 2; fi
st=$(ssh -i "$K" "$H" "powershell -NoProfile -Command \"(Get-ScheduledTask oxce_cmrun).State\"" 2>/dev/null | tr -d '\r')
if [ "$st" = "Running" ]; then echo "task is running"; exit 3; fi
echo $((done+n)) > "$W/runs_done.txt"
echo "$P $ARMS $PAIRS turns=$TURNS runs=$n total=$((done+n))" | tee -a "$W/runs_log.txt"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File $R\\cm_launch.ps1 -Jobs $JOBS -Tag $P -Arms $ARMS -Prefix $P -Turns $TURNS -Pairs $PAIRS" 2>/dev/null | cut -c1-200
t0=$(date +%s)
while :; do
	st=$(ssh -i "$K" "$H" "powershell -NoProfile -Command \"(Get-ScheduledTask oxce_cmrun).State\"" 2>/dev/null | tr -d '\r')
	[ "$st" = "Ready" ] && break
	if [ $(( $(date +%s) - t0 )) -gt 3400 ]; then echo "still running after 3400 s"; exit 4; fi
	ping -n 16 127.0.0.1 > /dev/null
done
ssh -i "$K" "$H" "C:\\OXCE_AIWorker\\python\\python.exe -I $R\\pack_logs.py $R $P $R\\res_$P.zip" 2>/dev/null | cut -c1-160
mkdir -p "$W/res"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/cmrun/res_$P.zip" "$H:C:/OXCE_AIWorker/cmrun/logs/run_$P.txt" "$W/res/" 2>/dev/null
tail -5 "$W/res/run_$P.txt" | cut -c1-160
ls -la "$W/res/res_$P.zip" | cut -c20-160
