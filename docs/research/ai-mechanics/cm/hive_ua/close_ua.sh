#!/bin/sh
# UNIFIED ARMY CONTROL V0 closure: BOM on the documents, code and tables into cm/hive_ua, raw logs, the save, build and tree into battles_archive, sums on both. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive_ua"
B="E:/OXCE_AIWorker/battles_archive/hive_ua_2026-11-05"
F="$S/hive/ua"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
mkdir -p "$D/analysis/tables" "$D/tree/src/Battlescape" "$D/tree/src/Savegame" "$B/exe_UA"
for f in HIVE_UNIFIED_ARMY_CONTROL_V0_RESULT.md HIVE_UNIFIED_ARMY_CONTROL_V0_DESIGN.md; do
	py -3.13 -I "$S/ff/bom.py" "$A/$f" "$A/$f"
	cp "$A/$f" "$D/"
done
for f in patch_ua.py make_ua.py build_ua.sh up_ua.sh run_ua.sh close_ua.sh rakes_ua.py runs_done.txt ua.diff; do
	cp "$F/$f" "$D/"
done
for f in AIModule.cpp AIModule.h HiveCommand.cpp HiveCommand.h; do
	cp "$F/tree/src/Battlescape/$f" "$D/tree/src/Battlescape/"
done
for f in SavedBattleGame.cpp SavedBattleGame.h; do
	cp "$F/tree/src/Savegame/$f" "$D/tree/src/Savegame/"
done
cp "$S/cm/st/run_cm.py" "$S/cm/st/env_UA.txt" "$S/cm/st/env_UL.txt" "$S/cm/st/load_ua.py" "$S/cm/st/load_ua.ps1" "$S"/cm/st/exe/UA/BUILD_INFO* "$D/"
for f in ua_eval.py ua_gates.py ua_more.py ua_last.py ua_idle.py ua_guard.py ua_final.py; do
	cp "$F/$f" "$D/analysis/"
done
cp "$F/gates.txt" "$F/more.txt" "$F/last.txt" "$F/guard.txt" "$F/final.txt" "$F/measures.tsv" "$D/analysis/tables/"
cp "$S/hive/fair.py" "$S/hive/hh_same.py" "$S/hive/mc/lib.py" "$S/hive/cc/plantime.py" "$S/hive/ra/empty_walks.py" "$D/analysis/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo ua sums ok )
cp "$S"/hive/res/res_ua*.zip "$S"/hive/res/run_ua*.txt "$B/"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/cmrun/work/oxce_ai_probe/arena_ua11_UV_M3_s1_w0/piratez/hive_3.asav" "$B/" 2>/dev/null || echo "save not fetched"
cp "$S"/cm/st/exe/UA/* "$B/exe_UA/"
tar --force-local -czf "$B/tree_ua.tar.gz" -C "$F" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
ls "$B" | grep -c asav || true
echo "main tree files that mention the headquarters:"
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
PYTHONIOENCODING=utf-8 py -3.13 -I "$F/rakes_ua.py"
