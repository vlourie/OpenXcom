#!/bin/sh
# STRIKE-V0: BOM on the report, the prototype's diff, the analysis and its results into cm/sv0 with sums
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/sv0"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
R="C:/OXCE_AIWorker/cmrun"
mkdir -p "$D"
py -3.13 -I "$S/ff/bom.py" "$A/TACTICAL_AI_2_0_STRIKE_V0_RESULT.md" "$A/TACTICAL_AI_2_0_STRIKE_V0_RESULT.md"
head -c 3 "$A/TACTICAL_AI_2_0_STRIKE_V0_RESULT.md" | od -An -tx1
for f in sv.diff fl_sv.py fl_sv2.py fl_sv3.py fl_sv4.py fl_sv5.py fl_sn.py fl_demo.py shadow_q1.txt on_result.txt on_checks.txt on_checks3.txt on_checks4.txt on_checks5.txt demo_M2_s2.txt demo_first.txt; do
	cp "$S/sv/$f" "$D/"
done
cp "$S/cm/st/exe/SV/BUILD_INFO.txt" "$D/BUILD_INFO_SV.txt"
cp "$S/cm/st/exe/D0/BUILD_INFO.txt" "$D/BUILD_INFO_D0.txt"
scp -q -i "$K" "$H:$R/logs/run_svhso.txt" "$H:$R/logs/run_svn.txt" "$H:$R/logs/run_svr.txt" "$D/" 2>/dev/null
( cd "$S/sv/res" && sha256sum res_svh.zip res_svo.zip res_svn.zip res_svr.zip > "$D/RAW_LOGS_SHA256.txt" )
cat "$D/RAW_LOGS_SHA256.txt"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo sums ok )
du -sh "$D"
