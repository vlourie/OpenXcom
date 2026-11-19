#!/bin/sh
# FH tree: the C2 tree (archived) back to the base exe E was built from (c1/base, 4ee3d1d37), then src compared whole
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
for f in AIModule.cpp AIModule.h AiProbe.cpp AiProbe.h BattlescapeGame.cpp ProjectileFlyBState.cpp; do
	cp -p "$S/c1/base/src/Battlescape/$f" "$S/c2/tree/src/Battlescape/$f"
done
diff -rq "$S/c1/base/src" "$S/c2/tree/src" && echo "tree == base"
diff -rq "$S/c1/base/CMakeLists.txt" "$S/c2/tree/CMakeLists.txt" && echo "cmake == base"
