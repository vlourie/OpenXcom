#!/bin/sh
# Movement diagnosis closure: BOM on the report, every count run once more into outputs.txt, scripts and tables into cm/hive_movement, sums.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive_movement"
F="$S/hive/mc"
mkdir -p "$D"
py -3.13 -I "$S/ff/bom.py" "$A/HIVE_MOVEMENT_COORDINATION_DIAGNOSIS.md" "$A/HIVE_MOVEMENT_COORDINATION_DIAGNOSIS.md"
OUT="$D/outputs.txt"
: > "$OUT"
for job in "ledger.py hh4_JA_M6_s2 hh6_JV_M3_s1" "classify.py hh4_JA_M6_s2 hh6_JV_M3_s1 hh3_JA_M6_s1" drops.py closers.py mapsame.py rest.py rest2.py shift.py legs.py loadcmp.py life.py saved.py final_checks.py check_hash.py; do
	echo "##### $job" >> "$OUT"
	py -3.13 -I "$F/${job%% *}" $(echo "$job" | cut -s -d' ' -f2-) >> "$OUT" 2>&1 || echo "FAILED $job" >> "$OUT"
done
echo "##### room.py hh4_JA_M6_s2 2948 18 50 0 22" >> "$OUT"
py -3.13 -I "$F/room.py" hh4_JA_M6_s2 2948 18 50 0 22 >> "$OUT" 2>&1 || echo "FAILED room" >> "$OUT"
grep -c "^FAILED" "$OUT" || true
for f in lib.py ledger.py classify.py closers.py gates.py room.py drops.py mapsame.py rest.py rest2.py shift.py legs.py loadcmp.py life.py saved.py final_checks.py check_hash.py rakes_mc.py close_mc.sh graph.py ledger_hh3_JA_M6_s1.tsv ledger_hh4_JA_M6_s2.tsv ledger_hh6_JV_M3_s1.tsv; do
	cp "$F/$f" "$D/"
done
cp "$A/HIVE_MOVEMENT_COORDINATION_DIAGNOSIS.md" "$D/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo sums ok )
du -sh "$D"
