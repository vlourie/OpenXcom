$ErrorActionPreference = 'Stop'
# P0 vs P1: results (battle logs, run notes, the save/load runs' saves and logs), logs, manifest, cfg -> pv_all.zip
$R = 'C:\OXCE_AIWorker\pvrun'
$Z = "$R\pv_all.zip"
if (Test-Path $Z) { Remove-Item $Z }
$stage = "$R\pack"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item -Recurse "$R\out", "$R\logs", "$R\cfg" $stage
Copy-Item "$R\manifest.txt", "$R\PREREG.md", "$R\PREREG.sha256", "$R\SHA256SUMS.txt" $stage
Compress-Archive -Path "$stage\*" -DestinationPath $Z
Remove-Item -Recurse -Force $stage
$h = (Get-FileHash -Algorithm SHA256 $Z).Hash.ToLower()
"$h $((Get-Item $Z).Length)"
(Get-ChildItem "$R\out" -Directory | Measure-Object).Count
