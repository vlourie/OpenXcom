#!/bin/sh
# FH: stage the exe (base + bit 16) with BUILD_INFO and the diff, upload it and the runner to c1run, compare sha256 both sides
W="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad"
S="$W/ff"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
EXE="openxcom"".exe"
cd "$W" || exit 1
diff -ru c1/base/src c2/tree/src > ff/fh.diff
wc -l ff/fh.diff
mkdir -p "$S/exe/FH"
cp "c2/b-c2dev/bin/$EXE" "$S/exe/FH/$EXE"
h=$(sha256sum "$S/exe/FH/$EXE" | cut -d' ' -f1)
printf 'build_label=c1run-FH\ngit_commit=4ee3d1d3724465fff02dfa45aed8b8eecc6b4b31\nnote=DEV (OXCE_AI_DEV=ON, Release) HEAD + OXCE_AI_FF_RISK bit 16 in ffLineRisk (hostile side only), fh.diff\nexe_sha256=%s\n' "$h" > "$S/exe/FH/BUILD_INFO.txt"
cd "$S" || exit 1
tr -d '\r' < env_FH.txt > env_FH.tmp && mv env_FH.tmp env_FH.txt
ssh -i "$K" "$H" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force C:\\OXCE_AIWorker\\c1run\\exe\\FH | Out-Null\"" 2>/dev/null
scp -q -i "$K" "exe/FH/$EXE" exe/FH/BUILD_INFO.txt "$H:C:/OXCE_AIWorker/c1run/exe/FH/" 2>/dev/null
scp -q -i "$K" run_ff.py env_FH.txt "$H:C:/OXCE_AIWorker/c1run/" 2>/dev/null
echo "local:"
sha256sum "exe/FH/$EXE" exe/FH/BUILD_INFO.txt run_ff.py env_FH.txt | cut -c1-16
echo "station:"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"\$R='C:\\OXCE_AIWorker\\c1run'; foreach (\$f in 'exe\\FH\\$EXE','exe\\FH\\BUILD_INFO.txt','run_ff.py','env_FH.txt') { (Get-FileHash (Join-Path \$R \$f)).Hash.Substring(0,16).ToLower() }; 'games running: ' + @(Get-Process -Name openxcom -ErrorAction SilentlyContinue).Count\"" 2>/dev/null
