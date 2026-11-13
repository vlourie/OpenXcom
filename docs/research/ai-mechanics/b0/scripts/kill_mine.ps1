param([string]$Which = 'P')
# stop only this stage's own games (exe under b0run\exe\<Which>), by PID
Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like "C:\OXCE_AIWorker\b0run\exe\$Which\*" } | ForEach-Object {
	"kill $($_.ProcessId) $($_.ExecutablePath)"
	Stop-Process -Id $_.ProcessId -Force
}
