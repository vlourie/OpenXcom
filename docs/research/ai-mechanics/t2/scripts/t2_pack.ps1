$ErrorActionPreference = 'Stop'
# AI-T2: results (battle logs and run notes F0/F1/F2/F2R, run logs, manifest, cfg) and the inputs to repeat them (tsrun.py,
# launch/state scripts, pvone.py, scen.tsv, stand, saves, exe T2) -> t2_all.zip; prints its sha256 and size
$R = 'C:\OXCE_AIWorker\tsrun'
$Z = "$R\t2_all.zip"
if (Test-Path $Z) { Remove-Item $Z }
Remove-Item "$R\get_*.zip" -ErrorAction SilentlyContinue
$stage = "$R\pack2"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force "$stage\out", "$stage\logs", "$stage\exe" | Out-Null
Get-ChildItem "$R\out" -Directory -Filter 'F*' | ForEach-Object { Copy-Item -Recurse $_.FullName "$stage\out\" }
Get-ChildItem "$R\logs" -File | Where-Object { $_.Name -like 'F*' -or $_.Name -like 'run_t2*' } | ForEach-Object { Copy-Item $_.FullName "$stage\logs\" }
Copy-Item -Recurse "$R\cfg", "$R\stand", "$R\saves" $stage
Copy-Item -Recurse "$R\exe\T2" "$stage\exe\"
Copy-Item "$R\manifest.txt", "$R\SHA256SUMS_T2.txt", "$R\tsrun.py", "$R\ts_launch.ps1", "$R\ts_state.ps1", "$R\pvone.py", "$R\scen.tsv" $stage
Get-ChildItem $stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Compress-Archive -Path "$stage\*" -DestinationPath $Z
Remove-Item -Recurse -Force $stage
$h = (Get-FileHash -Algorithm SHA256 $Z).Hash.ToLower()
"$h $((Get-Item $Z).Length)"
"battles: F* $((Get-ChildItem "$R\out" -Directory -Filter 'F*').Count)"
