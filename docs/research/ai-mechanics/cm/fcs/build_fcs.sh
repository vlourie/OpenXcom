#!/bin/sh
# FIRST CONTACT SURVIVAL: exe FC from the isolated tree fcs/tree (a copy of the D0 tree; a patch on it); no editq ticket (R-158).
# Low priority and 8 jobs: this machine stays usable. sh build_fcs.sh [patch script, on a fresh tree only]
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
W="$S/fcs"
export PATH="/c/msys64/mingw64/bin:$PATH"
export EDITQ_BYPASS=1
if [ ! -d "$W/tree/src" ]; then
	cp -r "$S/ce/tree_d0" "$W/tree" || exit 1
	PYTHONIOENCODING=utf-8 py -3.13 -I "$W/patch_probe.py" "$S" || exit 1
fi
B="$W/b-fc"
if [ ! -f "$B/build.ninja" ]; then
	cmake -S "$W/tree" -B "$B" -G Ninja -DCMAKE_BUILD_TYPE=Release -DDEPS_DIR=E:/OpenXCom/deps -DOXCE_AI_DEV=ON -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/cc.exe -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/c++.exe > "$W/cmake-fc.log" 2>&1 || { tail -5 "$W/cmake-fc.log"; exit 1; }
fi
grep -E "^OXCE_AI_DEV:" "$B/CMakeCache.txt"
cmd //c "start /low /b /wait ninja -j 8 -C $B" > "$W/ninja-fc.log" 2>&1
grep -q "error:" "$W/ninja-fc.log" && { echo "ninja errors"; grep -E "error" "$W/ninja-fc.log" | cut -c1-260 | head -30; exit 1; }
X="openxcom"".exe"
ls -la "$B/bin/$X" 2>&1 | cut -c1-120
tail -1 "$W/ninja-fc.log" | cut -c1-160
