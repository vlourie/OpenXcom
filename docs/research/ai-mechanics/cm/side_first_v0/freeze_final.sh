#!/bin/sh
# SIDE-FIRST COMBAT, Vitali's final verdict: check the report, add the dontReselect count to the copies, mark the archive frozen, recount the sums. No commit, no build, no battle.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
W="$S/sfc"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/side_first_v0"
B="E:/OXCE_AIWorker/battles_archive/side_first_v0"
py -3.13 -I "$W/check_v01.py" "$A/SIDE_FIRST_COMBAT_V0_RESULT.md" "$W/final.json" "$W/mix/partial_v01.json" "$W/mix/partial_v0.json" "$W/pass_check.txt" "$W/idle_repeats.txt" "$W/psi_effects.txt" "$W/fair_v01.txt" "$W/runs_done.txt" "$W/partial_dig.txt" | tail -4
py -3.13 -I "$S/ff/bom.py" "$A/SIDE_FIRST_COMBAT_V0_RESULT.md" "$A/TACTICAL_TURN_SOLVER_V0_PLAN.md"
cat > "$W/FROZEN.txt" <<'TXT'
SideCombatDirector V0 and V0.1 are frozen by Vitali's final verdict of 2026-11-06: NO-GO.
Do not change these files, do not create V0.2, do not run M8 and L4 on V0.1, do not move the director into the main OXCE or a release.
frozen = V0, v01 = intermediate V0.1, v01_final = V0.1 of the final check, res = all battle results, tree_src.tar.gz = source of the V0.1 build.
Verdict: docs/research/ai-mechanics/SIDE_FIRST_COMBAT_V0_RESULT.md
TXT
cp "$W/reselect_count.py" "$W/reselect_count.txt" "$W/reselect_case.py" "$W/reselect_log.py" "$W/freeze_final.sh" "$W/FROZEN.txt" "$D/"
cp "$W/FROZEN.txt" "$B/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo copies sums ok )
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo archive sums ok )
git -C E:/OpenXCom status --short CMakeLists.txt bin src/Battlescape | wc -l
