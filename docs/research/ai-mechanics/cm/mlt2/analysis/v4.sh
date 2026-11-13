#!/bin/sh
# STAGE 2: the last numbers for the report.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
O="$S/md2/res/out"
export PYTHONIOENCODING=utf-8
for b in p1_PL_L4_s1 p4_PL_L4_s2 p3_PO_L4_s1 p2_PN_L4_s1; do echo "$b:"; py -3.13 -I "$S/mlt/fl_m5.py" "$O/$b" 2>&1 | cut -c1-160 | head -2; done
for b in p3_PO_L4_s1 p1_PL_L4_s1; do printf '%s ' "$b"; zcat "$O/$b/openxcom.log.gz" | cut -f3 | grep -a "AIRESULT" | grep -a -o -E " ms=[0-9]+ vms=[0-9]+"; done
for b in p2_PN_L4_s1 p4_PN_L4_s2 p5_PN_L4_s3; do echo "== $b"; py -3.13 -I "$S/mlt/fl_m3.py" "$O/$b" 2>&1 | grep -a -E "how tasks went|by fighter" | cut -c1-900; done
echo "== who stays in a walk's end, TU of snap"
zcat "$O/p5_PN_L4_s3/openxcom.log.gz" | cut -f3 | grep -a -E "AIMISSION. what=task.*kind=shoot" | cut -c12-130 | head -8
zcat "$O/p2_PN_L4_s1/openxcom.log.gz" | cut -f3 | grep -a -E "AIMISSION. what=task.*kind=shoot" | cut -c12-130 | head -12
echo "== own side hits on own units by battle (casualties with both factions hostile)"
for b in p1_PL_L4_s1 p2_PN_L4_s1 p4_PL_L4_s2 p4_PN_L4_s2 p5_PL_L4_s3 p5_PN_L4_s3; do printf '%s: ' "$b"; zcat "$O/$b/openxcom.log.gz" | cut -f3 | grep -a "AICASUALTY" | head -1 | cut -c1-160; zcat "$O/$b/openxcom.log.gz" | cut -f3 | grep -a "AICASUALTY" | grep -a -c -E "vfaction=1 .*kfaction=1"; done
grep -n -E "21|17 мод" "E:/OpenXCom/docs/research/ai-mechanics/MISSION_LEVEL_TACTICS_STAGE1_RESULT.md" | cut -c1-200 | head -8
