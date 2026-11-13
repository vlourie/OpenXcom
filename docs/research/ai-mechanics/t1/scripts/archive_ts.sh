#!/bin/sh
# AI-T1 archive: E:/OXCE_AIWorker/battles_archive/ai_target_t1_2026-10-27 (stand exe T1, diff, patch, scripts, station results
# zip, analysis) with SHA256SUMS; diff, patch, scripts and analysis also into docs/research/ai-mechanics/t1
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/ts
A="E:/OXCE_AIWorker/battles_archive/ai_target_t1_2026-10-27"
D="E:/OpenXCom/docs/research/ai-mechanics/t1"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
X="openxcom"".exe"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\tsrun\\ts_pack.ps1" 2>/dev/null | tr -d '\r'
mkdir -p "$T/res/all"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/tsrun/ts_all.zip" "$T/res/all/ts_all.zip"
ZS=$(ssh -i "$K" "$H" "powershell -NoProfile -Command \"(Get-FileHash -Algorithm SHA256 C:\\OXCE_AIWorker\\tsrun\\ts_all.zip).Hash\"" 2>/dev/null | tr -d '\r' | tr 'A-F' 'a-f')
ZL=$(sha256sum "$T/res/all/ts_all.zip" | cut -d' ' -f1)
echo "zip station $ZS local $ZL"
[ "$ZS" = "$ZL" ] || { echo "ZIP HASH MISMATCH"; exit 1; }
mkdir -p "$A/exe/T1" "$A/src" "$A/scripts" "$A/results" "$D/src" "$D/scripts" "$D/results"
cp "$T/st/exe/T1/$X" "$A/exe/T1/"
cp "$T/t1.diff" "$T/patch_t1.py" "$A/src/"
cp "$T/st/tsrun.py" "$T/st/ts_launch.ps1" "$T/st/ts_prep.ps1" "$T/st/ts_reset.ps1" "$T/st/ts_pack.ps1" "$T/st/pv_cleanup.ps1" \
   "$T/st/SHA256SUMS.txt" "$T/cases.py" "$T/civ.py" "$T/ident.py" "$T/targets.py" "$T/verify_ev.py" "$T/switches.py" \
   "$T/repeats.py" "$T/sw_walk.py" "$T/mkcmp.sh" "$T/up_ts.sh" "$T/get_ts.sh" "$T/wait_ts.sh" "$T/archive_ts.sh" "$A/scripts/"
cp "$T/res/all/ts_all.zip" "$T/d0_cases.tsv" "$T/res/ident_log.txt" "$T/res/v1_ident_log.txt" "$T/res/examples_E1.tsv" \
   "$T/res/t1.txt" "$T/res/t1_battles.tsv" "$T/res/t1_pairs.tsv" "$T/res/analysis.txt" "$A/results/"
( cd "$A" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt )
( cd "$A" && sha256sum -c --quiet SHA256SUMS.txt && echo "archive sums ok: $(wc -l < SHA256SUMS.txt) files" )
cp "$A/src/"* "$D/src/"
cp "$A/scripts/"* "$D/scripts/"
cp "$A/results/"*.txt "$A/results/"*.tsv "$D/results/"
cp "$A/SHA256SUMS.txt" "$D/ARCHIVE_SHA256SUMS.txt"
du -sh "$A" "$D"
