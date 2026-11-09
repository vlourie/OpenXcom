#!/bin/sh
# FIRST CONTACT SURVIVAL: run 5 of the limit 8: the corrected shadow on s2, then the checks: shadow = OFF, and the corrected probe's picture.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
F="$S/fcs"
PY="py -3.13 -I"
sh "$F/up_fcs.sh" 2>&1 | grep -a -E "exe_sha256|mismatches|differs"
sh "$F/run_y.sh" FL 2 fy5 | tail -2
R="$F/res/out"
$PY "$F/same.py" "$R/fy1_FO_L4_s2" "$R/fy5_FL_L4_s2" | cut -c1-400
$PY "$F/los2.py" "$F/out/los2.tsv" "$R/fy5_FL_L4_s2" | cut -c1-240
