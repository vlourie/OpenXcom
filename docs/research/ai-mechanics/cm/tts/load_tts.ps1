param([string]$Arm = '', [string]$Save = '', [string]$Prefix = '', [string]$Scen = '', [string]$Seed = '', [int]$Turns = 1, [int]$Bot = 0)
# TACTICAL TURN SOLVER V0: the save loaded under the same own task oxce_cmrun as cm_launch.ps1 (pythonw, no console)
$R = 'C:\OXCE_AIWorker\cmrun'
$a = "-u $R\load_tts.py $Arm $Save $Prefix $Scen $Seed $Turns $Bot --log logs\run_$Prefix.txt"
$act = New-ScheduledTaskAction -Execute 'C:\OXCE_AIWorker\python\pythonw.exe' -Argument $a -WorkingDirectory $R
$pr = New-ScheduledTaskPrincipal -UserId user -LogonType Interactive -RunLevel Limited
$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2) -Priority 7
Register-ScheduledTask -TaskName oxce_cmrun -Action $act -Principal $pr -Settings $st -Force | Out-Null
Start-ScheduledTask -TaskName oxce_cmrun
Start-Sleep 3
$t = Get-ScheduledTask oxce_cmrun
"task=$($t.State) args=$a"
