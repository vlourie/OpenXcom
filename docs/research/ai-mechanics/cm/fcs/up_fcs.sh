#!/bin/sh
# FIRST CONTACT SURVIVAL: exe FC (fcs/tree: D0 + the code, DEV), its BUILD_INFO and fcs.diff, the runner and env_FC to the work machine (rabota, C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/FC"
cp "$S/fcs/b-fc/bin/$X" "$T/exe/FC/$X"
sed "s#/exe/D0/#/exe/FC/#" "$T/env_D0.txt" > "$T/env_FC.txt"
grep EXE "$T/env_FC.txt"
D0="$S/ce/tree_d0/src/Battlescape"
N="$S/fcs/tree/src/Battlescape"
( cd "$S/fcs" && : > fcs.diff && for f in AiProbe.h AiProbe.cpp AIModule.cpp TileEngine.h TileEngine.cpp BattlescapeGame.cpp; do diff -u --strip-trailing-cr "$D0/$f" "$N/$f" >> fcs.diff || true; done )
( cd "$S/ce/tree_d0/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/fcs/tree/src/$f" || echo "differs: $f"; done )
d=$(sha256sum "$S/fcs/fcs.diff" | cut -d' ' -f1)
c=$(cat "$S/fcs/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/FC/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-FC\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "DEV HEAD + al.diff + al3.diff + FIRST CONTACT SURVIVAL V0 (OXCE_AI_FCS=0 off, 1 shadow, 2 the rule)" "$d" "$h" > "$T/exe/FC/BUILD_INFO.txt"
cut -c1-120 "$T/exe/FC/BUILD_INFO.txt"
( cd "$T" && sha256sum "exe/D0/$X" "exe/FC/$X" exe/D0/BUILD_INFO.txt exe/FC/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_FC.txt make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\FC mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\FC" 2>/dev/null
scp -q -i "$K" "$T/exe/FC/$X" "$T/exe/FC/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/FC/" 2>/dev/null
scp -q -i "$K" "$S/fcs/fcs.diff" "$T/run_cm.py" "$T/env_FC.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3 | cut -c1-200
