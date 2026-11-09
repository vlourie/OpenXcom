$ErrorActionPreference = 'Stop'
# AI-T1 target selection: tsrun from the P0/P1 folder pvrun (stand, campaign saves, scenarios, pvone.py) plus the uploaded exe T1
$R = 'C:\OXCE_AIWorker\tsrun'
$B = 'C:\OXCE_AIWorker\pvrun'
New-Item -ItemType Directory -Force "$R\stand", "$R\logs", "$R\work", "$R\out", "$R\saves" | Out-Null
Copy-Item "$B\stand\ai_arena.py", "$B\stand\ai_probe.py", "$B\stand\mech_fp.py" "$R\stand\"
Copy-Item -Recurse -Force "$B\stand\scenario", "$B\stand\missions" "$R\stand\"
Copy-Item "$B\saves\*.sav" "$R\saves\"
Copy-Item "$B\pvone.py", "$B\scen.tsv" "$R\"
$bad = 0
foreach ($f in @(Get-ChildItem -Recurse -File "$B\stand", "$B\saves" | Where-Object { $_.FullName -notlike '*__pycache__*' }) + @(Get-Item "$B\pvone.py", "$B\scen.tsv")) {
	$rel = $f.FullName.Substring($B.Length)
	if ((Get-FileHash -Algorithm SHA256 $f.FullName).Hash -ne (Get-FileHash -Algorithm SHA256 "$R$rel").Hash) { "MISMATCH $rel"; $bad++ }
}
"copied from pvrun, mismatches: $bad"
$bad = 0
foreach ($l in Get-Content "$R\SHA256SUMS.txt") {
	$h, $f = $l -split ' \*', 2
	if ((Get-FileHash -Algorithm SHA256 (Join-Path $R $f)).Hash.ToLower() -ne $h) { "MISMATCH $f"; $bad++ }
}
"uploaded bundle mismatches: $bad"
(Get-ChildItem "$R\saves").Name -join ' '
