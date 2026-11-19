#!/bin/sh
# download the C2 pilot's results (arena c2_* and logs) into c2/res
W="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/c2"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
mkdir -p "$W/res"
cd "$W/res" || exit 1
ssh -i "$K" "$H" "powershell -NoProfile -Command \"Compress-Archive -Force -Path C:\\OXCE_AIWorker\\c1run\\work\\oxce_ai_probe\\arena\\c2_*,C:\\OXCE_AIWorker\\c1run\\logs\\c2_*.out,C:\\OXCE_AIWorker\\c1run\\logs\\run_c2.txt -DestinationPath C:\\OXCE_AIWorker\\c1run\\c2res.zip; (Get-FileHash C:\\OXCE_AIWorker\\c1run\\c2res.zip).Hash.ToLower()\"" 2>/dev/null
scp -q -i "$K" "$H:C:/OXCE_AIWorker/c1run/c2res.zip" . 2>/dev/null
sha256sum c2res.zip | cut -d' ' -f1
unzip -oq c2res.zip
ls | wc -l
