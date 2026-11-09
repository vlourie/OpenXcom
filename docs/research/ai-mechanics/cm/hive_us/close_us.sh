#!/bin/sh
# UNIFIED ARMY SAFETY closure: BOM on the documents, code and tables into cm/hive_us, raw logs, build and tree into battles_archive, sums on both. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive_us"
B="E:/OXCE_AIWorker/battles_archive/hive_us_2026-11-05"
F="$S/hive/us"
mkdir -p "$D/analysis/tables" "$D/tree/src/Battlescape" "$D/tree/src/Savegame" "$B/exe_US"
for f in HIVE_UNIFIED_ARMY_SAFETY_RESULT.md HIVE_UNIFIED_ARMY_SAFETY_PLAN.md; do
	py -3.13 -I "$S/ff/bom.py" "$A/$f" "$A/$f"
	cp "$A/$f" "$D/"
done
for f in patch_us.py make_us.py build_us.sh up_us.sh run_us.sh close_us.sh runs_done.txt us.diff; do
	cp "$F/$f" "$D/"
done
for f in AIModule.cpp HiveCommand.cpp HiveCommand.h; do
	cp "$F/tree/src/Battlescape/$f" "$D/tree/src/Battlescape/"
done
cp "$F/tree/src/Savegame/SavedBattleGame.cpp" "$D/tree/src/Savegame/"
cp "$S/cm/st/run_cm.py" "$S/cm/st/env_US.txt" "$S"/cm/st/exe/US/BUILD_INFO* "$D/"
for f in us_check.py make_gates.py us_gates.py us_more.py us_chain.py us_block.py us_last.py us_v0tries.py us_order.py rakes_us.py; do
	cp "$F/$f" "$D/analysis/"
done
py -3.13 -I "$F/us_order.py" > "$F/order.txt"
py -3.13 -I "$F/us_v0tries.py" > "$F/v0tries.txt"
cp "$F/gates.txt" "$F/more.txt" "$F/chain.txt" "$F/block.txt" "$F/last.txt" "$F/order.txt" "$F/v0tries.txt" "$F/measures.tsv" "$D/analysis/tables/"
cp "$S/hive/fair.py" "$S/hive/hh_same.py" "$S/hive/mc/lib.py" "$S/hive/ra/empty_walks.py" "$D/analysis/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo us sums ok )
cp "$S"/hive/res/res_us*.zip "$S"/hive/res/run_us*.txt "$B/"
cp "$S"/cm/st/exe/US/* "$B/exe_US/"
tar --force-local -czf "$B/tree_us.tar.gz" -C "$F" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
echo "main tree files that mention the headquarters:"
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
