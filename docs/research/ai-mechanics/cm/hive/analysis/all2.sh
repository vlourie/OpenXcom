#!/bin/sh
# HIVE COMMAND CORE V0: execution of the walking orders and the path refusals by floor, every active battle; the two battles the first pass stopped on.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
export PYTHONIOENCODING=utf-8
for b in "6 M6 s1" "8 M6 s2" "9 L6 s1" "10 L6 s2" "11 L7 s1"; do
	set -- $b
	dir="$S/hive/res/out/hv$1_HA_$2_$3"
	d0="$S/sv/res/out/scpa_D_$2_$3"
	echo "=== battle $1 $2 $3"
	py -3.13 -I "$S/hive/execution.py" "$dir" "$d0" | tee "$S/hive/out/exec_$1_$2_$3.txt"
	py -3.13 -I "$S/hive/nopath.py" "$dir" > "$S/hive/out/nopath_$1_$2_$3.txt"
	grep -a "^  (" "$S/hive/out/nopath_$1_$2_$3.txt" | tr -s " " | tr "\n" ";" | cut -c1-360
	echo
	grep -a -A6 "^units (movement" "$S/hive/out/nopath_$1_$2_$3.txt" | cut -c1-60
done
for b in "10 L6 s2" "11 L7 s1"; do
	set -- $b
	dir="$S/hive/res/out/hv$1_HA_$2_$3"
	echo "=== org $1 $2 $3"
	py -3.13 -I "$S/hive/orgcheck.py" "$dir" > "$S/hive/out/org_$1_$2_$3.txt" 2>&1
	py -3.13 -I "$S/hive/curve.py" "$dir" "$S/sv/res/out/scpa_D_$2_$3" 13 >> "$S/hive/out/org_$1_$2_$3.txt" 2>&1
	py -3.13 -I "$S/hive/fair.py" "$dir" >> "$S/hive/out/org_$1_$2_$3.txt" 2>&1
	grep -a -A40 "^orders " "$S/hive/out/org_$1_$2_$3.txt" | grep -av "^  *[0-9]* {" | cut -c1-210 | head -36
done
