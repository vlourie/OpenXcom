#!/bin/sh
# HIVE D2 CORRECTION: exe D2 (hive/d2/tree), its BUILD_INFO and d2.diff, the runner and env file to rabota (C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/D2"
cp "$S/hive/d2/b-d/bin/$X" "$T/exe/D2/$X"
py -3.13 -I "$S/hive/d2/make_d2.py"
grep EXE "$T/env_D2.txt"
: > "$S/hive/d2/d2.diff"
for f in Battlescape/HiveCommand.h Battlescape/HiveCommand.cpp Battlescape/AIModule.h Battlescape/AIModule.cpp Savegame/SavedBattleGame.h Savegame/SavedBattleGame.cpp; do
	diff -u "$S/hive/us/tree/src/$f" "$S/hive/d2/tree/src/$f" >> "$S/hive/d2/d2.diff" || true
done
( cd "$S/hive/us/tree/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/hive/d2/tree/src/$f" || echo "differs from US: $f"; done )
d=$(sha256sum "$S/hive/d2/d2.diff" | cut -d' ' -f1)
c=$(cat "$S/hive/d2/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/D2/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-D2\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "US + HIVE D2 CORRECTION: a refused offer costs no try, the kept node is not taken away, timings (OXCE_AI_HIVE=1 shadow, 2 active)" "$d" "$h" > "$T/exe/D2/BUILD_INFO.txt"
cut -c1-120 "$T/exe/D2/BUILD_INFO.txt"
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\D2 mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\D2" 2>/dev/null
scp -q -i "$K" "$T/exe/D2/$X" "$T/exe/D2/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/D2/" 2>/dev/null
( cd "$T" && sha256sum "exe/D0/$X" "exe/D2/$X" exe/D0/BUILD_INFO.txt exe/D2/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_D2.txt > SHA256SUMS.txt )
scp -q -i "$K" "$S/hive/d2/d2.diff" "$T/run_cm.py" "$T/env_D2.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3 | cut -c1-200
