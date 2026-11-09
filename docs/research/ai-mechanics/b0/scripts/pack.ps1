param([string]$Tag = 'res', [string]$Filter = '*')
# copy the finished outputs (out\<Filter> with after.sav or fixture.sav, fixtures, manifest, cfg, logs) aside, zip the copy
$ErrorActionPreference = 'Stop'
$R = 'C:\OXCE_AIWorker\b0run'
$P = "$R\pack_$Tag"
if (Test-Path $P) { Remove-Item $P -Recurse -Force }
New-Item -ItemType Directory -Force "$P\out", "$P\logs" | Out-Null
Get-ChildItem "$R\out" -Directory -Filter $Filter | ForEach-Object { Copy-Item $_.FullName "$P\out\" -Recurse -ErrorAction SilentlyContinue }
Copy-Item "$R\fixtures" "$P\" -Recurse
Copy-Item "$R\cfg" "$P\" -Recurse
Copy-Item "$R\manifest.txt", "$R\SHA256SUMS.txt" "$P\"
Get-ChildItem "$R\logs" -File | ForEach-Object { Copy-Item $_.FullName "$P\logs\" -ErrorAction SilentlyContinue }
$z = "$R\b0_$Tag.zip"
Compress-Archive -Force -Path "$P\*" -DestinationPath $z
Remove-Item $P -Recurse -Force
(Get-FileHash $z).Hash.ToLower()
