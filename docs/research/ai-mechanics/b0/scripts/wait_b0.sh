#!/bin/sh
# wait until logs/run_<tag>.txt on the station says ALL DONE (or 90 minutes), print its tail
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
TAG=$1
for i in $(seq 1 90); do
	T=$(ssh -i "$K" "$H" "powershell -NoProfile -Command \"Get-Content C:\\OXCE_AIWorker\\b0run\\logs\\run_$TAG.txt -Tail 3\"" 2>/dev/null)
	case "$T" in *"ALL DONE"*) break ;; esac
	ping -n 61 127.0.0.1 > /dev/null
done
ssh -i "$K" "$H" "powershell -NoProfile -Command \"Get-Content C:\\OXCE_AIWorker\\b0run\\logs\\run_$TAG.txt\"" 2>/dev/null | tail -40
