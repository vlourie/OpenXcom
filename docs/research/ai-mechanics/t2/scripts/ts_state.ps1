$ErrorActionPreference = 'Continue'
# AI-T2: is anything of ours running (task oxce_tsrun, pythonw tsrun, the game started from tsrun), and the station's load
$R = 'C:\OXCE_AIWorker\tsrun'
$t = Get-ScheduledTask -TaskName oxce_tsrun -ErrorAction SilentlyContinue
"task: " + $(if ($t) { $t.State } else { 'absent' })
$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like "*OXCE_AIWorker\tsrun*" }
"tsrun processes: $(@($p).Count)"
$p | ForEach-Object { "  $($_.ProcessId) $($_.Name)" }
$g = Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'openxcom*' }
"game processes on the station (all owners): $(@($g).Count)"
"cpu load %: " + (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
"out F*: $(@(Get-ChildItem "$R\out" -Directory -Filter 'F*' -ErrorAction SilentlyContinue).Count)"
"exe T2: " + $(if (Test-Path "$R\exe\T2\openxcom.exe") { (Get-FileHash -Algorithm SHA256 "$R\exe\T2\openxcom.exe").Hash.ToLower() } else { 'absent' })
