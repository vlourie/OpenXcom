#!/bin/sh
# D2 CORRECTION closure: BOM on the documents, code and tables into cm/hive_d2, raw logs, build and tree into battles_archive, sums on both. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive_d2"
B="E:/OXCE_AIWorker/battles_archive/hive_d2_2026-11-05"
F="$S/hive/d2"
mkdir -p "$D/analysis/tables" "$D/tree/src/Battlescape" "$B/exe_D2"
for f in HIVE_UA_D2_CORRECTION_DESIGN.md HIVE_UA_D2_CORRECTION_PLAN.md HIVE_UA_D2_CORRECTION_RESULT.md; do
	py -3.13 -I "$S/ff/bom.py" "$A/$f" "$A/$f"
	cp "$A/$f" "$D/"
done
for f in patch_d2.py make_d2.py build_d2.sh up_d2.sh run_d2.sh close_d2.sh runs_done.txt d2.diff; do
	cp "$F/$f" "$D/"
done
for f in AIModule.cpp AIModule.h HiveCommand.cpp HiveCommand.h; do
	cp "$F/tree/src/Battlescape/$f" "$D/tree/src/Battlescape/"
done
cp "$S/cm/st/run_cm.py" "$S/cm/st/env_D2.txt" "$S"/cm/st/exe/D2/BUILD_INFO* "$D/"
for f in d2_check.py d2_pocket.py d2_block.py d2_t2.py d2_idle.py d2_stuck.py d2_first.py d2_verify.py d2_lines.py make_gates_d2.py d2_gates.py rakes_d2.py; do
	cp "$F/$f" "$D/analysis/"
done
cp "$F"/check_d2*.txt "$F/pocket.txt" "$F/block.txt" "$F/t2.txt" "$F/idle.txt" "$F/stuck.txt" "$F/first.txt" "$F/gates.txt" "$F/measures.tsv" "$F/verify.txt" "$F/dk_new.txt" "$F/dk_old.txt" "$D/analysis/tables/"
cp "$S/hive/fair.py" "$S/hive/hh_same.py" "$S/hive/mc/lib.py" "$S/hive/ra/empty_walks.py" "$S/hive/d2_flags.py" "$D/analysis/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo d2 sums ok )
cp "$S"/hive/res/res_d2*.zip "$S"/hive/res/run_d2*.txt "$B/"
cp "$S"/cm/st/exe/D2/* "$B/exe_D2/"
tar --force-local -czf "$B/tree_d2.tar.gz" -C "$F" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
echo "main tree files that mention the headquarters:"
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
