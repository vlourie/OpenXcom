#!/bin/sh
# DECISION ENGINE FOUNDATION closure: BOM on the document, scripts and tables into cm/hive_de, sums. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/hive_de"
F="$S/hive/de"
mkdir -p "$D"
py -3.13 -I "$S/ff/bom.py" "$A/HIVE_DECISION_ENGINE_FOUNDATION.md" "$A/HIVE_DECISION_ENGINE_FOUNDATION.md"
cp "$A/HIVE_DECISION_ENGINE_FOUNDATION.md" "$D/"
for f in de_tags.py de_scan.py de_all.py de_group.py de_peek.py de_dbg.py de_alt.py de_plug.py de_lane.py de_swap.py de_ep.py de_check.py rakes_de.py close_de.sh all.txt alt.txt plug.txt lane.txt swap.txt ep_l5_5.txt ep_m10_8.txt ep_m10_8b.txt; do
	cp "$F/$f" "$D/"
done
cp "$S/hive/mc/lib.py" "$D/"
py -3.13 -I "$D/check_moves_tu.py" "$D"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo sums ok )
du -sh "$D"
echo "main tree files that mention the headquarters:"
grep -rl "HiveCommand" E:/OpenXCom/src E:/OpenXCom/bin/common 2>/dev/null | wc -l
