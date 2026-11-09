#!/bin/sh
# HIVE COMMAND CORE V0 closure: BOM on the documents, code and tables into cm/hive, raw logs, build and tree into battles_archive, sums on both. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive"
B="E:/OXCE_AIWorker/battles_archive/hive_command_core_v0_2026-11-05"
F="$S/hive"
mkdir -p "$D/analysis" "$D/tree/src/Battlescape" "$B/exe_HV"
py -3.13 -I "$S/ff/bom.py" "$F/GATES_AND_RUN_LIST.md" "$F/GATES_AND_RUN_LIST.md"
for f in HIVE_COMMAND_ARCHITECTURE.md HIVE_COMMAND_CORE_V0_RESULT.md HIVE_COMMAND_ROADMAP.md; do
	py -3.13 -I "$S/ff/bom.py" "$A/$f" "$A/$f"
	head -c 3 "$A/$f" | od -An -tx1
	cp "$A/$f" "$D/"
done
for f in GATES_AND_RUN_LIST.md patch_hooks.py patch_arms.py build_hive.sh up_hive.sh run_h.sh run_rest.sh close_hive.sh rakes.py; do
	cp "$F/$f" "$D/"
done
cp "$F/tree/src/Battlescape/HiveCommand.h" "$F/tree/src/Battlescape/HiveCommand.cpp" "$D/tree/src/Battlescape/"
cp "$S/cm/st/run_cm.py" "$S/cm/st/env_HV.txt" "$S/cm/st/exe/HV/BUILD_INFO.txt" "$F/hive.diff" "$D/"
for f in scan.py scan2.py objectives.py unitlist.py patrol_waste.py targets.py nodes.py evalhive.py blocked.py nopath.py fair.py curve.py orgcheck.py execution.py stuck.py reach.py modes.py cmdcheck.py wiped.py sums.py tags.py all.sh all2.sh all3.sh; do
	cp "$F/$f" "$D/analysis/"
done
cp "$F"/out/*.txt "$F/runs_done.txt" "$D/analysis/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo hive sums ok )
cp "$F"/res/res_hv*.zip "$F"/res/run_hv*.txt "$B/"
cp "$S"/cm/st/exe/HV/* "$B/exe_HV/"
tar --force-local -czf "$B/tree_hive.tar.gz" -C "$F" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
ls "$B" | wc -l
echo "main tree files that mention the headquarters:"
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
PYTHONIOENCODING=utf-8 py -3.13 -I "$F/rakes.py"
