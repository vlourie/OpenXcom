#!/bin/sh
# FIRST CONTACT SURVIVAL V0: how many players saw each of the six units moved on turn 1 at the start of the next player turn, D0 against the rule (read only).
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
R="$S/fcs/res/out"
one() {
	for u in $3; do
		for d in "$1" "$2"; do
			zcat "$d/openxcom.log.gz" | cut -f3 | grep -a -m1 "^.AISTATE. pstart turn=2 unit=$u " | grep -a -o -E "unit=[0-9]+|pos=[^ ]+|tu=[0-9]+|seenby=[0-9]+" | tr '\n' ' '
			echo
		done
	done
}
one "$S/sv/res/out/scpa_D_L4_s2" "$R/fy6_FN_L4_s2" "1000016 1000022 1000026 1000035"
one "$S/sv/res/out/scpa_D_L4_s1" "$R/fy7_FN_L4_s1" "1000001 1000011"
