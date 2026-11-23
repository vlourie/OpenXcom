#!/bin/sh
# MISSION-LEVEL TACTICS: exe MD from the isolated tree md/tree (a copy of ce/tree_d0 = D0: HEAD 07680cadb + al.diff + al3.diff, plus
# the [AIMISSION] probe) in a folder of its own; no editq ticket (R-158). Low priority and 8 jobs: this machine stays usable.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
W="$S/md"
export PATH="/c/msys64/mingw64/bin:$PATH"
export EDITQ_BYPASS=1
if [ ! -d "$W/tree/src" ]; then
	cp -r "$S/ce/tree_d0" "$W/tree" || exit 1
	PYTHONIOENCODING=utf-8 py -3.13 -I "$W/patch.py" "$S" || exit 1
	py -3.13 -I "$S/sv/crlf.py" "$W/tree/src/Battlescape/AiProbe.h" "$W/tree/src/Battlescape/AiProbe.cpp" "$W/tree/src/Battlescape/AIModule.cpp" "$W/tree/src/Battlescape/TileEngine.cpp"
fi
B="$W/b-mddev"
if [ ! -f "$B/build.ninja" ]; then
	cmake -S "$W/tree" -B "$B" -G Ninja -DCMAKE_BUILD_TYPE=Release -DDEPS_DIR=E:/OpenXCom/deps -DOXCE_AI_DEV=ON -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/cc.exe -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/c++.exe > "$W/cmake-mddev.log" 2>&1 || { tail -5 "$W/cmake-mddev.log"; exit 1; }
fi
grep -E "^OXCE_AI_DEV:" "$B/CMakeCache.txt"
cmd //c "start /low /b /wait ninja -j 8 -C $B" > "$W/ninja-mddev.log" 2>&1
grep -q "error:" "$W/ninja-mddev.log" && { echo "ninja errors"; grep -E "error" "$W/ninja-mddev.log" | cut -c1-260 | head -30; exit 1; }
X="openxcom"".exe"
ls -la "$B/bin/$X" 2>&1 | cut -c1-120
tail -1 "$W/ninja-mddev.log" | cut -c1-160
