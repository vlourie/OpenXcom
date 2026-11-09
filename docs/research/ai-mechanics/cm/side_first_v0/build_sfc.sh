#!/bin/sh
# SIDE-FIRST COMBAT: exe from the isolated tree sfc/tree; no editq ticket (R-158). Low priority, 12 jobs. The sources of the director are copied in from sfc/. sh build_sfc.sh
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
W="$S/sfc"
export PATH="/c/msys64/mingw64/bin:$PATH"
export EDITQ_BYPASS=1
B="$W/b-d"
for f in SideCombatDirector.h SideCombatDirector.cpp; do
	cmp -s "$W/$f" "$W/tree/src/Battlescape/$f" || cp "$W/$f" "$W/tree/src/Battlescape/$f"
done
if [ ! -f "$B/build.ninja" ]; then
	cmake -S "$W/tree" -B "$B" -G Ninja -DCMAKE_BUILD_TYPE=Release -DDEPS_DIR=E:/OpenXCom/deps -DOXCE_AI_DEV=ON -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/cc.exe -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/c++.exe > "$W/cmake-c.log" 2>&1
fi
grep -E "^OXCE_AI_DEV:" "$B/CMakeCache.txt"
cmd //c "start /low /b /wait ninja -j 12 -C $B" > "$W/ninja-d.log" 2>&1
grep -q "error:" "$W/ninja-d.log" && { echo "ninja errors"; grep -E "error" "$W/ninja-d.log" | cut -c1-300 | head -40; exit 1; }
X="openxcom"".exe"
ls -la "$B/bin/$X" 2>&1 | cut -c1-120
grep -E "warning" "$W/ninja-d.log" | grep -a "SideCombatDirector" | cut -c1-220 | head
tail -1 "$W/ninja-d.log" | cut -c1-160
