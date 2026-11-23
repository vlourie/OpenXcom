$ErrorActionPreference = 'Stop'
# P0 vs P1: pvrun from the stage 0B folder (stand, campaign saves, the player's exe, b0one.py) plus the uploaded bundle
$R = 'C:\OXCE_AIWorker\pvrun'
$B = 'C:\OXCE_AIWorker\b0run'
New-Item -ItemType Directory -Force "$R\stand", "$R\logs", "$R\work", "$R\out", "$R\saves", "$R\exe\P" | Out-Null
Copy-Item "$B\stand\ai_arena.py", "$B\stand\ai_probe.py", "$B\stand\mech_fp.py" "$R\stand\"
Copy-Item -Recurse -Force "$B\stand\scenario", "$B\stand\missions" "$R\stand\"
Copy-Item "$B\saves\*.sav" "$R\saves\"
Copy-Item "$B\exe\P\openxcom_hd.exe" "$R\exe\P\"
Copy-Item "$B\b0one.py" "$R\"
$bad = 0
foreach ($l in Get-Content "$R\SHA256SUMS.txt") {
	$h, $f = $l -split ' \*', 2
	$got = (Get-FileHash -Algorithm SHA256 (Join-Path $R $f)).Hash.ToLower()
	if ($got -ne $h) { "MISMATCH $f"; $bad++ }
}
"sums mismatches: $bad"
Get-FileHash -Algorithm SHA256 "$R\stand\ai_probe.py", "$B\stand\ai_probe.py", "$R\exe\P\openxcom_hd.exe", "$R\b0one.py" | ForEach-Object { $_.Hash.Substring(0, 16) + ' ' + $_.Path }
(Get-ChildItem "$R\saves").Name -join ' '
