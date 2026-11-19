#!/bin/sh
# FIRST CONTACT SURVIVAL: runs 2-4 of the declared list (shadow on s2, s1, s3), then the checks: shadow = OFF on s2, shadow = D0 on s1 and s3 up to the turn limit.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
F="$S/fcs"
PY="py -3.13 -I"
sh "$F/run_y.sh" FL 2 fy2 | tail -2
sh "$F/run_y.sh" FL 1 fy3 | tail -2
sh "$F/run_y.sh" FL 3 fy4 | tail -2
R="$F/res/out"
$PY "$F/same.py" "$R/fy1_FO_L4_s2" "$R/fy2_FL_L4_s2" | cut -c1-400
$PY "$F/same.py" "$S/sv/res/out/scpa_D_L4_s1" "$R/fy3_FL_L4_s1" | cut -c1-300
$PY "$F/same.py" "$S/md2/res/out/p5_PL_L4_s3" "$R/fy4_FL_L4_s3" | cut -c1-300
$PY "$F/los.py" "$F/out/los.tsv" "$R/fy3_FL_L4_s1" "$R/fy2_FL_L4_s2" "$R/fy4_FL_L4_s3" | cut -c1-240
