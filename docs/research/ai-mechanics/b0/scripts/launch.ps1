param([string]$Phase = 'fx,run', [int]$Jobs = 12, [string]$Scen = '', [string]$Only = '', [string]$Tag = 'all')
# a task of our own (oxce_b0run) in the user's session, like oxce_c1run: pythonw without a console, the game on the hidden desktop
$R = 'C:\OXCE_AIWorker\b0run'
$a = "-u $R\b0run.py --jobs $Jobs --log logs\run_$Tag.txt --phase $Phase"
if ($Scen) { $a += " --scen $Scen" }
if ($Only) { $a += " --only $Only" }
$act = New-ScheduledTaskAction -Execute 'C:\OXCE_AIWorker\python\pythonw.exe' -Argument $a -WorkingDirectory $R
$pr = New-ScheduledTaskPrincipal -UserId user -LogonType Interactive -RunLevel Limited
$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12) -Priority 7
Register-ScheduledTask -TaskName oxce_b0run -Action $act -Principal $pr -Settings $st -Force | Out-Null
Start-ScheduledTask -TaskName oxce_b0run
Start-Sleep 3
$t = Get-ScheduledTask oxce_b0run
"task=$($t.State) args=$a"
