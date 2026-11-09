#!/bin/sh
# download the FF run's results (arena ff_* and logs) into ff/res, then drop the station's task oxce_ffrun
W="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/ff"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
mkdir -p "$W/res"
cd "$W/res" || exit 1
ssh -i "$K" "$H" "powershell -NoProfile -Command \"Compress-Archive -Force -Path C:\\OXCE_AIWorker\\c1run\\work\\oxce_ai_probe\\arena\\ff_*,C:\\OXCE_AIWorker\\c1run\\logs\\ff_*.out,C:\\OXCE_AIWorker\\c1run\\logs\\run_ff.txt -DestinationPath C:\\OXCE_AIWorker\\c1run\\ffres.zip; (Get-FileHash C:\\OXCE_AIWorker\\c1run\\ffres.zip).Hash.ToLower()\"" 2>/dev/null
scp -q -i "$K" "$H:C:/OXCE_AIWorker/c1run/ffres.zip" . 2>/dev/null
sha256sum ffres.zip | cut -d' ' -f1
unzip -oq ffres.zip
ls | wc -l
ssh -i "$K" "$H" "powershell -NoProfile -Command \"Unregister-ScheduledTask -TaskName oxce_ffrun -Confirm:\$false; 'task removed'\"" 2>/dev/null
