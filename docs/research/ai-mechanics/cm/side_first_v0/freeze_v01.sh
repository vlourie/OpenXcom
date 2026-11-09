#!/bin/sh
# SIDE-FIRST COMBAT V0.1: exe to rabota, the frozen copy, hashes and the diff against V0.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
W="$S/sfc"
X="openxcom"".exe"
sh "$W/up_sfc.sh" 2>&1 | tail -6 | cut -c1-130
mkdir -p "$W/frozen_v01"
cp "$S/cm/st/exe/SD/$X" "$S/cm/st/exe/SD/BUILD_INFO.txt" "$W/SideCombatDirector.cpp" "$W/SideCombatDirector.h" "$W/tree/src/Battlescape/BattlescapeGame.cpp" "$W/frozen_v01/"
( cd "$W/frozen_v01" && sha256sum "$X" SideCombatDirector.cpp SideCombatDirector.h BattlescapeGame.cpp ) | tee "$W/freeze_v01.txt"
{
	diff -u --strip-trailing-cr --label V0/SideCombatDirector.cpp --label V01/SideCombatDirector.cpp "$W/frozen/SideCombatDirector.cpp" "$W/SideCombatDirector.cpp" || true
	diff -u --strip-trailing-cr --label V0/SideCombatDirector.h --label V01/SideCombatDirector.h "$W/frozen/SideCombatDirector.h" "$W/SideCombatDirector.h" || true
} > "$W/side_first_v01.diff"
wc -l "$W/side_first_v01.diff"
grep -c "SideCombatDirector::roundsAfterSwitch" "$W/tree/src/Battlescape/BattlescapeGame.cpp"
grep -n "XN\|XO\|XS" "$W/patch_run.py" | cut -c1-140 | head -8
