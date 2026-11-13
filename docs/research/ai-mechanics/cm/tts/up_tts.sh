#!/bin/sh
# TACTICAL TURN SOLVER V0: exe TS, its BUILD_INFO, the diff against D0, env files, runner and saves to rabota (C:/OXCE_AIWorker/cmrun); then prep (sums).
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
T=$S/cm/st
W=$S/tts
K="$HOME/.ssh/oxce_worker"
H="user@100.93.184.94"
X="openxcom"".exe"
mkdir -p "$T/exe/TS"
cp "$W/b-d/bin/$X" "$T/exe/TS/$X"
sed 's#/exe/UA/#/exe/D0/#; /OXCE_AI_HIVE=/d; /OXCE_AI_RACE=/d' "$T/env_UL.txt" > "$T/env_ZD.txt"
sed 's#/exe/D0/#/exe/TS/#' "$T/env_ZD.txt" > "$T/env_ZS.txt"
echo "OXCE_AI_TTS=1" >> "$T/env_ZS.txt"
c=$(cat "$W/tree/GIT_COMMIT.txt")
h=$(sha256sum "$T/exe/TS/$X" | cut -d' ' -f1)
s1=$(sha256sum "$W/tree/src/Battlescape/TurnSolver.cpp" | cut -d' ' -f1)
s2=$(sha256sum "$W/tree/src/Battlescape/BattlescapeGame.cpp" | cut -d' ' -f1)
printf 'build_label=cmrun-TS\ngit_commit=%s\nnote=%s\nturnsolver_sha256=%s\nbattlescapegame_sha256=%s\nexe_sha256=%s\n' "$c" "HEAD + al.diff + al3.diff + TACTICAL TURN SOLVER V0 (TurnSolver.h/.cpp, three hooks in handleAI, patch_tts.py)" "$s1" "$s2" "$h" > "$T/exe/TS/BUILD_INFO.txt"
cat "$T/exe/TS/BUILD_INFO.txt" | cut -c1-140
py -3.13 -I "$W/make_scene.py" "$W/src_m10.asav" "$W/scene_s1.asav" 1001 | tail -1 | cut -c1-120
py -3.13 -I "$W/make_scene.py" "$W/src_m10.asav" "$W/scene_s2.asav" 2002 | tail -1 | cut -c1-120
ssh -i "$K" "$H" "if not exist C:\\OXCE_AIWorker\\cmrun\\exe\\TS mkdir C:\\OXCE_AIWorker\\cmrun\\exe\\TS & if not exist C:\\OXCE_AIWorker\\cmrun\\saves_tts mkdir C:\\OXCE_AIWorker\\cmrun\\saves_tts" 2>/dev/null
scp -q -i "$K" "$T/exe/TS/$X" "$T/exe/TS/BUILD_INFO.txt" "$H:C:/OXCE_AIWorker/cmrun/exe/TS/" 2>/dev/null
scp -q -i "$K" "$W/scene_s1.asav" "$W/scene_s2.asav" "$W/src_m10.asav" "$H:C:/OXCE_AIWorker/cmrun/saves_tts/" 2>/dev/null
scp -q -i "$K" "$T/load_tts.py" "$T/load_tts.ps1" "$T/env_ZD.txt" "$T/env_ZS.txt" "$H:C:/OXCE_AIWorker/cmrun/" 2>/dev/null
ssh -i "$K" "$H" "powershell -NoProfile -Command \"Get-FileHash C:\\OXCE_AIWorker\\cmrun\\exe\\TS\\$X,C:\\OXCE_AIWorker\\cmrun\\exe\\D0\\$X,C:\\OXCE_AIWorker\\cmrun\\saves_tts\\scene_s1.asav,C:\\OXCE_AIWorker\\cmrun\\saves_tts\\scene_s2.asav,C:\\OXCE_AIWorker\\cmrun\\saves_tts\\src_m10.asav | ForEach-Object { \$_.Hash.ToLower() + ' ' + \$_.Path }\"" 2>/dev/null | tr -d '\r' | cut -c1-130
( cd "$T" && sha256sum "exe/TS/$X" "exe/D0/$X" ) | cut -c1-100
( cd "$W" && sha256sum scene_s1.asav scene_s2.asav src_m10.asav ) | cut -c1-100
