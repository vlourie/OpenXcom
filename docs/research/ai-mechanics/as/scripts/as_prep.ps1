$ErrorActionPreference = 'Stop'
# AI-IF: a fresh run folder C:\OXCE_AIWorker\asrun from the archived T2 inputs (t2_all.zip: stand, saves, pvone.py, scen.tsv);
# the T2 outputs, logs and exe from that zip are not kept. Then the hashes of what the run will use.
$R = 'C:\OXCE_AIWorker\asrun'
$Z = "$R\t2_all.zip"
$x = "$R\unz"
if (Test-Path $x) { Remove-Item -Recurse -Force $x }
Expand-Archive -Path $Z -DestinationPath $x
foreach ($d in 'stand', 'saves') { if (-not (Test-Path "$R\$d")) { Move-Item "$x\$d" "$R\$d" } }
foreach ($f in 'pvone.py', 'scen.tsv') { if (-not (Test-Path "$R\$f")) { Move-Item "$x\$f" "$R\$f" } }
Remove-Item -Recurse -Force $x
Remove-Item $Z
Get-ChildItem $R -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Get-ChildItem $R -Recurse -File | Where-Object { $_.FullName -notlike "$R\out\*" -and $_.FullName -notlike "$R\logs\*" -and $_.FullName -notlike "$R\work\*" } |
	Sort-Object FullName | ForEach-Object { "$((Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower()) $($_.FullName.Substring($R.Length + 1))" }
