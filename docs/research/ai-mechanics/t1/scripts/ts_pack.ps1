$ErrorActionPreference = 'Stop'
# AI-T1: results (battle logs and run notes of both exe builds, run logs, manifests, cfg) -> ts_all.zip
$R = 'C:\OXCE_AIWorker\tsrun'
$Z = "$R\ts_all.zip"
if (Test-Path $Z) { Remove-Item $Z }
Remove-Item "$R\get_*.zip" -ErrorAction SilentlyContinue
$stage = "$R\pack"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item -Recurse "$R\out", "$R\logs", "$R\cfg", "$R\old" $stage
Copy-Item "$R\manifest.txt", "$R\SHA256SUMS.txt" $stage
Compress-Archive -Path "$stage\*" -DestinationPath $Z
Remove-Item -Recurse -Force $stage
$h = (Get-FileHash -Algorithm SHA256 $Z).Hash.ToLower()
"$h $((Get-Item $Z).Length)"
"battles: out $((Get-ChildItem "$R\out" -Directory).Count), old\v1 $((Get-ChildItem "$R\old\v1\out" -Directory).Count)"
