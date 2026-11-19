#!/bin/sh
# STRIKE-V0: exe SV (sv/tree: D0 + SideContext / StrikeCoordinator / OrderExecutor, DEV), its BUILD_INFO and sv.diff, the
# runner with arms SO/SH/SN and env_SV to the work machine (rabota, C:/OXCE_AIWorker/cmrun); then prep (sums). Arm D is D0's
# saved logs (scpa_D_*).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/SV"
cp "$S/sv/b-svdev/bin/$X" "$T/exe/SV/$X"
sed "s#/exe/D0/#/exe/SV/#" "$T/env_D0.txt" > "$T/env_SV.txt"
grep EXE "$T/env_SV.txt"
D0="$S/ce/tree_d0/src/Battlescape"
N="$S/sv/tree/src/Battlescape"
( cd "$S/sv" && : > sv.diff && for f in AiProbe.h AiProbe.cpp BattlescapeGame.cpp; do diff -u --strip-trailing-cr "$D0/$f" "$N/$f" >> sv.diff || true; done )
( cd "$S/ce/tree_d0/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/sv/tree/src/$f" || echo "differs: $f"; done )
d=$(sha256sum "$S/sv/sv.diff" | cut -d' ' -f1)
c=$(cat "$S/sv/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/SV/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-SV\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "DEV HEAD + al.diff + al3.diff + STRIKE-V0 (AiProbe.cpp/.h, BattlescapeGame.cpp), OXCE_AI_STRIKE=0 off, 1 shadow, 2 on" "$d" "$h" > "$T/exe/SV/BUILD_INFO.txt"
cat "$T/exe/SV/BUILD_INFO.txt"
( cd "$T" && sha256sum "exe/D0/$X" "exe/SV/$X" exe/D0/BUILD_INFO.txt exe/SV/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_SV.txt make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\SV mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\SV" 2>/dev/null
scp -q -i "$K" "$T/exe/SV/$X" "$T/exe/SV/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/SV/" 2>/dev/null
scp -q -i "$K" "$S/sv/sv.diff" "$T/run_cm.py" "$T/env_SV.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3
