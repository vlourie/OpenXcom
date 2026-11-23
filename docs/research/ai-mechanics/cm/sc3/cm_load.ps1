param([string]$Label = '', [string]$Save = '', [string]$Prefix = 'sc5l', [int]$Turns = 2, [string]$Tag = 'load')
# stage 3: the mid-turn save loaded in arms S and Q - the same own task oxce_cmrun as cm_launch.ps1 (pythonw, no console)
$R = 'C:\OXCE_AIWorker\cmrun'
$a = "-u $R\cm_load.py $Label $Save $Prefix --turns $Turns --log logs\run_$Tag.txt"
$act = New-ScheduledTaskAction -Execute 'C:\OXCE_AIWorker\python\pythonw.exe' -Argument $a -WorkingDirectory $R
$pr = New-ScheduledTaskPrincipal -UserId user -LogonType Interactive -RunLevel Limited
$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2) -Priority 7
Register-ScheduledTask -TaskName oxce_cmrun -Action $act -Principal $pr -Settings $st -Force | Out-Null
Start-ScheduledTask -TaskName oxce_cmrun
Start-Sleep 3
$t = Get-ScheduledTask oxce_cmrun
"task=$($t.State) args=$a"
