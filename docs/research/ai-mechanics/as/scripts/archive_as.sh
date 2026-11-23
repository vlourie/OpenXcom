#!/bin/sh
# AI-IF archive: E:/OXCE_AIWorker/battles_archive/ai_action_selection_2026-10-27 (exe IF, diff, patch, scripts, station results zip,
# analysis, report) with SHA256SUMS; diff, patch, scripts and analysis also into docs/research/ai-mechanics/as
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/as
A="E:/OXCE_AIWorker/battles_archive/ai_action_selection_2026-10-27"
D="E:/OpenXCom/docs/research/ai-mechanics/as"
R="E:/OpenXCom/docs/research/ai-mechanics/AI_ACTION_SELECTION_RESULT.md"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
X="openxcom"".exe"
ZS=$(ssh -i "$K" "$H" "powershell -NoProfile -Command \"(Get-FileHash -Algorithm SHA256 C:\\OXCE_AIWorker\\asrun\\as_all.zip).Hash\"" 2>/dev/null | tr -d '\r' | tr 'A-F' 'a-f')
ZL=$(sha256sum "$T/res/all/as_all.zip" | cut -d' ' -f1)
echo "zip station $ZS local $ZL"
[ "$ZS" = "$ZL" ] || { echo "ZIP HASH MISMATCH"; exit 1; }
mkdir -p "$A/exe/IF" "$A/src" "$A/scripts" "$A/results" "$D/src" "$D/scripts" "$D/results"
cp "$T/st/exe/IF/$X" "$A/exe/IF/"
cp "$T/if.diff" "$T/patch_if.py" "$A/src/"
cp "$T/st/asrun.py" "$T/st/as_launch.ps1" "$T/st/as_prep.ps1" "$T/st/as_pack.ps1" "$T/st/SHA256SUMS_IF.txt" \
   "$T/if_ana.py" "$T/if_why.py" "$T/up_as.sh" "$T/get_as.sh" "$T/archive_as.sh" "$S/ts/ident.py" "$A/scripts/"
cp "$T/res/all/as_all.zip" "$T/res/ana/"* "$A/results/"
cp "$R" "$A/"
( cd "$A" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt )
( cd "$A" && sha256sum -c --quiet SHA256SUMS.txt && echo "archive sums ok: $(wc -l < SHA256SUMS.txt) files" )
cp "$A/src/"* "$D/src/"
cp "$A/scripts/"* "$D/scripts/"
cp "$A/results/"*.txt "$A/results/"*.tsv "$D/results/"
cp "$A/SHA256SUMS.txt" "$D/ARCHIVE_SHA256SUMS.txt"
du -sh "$A" "$D"
