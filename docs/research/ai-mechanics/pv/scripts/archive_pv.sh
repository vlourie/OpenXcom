#!/bin/sh
# P0 vs P1 archive: E:/OXCE_AIWorker/battles_archive/real_ai_p0_vs_p1_2026-10-27 (stand exe, diffs, scripts, prereg, station
# results zip, reports) with SHA256SUMS; scripts, diffs and reports also into docs/research/ai-mechanics/pv
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
P=$S/pv
A="E:/OXCE_AIWorker/battles_archive/real_ai_p0_vs_p1_2026-10-27"
D="E:/OpenXCom/docs/research/ai-mechanics/pv"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
X="openxcom"".exe"
ZS=$(ssh -i "$K" "$H" "powershell -NoProfile -Command \"(Get-FileHash -Algorithm SHA256 C:\\OXCE_AIWorker\\pvrun\\pv_all.zip).Hash\"" 2>/dev/null | tr -d '\r' | tr 'A-F' 'a-f')
ZL=$(sha256sum "$P/res/all/pv_all.zip" | cut -d' ' -f1)
echo "zip station $ZS local $ZL"
[ "$ZS" = "$ZL" ] || { echo "ZIP HASH MISMATCH"; exit 1; }
mkdir -p "$A/exe/AL" "$A/src" "$A/scripts" "$A/results" "$A/cfg" "$D/src" "$D/scripts" "$D/results"
cp "$P/st/exe/AL/$X" "$A/exe/AL/"
cp "$P/al3.diff" "$P/patch_al3.py" "$S/b0/al.diff" "$S/b0/patch_al.py" "$S/b0/patch_al2.py" "$A/src/"
cp "$P/st/pvone.py" "$P/st/pvrun.py" "$P/st/pv_prep.ps1" "$P/st/pv_launch.ps1" "$P/st/pv_pack.ps1" "$P/st/b0_cleanup.ps1" \
   "$P/st/scen.tsv" "$P/st/SHA256SUMS.txt" "$P/pv_analyze.py" "$P/start_diff.py" "$P/wait_pv.sh" "$P/archive_pv.sh" "$A/scripts/"
cp "$P/PREREG.md" "$P/PREREG.sha256" "$A/"
cp "$P/res/all/pv_all.zip" "$P/res/all/pv.txt" "$P/res/all/pv_battles.tsv" "$P/res/all/pv_pairs.tsv" "$P/res/all/start_diff.txt" \
   "$P/res/all/u/manifest.txt" "$P/res/all/u/logs/run_check.txt" "$P/res/all/u/logs/run_main.txt" "$A/results/"
cp "$P/res/all/u/cfg/"*.cfg "$A/cfg/"
( cd "$A" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt )
( cd "$A" && sha256sum -c --quiet SHA256SUMS.txt && echo "archive sums ok: $(wc -l < SHA256SUMS.txt) files" )
cp "$A/src/al3.diff" "$A/src/patch_al3.py" "$D/src/"
cp "$A/scripts/"* "$D/scripts/"
cp "$A/PREREG.md" "$A/PREREG.sha256" "$D/"
cp "$A/results/"*.txt "$A/results/"*.tsv "$D/results/"
cp "$A/cfg/"*.cfg "$D/results/"
cp "$A/SHA256SUMS.txt" "$D/ARCHIVE_SHA256SUMS.txt"
du -sh "$A" "$D"
