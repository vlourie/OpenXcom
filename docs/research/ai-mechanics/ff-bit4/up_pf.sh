#!/bin/sh
# upload the FF pilot runner and its launcher to c1run, compare sha256 both sides, check scen.tsv / env files are there
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/ff"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
cd "$S" || exit 1
scp -q -i "$K" run_pf.py launch_pf.ps1 "$H:C:/OXCE_AIWorker/c1run/" 2>/dev/null
echo "local:"
sha256sum run_pf.py launch_pf.ps1 env_FH.txt | cut -c1-16
echo "station:"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"foreach (\$f in 'run_pf.py','launch_pf.ps1','env_FH.txt') { (Get-FileHash (Join-Path C:/OXCE_AIWorker/c1run \$f)).Hash.Substring(0,16).ToLower() }; 'scen lines: ' + (Get-Content C:/OXCE_AIWorker/c1run/scen.tsv).Count; 'saves: ' + @(Get-ChildItem C:/OXCE_AIWorker/c1run/saves).Count; 'games running: ' + @(Get-Process -Name openxcom -ErrorAction SilentlyContinue).Count\"" 2>/dev/null
