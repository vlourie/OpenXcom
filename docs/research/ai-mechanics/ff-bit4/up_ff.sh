#!/bin/sh
# upload the FF runner to the station's c1run, compare sha256 both sides, show what else runs there
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/ff"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
cd "$S" || exit 1
scp -q -i "$K" run_ff.py ff_battles.tsv launch_ff.ps1 "$H:C:/OXCE_AIWorker/c1run/" 2>/dev/null
echo "local:"
sha256sum run_ff.py ff_battles.tsv launch_ff.ps1 | cut -c1-16
echo "station:"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"foreach (\$f in 'run_ff.py','ff_battles.tsv','launch_ff.ps1') { (Get-FileHash (Join-Path C:/OXCE_AIWorker/c1run \$f)).Hash.Substring(0,16).ToLower() }; 'games running: ' + @(Get-Process -Name openxcom -ErrorAction SilentlyContinue).Count; 'cpu: ' + (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average\"" 2>/dev/null
