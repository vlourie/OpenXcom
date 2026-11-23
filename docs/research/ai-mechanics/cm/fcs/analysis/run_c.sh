#!/bin/sh
# FIRST CONTACT SURVIVAL, stage 1: the categories and the starting positions over L4, M1, M10 (read only).
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
F="$S/fcs"
O="$S/sv/res/out"
M="$S/md2/res/out"
PY="py -3.13 -I"
$PY "$F/cat.py" "$F/out/cat.tsv" "$F/out/l4x.tsv" "$F/out/M1x.tsv" "$F/out/M10x.tsv"
echo
$PY "$F/deploy.py" "$M/p1_PL_L4_s1" "$M/p4_PL_L4_s2" "$M/p5_PL_L4_s3" "$O/scpa_D_M1_s1" "$O/scpa_D_M1_s2" "$O/scpa_D_M10_s1" "$O/scpa_D_M10_s2"
