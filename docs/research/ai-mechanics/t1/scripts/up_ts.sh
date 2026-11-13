#!/bin/sh
# AI-T1: bundle (exe T1, tsrun.py, launch/prep/cleanup scripts) to C:/OXCE_AIWorker/tsrun, prep from pvrun, then pvrun cleanup
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/ts
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
X="openxcom"".exe"
mkdir -p "$T/st/exe/T1"
cp "$S/c2/b-c2dev/bin/$X" "$T/st/exe/T1/$X"
( cd "$T/st" && sha256sum "exe/T1/$X" tsrun.py ts_launch.ps1 ts_prep.ps1 pv_cleanup.ps1 | sed 's#/#\\#g' > SHA256SUMS.txt )
cat "$T/st/SHA256SUMS.txt"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force C:\\OXCE_AIWorker\\tsrun\\exe\\T1 | Out-Null\""
scp -q -i "$K" "$T/st/exe/T1/$X" "$H:C:/OXCE_AIWorker/tsrun/exe/T1/$X"
scp -q -i "$K" "$T/st/tsrun.py" "$T/st/ts_launch.ps1" "$T/st/ts_prep.ps1" "$T/st/pv_cleanup.ps1" "$T/st/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/tsrun/"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\tsrun\\ts_prep.ps1"
