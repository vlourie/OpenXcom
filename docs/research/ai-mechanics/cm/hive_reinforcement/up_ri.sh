#!/bin/sh
# REINFORCEMENT INTELLIGENCE V0: exe RI (hive/ri/tree), its BUILD_INFO and ri.diff, the runner, env files and the load runner to rabota (C:/OXCE_AIWorker/cmrun); then prep (sums). Nothing else on that machine is touched.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/RI"
cp "$S/hive/ri/b-r/bin/$X" "$T/exe/RI/$X"
grep EXE "$T/env_RI.txt" "$T/env_RL.txt"
diff -u "$S/hive/cc/tree/src/Battlescape/HiveCommand.cpp" "$S/hive/ri/tree/src/Battlescape/HiveCommand.cpp" > "$S/hive/ri/ri.diff" || true
( cd "$S/hive/cc/tree/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/hive/ri/tree/src/$f" || echo "differs from CC: $f"; done )
d=$(sha256sum "$S/hive/ri/ri.diff" | cut -d' ' -f1)
c=$(cat "$S/hive/ri/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/RI/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-RI\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "CC + REINFORCEMENT INTELLIGENCE V0 (OXCE_AI_HIVE_REINF=1 over OXCE_AI_HIVE=2 and OXCE_AI_HIVE_CONTACT=1)" "$d" "$h" > "$T/exe/RI/BUILD_INFO.txt"
cut -c1-120 "$T/exe/RI/BUILD_INFO.txt"
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\RI mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\RI" 2>/dev/null
scp -q -i "$K" "$T/exe/RI/$X" "$T/exe/RI/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/RI/" 2>/dev/null
scp -q -i "$K" "$S/hive/ri/ri.diff" "$T/run_cm.py" "$T/env_RI.txt" "$T/env_RL.txt" "$T/load_ri.py" "$T/load_ri.ps1" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "certutil -hashfile C:\\OXCE_AIWorker\\cmrun\\exe\\RI\\$X SHA256" 2>/dev/null | tr -d '\r' | sed -n 2p
echo "local $h"
