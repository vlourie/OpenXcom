#!/bin/sh
# TACTICAL STAGE 2: exe BO (bo/tree: D0 + the experiment's orders, DEV), its BUILD_INFO and bo.diff, the runner with arms
# FB/AC/FD/BO, env_BO to the work machine (rabota, C:/OXCE_AIWorker/cmrun); then prep (sums). Arm A is D (exe D0) as uploaded.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/BO"
cp "$S/bo/b-bodev/bin/$X" "$T/exe/BO/$X"
D0="$S/ce/tree_d0/src/Battlescape"
N="$S/bo/tree/src/Battlescape"
( cd "$S/bo" && : > bo.diff && for f in AiProbe.h AiProbe.cpp BattlescapeGame.cpp; do diff -u --strip-trailing-cr "$D0/$f" "$N/$f" >> bo.diff || true; done )
( cd "$S/ce/tree_d0/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/bo/tree/src/$f" || echo "differs: $f"; done )
d=$(sha256sum "$S/bo/bo.diff" | cut -d' ' -f1)
c=$(cat "$S/bo/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/BO/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-BO\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "DEV HEAD + al.diff + al3.diff + TACTICAL STAGE 2 orders (AiProbe.cpp/.h, BattlescapeGame.cpp), flags OXCE_AI_ORDER_FIRE / OXCE_AI_ORDER_AVOID" "$d" "$h" > "$T/exe/BO/BUILD_INFO.txt"
cat "$T/exe/BO/BUILD_INFO.txt"
( cd "$T" && sha256sum "exe/D0/$X" "exe/BO/$X" exe/D0/BUILD_INFO.txt exe/BO/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_BO.txt make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\BO mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\BO" 2>/dev/null
scp -q -i "$K" "$T/exe/BO/$X" "$T/exe/BO/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/BO/" 2>/dev/null
scp -q -i "$K" "$S/bo/bo.diff" "$T/run_cm.py" "$T/env_BO.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3
