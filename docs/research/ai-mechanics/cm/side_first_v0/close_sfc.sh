#!/bin/sh
# SIDE-FIRST COMBAT V0 closure: BOM, the check, code and scripts into cm/side_first_v0, builds and logs into battles_archive, sums on both. No commit.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
W="$S/sfc"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/side_first_v0"
T="$S/cm/st"
B="E:/OXCE_AIWorker/battles_archive/side_first_v0"
X="openxcom"".exe"
mkdir -p "$D" "$B/frozen" "$B/v01" "$B/res"
py -3.13 -I "$S/ff/bom.py" "$A/SIDE_FIRST_COMBAT_V0_RESULT.md" "$A/TACTICAL_TURN_SOLVER_V0_PLAN.md"
py -3.13 -I "$W/check_sfc.py" "$W" "$A/SIDE_FIRST_COMBAT_V0_RESULT.md"
py -3.13 -I "$S/ff/bom.py" "$W/FINAL_PLAN.md" "$A/TACTICAL_TURN_SOLVER_V0_PLAN.md"
cp "$A/SIDE_FIRST_COMBAT_V0_RESULT.md" "$W/FINAL_PLAN.md" "$D/"
cp "$W/frozen/SideCombatDirector.cpp" "$D/SideCombatDirector_V0.cpp"
cp "$W/frozen/SideCombatDirector.h" "$D/SideCombatDirector_V0.h"
cp "$W/SideCombatDirector.cpp" "$D/SideCombatDirector_V01.cpp"
cp "$W/SideCombatDirector.h" "$D/SideCombatDirector_V01.h"
for f in make_tree.py build_sfc.sh up_sfc.sh patch_run.py run_sfc.sh same.py battle_stats.py veto_look.py hits_look.py look2.py fair_check.py fair_cases.py fair_sum.py final_stats.py first_cause.py dig.py t1_units.py t1v.py ff_weapon.py ff_look.py order_look.py fix1.py fix2.py check_sfc.py rakes_sfc.py close_sfc.sh; do
	cp "$W/$f" "$D/"
done
for f in final.txt final.json dig.txt first_cause.txt fair.txt fair_sum.txt ff_weapon.txt freeze.txt runs_done.txt runs_log.txt; do
	cp "$W/$f" "$D/"
done
cp "$T/scen.tsv" "$D/"
cp "$T/exe/SD/BUILD_INFO.txt" "$D/BUILD_INFO_V01.txt"
cp "$W/frozen/BUILD_INFO.txt" "$D/BUILD_INFO_V0.txt"
for f in src/Battlescape/BattlescapeGame.cpp src/Battlescape/AIModule.cpp src/Battlescape/AIModule.h src/CMakeLists.txt; do
	git -C E:/OpenXCom show "07680cadb:$f" > "$W/d0_file.tmp"
	diff -u --strip-trailing-cr --label "d0/$f" --label "sfc/$f" "$W/d0_file.tmp" "$W/tree/$f" || true
done > "$D/side_first_v0.diff"
rm -f "$W/d0_file.tmp"
wc -l "$D/side_first_v0.diff"
cp "$W/frozen/$X" "$W/frozen/BUILD_INFO.txt" "$B/frozen/"
cp "$T/exe/SD/$X" "$T/exe/SD/BUILD_INFO.txt" "$B/v01/"
cp "$W"/res/res_sf*.zip "$W"/res/run_sf*.txt "$B/res/"
tar --force-local -czf "$B/tree_src.tar.gz" -C "$W/tree" src CMakeLists.txt GIT_COMMIT.txt
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo sums ok )
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo archive sums ok )
sha256sum "$B/frozen/$X" "$B/v01/$X" | cut -c1-64
du -sh "$D" "$B"
echo "main tree files that mention the director:"
grep -rl "SideCombatDirector" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
echo "main tree changes in src, bin, CMakeLists:"
git -C E:/OpenXCom status --short src bin CMakeLists.txt | wc -l
git -C E:/OpenXCom log -1 --format=%h
