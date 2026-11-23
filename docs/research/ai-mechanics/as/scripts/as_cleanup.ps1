param([string]$Zip = '')
$ErrorActionPreference = 'Stop'
# AI-IF (GO Vitali 27.10): remove our own folder C:\OXCE_AIWorker\asrun and the task oxce_asrun - only when the result zip
# on the station matches the archived hash and nothing of ours runs. Nothing else on the station is touched.
$R = 'C:\OXCE_AIWorker\asrun'
$h = (Get-FileHash -Algorithm SHA256 "$R\as_all.zip").Hash.ToLower()
"as_all.zip $h expected $Zip"
if ($h -ne $Zip) { 'HASH MISMATCH - nothing removed'; exit 1 }
$t = Get-ScheduledTask -TaskName oxce_asrun -ErrorAction SilentlyContinue
if ($t -and $t.State -eq 'Running') { 'task oxce_asrun is running - nothing removed'; exit 1 }
$me = $PID
$p = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like "*OXCE_AIWorker\asrun*" -and $_.ProcessId -ne $me -and $_.CommandLine -notlike '*as_cleanup.ps1*' })
$g = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -like "$R\*" })
if ($p.Count -gt 0 -or $g.Count -gt 0) { "processes of ours: $($p.Count + $g.Count) - nothing removed"; $p + $g | ForEach-Object { "  $($_.ProcessId) $($_.Name) $($_.CommandLine)" }; exit 1 }
if ($t) { Unregister-ScheduledTask -TaskName oxce_asrun -Confirm:$false; 'task oxce_asrun removed' }
Remove-Item -Recurse -Force $R
"asrun removed: $(-not (Test-Path $R))"
"task present: $([bool](Get-ScheduledTask -TaskName oxce_asrun -ErrorAction SilentlyContinue))"
