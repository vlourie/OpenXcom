$ErrorActionPreference = 'Stop'
# commander stage: stand2's scenario/ and missions/ and the station's envrun.py into cmrun (copies; the originals stay),
# then the package sums
$R = 'C:\OXCE_AIWorker\cmrun'
New-Item -ItemType Directory -Force "$R\stand", "$R\logs", "$R\work" | Out-Null
foreach ($d in 'scenario', 'missions') { if (-not (Test-Path "$R\stand\$d")) { Copy-Item -Recurse "C:\OXCE_AIWorker\stand2\$d" "$R\stand\" } }
Copy-Item C:\OXCE_AIWorker\envrun.py "$R\"
# ai_arena imports the data fingerprint module of the stand
Copy-Item C:\OXCE_AIWorker\stand2\mech_fp.py "$R\stand\"
$bad = 0
foreach ($l in Get-Content "$R\SHA256SUMS.txt") {
    $h, $f = $l -split ' \*', 2
    $got = (Get-FileHash -Algorithm SHA256 (Join-Path $R $f)).Hash.ToLower()
    if ($got -ne $h) { "MISMATCH $f"; $bad++ }
}
"sums mismatches: $bad"
Get-FileHash -Algorithm SHA256 "$R\envrun.py", "$R\stand\mech_fp.py" | ForEach-Object { $_.Hash.Substring(0, 16).ToLower() + ' ' + $_.Path }
(Get-ChildItem -Recurse "$R\stand\scenario", "$R\stand\missions" | Measure-Object).Count
