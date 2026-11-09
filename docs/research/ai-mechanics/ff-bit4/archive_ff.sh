#!/bin/sh
# FF bit 4 / FH: scripts, diff and summaries to docs/research/ai-mechanics/ff-bit4; raw results, exe and source to the archive
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
DOC="E:/OpenXCom/docs/research/ai-mechanics/ff-bit4"
A="E:/OXCE_AIWorker/battles_archive/ff_bit4_2026-10-27"
EXE="openxcom"".exe"
mkdir -p "$DOC" "$A/exe" "$A/src"
cd "$S/ff" || exit 1
cp ff_battles.tsv pf_battles.tsv run_ff.py run_pf.py env_FH.txt launch_ff.ps1 launch_pf.ps1 ff_cmp.py ff_side0.py pf_ident.py ff_cas.py \
	up_ff.sh up_fh.sh up_pf.sh get_ff.sh get_pf.sh wait_ff.sh stage_fh.sh archive_ff.sh fh.diff \
	ff_cmp.txt fh_cmp.txt pf_cmp.txt pf_ident.txt exe/FH/BUILD_INFO.txt "$DOC/"
cp res/ffres.zip pres/pfres.zip fh.diff "$A/"
cp "exe/FH/$EXE" exe/FH/BUILD_INFO.txt "$A/exe/"
cp "$S/c2/tree/src/Battlescape/AIModule.cpp" "$A/src/"
echo "4ee3d1d3724465fff02dfa45aed8b8eecc6b4b31" > "$A/BASE_COMMIT.txt"
cd "$A" && sha256sum ffres.zip pfres.zip fh.diff BASE_COMMIT.txt "exe/$EXE" exe/BUILD_INFO.txt src/AIModule.cpp > SHA256SUMS.txt && sha256sum -c SHA256SUMS.txt
unzip -l ffres.zip | tail -1; unzip -l pfres.zip | tail -1
cd "$DOC" && sha256sum * > SHA256SUMS.txt && ls | wc -l
