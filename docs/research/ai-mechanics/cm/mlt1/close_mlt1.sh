#!/bin/sh
# MISSION-LEVEL TACTICS STAGE 1 closure: BOM on the report, code and configs into cm/mlt1, raw logs, build and tree into battles_archive, sums on both
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/mlt1"
B="E:/OXCE_AIWorker/battles_archive/mission_level_tactics_stage1_2026-11-05"
mkdir -p "$D/analysis" "$B/exe_MD"
py -3.13 -I "$S/ff/bom.py" "$A/MISSION_LEVEL_TACTICS_STAGE1_RESULT.md" "$A/MISSION_LEVEL_TACTICS_STAGE1_RESULT.md"
head -c 5 "$A/MISSION_LEVEL_TACTICS_STAGE1_RESULT.md" | od -An -tx1
for f in md.diff mission_block.cpp patch.py patch_tail.py fix1.py fix2.py fix3.py build_md.sh up_md.sh wait_run.sh last4.sh cmake-mddev.log ninja-mddev.log; do
	cp "$S/md/$f" "$D/"
done
for f in run_cm.py env_MD.txt; do
	cp "$S/cm/st/$f" "$D/"
done
cp "$S/cm/st/exe/MD/BUILD_INFO.txt" "$D/"
cp "$S/mlt/close_mlt1.sh" "$D/"
for f in rul_scan.py fl_bd1.py log_ctx.py fl_m1.py fl_m2.py fl_m3.py fl_m4.py fl_m5.py fl_m6.py fl_m7.py; do
	cp "$S/mlt/$f" "$D/analysis/"
done
cp "$S"/mlt/out/*.txt "$D/analysis/"
cp "$A/MISSION_LEVEL_TACTICS_STAGE1_RESULT.md" "$D/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo mlt1 sums ok )
cp "$S"/md/res/res_ml*.zip "$S"/md/res/run_ml*.txt "$B/"
cp "$S"/cm/st/exe/MD/* "$B/exe_MD/"
tar --force-local -czf "$B/tree_md.tar.gz" -C "$S/md" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
