$ErrorActionPreference = 'Stop'
# P0/P1 cleanup (Vitali 27.10, after the archive and the hashes are checked): our task oxce_pvrun and the folder pvrun only
$R = 'C:\OXCE_AIWorker\pvrun'
$me = $PID
$procs = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*OXCE_AIWorker\pvrun*' -and $_.ProcessId -ne $me -and $_.ParentProcessId -ne $me -and $_.CommandLine -notlike '*pv_cleanup.ps1*' })
if ($procs.Count -gt 0) { $procs | ForEach-Object { "BUSY $($_.ProcessId) $($_.CommandLine)" }; exit 1 }
$h = (Get-FileHash -Algorithm SHA256 "$R\pv_all.zip").Hash.ToLower()
if ($h -ne 'e92d80dda084604b0cd72dba027ac36b93fd5d93308e48778829cc3b082bf05c') { "ZIP $h differs from the archived copy"; exit 1 }
$t = Get-ScheduledTask -TaskName oxce_pvrun -ErrorAction SilentlyContinue
if ($t) {
	if ($t.State -eq 'Running') { 'BUSY task running'; exit 1 }
	if ($t.Actions.Arguments -notlike '*OXCE_AIWorker\pvrun\pvrun.py*') { "NOT OURS $($t.Actions.Arguments)"; exit 1 }
	Unregister-ScheduledTask -TaskName oxce_pvrun -Confirm:$false
	'task oxce_pvrun removed'
}
$n = (Get-ChildItem -Recurse -File $R | Measure-Object).Count
Remove-Item -Recurse -Force $R
"folder pvrun removed: $n files; exists now: $(Test-Path $R)"
