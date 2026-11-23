#!/bin/sh
# FIRST CONTACT SURVIVAL V0 closure: BOM on the report, code and tables into cm/fcs, raw logs, build and tree into battles_archive, sums on both. No battle, no build.
set -e
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
A="E:/OpenXCom/docs/research/ai-mechanics"
D="$A/cm/fcs"
B="E:/OXCE_AIWorker/battles_archive/first_contact_survival_v0_2026-11-05"
F="$S/fcs"
mkdir -p "$D/analysis" "$B/exe_FC"
py -3.13 -I "$S/ff/bom.py" "$A/FIRST_CONTACT_SURVIVAL_V0_RESULT.md" "$A/FIRST_CONTACT_SURVIVAL_V0_RESULT.md"
head -c 3 "$A/FIRST_CONTACT_SURVIVAL_V0_RESULT.md" | od -An -tx1
for f in fcs.diff patch_probe.py patch_probe2.py patch_active.py build_fcs.sh up_fcs.sh run_y.sh run_shadow.sh run_shadow2.sh run_active.sh close_fcs.sh ninja-fc.log cmake-fc.log; do
	cp "$F/$f" "$D/"
done
cp "$S/cm/st/run_cm.py" "$S/cm/st/env_FC.txt" "$S/cm/st/exe/FC/BUILD_INFO.txt" "$D/"
for f in chrono.py expo.py cat.py deploy.py never.py final.py same.py los.py los2.py evalfc.py fate.py seen6.sh run_m.sh run_c.sh run_d.sh; do
	cp "$F/$f" "$D/analysis/"
done
for f in losses.tsv cat.tsv l4.tsv l4x.tsv M1.tsv M1x.tsv M10.tsv M10x.tsv los.tsv los2.tsv acts.tsv shadow.txt shadow2.txt active.txt; do
	cp "$F/out/$f" "$D/analysis/"
done
cp "$A/FIRST_CONTACT_SURVIVAL_V0_RESULT.md" "$D/"
( cd "$D" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo fcs sums ok )
cp "$F"/res/res_fy*.zip "$F"/res/run_fy*.txt "$B/"
cp "$S"/cm/st/exe/FC/* "$B/exe_FC/"
tar --force-local -czf "$B/tree_fcs.tar.gz" -C "$F" tree
( cd "$B" && find . -type f ! -name SHA256SUMS.txt | sort | xargs sha256sum > SHA256SUMS.txt && wc -l SHA256SUMS.txt && sha256sum -c --quiet SHA256SUMS.txt && echo raw sums ok )
du -sh "$D" "$B"
git -C E:/OpenXCom status --short -- src bin | wc -l
