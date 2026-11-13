#!/bin/sh
# HIVE hardening: exe HH (hive/tree), its BUILD_INFO and hh.diff, the runner, the load runner and env files to rabota (C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/HH"
cp "$S/hive/b-h/bin/$X" "$T/exe/HH/$X"
sed "s#/exe/D0/#/exe/HH/#" "$T/env_D0.txt" > "$T/env_HH.txt"
sed -e "s#/exe/SC/#/exe/HH/#" -e "/OXCE_AI_SCHEDULER=/d" -e "s#OXCE_AI_RACE=.*#OXCE_AI_RACE=STR_ERIDIAN#" "$T/env_SL.txt" > "$T/env_HL.txt"
echo "OXCE_AI_HIVE=2" >> "$T/env_HL.txt"
grep EXE "$T/env_HH.txt" "$T/env_HL.txt"
cp "$S/hive/load_hh.py" "$S/hive/load_hh.ps1" "$T/"
py -3.13 -I "$S/hive/patch_arms_hh.py" "$T/run_cm.py"
D0="$S/ce/tree_d0/src"
N="$S/hive/tree/src"
( cd "$S/hive" && : > hh.diff && for f in Battlescape/AIModule.cpp Battlescape/BattlescapeGame.cpp Battlescape/Pathfinding.cpp Battlescape/Pathfinding.h Battlescape/AiProbe.cpp Savegame/SavedBattleGame.cpp CMakeLists.txt; do diff -u --strip-trailing-cr "$D0/$f" "$N/$f" >> hh.diff || true; done; cat "$N/Battlescape/HiveCommand.h" "$N/Battlescape/HiveCommand.cpp" >> hh.diff )
( cd "$D0" && find . -type f | sort | while read f; do cmp -s "$f" "$N/$f" || echo "differs: $f"; done )
( cd "$N" && find . -type f | sort | while read f; do [ -f "$D0/$f" ] || echo "new: $f"; done )
d=$(sha256sum "$S/hive/hh.diff" | cut -d' ' -f1)
c=$(cat "$S/hive/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/HH/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-HH\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "DEV HEAD + al.diff + al3.diff + HIVE COMMAND CORE hardening (OXCE_AI_HIVE=0 off, 1 shadow, 2 active)" "$d" "$h" > "$T/exe/HH/BUILD_INFO.txt"
cut -c1-120 "$T/exe/HH/BUILD_INFO.txt"
( cd "$T" && sha256sum "exe/D0/$X" "exe/HH/$X" exe/D0/BUILD_INFO.txt exe/HH/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_HH.txt env_HL.txt load_hh.py load_hh.ps1 make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\HH mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\HH" 2>/dev/null
scp -q -i "$K" "$T/exe/HH/$X" "$T/exe/HH/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/HH/" 2>/dev/null
scp -q -i "$K" "$S/hive/hh.diff" "$T/run_cm.py" "$T/env_HH.txt" "$T/env_HL.txt" "$T/load_hh.py" "$T/load_hh.ps1" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3 | cut -c1-200
