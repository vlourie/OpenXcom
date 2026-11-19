#!/bin/sh
# FIRST CONTACT SURVIVAL, stage 1: the same chronology on the two other allowed scenarios, the existing D0 logs (read only).
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
O="$S/sv/res/out"
F="$S/fcs"
PY="py -3.13 -I"
for sc in M1 M10; do
  $PY "$F/chrono.py" "$F/out/$sc.tsv" "$O/scpa_D_${sc}_s1" "$O/scpa_D_${sc}_s2" | grep -a -E "^== |^rows"
  $PY "$F/expo.py" "$F/out/$sc.tsv" "$F/out/${sc}x.tsv" "$O" | grep -a -E "^units lost|^  scpa|^acted|player-turn losses|own-turn losses"
done
echo --- hit and weapon fields, L4
cut -f13,14,15,16 "$F/out/l4x.tsv" | head -6
cut -f15 "$F/out/l4x.tsv" | sort | uniq -c | sort -rn | head -12
cut -f14 "$F/out/l4x.tsv" | sort | uniq -c | sort -rn | head -30
