#!/bin/sh
# STAGE 2: the checks over the 8 battles.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
O="$S/md2/res/out"
D="$S/sv/res/out"
export PYTHONIOENCODING=utf-8
mkdir -p "$S/md2/out"
echo "--- identity"
for p in "p1_PL_L4_s1 scpa_D_L4_s1" "p3_PO_L4_s1 scpa_D_L4_s1" "p4_PL_L4_s2 scpa_D_L4_s2"; do set -- $p; printf '%s vs %s: ' "$1" "$2"; py -3.13 -I "$S/mlt/fl_m3.py" "$O/$1" "$D/$2" 2>&1 | grep -a "identity with" | cut -c1-120; done
echo "--- repeat and limits"
for p in "p2_PN_L4_s1 p3_PN_L4_s1"; do set -- $p; py -3.13 -I "$S/mlt/fl_m5.py" "$O/$1" "$O/$2" 2>&1 | cut -c1-200 | head -8; done
for b in p4_PN_L4_s2 p5_PN_L4_s3 p5_PL_L4_s3; do echo "$b:"; py -3.13 -I "$S/mlt/fl_m5.py" "$O/$b" 2>&1 | cut -c1-200 | head -4; done
echo "--- all"
py -3.13 -I "$S/md2/s2_all.py" "$O" p1_PL_L4_s1 p3_PO_L4_s1 p2_PN_L4_s1 p3_PN_L4_s1 p4_PL_L4_s2 p4_PN_L4_s2 p5_PL_L4_s3 p5_PN_L4_s3 > "$S/md2/out/all.txt" 2>&1
cut -c1-300 "$S/md2/out/all.txt"
