#!/bin/sh
# STAGE 2: one battle at a glance. sh v1.sh <battle> [<D0 battle dir for fl_m3>]
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
L="$S/md2/res/out/$1/openxcom.log.gz"
[ -n "$2" ] && PYTHONIOENCODING=utf-8 py -3.13 -I "$S/mlt/fl_m3.py" "$S/md2/res/out/$1" "$2" 2>&1 | cut -c1-200 | head -30
echo "--- AIMISSION kinds"
zcat "$L" | cut -f3 | grep -a "AIMISSION" | grep -a -o "what=[a-z]*" | sort | uniq -c | tr '\n' ' '
echo
echo "--- plan lines"
zcat "$L" | cut -f3 | grep -a -E "AIMISSION. what=(cand|objective|plan|noplan|done|release|repos|base|demolished)" | cut -c12-260 | head -"${3:-40}"
echo "--- result"
zcat "$L" | cut -f3 | grep -a "AIRESULT" | cut -c1-400
