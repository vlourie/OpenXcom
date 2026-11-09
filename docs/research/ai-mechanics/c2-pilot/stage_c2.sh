#!/bin/sh
# stage the C2 exe (exe/C2) with BUILD_INFO and its env file; the diff against the clean HEAD
W="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
S="$W/c1/station"
EXE="openxcom"".exe"
cd "$W" || exit 1
diff -rq c1/base/src c2/tree/src
diff -ru c1/base/src c2/tree/src > c2/c2.diff
wc -l c2/c2.diff
grep -c "OXCE_AI_PREATTACK_COVER" "c2/b-c2dev/bin/$EXE" "c2/b-c2rel/bin/$EXE"
grep -c "OXCE_AI_COVER_STEP" "c2/b-c2dev/bin/$EXE"
mkdir -p "$S/exe/C2"
cp "c2/b-c2dev/bin/$EXE" "$S/exe/C2/$EXE"
h=$(sha256sum "$S/exe/C2/$EXE" | cut -d' ' -f1)
printf 'build_label=c1run-C2\ngit_commit=4ee3d1d3724465fff02dfa45aed8b8eecc6b4b31\nnote=DEV (OXCE_AI_DEV=ON, DEV_BUILD=ON, Release) HEAD + C2 PREATTACK_COVER (flag OXCE_AI_PREATTACK_COVER, default off), without C1\nexe_sha256=%s\n' "$h" > "$S/exe/C2/BUILD_INFO.txt"
echo "C2 $h"
sed "s#exe/C1/#exe/C2/#" "$S/env_C1.txt" > "$S/env_C2.txt"
cat "$S/env_C2.txt"
