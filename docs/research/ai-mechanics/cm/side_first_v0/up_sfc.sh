#!/bin/sh
# SIDE-FIRST COMBAT: exe SD with its BUILD_INFO, env file and runner to rabota (C:/OXCE_AIWorker/cmrun), hashes compared. sh up_sfc.sh
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
W=$S/sfc
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/SD"
cp "$W/b-d/bin/$X" "$T/exe/SD/$X"
sed 's#/exe/D0/#/exe/SD/#' "$T/env_D0.txt" > "$T/env_SD.txt"
py -3.13 -I "$W/patch_run.py" "$T/run_cm.py"
h=$(sha256sum "$T/exe/SD/$X" | cut -d' ' -f1)
s1=$(sha256sum "$W/SideCombatDirector.cpp" | cut -d' ' -f1)
s2=$(sha256sum "$W/tree/src/Battlescape/BattlescapeGame.cpp" | cut -d' ' -f1)
printf 'build_label=cmrun-SD\ngit_commit=07680cadb\nnote=HEAD + al.diff + al3.diff + SIDE-FIRST COMBAT (SideCombatDirector.h/.cpp, hooks in handleAI, AIModule::clearReserve)\ndirector_sha256=%s\nbattlescapegame_sha256=%s\nexe_sha256=%s\n' "$s1" "$s2" "$h" > "$T/exe/SD/BUILD_INFO.txt"
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\SD mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\SD" 2>/dev/null
scp -q -i "$K" "$T/exe/SD/$X" "$T/exe/SD/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/SD/" 2>/dev/null
scp -q -i "$K" "$T/env_SD.txt" "$T/run_cm.py" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -Command \"(Get-FileHash C:\\OXCE_AIWorker\\cmrun\\exe\\SD\\$X).Hash; (Get-FileHash C:\\OXCE_AIWorker\\cmrun\\exe\\D0\\$X).Hash\"" 2>/dev/null
( cd "$T" && sha256sum "exe/SD/$X" "exe/D0/$X" ) | cut -c1-100
