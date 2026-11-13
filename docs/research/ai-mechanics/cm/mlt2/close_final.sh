#!/bin/sh
# MISSION-LEVEL TACTICS closure by Vitali's decision: BOM on the closing record, the final report and the record into cm/mlt2, its sums again. No build, no battle, no test.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/mlt2"
py -3.13 -I "$S/ff/bom.py" "$A/MISSION_LEVEL_TACTICS_CLOSED.md" "$A/MISSION_LEVEL_TACTICS_CLOSED.md"
for f in "$A/MISSION_LEVEL_TACTICS_CLOSED.md" "$A/MISSION_LEVEL_TACTICS_STAGE2_RESULT.md"; do head -c 3 "$f" | od -An -tx1; cp "$f" "$D/"; done
cp "$S/md2/close_final.sh" "$D/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo mlt2 sums ok )
git -C E:/OpenXCom status --short -- src bin | wc -l
