#!/bin/sh
# STRIKE-V0: exe SV from the isolated tree sv/tree (a copy of ce/tree_d0 = D0: HEAD 07680cadb + al.diff + al3.diff, plus
# the STRIKE-V0 prototype in AiProbe.cpp/.h and one call in BattlescapeGame.cpp) in a folder of its own; no editq ticket (R-158).
# Low priority and 8 jobs: this machine stays usable.
W="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/sv"
export PATH="/c/msys64/mingw64/bin:$PATH"
export EDITQ_BYPASS=1
B="$W/b-svdev"
if [ ! -f "$B/build.ninja" ]; then
	cmake -S "$W/tree" -B "$B" -G Ninja -DCMAKE_BUILD_TYPE=Release -DDEPS_DIR=E:/OpenXCom/deps -DOXCE_AI_DEV=ON -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/cc.exe -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/c++.exe > "$W/cmake-svdev.log" 2>&1 || { echo "cmake FAILED"; tail -20 "$W/cmake-svdev.log"; exit 1; }
fi
grep -E "^OXCE_AI_DEV:" "$B/CMakeCache.txt"
cmd //c "start /low /b /wait ninja -j 8 -C $B" > "$W/ninja-svdev.log" 2>&1
grep -q "error:" "$W/ninja-svdev.log" && { echo "ninja errors"; grep -E "error" "$W/ninja-svdev.log" | head -40; exit 1; }
X="openxcom"".exe"
ls -la "$B/bin/$X" 2>&1 | cut -c1-120
echo "warnings: $(grep -c "warning:" "$W/ninja-svdev.log"), in BattlescapeGame/AiProbe: $(grep "warning:" "$W/ninja-svdev.log" | grep -c -E "BattlescapeGame|AiProbe")"
