#!/bin/sh
# FIRST CONTACT SURVIVAL V0, closing by Vitali's decision: BOM on the three reports, copies into cm/fcs, sums rewritten there; the raw archive only checked. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/fcs"
B="E:/OXCE_AIWorker/battles_archive/first_contact_survival_v0_2026-11-05"
for f in FIRST_CONTACT_SURVIVAL_V0_RESULT.md FIRST_CONTACT_SURVIVAL_V0_CLOSED.md KNOWN-ISSUE-R635-EMPTY-CELL-LOS-2026-11-05.md; do
	if [ "$(head -c 3 "$A/$f" | od -An -tx1 | tr -d ' ')" != "efbbbf" ]; then
		py -3.13 -I "$S/ff/bom.py" "$A/$f" "$A/$f"
	fi
	head -c 3 "$A/$f" | od -An -tx1
	cp "$A/$f" "$D/"
done
cp "$S/fcs/close2_fcs.sh" "$D/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo fcs sums ok )
( cd "$B" && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
grep -c "fcsEscape" "$D/fcs.diff"
head -c 3 E:/OpenXCom/docs/rakes/aibench.md | od -An -tx1
git -C E:/OpenXCom status --short -- src bin | wc -l
