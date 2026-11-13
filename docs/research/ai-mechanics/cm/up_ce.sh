#!/bin/sh
# COORDINATED_ENGAGEMENT_V1: exe D0 (ce/tree_d0: HEAD + al.diff + al3.diff, DEV) and exe CE (ce/tree: the same + the commander,
# DEV), the runner with arms D/C/E, the env files and make_cfg.py to the work machine (rabota); then prep (sums) and base.cfg
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/D0" "$T/exe/CE"
cp "$S/ce/b-d0dev/bin/$X" "$T/exe/D0/$X"
cp "$S/ce/b-cedev/bin/$X" "$T/exe/CE/$X"
( cd "$S/ce" && { diff -u AIModule.d0.cpp tree/src/Battlescape/AIModule.cpp > ce.diff || true; }; diff -u AIModule.d0.h tree/src/Battlescape/AIModule.h >> ce.diff || true )
d=$(sha256sum "$S/ce/ce.diff" | cut -d' ' -f1)
c=$(cat "$S/ce/tree/GIT_COMMIT.txt")
for e in D0 CE; do
	h=$(sha256sum "$T/exe/$e/$X" | cut -d' ' -f1)
	if [ $e = D0 ]; then note="DEV (OXCE_AI_DEV=ON, Release) HEAD + al.diff + al3.diff (P0 vs P1 switches, OXCE_AI_RELEASE_BASE)"; p=-; else note="DEV HEAD + al.diff + al3.diff + COORDINATED_ENGAGEMENT_V1 (AIModule.cpp/.h), flag OXCE_AI_COORD_ENGAGE"; p=$d; fi
	printf 'build_label=cmrun-%s\ngit_commit=%s\nnote=%s\npatch_sha256=%s\nexe_sha256=%s\n' "$e" "$c" "$note" "$p" "$h" > "$T/exe/$e/BUILD_INFO.txt"
done
( cd "$T" && sha256sum "exe/CM/$X" "exe/SR/$X" "exe/D0/$X" "exe/CE/$X" exe/*/BUILD_INFO.txt saves/*.sav scen.tsv stand/ai_arena.py stand/ai_probe.py run_cm.py env_CM.txt env_SR.txt env_D0.txt env_CE.txt make_cfg.py cm_launch.ps1 cm_prep.ps1 > SHA256SUMS.txt )
grep -E "D0|CE|run_cm|make_cfg|launch" "$T/SHA256SUMS.txt"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force C:\\OXCE_AIWorker\\cmrun\\exe\\D0, C:\\OXCE_AIWorker\\cmrun\\exe\\CE | Out-Null\""
scp -q -i "$K" "$T/exe/D0/$X" "$T/exe/D0/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/D0/"
scp -q -i "$K" "$T/exe/CE/$X" "$T/exe/CE/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/CE/"
scp -q -i "$K" "$S/ce/ce.diff" "$T/run_cm.py" "$T/env_D0.txt" "$T/env_CE.txt" "$T/make_cfg.py" "$T/cm_launch.ps1" "$T/SHA256SUMS.txt" "$H:C:/OXCE_AIWorker/cmrun/"
ssh -i "$K" "$H" "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\OXCE_AIWorker\\cmrun\\cm_prep.ps1" | tr -d '\r' | head -3
ssh -i "$K" "$H" "C:\\OXCE_AIWorker\\python\\python.exe C:\\OXCE_AIWorker\\cmrun\\make_cfg.py" | tr -d '\r'
