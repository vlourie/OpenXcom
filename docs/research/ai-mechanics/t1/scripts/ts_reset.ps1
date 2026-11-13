$ErrorActionPreference = 'Stop'
# AI-T1: the first exe's battles (E0/E1) and logs aside into old\v1, so the rebuilt exe runs the record phase again
$R = 'C:\OXCE_AIWorker\tsrun'
New-Item -ItemType Directory -Force "$R\old\v1\out", "$R\old\v1\logs" | Out-Null
Get-ChildItem "$R\out" -Directory | Where-Object { $_.Name -like 'E*' } | Move-Item -Destination "$R\old\v1\out"
Get-ChildItem "$R\logs" -File | Move-Item -Destination "$R\old\v1\logs"
Move-Item "$R\manifest.txt" "$R\old\v1\" -ErrorAction SilentlyContinue
Remove-Item "$R\get_E.zip" -ErrorAction SilentlyContinue
"moved: $((Get-ChildItem "$R\old\v1\out" -Directory).Count) battles; out now: $((Get-ChildItem "$R\out" -Directory).Count)"
