#!/bin/sh
# FIRST CONTACT SURVIVAL V0: runs 6-8 of the limit 8 (the rule on s2, s1, s3) and the comparison with D0.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
F="$S/fcs"
PY="py -3.13 -I"
sh "$F/up_fcs.sh" 2>&1 | grep -a -E "exe_sha256|patch_sha256|mismatches"
sh "$F/run_y.sh" FN 2 fy6 | tail -2
sh "$F/run_y.sh" FN 1 fy7 | tail -2
sh "$F/run_y.sh" FN 3 fy8 | tail -2
R="$F/res/out"
$PY "$F/evalfc.py" "$F/out/acts.tsv" "$S/sv/res/out/scpa_D_L4_s2" "$R/fy6_FN_L4_s2" "$S/sv/res/out/scpa_D_L4_s1" "$R/fy7_FN_L4_s1" "$S/md2/res/out/p5_PL_L4_s3" "$R/fy8_FN_L4_s3" | cut -c1-280
