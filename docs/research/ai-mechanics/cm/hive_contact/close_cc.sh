#!/bin/sh
# CONTACT_COORDINATION_V0 closure: BOM on the documents, code and tables into cm/hive_contact, raw logs, the save, build and tree into battles_archive, sums on both. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive_contact"
B="E:/OXCE_AIWorker/battles_archive/hive_contact_2026-11-05"
F="$S/hive/cc"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
mkdir -p "$D/analysis/tables" "$D/tree/src/Battlescape" "$B/exe_CC"
cp "$F/GATES_AND_RUN_LIST.md" "$D/"
py -3.13 -I "$S/ff/bom.py" "$D/GATES_AND_RUN_LIST.md" "$D/GATES_AND_RUN_LIST.md"
py -3.13 -I "$S/ff/bom.py" "$A/HIVE_CONTACT_COORDINATION_V0_RESULT.md" "$A/HIVE_CONTACT_COORDINATION_V0_RESULT.md"
cp "$A/HIVE_CONTACT_COORDINATION_V0_RESULT.md" "$D/"
for f in patch_cc.py make_cc.py build_cc.sh up_cc.sh run_cc.sh close_cc.sh rakes_cc.py runs_done.txt cc.diff; do
	cp "$F/$f" "$D/"
done
cp "$F/tree/src/Battlescape/HiveCommand.cpp" "$D/tree/src/Battlescape/"
cp "$S/cm/st/run_cm.py" "$S/cm/st/env_CC.txt" "$S/cm/st/env_CL.txt" "$S/cm/st/load_cc.py" "$S/cm/st/load_cc.ps1" "$S/cm/st/exe/CC/BUILD_INFO.txt" "$D/"
for f in episode.py scan.py feas.py traj.py arrive.py cc_eval.py chain.py plantime.py nonode.py cc_same.py cc_tail.py cc_load.py cc_final.py cc_scene.py cc_more.py; do
	cp "$F/$f" "$D/analysis/"
done
cp "$F"/ev/*.txt "$D/analysis/tables/"
cp "$S/hive/fair.py" "$S/hive/hh_same.py" "$S/hive/mc/lib.py" "$D/analysis/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo contact sums ok )
cp "$S"/hive/res/res_cc*.zip "$S"/hive/res/run_cc*.txt "$B/"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/cmrun/work/oxce_ai_probe/arena_cc6_CV_M3_s1_w0/piratez/hive_3.asav" "$B/" 2>/dev/null
cp "$S"/cm/st/exe/CC/* "$B/exe_CC/"
tar --force-local -czf "$B/tree_cc.tar.gz" -C "$F" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
echo "main tree files that mention the headquarters:"
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
PYTHONIOENCODING=utf-8 py -3.13 -I "$F/rakes_cc.py"
