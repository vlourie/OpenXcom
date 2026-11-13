#!/bin/sh
# COORDINATED_ENGAGEMENT_V1: pack the series <prefix>... on rabota (pack_logs.py), bring the zips here and unpack them into
# cm/res/all (out/<label>/openxcom.log.gz, arena/<label>.tsv)
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
for p in "$@"; do
	ssh -i "$K" -o BatchMode=yes "$H" "C:\\OXCE_AIWorker\\python\\python.exe -I C:\\OXCE_AIWorker\\cmrun\\pack_logs.py C:\\OXCE_AIWorker\\cmrun $p C:\\OXCE_AIWorker\\cmrun\\res_$p.zip" 2>&1 | grep -v "post-quantum\|store now\|openssh.com" | tail -1
	scp -q -i "$K" "$H:C:/OXCE_AIWorker/cmrun/res_$p.zip" "$S/cm/res/" 2>/dev/null
	unzip -o -q "$S/cm/res/res_$p.zip" -d "$S/cm/res/all"
	echo "$p: $(sha256sum "$S/cm/res/res_$p.zip" | cut -c1-16) logs $(ls -d "$S/cm/res/all/out/$p"_* | wc -l)"
done
