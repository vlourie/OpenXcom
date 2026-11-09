param([int]$Jobs = 24, [string]$Tag = 'ff', [string]$Only = 'E0,E,F')
# the game's hidden desktop lives in the user's session: a task of our own (oxce_ffrun), interactive like oxce_c1run,
# pythonw without a console; ai_probe gives the game BELOW_NORMAL and the SDL dummy drivers
$R = 'C:\OXCE_AIWorker\c1run'
$a = "-u $R\run_ff.py --jobs $Jobs --log $R\logs\run_$Tag.txt --only $Only"
$act = New-ScheduledTaskAction -Execute 'C:\OXCE_AIWorker\python\pythonw.exe' -Argument $a -WorkingDirectory $R
$pr = New-ScheduledTaskPrincipal -UserId user -LogonType Interactive -RunLevel Limited
$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 24) -Priority 7
Register-ScheduledTask -TaskName oxce_ffrun -Action $act -Principal $pr -Settings $st -Force | Out-Null
Start-ScheduledTask -TaskName oxce_ffrun
Start-Sleep 3
$t = Get-ScheduledTask oxce_ffrun
"task=$($t.State) args=$a"
