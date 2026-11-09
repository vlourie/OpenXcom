#!/bin/sh
# HIVE COMMAND CORE V0: the rest of the declared list, 7 to 11 (GATES_AND_RUN_LIST.md); each battle evaluated against its D0 journal into hive/out.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
mkdir -p "$S/hive/out"
export PYTHONIOENCODING=utf-8
one() {
	sh "$S/hive/run_h.sh" "$1" HA "$2" "$3" 2>&1 | tail -2 | cut -c1-120
	py -3.13 -I "$S/hive/evalhive.py" "$S/hive/res/out/hv$1_HA_$2_s$3" "$S/sv/res/out/scpa_D_$2_s$3" 12 > "$S/hive/out/eval_$1_$2_s$3.txt" 2>&1
}
one 7 M6 1
py -3.13 -I "$S/fcs/same.py" "$S/hive/res/out/hv7_HA_M6_s1" "$S/hive/res/out/hv6_HA_M6_s1" | cut -c1-300
py -3.13 -I "$S/hive/evalhive.py" "$S/hive/res/out/hv6_HA_M6_s1" "$S/sv/res/out/scpa_D_M6_s1" 12 > "$S/hive/out/eval_6_M6_s1.txt" 2>&1
one 8 M6 2
one 9 L6 1
one 10 L6 2
one 11 L7 1
grep -a "^active\|^D0\|^result\|^GO orders\|^orders\|^identical" "$S"/hive/out/eval_*.txt | cut -c1-260
