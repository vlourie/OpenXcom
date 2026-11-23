#!/bin/sh
# STAGE 2: why the orders did so little on s2 and s3; the split 17 against 21-26.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
O="$S/md2/res/out"
export PYTHONIOENCODING=utf-8
for b in p4_PN_L4_s2 p5_PN_L4_s3; do
	echo "=== $b"
	py -3.13 -I "$S/mlt/fl_m3.py" "$O/$b" 2>&1 | grep -a -E "^  t[0-9]+ |how tasks went|by fighter|hostile hits|OBJECTIVE" | cut -c1-175 | head -48
done
echo "=== split"
ls "$S/md/res/out" | grep -a -E "M1" | tr '\n' ' '
echo
py -3.13 -I "$S/md2/s2_split.py" "$S/md/res/out" "$O" $(ls "$S/md/res/out" | grep -a -E "^(mln|mlz|mly|mls)_.*M1" | grep -a -E "_MN_" | head -3) p1_PL_L4_s1 p2_PN_L4_s1 p4_PL_L4_s2 p4_PN_L4_s2 p5_PL_L4_s3 p5_PN_L4_s3 2>&1 | cut -c1-300
