#!/bin/sh
# wait for ALL DONE in the station's run_c2.txt (checks once a minute, up to 3 h)
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
i=0
until ssh -i "$K" "$H" "powershell -NoProfile -Command \"Select-String -Quiet -Pattern 'ALL DONE' C:\\OXCE_AIWorker\\c1run\\logs\\run_c2.txt\"" 2>/dev/null | grep -q True; do
	i=$((i+1))
	[ $i -gt 180 ] && { echo TIMEOUT; break; }
	ping -n 61 127.0.0.1 > /dev/null
done
ssh -i "$K" "$H" "powershell -NoProfile -Command \"Get-Content C:\\OXCE_AIWorker\\c1run\\logs\\run_c2.txt\"" 2>/dev/null
