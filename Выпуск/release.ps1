<#
  OXCE HD — выпуск одним запуском: сборка «Обе» -> подпись -> публикация -> проверка -> архив для станции.

    OXCE_Release.cmd                  канал из release_config.json (stable)
    OXCE_Release.cmd test             другой канал
    OXCE_Release.cmd nobuild          без сборки: подписать то, что лежит в dist\_stage

  Имя выпуска выбирается само по дате: 2026.09.24, второй за день 2026.09.24-2; в канале test -
  2026.09.24-test, 2026.09.24-test2. Версия - 2026.9.24 (2026.9.24.2 для второго за день).
  «Что нового»: notes\next.ru.txt и notes\next.en.txt. После выпуска они переименовываются в
  notes\<имя выпуска>.ru.txt, чтобы следующий выпуск не показал старый текст.
  Лаунчер выпускается, только если его версии (<Version> в Xp.Launcher.csproj) ещё нет в хранилище.

  Приватный ключ скрипт не читает: путь к нему передаётся xp-release, и всё.
  Настройки - release_config.json рядом. Журнал - dist\release_<имя>.log.
#>
param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $Rest)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$clock = [Diagnostics.Stopwatch]::StartNew()
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Step([string] $t) { Write-Host ''; Write-Host "==> $t" -ForegroundColor Cyan }
function Ok([string] $t)   { Write-Host "    $t" -ForegroundColor Green }
function Warn([string] $t) { Write-Host "    ВНИМАНИЕ: $t" -ForegroundColor Yellow }

# xp-release печатает в консоль сам; ненулевой код - остановка
function Xpr([string[]] $a) {
    & $script:xpr @a | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "xp-release $($a[0]) завершился с кодом $LASTEXITCODE" }
}

# другой файл настроек (для пробы на одноразовом ключе): любой аргумент, кончающийся на .json
$args_ = @($Rest | Where-Object { $_ })
$cfgFile = $args_ | Where-Object { $_ -like '*.json' } | Select-Object -Last 1
if (-not $cfgFile) { $cfgFile = Join-Path $PSScriptRoot 'release_config.json' }
$cfg = Get-Content -LiteralPath $cfgFile -Raw -Encoding UTF8 | ConvertFrom-Json
$channel = $cfg.Channel
$noBuild = $false
foreach ($a in $args_ | Where-Object { $_ -notlike '*.json' }) {
    if ($a -ieq 'nobuild') { $noBuild = $true } else { $channel = $a.ToLowerInvariant() }
}
if ($channel -notmatch '^[a-z0-9][a-z0-9-]*$') { throw "плохое имя канала: $channel" }
$launcherChannel = "launcher-$channel"
$repo = $cfg.Repo
$notes = Join-Path $PSScriptRoot 'notes'
$dist = Join-Path $root 'dist'
$failed = $false
$logFile = Join-Path $dist ('release_{0:yyyy-MM-dd_HHmmss}.log' -f (Get-Date))
New-Item -ItemType Directory -Force -Path $dist | Out-Null
try { Start-Transcript -LiteralPath $logFile -Force | Out-Null } catch {}

