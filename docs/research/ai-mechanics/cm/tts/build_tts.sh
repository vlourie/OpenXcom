#!/bin/sh
# TACTICAL TURN SOLVER: exe from the isolated tree tts/tree (git archive 07680cadb + al + al3 + patch_tts.py + TurnSolver); no editq ticket (R-158). Low priority, 8 jobs. sh build_tts.sh
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
W="$S/tts"
export PATH="/c/msys64/mingw64/bin:$PATH"
export EDITQ_BYPASS=1
B="$W/b-d"
if [ ! -f "$B/build.ninja" ]; then
	cmake -S "$W/tree" -B "$B" -G Ninja -DCMAKE_BUILD_TYPE=Release -DDEPS_DIR=E:/OpenXCom/deps -DOXCE_AI_DEV=ON -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/cc.exe -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/c++.exe > "$W/cmake-c.log" 2>&1
fi
grep -E "^OXCE_AI_DEV:" "$B/CMakeCache.txt"
cmd //c "start /low /b /wait ninja -j 8 -C $B" > "$W/ninja-d.log" 2>&1
grep -q "error:" "$W/ninja-d.log" && { echo "ninja errors"; grep -E "error" "$W/ninja-d.log" | cut -c1-260 | head -30; exit 1; }
X="openxcom"".exe"
ls -la "$B/bin/$X" 2>&1 | cut -c1-120
grep -E "warning" "$W/ninja-d.log" | grep -a "TurnSolver" | cut -c1-200 | head
tail -1 "$W/ninja-d.log" | cut -c1-160
