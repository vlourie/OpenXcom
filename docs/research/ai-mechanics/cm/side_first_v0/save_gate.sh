#!/bin/sh
# SIDE-FIRST COMBAT V0.1: the M3 gate's outputs, the plan and this step's scripts into cm/side_first_v0, archive of the runs so far. No commit.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
W="$S/sfc"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/side_first_v0"
B="E:/OXCE_AIWorker/battles_archive/side_first_v0"
X="openxcom"".exe"
{
	py -3.13 -I "$W/same.py" "$W/res/res_sfF.zip" sfF_D_M3_s1 "$W/res/res_sfG.zip" sfG_XO_M3_s1
	py -3.13 -I "$W/same.py" "$W/res/res_sfF.zip" sfF_D_M3_s1 "$W/res/res_sfG.zip" sfG_XS_M3_s1
	py -3.13 -I "$W/pass_gate.py" "$W/res/res_sfF.zip:sfF:D" "$W/res/res_sfF.zip:sfF:XN" "$W/res/res_sfH.zip:sfH:XN"
	py -3.13 -I "$W/restarts.py" "$W/res/res_sfF.zip:sfF:D" "$W/res/res_sfF.zip:sfF:XN" "$W/res/res_sfH.zip:sfH:XN"
	py -3.13 -I "$W/fair_check.py" "$W/res/res_sfH.zip" sfH_XN_M3_s1 "$W/res/res_sfH.zip" sfH_XN_M3_s2 "$W/res/res_sfH.zip" sfH_XN_M3_s3 "$W/res/res_sfH.zip" sfH_XN_M3_s4
	for s in 1 2 3 4; do py -3.13 -I "$W/battle_stats.py" "$W/res/res_sfH.zip:sfH_XN_M3_s$s" | sed -n 2p; done
} > "$W/gate_m3.txt" 2>&1
py -3.13 -I "$S/ff/bom.py" "$W/FINAL_PLAN_V01.md" "$A/TACTICAL_TURN_SOLVER_V0_PLAN.md"
cp "$W/FINAL_PLAN_V01.md" "$W/gate_m3.txt" "$W/freeze_v01.txt" "$W/side_first_v01.diff" "$W/runs_done.txt" "$W/runs_log.txt" "$D/"
for f in rounds.py pass_gate.py restarts.py chr_rounds.py seq_look.py psi_look.py freeze_v01.sh save_gate.sh rakes_v01.py run_sfc.sh; do cp "$W/$f" "$D/"; done
cp "$W/SideCombatDirector.cpp" "$D/SideCombatDirector_V01.cpp"
cp "$W/SideCombatDirector.h" "$D/SideCombatDirector_V01.h"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo sums ok )
mkdir -p "$B/v01_final" "$B/res"
cp "$W/frozen_v01/$X" "$W/frozen_v01/BUILD_INFO.txt" "$B/v01_final/"
cp "$W"/res/res_sfG.zip "$W"/res/res_sfH.zip "$W"/res/run_sfG.txt "$W"/res/run_sfH.txt "$B/res/"
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo archive sums ok )
cat "$W/runs_done.txt"
git -C E:/OpenXCom status --short src bin CMakeLists.txt | wc -l
