#!/bin/sh
# UNIFIED ARMY CONTROL V0: exe UA (hive/ua/tree), its BUILD_INFO and ua.diff, the runner and env file to rabota (C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/UA"
cp "$S/hive/ua/b-u/bin/$X" "$T/exe/UA/$X"
py -3.13 -I "$S/hive/ua/make_ua.py"
grep EXE "$T/env_UA.txt"
: > "$S/hive/ua/ua.diff"
for f in Battlescape/HiveCommand.h Battlescape/HiveCommand.cpp Battlescape/AIModule.h Battlescape/AIModule.cpp Savegame/SavedBattleGame.h Savegame/SavedBattleGame.cpp; do
	diff -u "$S/hive/ra/tree/src/$f" "$S/hive/ua/tree/src/$f" >> "$S/hive/ua/ua.diff" || true
done
( cd "$S/hive/ra/tree/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/hive/ua/tree/src/$f" || echo "differs from RA: $f"; done )
d=$(sha256sum "$S/hive/ua/ua.diff" | cut -d' ' -f1)
c=$(cat "$S/hive/ua/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/UA/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-UA\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "RA minus orders and stand + UNIFIED ARMY CONTROL V0 (OXCE_AI_HIVE=1 shadow, 2 active)" "$d" "$h" > "$T/exe/UA/BUILD_INFO.txt"
cut -c1-120 "$T/exe/UA/BUILD_INFO.txt"
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\UA mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\UA" 2>/dev/null
scp -q -i "$K" "$T/exe/UA/$X" "$T/exe/UA/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/UA/" 2>/dev/null
( cd "$T" && sha256sum "exe/D0/$X" "exe/UA/$X" exe/D0/BUILD_INFO.txt exe/UA/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_UA.txt > SHA256SUMS.txt )
scp -q -i "$K" "$S/hive/ua/ua.diff" "$T/run_cm.py" "$T/env_UA.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3 | cut -c1-200
