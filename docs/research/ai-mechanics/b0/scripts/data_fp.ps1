# Stage 0B: fingerprint of the game data every configuration loaded (-data C:\OXCE_AIWorker\game): per top folder, the
# number of files and one SHA256 over the sorted "relative path + file hash" list; rulesets (*.rul) counted separately.
# Writes C:\OXCE_AIWorker\b0run\data_fp.txt
$root = 'C:\OXCE_AIWorker\game'
$out = 'C:\OXCE_AIWorker\b0run\data_fp.txt'
$sha = [System.Security.Cryptography.SHA256]::Create()
$lines = @("# data fingerprint $root $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
function Fp($files, $base) {
	$list = foreach ($f in ($files | Sort-Object FullName)) {
		$rel = $f.FullName.Substring($base.Length).Replace('\', '/')
		"$rel $((Get-FileHash -Algorithm SHA256 -LiteralPath $f.FullName).Hash)"
	}
	$bytes = [System.Text.Encoding]::UTF8.GetBytes(($list -join "`n"))
	return @{ n = @($list).Count; h = ([System.BitConverter]::ToString($sha.ComputeHash($bytes)) -replace '-', '').ToLower() }
}
foreach ($d in Get-ChildItem -LiteralPath $root -Directory) {
	if ($d.Name -eq 'user') { continue }
	$all = Get-ChildItem -LiteralPath $d.FullName -Recurse -File
	$r = Fp $all $root
	$rul = Fp ($all | Where-Object { $_.Extension -eq '.rul' }) $root
	$lines += "$($d.Name) files=$($r.n) sha256=$($r.h) rul=$($rul.n) rul_sha256=$($rul.h)"
}
$mods = 'C:\OXCE_AIWorker\game\user\mods'
if (Test-Path $mods) {
	foreach ($d in Get-ChildItem -LiteralPath $mods -Directory) {
		$all = Get-ChildItem -LiteralPath $d.FullName -Recurse -File
		$r = Fp $all $root
		$rul = Fp ($all | Where-Object { $_.Extension -eq '.rul' }) $root
		$lines += "user/mods/$($d.Name) files=$($r.n) sha256=$($r.h) rul=$($rul.n) rul_sha256=$($rul.h)"
	}
}
$lines | Set-Content -LiteralPath $out -Encoding UTF8
$lines
