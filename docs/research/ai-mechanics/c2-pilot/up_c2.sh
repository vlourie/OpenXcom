#!/bin/sh
# upload the C2 exe and the runner to the station's c1run, then compare sha256 both sides
S="C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/c1/station"
K="$HOME/.ssh/oxce_worker"
H="user@100.83.70.95"
EXE="openxcom"".exe"
cd "$S" || exit 1
ssh -i "$K" "$H" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force C:\\OXCE_AIWorker\\c1run\\exe\\C2 | Out-Null\"" 2>/dev/null
scp -q -i "$K" "exe/C2/$EXE" exe/C2/BUILD_INFO.txt "$H:C:/OXCE_AIWorker/c1run/exe/C2/" 2>/dev/null
scp -q -i "$K" run_c1.py launch.ps1 env_C2.txt "$H:C:/OXCE_AIWorker/c1run/" 2>/dev/null
echo "local:"
sha256sum "exe/C2/$EXE" exe/C2/BUILD_INFO.txt run_c1.py launch.ps1 env_C2.txt exe/E/$EXE | cut -c1-16
echo "station:"
ssh -i "$K" "$H" "powershell -NoProfile -Command \"\$R='C:\\OXCE_AIWorker\\c1run'; foreach (\$f in 'exe\\C2\\$EXE','exe\\C2\\BUILD_INFO.txt','run_c1.py','launch.ps1','env_C2.txt','exe\\E\\$EXE') { (Get-FileHash (Join-Path \$R \$f)).Hash.Substring(0,16).ToLower() }; Get-ScheduledTask oxce_c1run -ErrorAction SilentlyContinue | Select -Expand State\"" 2>/dev/null
