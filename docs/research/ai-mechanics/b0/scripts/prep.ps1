$ErrorActionPreference = 'Stop'
# stage 0B: the stand scripts copied from c1run\stand (itself a copy of stand2), sums of the uploaded bundle checked
$R = 'C:\OXCE_AIWorker\b0run'
New-Item -ItemType Directory -Force "$R\stand", "$R\logs", "$R\work", "$R\out", "$R\fixtures" | Out-Null
Copy-Item C:\OXCE_AIWorker\c1run\stand\ai_arena.py, C:\OXCE_AIWorker\c1run\stand\ai_probe.py, C:\OXCE_AIWorker\c1run\stand\mech_fp.py "$R\stand\"
Copy-Item -Recurse -Force C:\OXCE_AIWorker\c1run\stand\scenario, C:\OXCE_AIWorker\c1run\stand\missions "$R\stand\"
$bad = 0
foreach ($l in Get-Content "$R\SHA256SUMS.txt") {
	$h, $f = $l -split ' \*', 2
	$got = (Get-FileHash -Algorithm SHA256 (Join-Path $R $f)).Hash.ToLower()
	if ($got -ne $h) { "MISMATCH $f"; $bad++ }
}
"sums mismatches: $bad"
Get-FileHash -Algorithm SHA256 "$R\stand\ai_probe.py", C:\OXCE_AIWorker\stand2\ai_probe.py, "$R\stand\mech_fp.py" | ForEach-Object { $_.Hash.Substring(0, 16) + ' ' + $_.Path }
