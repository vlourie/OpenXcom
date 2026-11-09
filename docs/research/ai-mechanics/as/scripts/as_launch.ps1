param([string]$Phase = 'iflog', [int]$Jobs = 24, [string]$List = '')
# a task of our own (oxce_asrun) in the user's session: pythonw without a console, the game on the hidden desktop
$R = 'C:\OXCE_AIWorker\asrun'
$a = "-u $R\asrun.py --jobs $Jobs --log logs\run_$Phase.txt --phase $Phase"
if ($List) { $a += " --list $List" }
$act = New-ScheduledTaskAction -Execute 'C:\OXCE_AIWorker\python\pythonw.exe' -Argument $a -WorkingDirectory $R
$pr = New-ScheduledTaskPrincipal -UserId user -LogonType Interactive -RunLevel Limited
$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12) -Priority 7
Register-ScheduledTask -TaskName oxce_asrun -Action $act -Principal $pr -Settings $st -Force | Out-Null
Start-ScheduledTask -TaskName oxce_asrun
Start-Sleep 3
$t = Get-ScheduledTask oxce_asrun
"task=$($t.State) args=$a"
