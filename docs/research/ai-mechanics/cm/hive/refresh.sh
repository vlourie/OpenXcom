#!/bin/sh
# HIVE COMMAND CORE V0: last copies into cm/hive after the closure script's own fixes, the sums again, and the record of the rakes and the state of the main tree.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive"
F="$S/hive"
py -3.13 -I "$S/ff/bom.py" "$A/HIVE_COMMAND_CORE_V0_RESULT.md" "$A/HIVE_COMMAND_CORE_V0_RESULT.md"
cp "$A/HIVE_COMMAND_CORE_V0_RESULT.md" "$F/hive.diff" "$F/close_hive.sh" "$F/rakes.py" "$F/refresh.sh" "$D/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo hive sums ok )
grep -a -o "R-64[0-9]" E:/OpenXCom/docs/rakes/aibench.md | sort -u | tr "\n" " "
echo
grep -a -c "Анализ считал живых по последней записи" E:/OpenXCom/docs/rakes/aibench.md
grep -a -n "Анализ считал живых" E:/OpenXCom/docs/rakes/aibench.md | cut -c1-90
wc -l "$D/hive.diff"
grep -c "HiveCommand" "$D/hive.diff"
git -C E:/OpenXCom log -1 --format=%h
git -C E:/OpenXCom status --short -- src | grep -i hive | wc -l
