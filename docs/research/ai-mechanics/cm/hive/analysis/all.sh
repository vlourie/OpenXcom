#!/bin/sh
# HIVE COMMAND CORE V0: curve, organization and fairness of every active battle of the new build into hive/out, and the runs ledger.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
export PYTHONIOENCODING=utf-8
cat "$S/hive/runs_done.txt"
for b in "6 M6 s1" "7 M6 s1" "8 M6 s2" "9 L6 s1" "10 L6 s2" "11 L7 s1"; do
	set -- $b
	dir="$S/hive/res/out/hv$1_HA_$2_$3"
	d0="$S/sv/res/out/scpa_D_$2_$3"
	{
		echo "=== battle $1 $2 $3"
		py -3.13 -I "$S/hive/curve.py" "$dir" "$d0" 13
		py -3.13 -I "$S/hive/orgcheck.py" "$dir"
		py -3.13 -I "$S/hive/fair.py" "$dir"
	} > "$S/hive/out/org_$1_$2_$3.txt" 2>&1
	cat "$S/hive/out/org_$1_$2_$3.txt"
	grep -a "^identical\|^ active\|^ D0\|^GO orders\|^ of the completed\|^orders:\|^the units" "$S/hive/out/eval_$1_$2_$3.txt" | cut -c1-200
done
