#!/bin/sh
# COUNTERFIRE V0: exe CF (cf/tree: D0 + the counterfire rule, DEV), its BUILD_INFO and cf.diff, the runner with arm CF and env_CF
# to the work machine (rabota, C:/OXCE_AIWorker/cmrun); then prep (sums). Arm A is D's saved logs.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/CF"
cp "$S/cf/b-cfdev/bin/$X" "$T/exe/CF/$X"
sed "s#/exe/BO/#/exe/CF/#" "$T/env_BO.txt" > "$T/env_CF.txt"
grep EXE "$T/env_CF.txt"
D0="$S/ce/tree_d0/src/Battlescape"
N="$S/cf/tree/src/Battlescape"
( cd "$S/cf" && : > cf.diff && for f in AiProbe.h AiProbe.cpp BattlescapeGame.cpp; do diff -u --strip-trailing-cr "$D0/$f" "$N/$f" >> cf.diff || true; done )
( cd "$S/ce/tree_d0/src" && find . -type f | sort | while read f; do cmp -s "$f" "$S/cf/tree/src/$f" || echo "differs: $f"; done )
d=$(sha256sum "$S/cf/cf.diff" | cut -d' ' -f1)
c=$(cat "$S/cf/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/CF/$X" | cut -d' ' -f1)
printf 'build_label=cmrun-CF\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$c" "DEV HEAD + al.diff + al3.diff + COUNTERFIRE V0 (AiProbe.cpp/.h, BattlescapeGame.cpp), flag OXCE_AI_COUNTERFIRE=1" "$d" "$h" > "$T/exe/CF/BUILD_INFO.txt"
cat "$T/exe/CF/BUILD_INFO.txt"
( cd "$T" && sha256sum "exe/D0/$X" "exe/BO/$X" "exe/CF/$X" exe/D0/BUILD_INFO.txt exe/BO/BUILD_INFO.txt exe/CF/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_D0.txt env_BO.txt env_CF.txt make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\CF mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\CF" 2>/dev/null
scp -q -i "$K" "$T/exe/CF/$X" "$T/exe/CF/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/CF/" 2>/dev/null
scp -q -i "$K" "$S/cf/cf.diff" "$T/run_cm.py" "$T/env_CF.txt" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" 2>/dev/null | tr -d '\r' | head -3
