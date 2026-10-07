# Архив хранилища релизов для станции: только то, что изменилось с прошлой упаковки.
# На станции его раскладывает '.\station.ps1 releases <архив>' - в правильном порядке.
#
#   powershell -ExecutionPolicy Bypass -File portal\deploy\pack-releases.ps1
#   powershell -ExecutionPolicy Bypass -File portal\deploy\pack-releases.ps1 -Full     всё хранилище
#
# Что уже упаковано, помнит файл <хранилище>.sent.txt (D:\xp-repo.sent.txt): путь, размер, время.
# Архив, который так и не доехал до станции, - повод для -Full: иначе его файлы туда не попадут.
# Указатели каналов и каталог кладутся всегда: они маленькие, а без них релиз не виден.
# Результат: dist\xp-releases_<дата_время>.zip (время с секундами: два запуска подряд не затрут друг друга)
param(
    [string] $Repo = 'D:\xp-repo',
    [switch] $Full
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Repo = (Resolve-Path -LiteralPath $Repo).Path.TrimEnd('\')
if (-not (Test-Path (Join-Path $Repo 'channels'))) { throw "в $Repo нет папки channels: это не хранилище релизов (сначала xp-release publish)" }

$sentFile = "$Repo.sent.txt"
$sent = @{}
# третий столбец - архив, в который файл попал впервые: по нему видно, что ещё нужно разложить (грабли R-065)
$sentZip = @{}
if (Test-Path -LiteralPath $sentFile) {
    foreach ($line in Get-Content -LiteralPath $sentFile -Encoding UTF8) {
        $p = $line -split "`t"
        if ($p.Count -lt 2) { continue }
        if (-not $Full) { $sent[$p[0]] = $p[1] }
        if ($p.Count -ge 3) { $sentZip[$p[0]] = $p[2] }
    }
}

$now = @{}
$pick = New-Object System.Collections.Generic.List[string]
$bytes = [long]0
foreach ($dir in 'blobs', 'releases', 'channels') {
    $d = Join-Path $Repo $dir
    if (-not (Test-Path $d)) { continue }
    foreach ($f in (New-Object IO.DirectoryInfo $d).EnumerateFiles('*', [IO.SearchOption]::AllDirectories)) {
        $rel = $f.FullName.Substring($Repo.Length + 1)
        $sig = '{0}|{1}' -f $f.Length, $f.LastWriteTimeUtc.Ticks
        $now[$rel] = $sig
        if ($dir -eq 'channels' -or $sent[$rel] -ne $sig) { $pick.Add($rel); $bytes += $f.Length }
    }
}
foreach ($n in 'catalog.json', 'catalog.json.sig') {
    $f = Get-Item -LiteralPath (Join-Path $Repo $n) -ErrorAction SilentlyContinue
    if ($f) { $now[$n] = '{0}|{1}' -f $f.Length, $f.LastWriteTimeUtc.Ticks; $pick.Add($n); $bytes += $f.Length }
}

$dist = Join-Path $root 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$zip = Join-Path $dist ('xp-releases_{0}{1}.zip' -f (Get-Date -Format 'yyyy-MM-dd_HHmmss'), $(if ($Full) { '_full' } else { '' }))
$list = Join-Path $env:TEMP 'xp-releases-list.txt'
# список путей для архиватора: без спецификации, иначе первая строка не найдётся
[IO.File]::WriteAllLines($list, $pick, (New-Object Text.UTF8Encoding $false))
Write-Host ("упаковываю {0:N0} файлов, {1:N1} МБ{2}" -f $pick.Count, ($bytes / 1MB), $(if ($Full) { ' (всё хранилище)' } else { '' }))

Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
$sevenZip = @((Join-Path $env:ProgramFiles '7-Zip\7z.exe'), (Join-Path ${env:ProgramFiles(x86)} '7-Zip\7z.exe')) | Where-Object { Test-Path $_ } | Select-Object -First 1
Push-Location $Repo
try {
    # без сжатия: блобы - это PNG и OGG, они уже сжаты, а упаковка идёт в разы быстрее
    if ($sevenZip) { & $sevenZip a -tzip -mx=0 -bso0 -bsp0 $zip "@$list" }
    # tar из Windows по полному пути: tar из Git в PATH принимает 'E:' за имя сервера
    else { & (Join-Path $env:WINDIR 'System32\tar.exe') -a -c -f $zip -T $list }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $zip)) { throw "архив не создан (код $LASTEXITCODE)" }
} finally { Pop-Location; Remove-Item -LiteralPath $list -Force -ErrorAction SilentlyContinue }

$zipName = Split-Path -Leaf $zip
$picked = @{}
foreach ($p in $pick) { $picked[$p] = $true; $sentZip[$p] = $zipName }
$lines = foreach ($k in ($now.Keys | Sort-Object)) { "$k`t$($now[$k])`t$($sentZip[$k])" }
[IO.File]::WriteAllLines($sentFile, [string[]]$lines, (New-Object Text.UTF8Encoding $true))

foreach ($c in @(Get-ChildItem -LiteralPath (Join-Path $Repo 'channels') -Filter '*.json' | Where-Object { $_.Name -notlike '*.history.json' })) {
    $j = Get-Content -LiteralPath $c.FullName -Raw | ConvertFrom-Json
    Write-Host ("  {0,-18} -> {1}" -f $c.BaseName, $j.releaseId)
    # указатель канала едет всегда, а файлы выпуска - только те, что новые. Назвать архивы,
    # без которых канал позовёт лаунчеры за тем, чего на станции нет (грабли R-065)
    $id = $j.releaseId
    if (-not $id) { continue }
    $need = New-Object System.Collections.Generic.List[string]
    foreach ($n in 'manifest.json', 'manifest.json.sig', 'release.json') { $need.Add("releases\$id\$n") }
    $mfPath = Join-Path $Repo "releases\$id\manifest.json"
    if (Test-Path -LiteralPath $mfPath) {
        foreach ($f in (Get-Content -LiteralPath $mfPath -Raw | ConvertFrom-Json).files) {
            $h = $f.sha256
            $need.Add(('blobs\sha256\{0}\{1}' -f $h.Substring(0, 2), $h))
        }
    }
    $where = @{}
    foreach ($n in $need) {
        if ($picked[$n]) { continue }
        # пустой столбец - файл из времён до этой записи: про него ничего не известно,
        # и за него отвечает проверка на станции, а не предупреждение здесь
        $w = $sentZip[$n]
        if ($w) { $where[$w] = $true }
    }
    if ($where.Count) {
        Write-Host ("  {0,-18}    файлы выпуска есть ещё в: {1}" -f '', (($where.Keys | Sort-Object) -join ', ')) -ForegroundColor Yellow
    }
}
Write-Host ("Готово: {0}  ({1:N1} МБ)" -f $zip, ((Get-Item -LiteralPath $zip).Length / 1MB)) -ForegroundColor Green
Write-Host 'На станции:  .\station.ps1 releases <этот архив>'
