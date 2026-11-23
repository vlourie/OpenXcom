#!/bin/sh
# Commander stage: cmdev / cmrel from the isolated tree cm/tree (git archive of HEAD), each in a folder of its own; no editq
# ticket (R-158). Low priority and 8 jobs: this machine stays usable.
W="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/cm"
export PATH="/c/msys64/mingw64/bin:$PATH"
export EDITQ_BYPASS=1
for cfg in ${@:-cmdev}; do
	B="$W/b-$cfg"
	case $cfg in
		cmdev) DEV=ON ;;
		cmrel) DEV=OFF ;;
	esac
	if [ ! -f "$B/build.ninja" ]; then
		cmake -S "$W/tree" -B "$B" -G Ninja -DCMAKE_BUILD_TYPE=Release -DDEPS_DIR=E:/OpenXCom/deps -DOXCE_AI_DEV=$DEV -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/cc.exe -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/c++.exe > "$W/cmake-$cfg.log" 2>&1 || { echo "cmake $cfg FAILED"; tail -20 "$W/cmake-$cfg.log"; exit 1; }
	fi
	grep -E "^OXCE_AI_DEV:" "$B/CMakeCache.txt"
	cmd //c "start /low /b /wait ninja -j 8 -C $B" > "$W/ninja-$cfg.log" 2>&1 || { echo "ninja $cfg FAILED"; grep -E "error" "$W/ninja-$cfg.log" | head -40; exit 1; }
	grep -q "error:" "$W/ninja-$cfg.log" && { echo "ninja $cfg errors"; grep -E "error" "$W/ninja-$cfg.log" | head -40; exit 1; }
	echo "built $cfg warnings: $(grep -c "warning:" "$W/ninja-$cfg.log")"
done
