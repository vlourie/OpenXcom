#!/bin/sh
# TACTICAL TURN SOLVER V0: one run of the declared list (TACTICAL_TURN_SOLVER_V0_PLAN.md) on rabota; the logs land in tts/res. Hard limit: 6 runs in all.
# sh run_tts.sh <no>
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
R="C:/OXCE_AIWorker/cmrun"
P="tts$1"
D="$S/tts/runs_done.txt"
case "$1" in
	1) ARM=ZD; SAVE=scene_s1.asav; SCEN=SC; SEED=1; TURNS=1; BOT=0;;
	2) ARM=ZS; SAVE=scene_s1.asav; SCEN=SC; SEED=1; TURNS=1; BOT=0;;
	3) ARM=ZD; SAVE=scene_s2.asav; SCEN=SC; SEED=2; TURNS=1; BOT=0;;
	4) ARM=ZS; SAVE=scene_s2.asav; SCEN=SC; SEED=2; TURNS=1; BOT=0;;
	5) ARM=ZD; SAVE=src_m10.asav; SCEN=M10; SEED=1; TURNS=8; BOT=1;;
	6) ARM=ZS; SAVE=src_m10.asav; SCEN=M10; SEED=1; TURNS=8; BOT=1;;
	*) echo "not in the list"; exit 1;;
esac
grep -q "^$1 " "$D" 2>/dev/null && { echo "run $1 already done"; exit 1; }
[ "$(wc -l < "$D" 2>/dev/null || echo 0)" -ge 6 ] && { echo "the limit of 6 is spent"; exit 1; }
st=$(ssh -i "$K" "$H" "powershell -NoProfile -Command (Get-ScheduledTask oxce_cmrun).State" 2>/dev/null | tr -d '\r')
echo "task before: $st"
[ "$st" = "Running" ] && { echo "someone's run is going, not starting"; exit 1; }
echo "$1 $ARM $SAVE $SCEN s$SEED turns=$TURNS bot=$BOT" >> "$D"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\load_tts.ps1 -Arm $ARM -Save $SAVE -Prefix $P -Scen $SCEN -Seed $SEED -Turns $TURNS -Bot $BOT" 2>/dev/null | tr -d '\r' | cut -c1-200
n=0
while [ $n -lt 70 ]; do
	sleep 15
	n=$((n+1))
	st=$(ssh -i "$K" "$H" "powershell -NoProfile -Command (Get-ScheduledTask oxce_cmrun).State" 2>/dev/null | tr -d '\r')
	[ "$st" = "Ready" ] && break
done
echo "state: $st after $((n*15)) s"
ssh -i "$K" "$H" "C:\\OXCE_AIWorker\\python\\python.exe -I $R/pack_logs.py $R $P $R/res_$P.zip" 2>/dev/null | tr -d '\r' | tail -1 | cut -c1-200
mkdir -p "$S/tts/res"
scp -q -i "$K" "$H:$R/res_$P.zip" "$S/tts/res/" 2>/dev/null
scp -q -i "$K" "$H:$R/logs/run_$P.txt" "$S/tts/res/" 2>/dev/null
( cd "$S/tts/res" && unzip -oq "res_$P.zip" && ls out | grep "^$P" | head -5 )
tail -2 "$S/tts/res/run_$P.txt" | cut -c1-200
