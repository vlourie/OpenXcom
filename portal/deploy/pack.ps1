# Архив сайта: исходники из ЗАКОММИЧЕННОГО состояния репозитория (git archive) плюс вики,
# собранная из рулсетов. Что не в коммите, в архив не попадёт - коммитить до упаковки.
# Секреты (.env, portal.env, keys/*.key) в гите не лежат и в архив не идут.
#
#   powershell -ExecutionPolicy Bypass -File portal\deploy\pack.ps1
#   powershell -ExecutionPolicy Bypass -File portal\deploy\pack.ps1 -NoWiki    только код
#
# Вики берётся из dist\wiki\*.json (их собирает tools\portal_wiki.py) и ложится в архив по пути
# portal\deploy\wiki\ - откуда её и читает контейнер. Файл большой (12,7 МБ у Пираток), но
# сжимается примерно в десять раз.
#
# Результат: dist\xp-portal_<дата_время>_<коммит>.zip; в корне архива README.txt (инструкция для
# человека) и CLAUDE.md (инструкция для Claude на той машине), рядом portal\ и docs\portal\.
param([switch] $NoWiki)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
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
$zip = Join-Path $dist "xp-portal_${stamp}_$hash.zip"

$paths = @(
    'portal/Dockerfile', 'portal/.dockerignore', 'portal/Directory.Build.props',
    'portal/src/Xp.Portal', 'portal/src/Xp.Manifest', 'portal/src/Xp.Launcher.Core',
    'portal/deploy', 'docs/portal',
    'portal/keys/release-keys.txt'   # открытые ключи релизов: station.ps1 releases пишет prod в portal.env
)
# --add-file кладёт файл в корень архива: инструкции видны сразу при распаковке
& git -C $repo archive --format=zip -o $zip `
    --add-file=portal/deploy/README.txt --add-file=portal/deploy/station/CLAUDE.md `
    HEAD @paths
if ($LASTEXITCODE -ne 0) { throw "git archive завершился с кодом $LASTEXITCODE" }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$wiki = @()
if (-not $NoWiki) {
    $wiki = @(Get-ChildItem -Path (Join-Path $repo 'dist\wiki') -Filter '*.json' -ErrorAction SilentlyContinue)
    if (-not $wiki) {
        Write-Host 'В dist\wiki нет ни одного JSON - архив уедет без вики. Собрать:' -ForegroundColor Yellow
        Write-Host '  py -3 tools\portal_wiki.py --mod "Пиратки\Dioxine_XPiratez\user\mods\Piratez" --base bin\standard\xcom1 --slug piratez --lang ru --lang en --out dist\wiki\piratez.json'
    }
    else {
        $z = [IO.Compression.ZipFile]::Open($zip, 'Update')
        try {
            foreach ($f in $wiki) {
                # мод и версию печатаем из самого файла: так видно, что уезжает не вчерашняя сборка
                $head = (Get-Content -LiteralPath $f.FullName -TotalCount 4 -Encoding UTF8) -join ' '
                Write-Host ("вики: {0}  {1:N1} МБ  {2}" -f $f.Name, ($f.Length / 1MB), ($head -replace '[{"]|\s+', ' ').Trim())
                [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $z, $f.FullName, "portal/deploy/wiki/$($f.Name)", [IO.Compression.CompressionLevel]::Optimal) | Out-Null
            }
        }
        finally { $z.Dispose() }
    }
}

$z = [IO.Compression.ZipFile]::OpenRead($zip)
try {
    $names = $z.Entries | ForEach-Object { $_.FullName }
    $must = @('README.txt', 'CLAUDE.md', 'portal/Dockerfile', 'portal/deploy/station.ps1', 'portal/deploy/update.sh',
        'portal/deploy/compose.yaml', 'portal/deploy/compose.station.yaml', 'portal/deploy/compose.internet.yaml',
        'portal/deploy/Caddyfile.internet', 'portal/deploy/caddy/Dockerfile',
        'portal/deploy/seed/community.json', 'portal/src/Xp.Portal/Program.cs')
    foreach ($m in $must) { if ($names -notcontains $m) { throw "в архиве нет $m" } }
    foreach ($f in $wiki) { if ($names -notcontains "portal/deploy/wiki/$($f.Name)") { throw "в архив не попала вики $($f.Name)" } }
    $bad = $names | Where-Object { $_ -match '(^|/)(bin|obj)/|\.key$|(^|/)\.env$|portal\.env$' }
    if ($bad) { throw "в архив попало лишнее: $($bad -join ', ')" }
    Write-Host ("Готово: {0}  ({1} файлов, {2:N1} МБ, коммит {3})" -f $zip, $names.Count, ((Get-Item $zip).Length / 1MB), $hash) -ForegroundColor Green
}
finally { $z.Dispose() }
