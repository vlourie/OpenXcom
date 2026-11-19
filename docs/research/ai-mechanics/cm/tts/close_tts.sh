#!/bin/sh
# TACTICAL TURN SOLVER V0 closure: BOM on the documents, code and scripts into cm/tts, raw logs, exe, saves and tree into battles_archive, sums on both. No commit.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/tts"
W="$S/tts"
T="$S/cm/st"
B="E:/OXCE_AIWorker/battles_archive/tts_v0_2026-11-05"
X="openxcom"".exe"
mkdir -p "$D" "$B/exe/TS" "$B/res"
py -3.13 -I "$S/ff/bom.py" "$A/TACTICAL_TURN_SOLVER_V0_RESULT.md" "$A/TACTICAL_TURN_SOLVER_V0_PLAN.md"
py -3.13 -I "$W/check_report.py" "$W/res" "$A/TACTICAL_TURN_SOLVER_V0_RESULT.md"
cp "$A/TACTICAL_TURN_SOLVER_V0_RESULT.md" "$A/TACTICAL_TURN_SOLVER_V0_PLAN.md" "$D/"
cp "$W/tree/src/Battlescape/TurnSolver.h" "$W/tree/src/Battlescape/TurnSolver.cpp" "$D/"
for f in patch_tts.py make_scene.py save_lib.py survey.py peek_save.py build_tts.sh up_tts.sh run_tts.sh cmp_tts.py cmp2_tts.py check_report.py rakes_tts.py close_tts.sh runs_done.txt; do
	cp "$W/$f" "$D/"
done
cp "$T/load_tts.py" "$T/load_tts.ps1" "$T/env_ZD.txt" "$T/env_ZS.txt" "$T/exe/TS/BUILD_INFO.txt" "$D/"
py -3.13 -I "$W/cmp_tts.py" "$W/res" > "$D/cmp.txt" 2>&1
py -3.13 -I "$W/cmp2_tts.py" "$W/res" "$D" > "$D/cmp2.txt" 2>&1
git -C E:/OpenXCom show 07680cadb:src/Battlescape/BattlescapeGame.cpp > "$W/bg_d0.cpp"
git -C E:/OpenXCom show 07680cadb:src/CMakeLists.txt > "$W/cm_d0.txt"
{ diff -u --strip-trailing-cr "$W/bg_d0.cpp" "$W/tree/src/Battlescape/BattlescapeGame.cpp" || true; diff -u --strip-trailing-cr "$W/cm_d0.txt" "$W/tree/src/CMakeLists.txt" || true; } > "$D/tts.diff"
wc -l "$D/tts.diff"
( cd "$W/res" && cp -r out res_tts*.zip run_tts*.txt r1 "$B/res/" )
cp "$T/exe/TS/$X" "$T/exe/TS/BUILD_INFO.txt" "$B/exe/TS/"
cp "$W/scene_s1.asav" "$W/scene_s2.asav" "$W/src_m10.asav" "$B/"
tar --force-local -czf "$B/tree_src.tar.gz" -C "$W/tree" src CMakeLists.txt GIT_COMMIT.txt
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo sums ok )
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo archive sums ok )
du -sh "$D" "$B"
echo "main tree files that mention the solver:"
grep -rl "TurnSolver" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
git -C E:/OpenXCom status --short src bin CMakeLists.txt | wc -l
git -C E:/OpenXCom log -1 --format=%h
