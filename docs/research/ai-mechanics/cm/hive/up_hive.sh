#!/bin/sh
# HIVE COMMAND CORE V0: exe HV (hive/tree: D0 + HiveCommand, DEV), its BUILD_INFO and hive.diff, the runner and env_HV to the work machine (rabota, C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/HV"
cp "$S/hive/b-h/bin/$X" "$T/exe/HV/$X"
sed "s#/exe/D0/#/exe/HV/#" "$T/env_D0.txt" > "$T/env_HV.txt"
grep EXE "$T/env_HV.txt"
py -3.13 -I "$S/hive/patch_arms.py" "$T/run_cm.py"
D0="$S/ce/tree_d0/src"
N="$S/hive/tree/src"
( cd "$S/hive" && : > hive.diff && for f in Battlescape/AIModule.cpp Battlescape/BattlescapeGame.cpp CMakeLists.txt; do diff -u --strip-trailing-cr "$D0/$f" "$N/$f" >> hive.diff || true; done; cat "$N/Battlescape/HiveCommand.h" "$N/Battlescape/HiveCommand.cpp" >> hive.diff )
( cd "$D0" && find . -type f | sort | while read f; do cmp -s "$f" "$N/$f" || echo "differs: $f"; done )
( cd "$N" && find . -type f | sort | while read f; do [ -f "$D0/$f" ] || echo "new: $f"; done )
d=$(sha256sum "$S/hive/hive.diff" | cut -d' ' -f1)
c=$(cat "$S/hive/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/HV/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-HV\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "DEV HEAD + al.diff + al3.diff + HIVE COMMAND CORE V0 (OXCE_AI_HIVE=0 off, 1 shadow, 2 active)" "$d" "$h" > "$T/exe/HV/BUILD_INFO.txt"
cut -c1-120 "$T/exe/HV/BUILD_INFO.txt"
( cd "$T" && sha256sum "exe/D0/$X" "exe/HV/$X" exe/D0/BUILD_INFO.txt exe/HV/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_HV.txt make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\HV mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\HV" 2>/dev/null
scp -q -i "$K" "$T/exe/HV/$X" "$T/exe/HV/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/HV/" 2>/dev/null
scp -q -i "$K" "$S/hive/hive.diff" "$T/run_cm.py" "$T/env_HV.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3 | cut -c1-200
