#!/bin/sh
# fetch tsrun battle logs and run notes of one prefix into ts/res/out (zip on the station, then unz.py)
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
P=${1:-E}
ssh -i "$K" "$H" "powershell -NoProfile -Command \"Compress-Archive -Force -Path C:\\OXCE_AIWorker\\tsrun\\out\\${P}* -DestinationPath C:\\OXCE_AIWorker\\tsrun\\get_$P.zip\"" 2>/dev/null
mkdir -p "$S/ts/res/zip" "$S/ts/res/out"
scp -q -i "$K" "$H:C:/OXCE_AIWorker/tsrun/get_$P.zip" "$S/ts/res/zip/get_$P.zip"
py -3.13 -I "$S/b0/unz.py" "$S/ts/res/zip/get_$P.zip" "$S/ts/res/out"
ls "$S/ts/res/out" | grep -c "^$P"
