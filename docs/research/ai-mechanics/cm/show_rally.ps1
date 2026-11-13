param([string]$Prefix = 'srt1')
# the small check of STAGE_RALLY_V1: per battle the result columns and the rally tallies, then the plans of the log
$R = 'C:\OXCE_AIWorker\cmrun\work\oxce_ai_probe'
Get-ChildItem "$R\arena\$($Prefix)_*.tsv" | Where-Object { $_.Name -notlike '*data_manifest*' } | ForEach-Object {
    $c = (Get-Content $_.FullName -Tail 1).Split([char]9)
    $tac = ($c[26].Split(',') | Where-Object { $_ -like 'h.rally*' }) -join ','
    "$($_.BaseName) turn=$($c[11]) pdead=$($c[13]) phplost=$($c[16]) hdead=$($c[18]) $tac"
}
Get-ChildItem "$R\arena_$($Prefix)_*_w0\openxcom.log" | ForEach-Object {
    $n = $_.Directory.Name
    $lines = Select-String -Path $_.FullName -Pattern 'rally turn' | ForEach-Object { $_.Line.Substring($_.Line.IndexOf('rally turn')) }
    "$n plans $($lines.Count)"
    $lines | Select-Object -First 6 | ForEach-Object { "   $_" }
}
