#!/bin/sh
# first differing AI decision per scenario, D1 against DS (BetterAI on through the release formula against the protocol
# stand); appended to res/all/first_div.txt; then the comparison with the new pairs (auto.sav)
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/b0"
R=$S/res/all/out
O=$S/res/all/first_div.txt
for sc in M1 M2 M3 M5 M8 M10 M11 L4 L5 L10 L11 L12; do
	echo "== $sc D1~DS" >> $O
	py -3.13 $S/first_div.py $R/D1_$sc/openxcom.log $R/DS_$sc/openxcom.log 1 >> $O 2>&1
done
py -3.13 $S/cmp_b0.py $R $S/res/all/fixtures $S/res/all/cmp_auto.txt > /dev/null
py -3.13 $S/verdicts.py $S/res/all/cmp_auto.tsv
grep -A1 "D1~DS" $O | grep decisions
