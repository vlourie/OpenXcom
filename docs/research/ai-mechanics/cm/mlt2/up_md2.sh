#!/bin/sh
# MISSION-LEVEL TACTICS STAGE 2: exe M2 (md2/tree: D0 + the stage 2 code, DEV), its BUILD_INFO and md2.diff, the runner and env_M2 to the work
# machine (rabota, C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/M2"
cp "$S/md2/b-md2/bin/$X" "$T/exe/M2/$X"
sed "s#/exe/D0/#/exe/M2/#" "$T/env_D0.txt" > "$T/env_M2.txt"
grep EXE "$T/env_M2.txt"
D0="$S/ce/tree_d0/src/Battlescape"
N="$S/md2/tree/src/Battlescape"
( cd "$S/md2" && : > md2.diff && for f in AiProbe.h AiProbe.cpp AIModule.cpp TileEngine.h TileEngine.cpp BattlescapeGame.cpp; do diff -u --strip-trailing-cr "$D0/$f" "$N/$f" >> md2.diff || true; done )
( cd "$S/ce/tree_d0/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/md2/tree/src/$f" || echo "differs: $f"; done )
d=$(sha256sum "$S/md2/md2.diff" | cut -d' ' -f1)
c=$(cat "$S/md2/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/M2/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-M2\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "DEV HEAD + al.diff + al3.diff + MISSION-LEVEL TACTICS STAGE 2 (OXCE_AI_MDIR=0 off, 1 log only, 2 the order on)" "$d" "$h" > "$T/exe/M2/BUILD_INFO.txt"
cat "$T/exe/M2/BUILD_INFO.txt" | cut -c1-120
( cd "$T" && sha256sum "exe/D0/$X" "exe/M2/$X" exe/D0/BUILD_INFO.txt exe/M2/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_M2.txt make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\M2 mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\M2" 2>/dev/null
scp -q -i "$K" "$T/exe/M2/$X" "$T/exe/M2/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/M2/" 2>/dev/null
scp -q -i "$K" "$S/md2/md2.diff" "$T/run_cm.py" "$T/env_M2.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3
