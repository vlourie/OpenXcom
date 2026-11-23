#!/bin/sh
# RESTORE COMBAT AUTONOMY: exe RA (hive/ra/tree), its BUILD_INFO and ra.diff, the runner and env file to rabota (C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/RA"
cp "$S/hive/ra/b-a/bin/$X" "$T/exe/RA/$X"
py -3.13 -I "$S/hive/ra/make_ra.py"
grep EXE "$T/env_RA.txt"
: > "$S/hive/ra/ra.diff"
for f in HiveCommand.h HiveCommand.cpp AIModule.h AIModule.cpp; do
	diff -u "$S/hive/cc/tree/src/Battlescape/$f" "$S/hive/ra/tree/src/Battlescape/$f" >> "$S/hive/ra/ra.diff" || true
done
( cd "$S/hive/cc/tree/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/hive/ra/tree/src/$f" || echo "differs from CC: $f"; done )
d=$(sha256sum "$S/hive/ra/ra.diff" | cut -d' ' -f1)
c=$(cat "$S/hive/ra/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/RA/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-RA\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "CC + RESTORE COMBAT AUTONOMY (OXCE_AI_HIVE_AUTONOMY=1 over OXCE_AI_HIVE=2 and OXCE_AI_HIVE_CONTACT=1)" "$d" "$h" > "$T/exe/RA/BUILD_INFO.txt"
cut -c1-120 "$T/exe/RA/BUILD_INFO.txt"
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\RA mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\RA" 2>/dev/null
scp -q -i "$K" "$T/exe/RA/$X" "$T/exe/RA/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/RA/" 2>/dev/null
( cd "$T" && sha256sum "exe/D0/$X" "exe/RA/$X" exe/D0/BUILD_INFO.txt exe/RA/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_RA.txt > SHA256SUMS.txt )
scp -q -i "$K" "$S/hive/ra/ra.diff" "$T/run_cm.py" "$T/env_RA.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3 | cut -c1-200
