#!/bin/sh
# FIRST CONTACT SURVIVAL: one run of the declared list on rabota, L4, limit 4 turns; the logs land in fcs/res. sh run_y.sh <arm> <seed> <prefix>
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
R="C:/OXCE_AIWorker/cmrun"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_launch.ps1 -Scen L4 -Jobs 1 -Tag $3 -Arms $1 -Seeds $2 -Prefix $3 -Turns 4" 2>/dev/null | tr -d '\r' | cut -c1-160
n=0
while [ $n -lt 160 ]; do
	sleep 15
	n=$((n+1))
	st=$(ssh -i "$K" "$H" "powershell -NoProfile -Command (Get-ScheduledTask oxce_cmrun).State" 2>/dev/null | tr -d '\r')
	[ "$st" = "Ready" ] && break
done
echo "state: $st after $((n*15)) s"
ssh -i "$K" "$H" "C:\\OXCE_AIWorker\\python\\python.exe -I $R/pack_logs.py $R $3 $R/res_$3.zip" 2>/dev/null | tr -d '\r' | tail -1 | cut -c1-200
mkdir -p "$S/fcs/res"
scp -q -i "$K" "$H:$R/res_$3.zip" "$S/fcs/res/" 2>/dev/null
scp -q -i "$K" "$H:$R/logs/run_$3.txt" "$S/fcs/res/" 2>/dev/null
( cd "$S/fcs/res" && unzip -oq "res_$3.zip" && ls out | grep "^$3_" | head -5 )
tail -3 "$S/fcs/res/run_$3.txt" | cut -c1-200