try {
    Step "Выпуск в канал $channel$(if ($noBuild) { ' (без сборки)' })"
    if (-not (Test-Path -LiteralPath $cfg.Key)) { throw "нет приватного ключа $($cfg.Key) - подключите диск с ключом" }
    if (-not (Test-Path -LiteralPath $cfg.Pub)) { throw "нет открытого ключа $($cfg.Pub)" }
    New-Item -ItemType Directory -Force -Path $repo | Out-Null

    # ---- xp-release: пересобрать, если его исходники новее
    $script:xpr = $cfg.XpRelease
    $srcDirs = 'Xp.ReleaseBuilder', 'Xp.Manifest' | ForEach-Object { Join-Path $root "portal\src\$_" }
    $newest = Get-ChildItem -LiteralPath $srcDirs -Recurse -File -Include *.cs, *.csproj |
        Where-Object { $_.FullName -notmatch '\\(bin|obj)\\' } | Sort-Object LastWriteTime | Select-Object -Last 1
    if (-not (Test-Path -LiteralPath $xpr) -or (Get-Item -LiteralPath $xpr).LastWriteTime -lt $newest.LastWriteTime) {
        Step 'Собираю xp-release'
        if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw 'dotnet не найден в PATH' }
        & dotnet publish (Join-Path $root 'portal\src\Xp.ReleaseBuilder') -c Release -o (Split-Path -Parent $xpr) --nologo -v quiet | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "dotnet publish завершился с кодом $LASTEXITCODE" }
    }

    # ---- сборка «Обе»: exe, моды, лаунчер -> dist\_stage и dist\_launcher_rel
    if (-not $noBuild) {
        Step 'Сборка «Обе» (tools\build\build.ps1 -Target Both)'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools\build\build.ps1') -Target Both
        if ($LASTEXITCODE -ne 0) { throw "сборка не удалась (код $LASTEXITCODE) - смотрите её вывод выше" }
    }
    $launchExe = Join-Path $cfg.Stage $cfg.Launch
    if (-not (Test-Path -LiteralPath $launchExe)) { throw "в $($cfg.Stage) нет $($cfg.Launch) - нужна сборка «Обе»" }
    Ok ("стейдж от {0:dd.MM HH:mm}" -f (Get-Item -LiteralPath $launchExe).LastWriteTime)

    # ---- имя и версия выпуска по дате
    $today = Get-Date
    $base = $today.ToString('yyyy.MM.dd')
    $n = 1
    while ($true) {
        $suffix = if ($channel -eq 'stable') { if ($n -eq 1) { '' } else { "-$n" } } else { "-$channel$(if ($n -gt 1) { $n })" }
        $id = "$base$suffix"
        if (-not (Test-Path -LiteralPath (Join-Path $repo "releases\$id"))) { break }
        $n++
    }
    $version = '{0}.{1}.{2}' -f $today.Year, $today.Month, $today.Day
    if ($n -gt 1) { $version += ".$n" }
    Ok "выпуск $id, версия $version"

    # ---- игра
    Step "Подписываю игру: $id"
    $buildArgs = @('build', '--repo', $repo, '--id', $id, '--version', $version, '--channel', $channel,
        '--stage', $cfg.Stage, '--launch', $cfg.Launch, '--key', $cfg.Key)
    $usedNotes = @()
    foreach ($lang in 'ru', 'en') {
        $f = Join-Path $notes "next.$lang.txt"
        if ((Test-Path -LiteralPath $f) -and (Get-Content -LiteralPath $f -Raw -Encoding UTF8).Trim()) {
            $buildArgs += @("--changelog-$lang", $f); $usedNotes += $f
        }
    }
    if (-not $usedNotes) { Warn 'нет notes\next.ru.txt - выпуск уйдёт без «Что нового»' }
    Xpr $buildArgs
    Xpr @('publish', '--repo', $repo, '--channel', $channel, '--id', $id, '--key', $cfg.Key)
    foreach ($f in $usedNotes) {
        $lang = [IO.Path]::GetFileNameWithoutExtension($f).Split('.')[-1]
        Move-Item -LiteralPath $f -Destination (Join-Path $notes "$id.$lang.txt") -Force
    }

    # ---- лаунчер: только новая версия
    $launcherExe = Join-Path $cfg.LauncherDir 'XPiratezLauncher.exe'
    if (-not (Test-Path -LiteralPath $launcherExe)) { throw "нет $launcherExe - сборка «Обе» его не положила" }
    $lv = ((Get-Item -LiteralPath $launcherExe).VersionInfo.ProductVersion -split '\+')[0]
    $lid = if ($channel -eq 'stable') { "launcher-$lv" } else { "launcher-$lv-$channel" }
    $ptrFile = Join-Path $repo "channels\$launcherChannel.json"
    $current = if (Test-Path -LiteralPath $ptrFile) { (Get-Content -LiteralPath $ptrFile -Raw | ConvertFrom-Json).releaseId }
    if ($current -eq $lid) {
        Ok "лаунчер $lv уже в канале $launcherChannel"
    } else {
        Step "Подписываю лаунчер $lv -> $launcherChannel"
        if (-not (Test-Path -LiteralPath (Join-Path $repo "releases\$lid"))) {
            Xpr @('build', '--repo', $repo, '--id', $lid, '--version', $lv, '--channel', $launcherChannel,
                '--stage', $cfg.LauncherDir, '--launcher-kind', '--key', $cfg.Key)
        }
        Xpr @('publish', '--repo', $repo, '--channel', $launcherChannel, '--id', $lid, '--key', $cfg.Key)
    }

    # ---- проверка подписей и файлов
    Step 'Проверяю хранилище'
    foreach ($ch in $channel, $launcherChannel) {
        $v = @('verify', '--repo', $repo, '--channel', $ch, '--pub', $cfg.Pub)
        if ($cfg.VerifyDeep) { $v += '--deep' }
        Xpr $v
    }

    # ---- архив для станции
    Step 'Упаковываю для станции'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'portal\deploy\pack-releases.ps1') -Repo $repo
    if ($LASTEXITCODE -ne 0) { throw "pack-releases завершился с кодом $LASTEXITCODE" }
    $zip = Get-ChildItem -LiteralPath $dist -Filter 'xp-releases_*.zip' | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($cfg.StationDrop) {
        Step "Копирую на станцию: $($cfg.StationDrop)"
        if (-not (Test-Path -LiteralPath $cfg.StationDrop -PathType Container)) { throw "нет папки $($cfg.StationDrop) (StationDrop) - станция выключена или папка не расшарена; архив остался в dist" }
        Copy-Item -LiteralPath $zip.FullName -Destination $cfg.StationDrop -Force
        Ok 'скопировано'
    }

    Write-Host ''
    Write-Host ("ГОТОВО за {0:hh\:mm\:ss}: {1} в канале {2}" -f $clock.Elapsed, $id, $channel) -ForegroundColor Green
    Write-Host "Архив: $($zip.FullName)"
    Write-Host 'На станции (PowerShell из C:\xp-portal\portal\deploy):'
    Write-Host "    powershell -ExecutionPolicy Bypass -File .\station.ps1 releases <папка>\$($zip.Name)"
    if ($cfg.OpenExplorer) { Start-Process explorer.exe "/select,`"$($zip.FullName)`"" }
} catch {
    $failed = $true
    Write-Host ''
    Write-Host "ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Уже опубликованное можно откатить: xp-release revoke --repo <хранилище> --channel <канал> --id <имя> --key <ключ>'
}
try { Stop-Transcript | Out-Null } catch {}
if ($failed) { exit 1 } else { exit 0 }
