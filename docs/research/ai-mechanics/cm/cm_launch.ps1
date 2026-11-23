param([string]$Scen = '', [int]$Jobs = 19, [string]$Tag = 'smoke', [string]$Arms = 'A', [string]$Seeds = '1', [string]$Prefix = 'cm0', [string]$BFlag = '', [int]$Turns = 60)
# a task of our own (oxce_cmrun) in the user's session, interactive like oxce_ai4: pythonw without a console;
# ai_probe gives the game BELOW_NORMAL and the SDL dummy drivers
$R = 'C:\OXCE_AIWorker\cmrun'
$a = "-u $R\run_cm.py --jobs $Jobs --log logs\run_$Tag.txt --arms $Arms --seeds $Seeds --prefix $Prefix --turns $Turns"
if ($Scen) { $a += " --scen $Scen" }
if ($BFlag) { $a += " --bflag $BFlag" }
$act = New-ScheduledTaskAction -Execute 'C:\OXCE_AIWorker\python\pythonw.exe' -Argument $a -WorkingDirectory $R
$pr = New-ScheduledTaskPrincipal -UserId user -LogonType Interactive -RunLevel Limited
$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12) -Priority 7
Register-ScheduledTask -TaskName oxce_cmrun -Action $act -Principal $pr -Settings $st -Force | Out-Null
Start-ScheduledTask -TaskName oxce_cmrun
Start-Sleep 3
$t = Get-ScheduledTask oxce_cmrun
"task=$($t.State) args=$a"
