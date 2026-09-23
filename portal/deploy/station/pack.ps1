# Архив сайта поддержки для тестовой станции (Windows 11 + Docker Desktop).
# Собирается из ЗАКОММИЧЕННОГО состояния репозитория (git archive): что не в коммите, в архив
# не попадёт - коммитить до упаковки. Секреты (.env, portal.env, keys/*.key) в гите не лежат
# и в архив не идут.
#
#   powershell -ExecutionPolicy Bypass -File portal\deploy\station\pack.ps1
#
# Результат: dist\xp-portal-station_<дата_время>_<коммит>.zip; в корне архива README.txt и
# CLAUDE.md (инструкция для Claude на станции), рядом portal\ и docs\portal\.
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git не найден в PATH' }

$dirty = & git -C $repo status --porcelain -- portal docs/portal
if ($dirty) {
    Write-Host 'Незакоммиченные правки в portal/ или docs/portal/ - в архив они НЕ попадут:' -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "  $_" }
}
$hash = (& git -C $repo rev-parse --short HEAD).Trim()
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$dist = Join-Path $repo 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$zip = Join-Path $dist "xp-portal-station_${stamp}_$hash.zip"

$paths = @(
    'portal/Dockerfile', 'portal/.dockerignore', 'portal/Directory.Build.props',
    'portal/src/Xp.Portal', 'portal/src/Xp.Manifest', 'portal/src/Xp.Launcher.Core',
    'portal/deploy', 'docs/portal'
)
# --add-file кладёт файл в корень архива: инструкции видны сразу при распаковке
& git -C $repo archive --format=zip -o $zip `
    --add-file=portal/deploy/station/README.txt --add-file=portal/deploy/station/CLAUDE.md `
    HEAD @paths
if ($LASTEXITCODE -ne 0) { throw "git archive завершился с кодом $LASTEXITCODE" }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [IO.Compression.ZipFile]::OpenRead($zip)
try {
    $names = $z.Entries | ForEach-Object { $_.FullName }
    foreach ($must in 'README.txt', 'CLAUDE.md', 'portal/Dockerfile', 'portal/deploy/station.ps1', 'portal/deploy/compose.station.yaml', 'portal/src/Xp.Portal/Program.cs') {
        if ($names -notcontains $must) { throw "в архиве нет $must" }
    }
    $bad = $names | Where-Object { $_ -match '(^|/)(bin|obj)/|\.key$|(^|/)\.env$|portal\.env$' }
    if ($bad) { throw "в архив попало лишнее: $($bad -join ', ')" }
    Write-Host ("Готово: {0}  ({1} файлов, {2:N1} МБ, коммит {3})" -f $zip, $names.Count, ((Get-Item $zip).Length / 1MB), $hash) -ForegroundColor Green
}
finally { $z.Dispose() }
