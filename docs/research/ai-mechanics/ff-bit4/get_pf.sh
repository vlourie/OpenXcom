#!/bin/sh
# download the FF pilot's results (arena pf_* and logs) into ff/pres, drop the station's task oxce_pfrun, make pf_battles.tsv
W="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/ff"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
mkdir -p "$W/pres"
cd "$W/pres" || exit 1
ssh -i "$K" "$H" "powershell -NoProfile -Command \"Compress-Archive -Force -Path C:\\OXCE_AIWorker\\c1run\\work\\oxce_ai_probe\\arena\\pf_*,C:\\OXCE_AIWorker\\c1run\\logs\\pf_*.out,C:\\OXCE_AIWorker\\c1run\\logs\\run_pf.txt -DestinationPath C:\\OXCE_AIWorker\\c1run\\pfres.zip; (Get-FileHash C:\\OXCE_AIWorker\\c1run\\pfres.zip).Hash.ToLower()\"" 2>/dev/null
scp -q -i "$K" "$H:C:/OXCE_AIWorker/c1run/pfres.zip" . 2>/dev/null
sha256sum pfres.zip | cut -d' ' -f1
unzip -oq pfres.zip
ls | wc -l
ssh -i "$K" "$H" "powershell -NoProfile -Command \"Unregister-ScheduledTask -TaskName oxce_pfrun -Confirm:\$false; 'task removed'\"" 2>/dev/null
awk -F'\t' 'BEGIN{OFS="\t"} NR==1{print "id","mission","seed","group"; next} NF>3{print $1,$4,$3,"target"}' "$W/../c1/station/scen.tsv" | tr -d '\r' > "$W/pf_battles.tsv"
wc -l "$W/pf_battles.tsv"
