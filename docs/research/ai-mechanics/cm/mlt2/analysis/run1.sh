#!/bin/sh
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
R="$S/md/res/out"
O="$S/mlt2/out"
F="$S/mlt2/s2_facts.py"
py -3.13 -I "$F" "$R/mln_MN_L4_s1" > "$O/facts_orders.txt" 2>&1
py -3.13 -I "$F" "$R/mls_ML_L4_s1" > "$O/facts_d0.txt" 2>&1
awk '/fighters. decisions/{f=1} f' "$O/facts_orders.txt" | grep -v -E "sp0 end" | grep -v -E "^---|^$" | cut -c1-100 | sed -n 1,62p
tail -3 "$O/facts_orders.txt" | cut -c1-700
zcat "$R/mln_MN_L4_s1/openxcom.log.gz" | cut -f3 | grep -a -n -E "^.AIMISSION. what=(plan|release|grid)|^.AIDECIDE. turn=1 side=(0|1) unit=[0-9]+ n=1 " | cut -c1-70 | awk 'NR<=3 || /plan|release|grid/' | head -24
