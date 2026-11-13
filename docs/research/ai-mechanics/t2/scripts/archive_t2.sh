#!/bin/sh
# AI-T2 archive: E:/OXCE_AIWorker/battles_archive/ai_target_t2_2026-10-27 (exe T2, diff, patch, scripts, station results zip,
# analysis) with SHA256SUMS; diff, patch, scripts and analysis also into docs/research/ai-mechanics/t2
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/ts2
A="E:/OXCE_AIWorker/battles_archive/ai_target_t2_2026-10-27"
D="E:/OpenXCom/docs/research/ai-mechanics/t2"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
X="openxcom"".exe"
mkdir -p "$T/res/all"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/tsrun/t2_all.zip" "$T/res/all/t2_all.zip"
ZS=$(ssh -i "$K" "$H" "powershell -NoProfile -Command \"(Get-FileHash -Algorithm SHA256 C:\\OXCE_AIWorker\\tsrun\\t2_all.zip).Hash\"" 2>/dev/null | tr -d '\r' | tr 'A-F' 'a-f')
ZL=$(sha256sum "$T/res/all/t2_all.zip" | cut -d' ' -f1)
echo "zip station $ZS local $ZL"
[ "$ZS" = "$ZL" ] || { echo "ZIP HASH MISMATCH"; exit 1; }
mkdir -p "$A/exe/T2" "$A/src" "$A/scripts" "$A/results" "$D/src" "$D/scripts" "$D/results"
cp "$T/st/exe/T2/$X" "$A/exe/T2/"
cp "$T/t2.diff" "$T/patch_t2.py" "$A/src/"
cp "$T/st/tsrun.py" "$T/st/ts_launch.ps1" "$T/st/ts_state.ps1" "$T/st/t2_pack.ps1" "$T/st/SHA256SUMS_T2.txt" \
   "$T/t2_repro.py" "$T/t2_ana.py" "$T/t2_fx.py" "$T/up_t2.sh" "$T/get_t2.sh" "$T/archive_t2.sh" "$S/ts/ident.py" "$S/ts/repeats.py" \
   "$S/ts/wait_ts.sh" "$A/scripts/"
cp "$T/res/all/t2_all.zip" "$T/res/repro_E1.tsv" "$T/res/repro_E1.txt" "$T/res/ident_t2log.txt" "$T/res/ident_t2pilot.txt" \
   "$T/res/ident_t2repeat.txt" "$T/res/pilot_plan.txt" "$T/res/t2log_ana.txt" "$T/res/t2log_fx.txt" "$T/res/t2log_battles.tsv" \
   "$T/res/t2pilot_ana.txt" "$T/res/t2pilot_battles.tsv" "$T/res/t2pilot_s2_ana.txt" "$T/res/t2pilot_s2_fx.txt" "$T/res/m10_s2.txt" \
   "$A/results/"
[ -f "$T/res/AI_TARGET_T2_RESULT.md" ] && cp "$T/res/AI_TARGET_T2_RESULT.md" "$A/"
( cd "$A" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt )
( cd "$A" && sha256sum -c --quiet SHA256SUMS.txt && echo "archive sums ok: $(wc -l < SHA256SUMS.txt) files" )
cp "$A/src/"* "$D/src/"
cp "$A/scripts/"* "$D/scripts/"
cp "$A/results/"*.txt "$A/results/"*.tsv "$D/results/"
cp "$A/SHA256SUMS.txt" "$D/ARCHIVE_SHA256SUMS.txt"
du -sh "$A" "$D"
