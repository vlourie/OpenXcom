#!/bin/sh
# AI-T2: exe T2, tsrun.py (with the t2 phases), launch and state scripts to C:/OXCE_AIWorker/tsrun; the T1 files stay as they are
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/ts2
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
X="openxcom"".exe"
mkdir -p "$T/st/exe/T2"
cp "$S/c2/b-c2dev/bin/$X" "$T/st/exe/T2/$X"
( cd "$T/st" && sha256sum "exe/T2/$X" tsrun.py ts_launch.ps1 ts_state.ps1 > SHA256SUMS_T2.txt )
cat "$T/st/SHA256SUMS_T2.txt"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force C:\\OXCE_AIWorker\\tsrun\\exe\\T2 | Out-Null\""
scp -q -i "$K" "$T/st/exe/T2/$X" "$H:C:/OXCE_AIWorker/tsrun/exe/T2/$X"
scp -q -i "$K" "$T/st/tsrun.py" "$T/st/ts_launch.ps1" "$T/st/ts_state.ps1" "$T/st/SHA256SUMS_T2.txt" "$H:C:/OXCE_AIWorker/tsrun/"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\tsrun\\ts_state.ps1" | tr -d '\r'
