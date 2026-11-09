#!/bin/sh
# fetch asrun battle logs and run notes of one prefix (AI-IF: G0, G1, G2) into as/res/out (zip on the station, then unz.py)
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
P=${1:-G}
ssh -i "$K" "$H" "powershell -NoProfile -Command \"Compress-Archive -Force -Path C:\\OXCE_AIWorker\\asrun\\out\\${P}* -DestinationPath C:\\OXCE_AIWorker\\asrun\\get_$P.zip\"" 2>/dev/null
mkdir -p "$S/as/res/zip" "$S/as/res/out"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/asrun/get_$P.zip" "$S/as/res/zip/get_$P.zip"
py -3.13 -I "$S/b0/unz.py" "$S/as/res/zip/get_$P.zip" "$S/as/res/out"
ls "$S/as/res/out" | grep -c "^$P"
