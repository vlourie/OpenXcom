#!/bin/sh
# FIRST CONTACT SURVIVAL, stage 1: the starting positions and the units lost before any decision (read only).
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
F="$S/fcs"
O="$S/sv/res/out"
M="$S/md2/res/out"
PY="py -3.13 -I"
B="$M/p1_PL_L4_s1 $M/p4_PL_L4_s2 $M/p5_PL_L4_s3 $O/scpa_D_M1_s1 $O/scpa_D_M1_s2 $O/scpa_D_M10_s1 $O/scpa_D_M10_s2"
$PY "$F/deploy.py" $B | cut -d';' -f1,2
$PY "$F/never.py" "$F/out/cat.tsv" $B
