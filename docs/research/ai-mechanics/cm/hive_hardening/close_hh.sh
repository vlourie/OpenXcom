#!/bin/sh
# HIVE hardening closure: BOM on the documents, code and tables into cm/hive_hardening, raw logs, the save, build and tree into battles_archive, sums on both. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive_hardening"
B="E:/OXCE_AIWorker/battles_archive/hive_hardening_2026-11-05"
F="$S/hive"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
mkdir -p "$D/analysis" "$D/tree/src/Battlescape" "$B/exe_HH"
py -3.13 -I "$S/ff/bom.py" "$D/GATES_AND_RUN_LIST.md" "$D/GATES_AND_RUN_LIST.md"
py -3.13 -I "$S/ff/bom.py" "$A/HIVE_COMMAND_CORE_HARDENING_RESULT.md" "$A/HIVE_COMMAND_CORE_HARDENING_RESULT.md"
cp "$A/HIVE_COMMAND_CORE_HARDENING_RESULT.md" "$D/"
for f in patch_hard.py patch_arms_hh.py build_hive.sh up_hh.sh run_hh.sh load_hh.py load_hh.ps1 close_hh.sh rakes_hh.py runs_done_hh.txt hh.diff; do
	cp "$F/$f" "$D/"
done
cp "$F/tree/src/Battlescape/HiveCommand.h" "$F/tree/src/Battlescape/HiveCommand.cpp" "$D/tree/src/Battlescape/"
cp "$S/cm/st/run_cm.py" "$S/cm/st/env_HH.txt" "$S/cm/st/env_HL.txt" "$S/cm/st/exe/HH/BUILD_INFO.txt" "$D/"
for f in fate_v0.py hh_eval.py hh_same.py hh_load.py hh_totals.py hh_final.py hh_locked.py fair.py hh_totals.txt; do
	cp "$F/$f" "$D/analysis/"
done
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo hardening sums ok )
cp "$F"/res/res_hh*.zip "$F"/res/run_hh*.txt "$B/"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/cmrun/work/oxce_ai_probe/arena_hh6_JV_M3_s1_w0/piratez/hive_5.asav" "$B/" 2>/dev/null
scp -q -i "$K" "$H:C:/OXCE_AIWorker/cmrun/logs/hh8_hive_5.asav" "$B/" 2>/dev/null
cp "$S"/cm/st/exe/HH/* "$B/exe_HH/"
tar --force-local -czf "$B/tree_hive.tar.gz" -C "$F" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
echo "main tree files that mention the headquarters:"
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
PYTHONIOENCODING=utf-8 py -3.13 -I "$F/rakes_hh.py"
