#!/bin/sh
# STRIKE-V0 closure: BOM on the documents, code and configs into cm/sv0, raw logs, build and tree into battles_archive, sums on both
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/sv0"
B="E:/OXCE_AIWorker/battles_archive/strike_v0_2026-10-30"
for f in TACTICAL_AI_2_0_STRIKE_V0_RESULT TACTICAL_AI_2_0_STRIKE_V0_CLOSED TACTICAL_AI_2_0_IMPLEMENTATION_PLAN TACTICAL_AI_2_0_ARCHITECTURE; do
	py -3.13 -I "$S/ff/bom.py" "$A/$f.md" "$A/$f.md"
	printf '%s ' "$f"; head -c 5 "$A/$f.md" | od -An -tx1
done
for f in strike_block.cpp patch.py crlf.py build_sv.sh up_sv.sh pack_sv0.sh close_sv0.sh cmake-svdev.log ninja-svdev.log; do
	cp "$S/sv/$f" "$D/"
done
for f in run_cm.py make_cfg.py scen.tsv env_SV.txt env_D0.txt; do
	cp "$S/cm/st/$f" "$D/"
done
cp "$S/cm/cmp_logs.py" "$S/ce/al.crlf.diff" "$S/ce/al3.crlf.diff" "$D/"
cp "$A/TACTICAL_AI_2_0_STRIKE_V0_RESULT.md" "$A/TACTICAL_AI_2_0_STRIKE_V0_CLOSED.md" "$D/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo sv0 sums ok )
mkdir -p "$B"
cp "$S/sv/res/res_svh.zip" "$S/sv/res/res_svo.zip" "$S/sv/res/res_svn.zip" "$S/sv/res/res_svr.zip" "$B/"
mkdir -p "$B/exe_SV"
cp "$S"/cm/st/exe/SV/* "$B/exe_SV/"
tar --force-local -czf "$B/tree_sv.tar.gz" -C "$S/sv" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && cat SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
