#!/bin/sh
# AI FORGE WP1: the isolated tree against commit 07680cadb + al + al3: the only differences must be the monitor's own files and hooks. The commit is read from git, the diffs applied in a temporary copy by patch. Git only read.
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
F="$S/forge"
B="$F/base_check_$$"
mkdir -p "$B"
git -C E:/OpenXCom archive 07680cadb src CMakeLists.txt | tar -x -C "$B"
patch -s -p2 --binary -d "$B" < "$S/ce/al.crlf.diff" && echo al ok
patch -s --binary "$B/src/Battlescape/AiProbe.cpp" < "$S/ce/al3.crlf.diff" && echo al3 ok
diff -rq --strip-trailing-cr "$B/src" "$F/tree/src" | sed "s#$F/##g; s#$B/##g"
diff -q --strip-trailing-cr "$B/CMakeLists.txt" "$F/tree/CMakeLists.txt" | sed "s#$F/##g; s#$B/##g"
diff -r --strip-trailing-cr "$B/src" "$F/tree/src" | grep -c '^[<>]'
echo diff done
