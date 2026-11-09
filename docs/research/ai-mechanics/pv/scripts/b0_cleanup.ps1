$ErrorActionPreference = 'Stop'
# stage 0B cleanup (Vitali 27.10: after the archive and the hashes are checked): our task oxce_b0run and the folder b0run only
$R = 'C:\OXCE_AIWorker\b0run'
$me = $PID
$procs = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*OXCE_AIWorker\b0run*' -and $_.ProcessId -ne $me -and $_.ParentProcessId -ne $me -and $_.CommandLine -notlike '*b0_cleanup.ps1*' })
if ($procs.Count -gt 0) { $procs | ForEach-Object { "BUSY $($_.ProcessId) $($_.CommandLine)" }; exit 1 }
$t = Get-ScheduledTask -TaskName oxce_b0run -ErrorAction SilentlyContinue
if ($t) {
	if ($t.State -eq 'Running') { 'BUSY task running'; exit 1 }
	if ($t.Actions.Arguments -notlike '*OXCE_AIWorker\b0run\b0run.py*') { "NOT OURS $($t.Actions.Arguments)"; exit 1 }
	Unregister-ScheduledTask -TaskName oxce_b0run -Confirm:$false
	'task oxce_b0run removed'
}
$n = (Get-ChildItem -Recurse -File $R | Measure-Object).Count
Remove-Item -Recurse -Force $R
"folder b0run removed: $n files; exists now: $(Test-Path $R)"
