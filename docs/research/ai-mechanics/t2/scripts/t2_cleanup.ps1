param([string]$T1Zip = '', [string]$T2Zip = '')
$ErrorActionPreference = 'Stop'
# AI-T2 (GO Vitali 27.10): remove our own folder C:\OXCE_AIWorker\tsrun and the task oxce_tsrun - only when both result zips
# on the station match the archived hashes and nothing of ours runs. Nothing else on the station is touched.
$R = 'C:\OXCE_AIWorker\tsrun'
$h1 = (Get-FileHash -Algorithm SHA256 "$R\ts_all.zip").Hash.ToLower()
$h2 = (Get-FileHash -Algorithm SHA256 "$R\t2_all.zip").Hash.ToLower()
"ts_all.zip $h1 expected $T1Zip"
"t2_all.zip $h2 expected $T2Zip"
if ($h1 -ne $T1Zip -or $h2 -ne $T2Zip) { 'HASH MISMATCH - nothing removed'; exit 1 }
$t = Get-ScheduledTask -TaskName oxce_tsrun -ErrorAction SilentlyContinue
if ($t -and $t.State -eq 'Running') { 'task oxce_tsrun is running - nothing removed'; exit 1 }
$me = $PID
$p = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like "*OXCE_AIWorker\tsrun*" -and $_.ProcessId -ne $me -and $_.CommandLine -notlike '*t2_cleanup.ps1*' })
$g = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -like "$R\*" })
if ($p.Count -gt 0 -or $g.Count -gt 0) { "processes of ours: $($p.Count + $g.Count) - nothing removed"; $p + $g | ForEach-Object { "  $($_.ProcessId) $($_.Name)" }; exit 1 }
if ($t) { Unregister-ScheduledTask -TaskName oxce_tsrun -Confirm:$false; 'task oxce_tsrun removed' }
Remove-Item -Recurse -Force $R
"tsrun removed: $(-not (Test-Path $R))"
"task present: $([bool](Get-ScheduledTask -TaskName oxce_tsrun -ErrorAction SilentlyContinue))"
