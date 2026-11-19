#!/bin/sh
# comparison folder for pv_analyze: D0_* = the archived P0/D0 battles, D1_* = the pilot's E2 battles (T1, OXCE_AI_TARGET_EV=2)
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
C=$S/ts/res/cmp
mkdir -p "$C"
for d in "$S"/pv/res/all/u/out/D0_*; do
	n=$(basename "$d")
	mkdir -p "$C/$n"
	cp "$d/openxcom.log.gz" "$d/run.txt" "$C/$n/"
done
for d in "$S"/ts/res/out/E2_*; do
	n=$(basename "$d")
	m="D1_${n#E2_}"
	mkdir -p "$C/$m"
	cp "$d/openxcom.log.gz" "$d/run.txt" "$C/$m/"
done
ls "$C" | cut -c1-2 | sort | uniq -c
