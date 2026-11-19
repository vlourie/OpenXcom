#!/bin/sh
# REINFORCEMENT INTELLIGENCE V0 closure: BOM on the documents, code and tables into cm/hive_reinforcement, raw logs, the save, build and tree into battles_archive, sums on both. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive_reinforcement"
B="E:/OXCE_AIWorker/battles_archive/hive_reinforcement_2026-11-05"
F="$S/hive/ri"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
mkdir -p "$D/analysis/tables" "$D/tree/src/Battlescape" "$B/exe_RI"
diff -u "$S/hive/cc/tree/src/Battlescape/HiveCommand.cpp" "$F/tree/src/Battlescape/HiveCommand.cpp" > "$F/ri.diff" || true
printf '\n## Поправка после боёв\n\nПрежняя строка про оговорку № 8 ошибается в номере: неверное утверждение в отчёте CC — оговорка № 3 и заголовок таблицы. Смысл поправки прежний. Счётчик `esc_dice` даёт 0–3 на бой, счёт решений с режимом 3 без действия по кубику — 1–8; и то и другое единицы.\n' >> "$F/GATES_AND_RUN_LIST.md"
cp "$F/GATES_AND_RUN_LIST.md" "$D/"
py -3.13 -I "$S/ff/bom.py" "$D/GATES_AND_RUN_LIST.md" "$D/GATES_AND_RUN_LIST.md"
py -3.13 -I "$S/ff/bom.py" "$A/HIVE_REINFORCEMENT_INTELLIGENCE_V0_RESULT.md" "$A/HIVE_REINFORCEMENT_INTELLIGENCE_V0_RESULT.md"
cp "$A/HIVE_REINFORCEMENT_INTELLIGENCE_V0_RESULT.md" "$D/"
for f in patch_ri.py make_ri.py build_ri.sh up_ri.sh run_ri.sh close_ri.sh rakes_ri.py runs_done.txt ri.diff; do
	cp "$F/$f" "$D/"
done
cp "$F/tree/src/Battlescape/HiveCommand.cpp" "$D/tree/src/Battlescape/"
cp "$S/cm/st/run_cm.py" "$S/cm/st/env_RI.txt" "$S/cm/st/env_RL.txt" "$S/cm/st/load_ri.py" "$S/cm/st/load_ri.ps1" "$S/cm/st/exe/RI/BUILD_INFO.txt" "$D/"
for f in diag.py members.py cross.py rollback.py truth.py fireline.py planpath.py replay.py show.py stage1_table.py stage1_sum.py ri_eval.py assign_eval.py ri_final.py spend.py bigdiff.py saw_first.py; do
	cp "$F/$f" "$D/analysis/"
done
cp "$F/STAGE1_ASSIGNMENTS.md" "$F/assignments.tsv" "$F/members.tsv" "$F/stand.tsv" "$F/unit_turns.tsv" "$D/analysis/tables/"
cp "$S/hive/fair.py" "$S/hive/hh_same.py" "$S/hive/mc/lib.py" "$S/hive/cc/plantime.py" "$D/analysis/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo reinforcement sums ok )
cp "$S"/hive/res/res_ri*.zip "$S"/hive/res/run_ri*.txt "$B/"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/cmrun/work/oxce_ai_probe/arena_ri4_RV_M3_s1_w0/piratez/hive_3.asav" "$B/" 2>/dev/null
cp "$S"/cm/st/exe/RI/* "$B/exe_RI/"
tar --force-local -czf "$B/tree_ri.tar.gz" -C "$F" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
echo "main tree files that mention the headquarters:"
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
PYTHONIOENCODING=utf-8 py -3.13 -I "$F/rakes_ri.py"
