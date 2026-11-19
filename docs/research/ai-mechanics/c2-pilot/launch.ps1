param([string]$Scen = '', [int]$Jobs = 24, [string]$Tag = 'all', [string]$Only = 'E,A,B', [string]$Prefix = 'c1', [string]$C1Env = 'env_C1.txt', [string]$BFlag = 'OXCE_AI_COVER_STEP=1')
# the game's hidden desktop lives in the user's session: a task of our own (oxce_c1run), interactive like oxce_ai4,
# pythonw without a console; ai_probe gives the game BELOW_NORMAL and the SDL dummy drivers
$R = 'C:\OXCE_AIWorker\c1run'
$a = "-u $R\run_c1.py --jobs $Jobs --log $R\logs\run_$Tag.txt --only $Only --prefix $Prefix --c1env $C1Env --bflag $BFlag"
if ($Scen) { $a += " --scen $Scen" }
$act = New-ScheduledTaskAction -Execute 'C:\OXCE_AIWorker\python\pythonw.exe' -Argument $a -WorkingDirectory $R
$pr = New-ScheduledTaskPrincipal -UserId user -LogonType Interactive -RunLevel Limited
$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 24) -Priority 7
Register-ScheduledTask -TaskName oxce_c1run -Action $act -Principal $pr -Settings $st -Force | Out-Null
Start-ScheduledTask -TaskName oxce_c1run
Start-Sleep 3
$t = Get-ScheduledTask oxce_c1run
"task=$($t.State) args=$a"
