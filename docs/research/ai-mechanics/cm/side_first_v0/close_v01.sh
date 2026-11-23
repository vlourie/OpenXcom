#!/bin/sh
# SIDE-FIRST COMBAT V0.1, the final check: report with BOM, outputs and scripts into cm/side_first_v0, the L8 runs and the tree of the frozen build into the archive. No commit.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
W="$S/sfc"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/side_first_v0"
B="E:/OXCE_AIWorker/battles_archive/side_first_v0"
py -3.13 -I "$W/check_v01.py" "$A/SIDE_FIRST_COMBAT_V0_RESULT.md" "$W/final.json" "$W/mix/partial_v01.json" "$W/mix/partial_v0.json" "$W/pass_check.txt" "$W/idle_repeats.txt" "$W/psi_effects.txt" "$W/fair_v01.txt" "$W/runs_done.txt" "$W/partial_dig.txt"
py -3.13 -I "$S/ff/bom.py" "$A/SIDE_FIRST_COMBAT_V0_RESULT.md" "$A/TACTICAL_TURN_SOLVER_V0_PLAN.md"
cp "$W/final_v01_partial.txt" "$W/final_v0_partial.txt" "$W/partial_dig.txt" "$W/psi_effects.txt" "$W/pass_check.txt" "$W/idle_repeats.txt" "$W/fair_v01.txt" "$W/l8_detail.txt" "$W/l8_effects.txt" "$W/runs_done.txt" "$W/runs_log.txt" "$D/"
cp "$W/mix/partial_v01.json" "$W/mix/partial_v0.json" "$D/"
for f in psi_gate.py psi_effects.py l8_detail.py l8_effects.py l8_first.py restarts_all.py pass_check.py idle_repeats.py partial_stats.py run_partial.py v01_tables.py check_v01.py rakes_v01_final.py close_v01.sh; do cp "$W/$f" "$D/"; done
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo sums ok )
cmp "$W/frozen_v01/SideCombatDirector.cpp" "$W/tree/src/Battlescape/SideCombatDirector.cpp" && cmp "$W/frozen_v01/BattlescapeGame.cpp" "$W/tree/src/Battlescape/BattlescapeGame.cpp" && echo tree matches frozen
tar --force-local -czf "$B/tree_src.tar.gz" -C "$W/tree" src CMakeLists.txt
cp "$W"/res/res_sfI.zip "$W"/res/run_sfI.txt "$B/res/"
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo archive sums ok )
cat "$W/runs_done.txt"
git -C E:/OpenXCom status --short CMakeLists.txt bin src/Battlescape | wc -l
