#!/bin/sh
# first differing AI decision per scenario for the stand pairs; output: res/all/first_div.txt
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/b0"
R=$S/res/all/out
O=$S/res/all/first_div.txt
: > $O
for sc in M1 M2 M3 M5 M8 M10 M11 L4 L5 L10 L11 L12; do
	for p in "D0 D0b" "D0 D0n" "D0 DH" "D0 D1" "DH D1" "DH DS" "DS DSE"; do
		set -- $p
		echo "== $sc $1~$2" >> $O
		py -3.13 $S/first_div.py $R/$1_$sc/openxcom.log $R/$2_$sc/openxcom.log 1 >> $O 2>&1
	done
done
echo done
