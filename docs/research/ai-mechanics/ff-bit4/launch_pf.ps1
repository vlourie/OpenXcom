param([int]$Jobs = 24)
# FF pilot: the 24 protocol v1 scenarios, arms PE / PF (run_pf.py, labels pf_*); a task of our own (oxce_pfrun), interactive,
# pythonw without a console; ai_probe gives the game BELOW_NORMAL and the SDL dummy drivers
$R = 'C:\OXCE_AIWorker\c1run'
$a = "-u $R\run_pf.py --jobs $Jobs --log $R\logs\run_pf.txt --prefix pf --only PE,PF"
$act = New-ScheduledTaskAction -Execute 'C:\OXCE_AIWorker\python\pythonw.exe' -Argument $a -WorkingDirectory $R
$pr = New-ScheduledTaskPrincipal -UserId user -LogonType Interactive -RunLevel Limited
$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 24) -Priority 7
Register-ScheduledTask -TaskName oxce_pfrun -Action $act -Principal $pr -Settings $st -Force | Out-Null
Start-ScheduledTask -TaskName oxce_pfrun
Start-Sleep 3
$t = Get-ScheduledTask oxce_pfrun
"task=$($t.State) args=$a"
