#!/bin/sh
# wait for tsrun's ALL DONE (log logs/run_<phase>.txt), up to ~9 minutes per call
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
for i in $(seq 1 17); do
	L=$(ssh -i "$K" "$H" "powershell -NoProfile -Command \"Get-Content C:\\OXCE_AIWorker\\tsrun\\logs\\run_${1:-log}.txt | Select-Object -Last 1\"" 2>/dev/null | tr -d '\r')
	echo "$L"
	case "$L" in *"ALL DONE"*) exit 0 ;; esac
	ping -n 30 127.0.0.1 > /dev/null
done
exit 1
