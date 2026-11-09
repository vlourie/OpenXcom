#!/bin/sh
# download the stage 0B outputs zipped on the station (pack.ps1) into b0/res/<tag>; usage: get_b0.sh <tag> [out filter]
W="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/b0"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
TAG=${1:-res}
F=${2:-*}
mkdir -p "$W/res/$TAG"
cd "$W/res/$TAG" || exit 1
scp -q -i "$K" "$W/st/pack.ps1" "$H:C:/OXCE_AIWorker/b0run/pack.ps1" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\b0run\\pack.ps1 -Tag $TAG -Filter $F" 2>/dev/null
scp -q -i "$K" "$H:C:/OXCE_AIWorker/b0run/b0_$TAG.zip" . 2>/dev/null
sha256sum "b0_$TAG.zip" | cut -d' ' -f1
py -3.13 "$W/unz.py" "b0_$TAG.zip" .
ls
