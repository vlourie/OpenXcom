param([string]$Phase = 'check', [int]$Jobs = 24)
# a task of our own (oxce_pvrun) in the user's session, like oxce_b0run: pythonw without a console, the game on the hidden desktop
$R = 'C:\OXCE_AIWorker\pvrun'
$a = "-u $R\pvrun.py --jobs $Jobs --log logs\run_$Phase.txt --phase $Phase"
$act = New-ScheduledTaskAction -Execute 'C:\OXCE_AIWorker\python\pythonw.exe' -Argument $a -WorkingDirectory $R
$pr = New-ScheduledTaskPrincipal -UserId user -LogonType Interactive -RunLevel Limited
$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12) -Priority 7
Register-ScheduledTask -TaskName oxce_pvrun -Action $act -Principal $pr -Settings $st -Force | Out-Null
Start-ScheduledTask -TaskName oxce_pvrun
Start-Sleep 3
$t = Get-ScheduledTask oxce_pvrun
"task=$($t.State) args=$a"
