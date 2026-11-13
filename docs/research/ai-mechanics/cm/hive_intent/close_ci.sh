#!/bin/sh
# COMBAT INTENT V0 closure: BOM on the documents, code and tables into cm/hive_intent, raw logs, the save, build and tree into battles_archive, sums on both. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive_intent"
B="E:/OXCE_AIWorker/battles_archive/hive_intent_2026-11-05"
F="$S/hive/ci"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
rm -f "$F/runs_done.bak"
mkdir -p "$D/analysis/tables" "$D/tree/src/Battlescape" "$B/exe_CI"
cp "$F/GATES_AND_RUN_LIST.md" "$D/"
py -3.13 -I "$S/ff/bom.py" "$D/GATES_AND_RUN_LIST.md" "$D/GATES_AND_RUN_LIST.md"
py -3.13 -I "$S/ff/bom.py" "$A/HIVE_COMBAT_INTENT_V0_RESULT.md" "$A/HIVE_COMBAT_INTENT_V0_RESULT.md"
cp "$A/HIVE_COMBAT_INTENT_V0_RESULT.md" "$D/"
for f in patch_ci.py make_ci.py build_ci.sh up_ci.sh run_ci.sh close_ci.sh rakes_ci.py runs_done.txt ci.diff; do
	cp "$F/$f" "$D/"
done
for f in AIModule.cpp AIModule.h HiveCommand.cpp HiveCommand.h; do
	cp "$F/tree/src/Battlescape/$f" "$D/tree/src/Battlescape/"
done
cp "$S/cm/st/run_cm.py" "$S/cm/st/env_CI.txt" "$S"/cm/st/exe/CI/BUILD_INFO* "$D/"
for f in turn1.py feasible.py episodes.py ci_eval.py shadow_count.py dmg_table.py effect_check.py effect_pairs.py around.py rifle_rules.py effect_notes.py ci_checks.py bounce.py ci_final.py ci_window.py ci_more.py casualty_look.py hit_check.py chain.py ra_eval.py empty_walks.py report_check.py report_check2.py report_check3.py report_check4.py; do
	cp "$F/$f" "$D/analysis/"
done
cp "$F"/chain_ci.txt "$F"/final.txt "$F"/more.txt "$F"/window.txt "$F"/eval_ci.txt "$F"/feasible.txt "$F"/report_check.txt "$F"/report_check2.txt "$F"/report_check3.txt "$F"/decisions_*.tsv "$D/analysis/tables/"
cp "$S/hive/fair.py" "$S/hive/hh_same.py" "$S/hive/mc/lib.py" "$S/hive/cc/plantime.py" "$D/analysis/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo intent sums ok )
cp "$S"/hive/res/res_ci*.zip "$S"/hive/res/run_ci*.txt "$B/"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/cmrun/work/oxce_ai_probe/arena_ci7_IV_M3_s1_w0/piratez/hive_3.asav" "$B/" 2>/dev/null || echo "save not fetched"
cp "$S"/cm/st/exe/CI/* "$B/exe_CI/"
tar --force-local -czf "$B/tree_ci.tar.gz" -C "$F" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
ls "$B" | grep -c asav || true
echo "main tree files that mention the headquarters:"
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
PYTHONIOENCODING=utf-8 py -3.13 -I "$F/rakes_ci.py"
