$ErrorActionPreference = 'Stop'
# AI-IF: results (battle logs and run notes G0/G1, run logs, manifest, cfg) and the inputs to repeat them (asrun.py,
# launch/prep scripts, pvone.py, scen.tsv, stand, saves, exe IF) -> as_all.zip; prints its sha256 and size
$R = 'C:\OXCE_AIWorker\asrun'
$Z = "$R\as_all.zip"
if (Test-Path $Z) { Remove-Item $Z }
Remove-Item "$R\get_*.zip" -ErrorAction SilentlyContinue
$stage = "$R\pack"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force "$stage\out", "$stage\logs", "$stage\exe" | Out-Null
Get-ChildItem "$R\out" -Directory -Filter 'G*' | ForEach-Object { Copy-Item -Recurse $_.FullName "$stage\out\" }
Get-ChildItem "$R\logs" -File | ForEach-Object { Copy-Item $_.FullName "$stage\logs\" }
Copy-Item -Recurse "$R\cfg", "$R\stand", "$R\saves" $stage
Copy-Item -Recurse "$R\exe\IF" "$stage\exe\"
Copy-Item "$R\manifest.txt", "$R\SHA256SUMS_IF.txt", "$R\asrun.py", "$R\as_launch.ps1", "$R\as_prep.ps1", "$R\as_pack.ps1", "$R\pvone.py", "$R\scen.tsv" $stage
Get-ChildItem $stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Compress-Archive -Path "$stage\*" -DestinationPath $Z
Remove-Item -Recurse -Force $stage
$h = (Get-FileHash -Algorithm SHA256 $Z).Hash.ToLower()
"$h $((Get-Item $Z).Length)"
"battles: G* $((Get-ChildItem "$R\out" -Directory -Filter 'G*').Count)"
