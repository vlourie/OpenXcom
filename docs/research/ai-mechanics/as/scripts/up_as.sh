#!/bin/sh
# AI-IF: a new run folder C:/OXCE_AIWorker/asrun - exe IF, asrun.py, launch/prep scripts and the archived T2 inputs (t2_all.zip)
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/as
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
X="openxcom"".exe"
mkdir -p "$T/st/exe/IF"
cp "$S/c2/b-c2dev/bin/$X" "$T/st/exe/IF/$X"
( cd "$T/st" && sha256sum "exe/IF/$X" asrun.py as_launch.ps1 as_prep.ps1 > SHA256SUMS_IF.txt )
cat "$T/st/SHA256SUMS_IF.txt"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force C:\\OXCE_AIWorker\\asrun\\exe\\IF | Out-Null\""
scp -q -i "$K" "$T/st/exe/IF/$X" "$H:C:/OXCE_AIWorker/asrun/exe/IF/$X"
scp -q -i "$K" "$T/st/asrun.py" "$T/st/as_launch.ps1" "$T/st/as_prep.ps1" "$T/st/SHA256SUMS_IF.txt" "$H:C:/OXCE_AIWorker/asrun/"
if [ "${1:-}" = "inputs" ]; then
	scp -q -i "$K" "$S/ts2/res/all/t2_all.zip" "$H:C:/OXCE_AIWorker/asrun/t2_all.zip"
	ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\asrun\\as_prep.ps1" | tr -d '\r'
fi
