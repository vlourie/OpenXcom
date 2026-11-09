#!/bin/sh
# MISSION-LEVEL TACTICS STAGE 2 closure: BOM on the report, code and configs into cm/mlt2, raw logs, build and tree into battles_archive, sums on both
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/mlt2"
B="E:/OXCE_AIWorker/battles_archive/mission_level_tactics_stage2_2026-11-05"
mkdir -p "$D/analysis" "$B/exe_M2"
py -3.13 -I "$S/ff/bom.py" "$A/MISSION_LEVEL_TACTICS_STAGE2_RESULT.md" "$A/MISSION_LEVEL_TACTICS_STAGE2_RESULT.md"
head -c 5 "$A/MISSION_LEVEL_TACTICS_STAGE2_RESULT.md" | od -An -tx1
for f in md2.diff mission_block.cpp patch2.py arms2.py build_md2.sh up_md2.sh wait_run2.sh run_b1.sh run_x.sh cmake-md2.log ninja-md2.log close_mlt2.sh; do
	cp "$S/md2/$f" "$D/"
done
for f in run_cm.py env_M2.txt; do
	cp "$S/cm/st/$f" "$D/"
done
cp "$S/cm/st/exe/M2/BUILD_INFO.txt" "$D/"
for f in v1.sh v2.sh v3.sh v4.sh s2_all.py s2_split.py s2_att.py; do
	cp "$S/md2/$f" "$D/analysis/"
done
for f in s2_facts.py map_levels.py run1.sh; do
	cp "$S/mlt2/$f" "$D/analysis/"
done
cp "$S"/mlt2/out/*.txt "$D/analysis/"
sh "$S/md2/v2.sh" > "$D/analysis/v2_checks.txt" 2>&1
sh "$S/md2/v3.sh" > "$D/analysis/v3_chains_split.txt" 2>&1
sh "$S/md2/v4.sh" > "$D/analysis/v4_numbers.txt" 2>&1
cp "$A/MISSION_LEVEL_TACTICS_STAGE2_RESULT.md" "$D/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo mlt2 sums ok )
cp "$S"/md2/res/res_p*.zip "$S"/md2/res/run_p*.txt "$B/"
cp "$S"/cm/st/exe/M2/* "$B/exe_M2/"
tar --force-local -czf "$B/tree_md2.tar.gz" -C "$S/md2" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
