#!/bin/sh
# MISSION-LEVEL TACTICS: exe MD (md/tree: D0 + the [AIMISSION] code, DEV), its BUILD_INFO and md.diff, the runner and env_MD to the work
# machine (rabota, C:/OXCE_AIWorker/cmrun); then prep (sums). Arm D is D0's saved logs (scpa_D_*, svh_SH_*).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/MD"
cp "$S/md/b-mddev/bin/$X" "$T/exe/MD/$X"
sed "s#/exe/D0/#/exe/MD/#" "$T/env_D0.txt" > "$T/env_MD.txt"
grep EXE "$T/env_MD.txt"
D0="$S/ce/tree_d0/src/Battlescape"
N="$S/md/tree/src/Battlescape"
( cd "$S/md" && : > md.diff && for f in AiProbe.h AiProbe.cpp AIModule.cpp TileEngine.cpp BattlescapeGame.cpp; do diff -u --strip-trailing-cr "$D0/$f" "$N/$f" >> md.diff || true; done )
( cd "$S/ce/tree_d0/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/md/tree/src/$f" || echo "differs: $f"; done )
d=$(sha256sum "$S/md/md.diff" | cut -d' ' -f1)
c=$(cat "$S/md/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/MD/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-MD\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "DEV HEAD + al.diff + al3.diff + MISSION-LEVEL TACTICS (OXCE_AI_MDIR=0 off, 1 log only, 2 the order on)" "$d" "$h" > "$T/exe/MD/BUILD_INFO.txt"
cat "$T/exe/MD/BUILD_INFO.txt" | cut -c1-120
( cd "$T" && sha256sum "exe/D0/$X" "exe/MD/$X" exe/D0/BUILD_INFO.txt exe/MD/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_MD.txt make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\MD mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\MD" 2>/dev/null
scp -q -i "$K" "$T/exe/MD/$X" "$T/exe/MD/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/MD/" 2>/dev/null
scp -q -i "$K" "$S/md/md.diff" "$T/run_cm.py" "$T/env_MD.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3
