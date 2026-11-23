#!/bin/sh
# AI FORGE WP4: the isolated build: the same flags as the FX, F3, D0 stand builds, DEV, Release, low priority, outside the edit queue (R-158). sh build_f4.sh
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
F="$S/forge4"
export PATH="/c/msys64/mingw64/bin:$PATH"
export EDITQ_BYPASS=1
c++ -std=c++17 -I"$F" "$F/test_legal.cpp" -o "$F/test_legal.bin" && "$F/test_legal.bin" | tail -1
cmake -S "$F/tree" -B "$F/b-x" -G Ninja -DCMAKE_BUILD_TYPE=Release -DDEPS_DIR=E:/OpenXCom/deps -DOXCE_AI_DEV=ON -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/cc.exe -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/c++.exe > "$F/cmake.log" 2>&1
tail -2 "$F/cmake.log" | cut -c1-160
cmd //c "start /low /b /wait ninja -j 12 -C $F/b-x" > "$F/ninja.log" 2>&1
echo "ninja exit $?"
grep -n -E "error|Error |FAILED" "$F/ninja.log" | head -30 | cut -c1-240
tail -2 "$F/ninja.log" | cut -c1-160
