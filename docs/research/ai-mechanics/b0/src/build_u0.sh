#!/bin/sh
# U0: upstream OXCE v8.7.1 (441cae1b0) + the stage 0B driver, the same compiler and deps as the fork; no editq ticket (R-158)
W="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/u0"
export PATH="/c/msys64/mingw64/bin:$PATH"
export EDITQ_BYPASS=1
B="$W/b-u0"
if [ ! -f "$B/build.ninja" ]; then
	cmake -S "$W/up" -B "$B" -G Ninja -DCMAKE_BUILD_TYPE=Release -DDEPS_DIR=E:/OpenXCom/deps -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/cc.exe -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/c++.exe > "$W/cmake-u0.log" 2>&1 || { echo "cmake FAILED"; tail -30 "$W/cmake-u0.log"; exit 1; }
fi
ninja -C "$B" > "$W/ninja-u0.log" 2>&1 || { echo "ninja FAILED"; grep -E "error" "$W/ninja-u0.log" | head -40; exit 1; }
echo "built u0 warnings: $(grep -c "warning:" "$W/ninja-u0.log")"
ls -la "$B"/bin/*.exe "$B"/*.exe 2>/dev/null
