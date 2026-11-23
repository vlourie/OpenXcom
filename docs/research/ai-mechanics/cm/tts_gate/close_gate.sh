#!/bin/sh
# NATURAL GATE closure: BOM, the check, scripts and outputs into cm/tts_gate, the scan into battles_archive, sums on both. No commit.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
G="$S/tts/gate"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/tts_gate"
B="E:/OXCE_AIWorker/battles_archive/tts_gate_2026-11-06"
Z="E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip"
mkdir -p "$D/ep" "$B"
py -3.13 -I "$S/ff/bom.py" "$A/TACTICAL_TURN_SOLVER_NATURAL_GATE.md" "$A/TACTICAL_TURN_SOLVER_V0_PLAN.md"
py -3.13 -I "$G/check_gate.py" "$G" "$Z" "$A/TACTICAL_TURN_SOLVER_NATURAL_GATE.md"
cp "$A/TACTICAL_TURN_SOLVER_NATURAL_GATE.md" "$D/"
for f in gate_lib.py scan.py judge.py proved.py flips.py m10_28.py m10_gate.py use.py ranges.py value2.py final.py leads.py ep.py ep2.py check_gate.py rakes_gate.py close_gate.sh; do
	cp "$G/$f" "$D/"
done
for f in judge.txt proved.txt flips.txt m10_28.txt m10_gate.txt use.txt value2.txt final.txt leads.txt scan_all.txt; do
	cp "$G/$f" "$D/"
done
cp "$G"/ep/*.txt "$D/ep/"
gzip -c "$G/all/cands.jsonl" > "$B/cands.jsonl.gz"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo sums ok )
( cd "$B" && sha256sum cands.jsonl.gz > SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo archive sums ok )
du -sh "$D" "$B"
echo "main tree changes in src, bin, CMakeLists:"
git -C E:/OpenXCom status --short src bin CMakeLists.txt | wc -l
git -C E:/OpenXCom log -1 --format=%h
