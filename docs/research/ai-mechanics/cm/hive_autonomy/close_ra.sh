#!/bin/sh
# RESTORE COMBAT AUTONOMY closure: BOM on the documents, code and tables into cm/hive_autonomy, raw logs, the save, build and tree into battles_archive, sums on both. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive_autonomy"
B="E:/OXCE_AIWorker/battles_archive/hive_autonomy_2026-11-05"
F="$S/hive/ra"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
mkdir -p "$D/analysis/tables" "$D/tree/src/Battlescape" "$B/exe_RA"
cp "$F/GATES_AND_RUN_LIST.md" "$D/"
py -3.13 -I "$S/ff/bom.py" "$D/GATES_AND_RUN_LIST.md" "$D/GATES_AND_RUN_LIST.md"
for f in HIVE_RESTORE_COMBAT_AUTONOMY_RESULT.md HIVE_REINFORCEMENT_INTELLIGENCE_V0_RESULT.md HIVE_CONTACT_COORDINATION_V0_RESULT.md; do
	py -3.13 -I "$S/ff/bom.py" "$A/$f" "$A/$f"
done
cp "$A/HIVE_RESTORE_COMBAT_AUTONOMY_RESULT.md" "$D/"
for f in patch_ra.py make_ra.py build_ra.sh up_ra.sh run_ra.sh close_ra.sh rakes_ra.py runs_done.txt ra.diff; do
	cp "$F/$f" "$D/"
done
for f in AIModule.cpp AIModule.h HiveCommand.cpp HiveCommand.h; do
	cp "$F/tree/src/Battlescape/$f" "$D/tree/src/Battlescape/"
done
cp "$S/cm/st/run_cm.py" "$S/cm/st/env_RA.txt" "$S"/cm/st/exe/RA/BUILD_INFO* "$D/"
for f in chain.py losses.py static.py ra_eval.py first_point.py empty_walks.py join_check.py ra_final.py ra_more.py ra_guard.py ra_spawn.py; do
	cp "$F/$f" "$D/analysis/"
done
cp "$F"/chain_*.txt "$F"/losses*.txt "$F"/static*.txt "$F"/eval_*.txt "$F"/first_*.txt "$F"/decisions_*.tsv "$F/final.txt" "$F/more.txt" "$F/guard.txt" "$F/spawn.txt" "$D/analysis/tables/"
cp "$S/hive/fair.py" "$S/hive/hh_same.py" "$S/hive/mc/lib.py" "$S/hive/cc/plantime.py" "$D/analysis/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo autonomy sums ok )
cp "$S"/hive/res/res_ra*.zip "$S"/hive/res/run_ra*.txt "$B/"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/cmrun/work/oxce_ai_probe/arena_ra3_AV_M3_s1_w0/piratez/hive_3.asav" "$B/" 2>/dev/null || echo "save not fetched"
cp "$S"/cm/st/exe/RA/* "$B/exe_RA/"
tar --force-local -czf "$B/tree_ra.tar.gz" -C "$F" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
ls "$B" | grep -c asav || true
echo "main tree files that mention the headquarters:"
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
PYTHONIOENCODING=utf-8 py -3.13 -I "$F/rakes_ra.py"
