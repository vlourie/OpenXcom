#!/bin/sh
# HIVE COMMAND CORE V0: evaluation again with the corrected columns, commander checks, D0's own commander-free timing of nothing: only journals are read.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
export PYTHONIOENCODING=utf-8
for b in "6 M6 s1" "7 M6 s1" "8 M6 s2" "9 L6 s1" "10 L6 s2" "11 L7 s1"; do
	set -- $b
	dir="$S/hive/res/out/hv$1_HA_$2_$3"
	d0="$S/sv/res/out/scpa_D_$2_$3"
	py -3.13 -I "$S/hive/evalhive.py" "$dir" "$d0" 12 > "$S/hive/out/eval_$1_$2_$3.txt" 2>&1
	py -3.13 -I "$S/hive/orgcheck.py" "$dir" > "$S/hive/out/org_$1_$2_$3.txt" 2>&1
	py -3.13 -I "$S/hive/curve.py" "$dir" "$d0" 13 > "$S/hive/out/curve_$1_$2_$3.txt" 2>&1
	py -3.13 -I "$S/hive/fair.py" "$dir" > "$S/hive/out/fair_$1_$2_$3.txt" 2>&1
	echo "=== $1 $2 $3"
	py -3.13 -I "$S/hive/cmdcheck.py" "$dir" | tee "$S/hive/out/cmd_$1_$2_$3.txt" | cut -c1-300
	grep -a "^ms\|how=" "$S/hive/res/run_hv$1"*.txt 2>/dev/null | head -2 | cut -c1-200
done
ls "$S/hive/res" | head -40
git -C E:/OpenXCom status --short -- src bin | cut -c1-90
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
cd E:/OpenXCom && python tools/rake.py add --help 2>&1 | head -30
