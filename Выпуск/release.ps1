<#
  OXCE HD — выпуск одним запуском: сборка «Обе» -> подпись -> публикация -> проверка -> архив для станции.

    OXCE_Release.cmd                  канал из release_config.json (stable)
    OXCE_Release.cmd test             другой канал
    OXCE_Release.cmd nobuild          без сборки: подписать то, что лежит в dist\_stage
    OXCE_Release.cmd launcher         только лаунчер: игра в канале остаётся прежней

  Имя выпуска выбирается само по дате: 2026.09.24, второй за день 2026.09.24-2; в канале test -
  2026.09.24-test, 2026.09.24-test2. Версия - 2026.9.24 (2026.9.24.2 для второго за день).
  «Что нового»: по-русски - раздел «[Не выпущено]» CHANGELOG.md сам, плюс notes\next.ru.txt (только то,
  чего в CHANGELOG нет); по-английски - notes\next.en.txt. После выпуска они переименовываются в
  notes\<имя выпуска>.ru.txt, чтобы следующий выпуск не показал старый текст. В канале stable
  раздел «[Не выпущено]» CHANGELOG.md становится разделом «<имя выпуска> — <дата>».
  Если в готовый стейдж вошла только часть накопленного, «Что нового» кладётся в notes\stage.ru.txt и
  stage.en.txt (только с nobuild): текст берётся из них, а из «[Не выпущено]» и next.* уходят ровно их пункты.
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
# CHANGELOG.md: всё, что копилось под «[Не выпущено]», становится разделом выпуска $id, а сверху
# остаётся пустой «[Не выпущено]» для следующего. Иначе выпуски сливаются в один раздел (аудит 26.09)
function Close-Changelog([string] $path, [string] $id, [datetime] $day) {
    if (-not (Test-Path -LiteralPath $path)) { Warn "нет $path"; return }
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    $nl = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $mark = '## [Не выпущено]'
    $at = $text.IndexOf($mark)
    if ($at -lt 0) { Warn "в CHANGELOG.md нет раздела «[Не выпущено]» - раздел выпуска не записан"; return }
    $from = $at + $mark.Length
    $next = $text.IndexOf("$nl## ", $from)
    if ($next -lt 0) { $next = $text.Length }
    $body = $text.Substring($from, $next - $from)
    if (-not $body.Trim()) { Warn 'в CHANGELOG.md под «[Не выпущено]» пусто - раздел выпуска не записан'; return }
    $months = 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    $title = '## {0} — {1} {2} {3}' -f $id, $day.Day, $months[$day.Month - 1], $day.Year
    $text = $text.Substring(0, $at) + $mark + $nl + $nl + $title + $nl + $body.TrimStart("`r", "`n") + $text.Substring($next)
    [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $true))
    Ok "CHANGELOG.md: раздел «$title» - закоммитьте его вместе с notes"
}

# «Что нового» по-русски из раздела «[Не выпущено]» CHANGELOG.md: пункты «- » становятся «— », заголовки ### уходят.
# Выпуски 27.09-5..28.09-3 ушли без описания, потому что notes\next.ru.txt никто не написал (R-130)
function Get-UnreleasedNotes([string] $path) {
    if (-not (Test-Path -LiteralPath $path)) { return '' }
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    $nl = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $mark = '## [Не выпущено]'
    $at = $text.IndexOf($mark)
    if ($at -lt 0) { return '' }
    $from = $at + $mark.Length
    $next = $text.IndexOf("$nl## ", $from)
    if ($next -lt 0) { $next = $text.Length }
    return Format-Notes $text.Substring($from, $next - $from)
}

function Format-Notes([string] $body) {
    $lines = foreach ($l in $body -split "`r?`n") {
        $l = $l.TrimEnd()
        if ($l -match '^\s*- (.+)$') { '— ' + $Matches[1] }
        elseif ($l -and $l -notmatch '^#') { $l }
    }
    return (@($lines) -join "`r`n").Trim()
}

# Стейдж с заранее подготовленным «Что нового» - notes\stage.ru.txt и stage.en.txt (пункты «- », по-русски можно ###).
# Нужен, когда в собранный стейдж вошла только часть накопленного в CHANGELOG: текст берётся только из этих файлов,
# а после выпуска из «[Не выпущено]» и notes\next.*.txt уходят ровно выпущенные пункты, остальное ждёт следующего
function Get-NoteItems([string] $path) {
    foreach ($l in [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) -split "`r?`n") {
        if ($l.TrimEnd() -match '^\s*- (.+)$') { $Matches[1] }
    }
}

# есть ли notes\stage.*.txt и годны ли они: только выпуск без сборки, оба языка, пунктов поровну и не ноль
function Test-StageNotes([string] $stageRu, [string] $stageEn, [bool] $noBuild) {
    if (-not ((Test-Path -LiteralPath $stageRu) -or (Test-Path -LiteralPath $stageEn))) { return $false }
    if (-not $noBuild) { throw 'есть notes\stage.*.txt - «Что нового» уже собранного стейджа; выпускайте с nobuild, а для новой сборки уберите их' }
    if (-not ((Test-Path -LiteralPath $stageRu) -and (Test-Path -LiteralPath $stageEn))) { throw 'нужны оба файла: notes\stage.ru.txt и notes\stage.en.txt' }
    $nRu = @(Get-NoteItems $stageRu).Count
    $nEn = @(Get-NoteItems $stageEn).Count
    if (-not $nRu -or $nRu -ne $nEn) { throw "в notes\stage.ru.txt $nRu пункт(ов), в stage.en.txt $nEn - нужно поровну и не ноль" }
    Ok "«Что нового» готового стейджа: notes\stage.*.txt, $nRu пункт(ов)"
    return $true
}

# убрать из списка строк пункты «- », выпущенные сейчас, и заголовки ###, под которыми не осталось пунктов
function Remove-Items([string[]] $lines, [string[]] $items) {
    $kept = @($lines | Where-Object { -not ($_.TrimEnd() -match '^\s*- (.+)$' -and $items -contains $Matches[1]) })
    for ($i = 0; $i -lt $kept.Count; $i++) {
        if ($kept[$i] -notmatch '^###') { $kept[$i]; continue }
        $j = $i + 1
        while ($j -lt $kept.Count -and $kept[$j] -notmatch '^#' -and $kept[$j] -notmatch '^\s*- ') { $j++ }
        if ($j -lt $kept.Count -and $kept[$j] -match '^\s*- ') { $kept[$i] }
    }
}

# notes\next.<язык>.txt: выпущенные пункты уходят, остальные строки и кодировка файла прежние
function Remove-NextItems([string] $path, [string[]] $items) {
    if (-not (Test-Path -LiteralPath $path)) { return }
    $bytes = [IO.File]::ReadAllBytes($path)
    $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    $nl = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $before = @($text.TrimEnd() -split "`r?`n")
    $after = @(Remove-Items $before $items)
    [IO.File]::WriteAllText($path, (($after -join $nl).TrimEnd() + $nl), (New-Object Text.UTF8Encoding $bom))
    Ok ("{0}: выпущено {1}, осталось {2} пункт(ов)" -f (Split-Path -Leaf $path), ($before.Count - $after.Count), @($after | Where-Object { $_ -match '^\s*- ' }).Count)
}

# CHANGELOG.md для такого выпуска: раздел выпуска - текст notes\stage.ru.txt, из «[Не выпущено]» уходят только его пункты
function Close-StageChangelog([string] $path, [string] $id, [datetime] $day, [string] $stageRu) {
    if (-not (Test-Path -LiteralPath $path)) { Warn "нет $path"; return }
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    $nl = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $mark = '## [Не выпущено]'
    $at = $text.IndexOf($mark)
    if ($at -lt 0) { Warn "в CHANGELOG.md нет раздела «[Не выпущено]» - раздел выпуска не записан"; return }
    $from = $at + $mark.Length
    $next = $text.IndexOf("$nl## ", $from)
    if ($next -lt 0) { $next = $text.Length }
    $items = @(Get-NoteItems $stageRu)
    $body = @($text.Substring($from, $next - $from).Trim("`r", "`n") -split "`r?`n" | Where-Object { $_ })
    $left = @(Remove-Items $body $items)
    $published = @([IO.File]::ReadAllText($stageRu, [Text.Encoding]::UTF8).Trim() -split "`r?`n" | Where-Object { $_.Trim() })
    $months = 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    $title = '## {0} — {1} {2} {3}' -f $id, $day.Day, $months[$day.Month - 1], $day.Year
    $head = $mark + $nl + $(if ($left) { ($left -join $nl) + $nl }) + $nl + $title + $nl + ($published -join $nl) + $nl
    $text = $text.Substring(0, $at) + $head + $text.Substring($next)
    [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $true))
    $was = @($body | Where-Object { $_ -match '^\s*- ' }).Count
    $now = @($left | Where-Object { $_ -match '^\s*- ' }).Count
    Ok ("CHANGELOG.md: раздел «{0}» из notes\stage.ru.txt ({1} пункт(ов), из них {2} сняты с «[Не выпущено]»); под «[Не выпущено]» осталось {3}" -f
        $title, $items.Count, ($was - $now), $now)
}

# sha256 содержимого с концами строк LF: рабочее дерево с autocrlf даёт CRLF, коммит - LF (R-252)
function Get-LfSha([string] $path) {
    $latin = [Text.Encoding]::GetEncoding(28591)
    $bytes = $latin.GetBytes($latin.GetString([IO.File]::ReadAllBytes($path)).Replace("`r`n", "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace '-', '').ToLowerInvariant() } finally { $sha.Dispose() }
}

# Грабли R-336: строка кода стенда ИИ (OXCE_AI_DEV) в exe - первая найденная, или пусто; та же, что ищет build.ps1
function Get-BenchMark([string] $exe) {
    $s = [Text.Encoding]::GetEncoding(28591).GetString([IO.File]::ReadAllBytes($exe))
    foreach ($m in @('OXCE-AI-DEV-BUILD-MARK', '[AIPROBE] start', '[COLLAPSE] debug')) { if ($s.Contains($m)) { return $m } }
    return ''
}

# Грабли R-044: с nobuild стейдж мог быть собран до последней правки движка. Выдаёт файлы исходников
# и сборки (src, cmake, корневой CMakeLists.txt), изменённые позже exe стейджа. Отбор явный по имени и
# расширению: в Windows PowerShell 5.1 -Include при -LiteralPath молча не действует, и прежняя проверка
# брала любой файл src (txt, png) и CMakeLists.txt без разбора. Файл из $allow (Path, Sha - Get-LfSha содержимого, Exe - sha256 exe) не
# выдаётся, только если совпали и содержимое, и сам exe: допуск дан одному стейджу, а не правке навсегда.
function Get-StaleBuildFiles([string] $root, [string] $exe, [object[]] $allow) {
    $exts = @('.cpp', '.cc', '.c', '.h', '.hpp', '.inl', '.rc', '.cmake')
    $root = [IO.Path]::GetFullPath($root).TrimEnd('\', '/')
    $exeTime = (Get-Item -LiteralPath $exe).LastWriteTime
    $files = @()
    foreach ($d in 'src', 'cmake') {
        $p = Join-Path $root $d
        if (Test-Path -LiteralPath $p) { $files += @(Get-ChildItem -LiteralPath $p -Recurse -File) }
    }
    $top = Join-Path $root 'CMakeLists.txt'
    if (Test-Path -LiteralPath $top) { $files += @(Get-Item -LiteralPath $top) }
    $exeSha = $null
    foreach ($f in $files) {
        if (-not ($f.Name -eq 'CMakeLists.txt' -or $exts -contains $f.Extension.ToLowerInvariant())) { continue }
        if ($f.LastWriteTime -le $exeTime) { continue }
        $rel = $f.FullName.Substring($root.Length + 1).Replace('\', '/')
        $ok = $false
        foreach ($a in @($allow)) {
            if ($null -eq $a -or $a.Path -ne $rel) { continue }
            if ($null -eq $exeSha) { $exeSha = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() }
            if ($a.Exe -eq $exeSha -and $a.Sha -eq (Get-LfSha $f.FullName)) { $ok = $true; break }
        }
        if (-not $ok) { $f }
    }
}

# Допуски Get-StaleBuildFiles: правки сборки новее exe, проверенные для КОНКРЕТНОГО стейджа
function Get-FreshAllow {
    # 7dfcce560 (R-279): OBJECT_DEPENDS для OpenXcom.rc - только пересборка ресурса версии, код игры тот же;
    # стейдж BR 07.10 23:05 (код 63a1ba623), допуск - решение 08.10
    @{ Path = 'src/CMakeLists.txt'; Sha = 'aea51c29abdfb58dd58a9a98c30b63eddca54f33a2ec9636e099f45f5fdb21ab'
       Exe = 'a3ad1147b0ac44339f7d3b6d85fe2d22f6e0c7baf3c633194c8485239db2dbc8' }
}

function Xpr([string[]] $a) {
    & $script:xpr @a | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "xp-release $($a[0]) завершился с кодом $LASTEXITCODE" }
}

# другой файл настроек (для пробы на одноразовом ключе): любой аргумент, кончающийся на .json
$args_ = @($Rest | Where-Object { $_ })
$cfgFile = $args_ | Where-Object { $_ -like '*.json' } | Select-Object -Last 1
if (-not $cfgFile) { $cfgFile = Join-Path $PSScriptRoot 'release_config.json' }
$cfg = Get-Content -LiteralPath $cfgFile -Raw -Encoding UTF8 | ConvertFrom-Json
# пути в настройках могут быть от корня репозитория (ключи и хранилище на своём диске - полными)
foreach ($key in 'Key', 'Pub', 'Repo', 'XpRelease', 'Stage', 'LauncherDir', 'StationDrop') {
    $v = $cfg.$key
    if ($v -is [string] -and $v -ne '' -and -not [IO.Path]::IsPathRooted($v)) { $cfg.$key = Join-Path $root $v }
}
$channel = $cfg.Channel
$noBuild = $false
$launcherOnly = $false
foreach ($a in $args_ | Where-Object { $_ -notlike '*.json' }) {
    if ($a -ieq 'nobuild') { $noBuild = $true }
    elseif ($a -ieq 'launcher') { $launcherOnly = $true }
    else { $channel = $a.ToLowerInvariant() }
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
    Step "Выпуск в канал $channel$(if ($launcherOnly) { ' (только лаунчер)' } elseif ($noBuild) { ' (без сборки)' })"
    if (-not (Test-Path -LiteralPath $cfg.Key)) { throw "нет приватного ключа $($cfg.Key) - подключите диск с ключом" }
    if (-not (Test-Path -LiteralPath $cfg.Pub)) { throw "нет открытого ключа $($cfg.Pub)" }
    New-Item -ItemType Directory -Force -Path $repo | Out-Null

    # ---- «Что нового» готового стейджа (notes\stage.*.txt): только для выпуска без сборки, оба языка, пунктов поровну
    $stageRu = Join-Path $notes 'stage.ru.txt'
    $stageEn = Join-Path $notes 'stage.en.txt'
    $stageNotes = -not $launcherOnly -and (Test-StageNotes $stageRu $stageEn $noBuild)

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

    # ---- только лаунчер: публикация на prod-ключах в dist\_launcher_rel, игра не собирается и не выпускается
    if ($launcherOnly -and -not $noBuild) {
        Step 'Публикую лаунчер (portal\publish.ps1, prod-ключи)'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'portal\publish.ps1') -Out $cfg.LauncherDir
        if ($LASTEXITCODE -ne 0) { throw "publish.ps1 завершился с кодом $LASTEXITCODE" }
        # та же пометка, что пишет build.ps1: следующая сборка «Обе» не станет публиковать лаунчер заново
        $work = Join-Path $dist '_work'
        New-Item -ItemType Directory -Force -Path $work | Out-Null
        [IO.File]::WriteAllText((Join-Path $work 'launcher_keys_mode.txt'), 'prod', (New-Object Text.UTF8Encoding $false))
    }

    # ---- сборка «Обе»: exe, моды, лаунчер -> dist\_stage и dist\_launcher_rel
    if (-not $noBuild -and -not $launcherOnly) {
        # -StageOnly: выпуску нужен только стейдж; full.zip на 3.8 ГБ - это «большой архив», его без надобности не собирать
        Step 'Сборка «Обе» (tools\build\build.ps1 -Target Both -StageOnly)'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools\build\build.ps1') -Target Both -StageOnly
        if ($LASTEXITCODE -ne 0) { throw "сборка не удалась (код $LASTEXITCODE) - смотрите её вывод выше" }
    }
    if (-not $launcherOnly) {
        $launchExe = Join-Path $cfg.Stage $cfg.Launch
        if (-not (Test-Path -LiteralPath $launchExe)) { throw "в $($cfg.Stage) нет $($cfg.Launch) - нужна сборка «Обе»" }
        Ok ("стейдж от {0:dd.MM HH:mm}" -f (Get-Item -LiteralPath $launchExe).LastWriteTime)
        # грабли R-044: с nobuild стейдж мог быть собран до последней правки движка
        $stale = @(Get-StaleBuildFiles $root $launchExe @(Get-FreshAllow) | Sort-Object LastWriteTime -Descending)
        if ($stale.Count) {
            $list = ($stale | Select-Object -First 5 | ForEach-Object { '{0} ({1:dd.MM HH:mm})' -f $_.FullName.Substring($root.Length + 1), $_.LastWriteTime }) -join ', '
            throw ("exe в стейдже старше исходников или сборки: {0} файл(ов) новее exe - {1}. Выпуск без сборки выложил бы игру без этой правки - запустите без nobuild" -f $stale.Count, $list)
        }
        Ok 'исходники и сборка не новее exe (допуски: только проверенные правки этого стейджа)'
        # грабли R-336: exe, собранный со стендом ИИ (OXCE_AI_DEV), игрокам не выпускать - и с nobuild тоже
        $bench = Get-BenchMark $launchExe
        if ($bench) { throw "в $launchExe код стенда ИИ (строка '$bench') - собран с OXCE_AI_DEV, игрокам нельзя. Пересоберите без nobuild: build.ps1 перенастроит OXCE_AI_DEV=OFF" }
        Ok 'в exe нет кода стенда ИИ'

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
        if ($stageNotes) {
            # готовый стейдж: CHANGELOG и next.* не читаются и до публикации не меняются
            $work = Join-Path $dist '_work'
            New-Item -ItemType Directory -Force -Path $work | Out-Null
            $ruOut = Join-Path $work "notes_$id.ru.txt"
            $enOut = Join-Path $work "notes_$id.en.txt"
            [IO.File]::WriteAllText($ruOut, (Format-Notes ([IO.File]::ReadAllText($stageRu, [Text.Encoding]::UTF8))) + "`r`n", (New-Object Text.UTF8Encoding $true))
            Copy-Item -LiteralPath $stageEn -Destination $enOut -Force
            $buildArgs += @('--changelog-ru', $ruOut, '--changelog-en', $enOut)
            $usedNotes = @($ruOut, $enOut)
            Ok '«Что нового» из notes\stage.ru.txt и stage.en.txt; CHANGELOG и next.* не читаются'
        } else {
        # русское «Что нового» = notes\next.ru.txt (то, чего нет в CHANGELOG) + раздел «[Не выпущено]» CHANGELOG.md.
        # Английское - только notes\next.en.txt; без него лаунчер покажет русское
        $fromLog = Get-UnreleasedNotes (Join-Path $root 'CHANGELOG.md')
        if ($fromLog) {
            $ruFile = Join-Path $notes 'next.ru.txt'
            $hand = if (Test-Path -LiteralPath $ruFile) { (Get-Content -LiteralPath $ruFile -Raw -Encoding UTF8).Trim() } else { '' }
            $ru = if ($hand) { $hand + "`r`n" + $fromLog } else { $fromLog }
            [IO.File]::WriteAllText($ruFile, $ru + "`r`n", (New-Object Text.UTF8Encoding $true))
            Ok ("«Что нового» из CHANGELOG: {0} пункт(ов){1}" -f @($fromLog -split "`r`n" | Where-Object { $_ -like '— *' }).Count, $(if ($hand) { ' + notes\next.ru.txt' } else { '' }))
        }
        if (-not (Test-Path -LiteralPath (Join-Path $notes 'next.en.txt'))) { Warn 'нет notes\next.en.txt - английским игрокам лаунчер покажет русское «Что нового»' }
        foreach ($lang in 'ru', 'en') {
            $f = Join-Path $notes "next.$lang.txt"
            if ((Test-Path -LiteralPath $f) -and (Get-Content -LiteralPath $f -Raw -Encoding UTF8).Trim()) {
                $buildArgs += @("--changelog-$lang", $f); $usedNotes += $f
            }
        }
        if (-not $usedNotes) { Warn 'нет notes\next.ru.txt - выпуск уйдёт без «Что нового»' }
        }
        # лаунчер, без которого выпуск не ставится (MinLauncher в настройках выпуска). hd_core у игрока включает только
        # миграция лаунчера 0.3.7 (HdCoreMigration): стейдж с ним без такого требования не выпускается
        $minLauncher = if ($cfg.PSObject.Properties.Name -contains 'MinLauncher') { [string]$cfg.MinLauncher } else { '' }
        if ((Test-Path -LiteralPath (Join-Path $cfg.Stage 'user\mods\hd_core')) -and
            (-not $minLauncher -or [version]$minLauncher -lt [version]'0.3.7')) {
            throw "в стейдже user\mods\hd_core, а MinLauncher '$minLauncher' ниже 0.3.7: игрок получил бы шрифты без миграции, которая их включает"
        }
        # мод и профиль едут вместе (tools\compat\hd_core_switch.py): профиль без мода или мод без профиля - полпереключения
        $stageProfiles = Join-Path $cfg.Stage 'xp-profiles.json'
        $coreInStage = Test-Path -LiteralPath (Join-Path $cfg.Stage 'user\mods\hd_core')
        $coreInProfile = (Test-Path -LiteralPath $stageProfiles) -and ((Get-Content -LiteralPath $stageProfiles -Raw -Encoding UTF8) -match '"id":\s*"hd_core"')
        if ($coreInStage -ne $coreInProfile) {
            throw "hd_core в стейдже: $coreInStage, в его xp-profiles.json: $coreInProfile - переключение сделано наполовину (tools\compat\hd_core_switch.py)"
        }
        if ($minLauncher) {
            $ownExe = Join-Path $cfg.LauncherDir 'XPiratezLauncher.exe'
            $own = if (Test-Path -LiteralPath $ownExe) { ((Get-Item -LiteralPath $ownExe).VersionInfo.ProductVersion -split '\+')[0] } else { '0.0.0' }
            if ([version]$own -lt [version]$minLauncher) { throw "выпуск требует лаунчер $minLauncher, а публикуется $own - игроку нечем было бы его поставить" }
            $buildArgs += @('--min-launcher', $minLauncher)
            Ok "требует лаунчер не ниже $minLauncher"
        }
        Xpr $buildArgs
        Xpr @('publish', '--repo', $repo, '--channel', $channel, '--id', $id, '--key', $cfg.Key)
        # история обновлений канала (её publish уже переписал) - теперь с дорожной картой из roadmap.<язык>.md:
        # вкладка «Обновления» лаунчера и страницы /releases и /roadmap сайта читают один подписанный файл
        $notesArgs = @('notes', '--repo', $repo, '--channel', $channel, '--key', $cfg.Key)
        foreach ($lang in 'ru', 'en') {
            $rm = Join-Path $PSScriptRoot "roadmap.$lang.md"
            if (Test-Path -LiteralPath $rm) { $notesArgs += @("--roadmap-$lang", $rm) } else { Warn "нет roadmap.$lang.md - в канале останется прежняя дорожная карта" }
        }
        Xpr $notesArgs
        foreach ($f in $usedNotes) {
            $lang = [IO.Path]::GetFileNameWithoutExtension($f).Split('.')[-1]
            Move-Item -LiteralPath $f -Destination (Join-Path $notes "$id.$lang.txt") -Force
        }
        if ($stageNotes) {
            if ($channel -eq 'stable') {
                Close-StageChangelog (Join-Path $root 'CHANGELOG.md') $id $today $stageRu
                Remove-NextItems (Join-Path $notes 'next.ru.txt') @(Get-NoteItems $stageRu)
                Remove-NextItems (Join-Path $notes 'next.en.txt') @(Get-NoteItems $stageEn)
            }
            Remove-Item -LiteralPath $stageRu, $stageEn
        }
        elseif ($channel -eq 'stable') { Close-Changelog (Join-Path $root 'CHANGELOG.md') $id $today }
    }

    # ---- лаунчер: только новая версия
    $launcherExe = Join-Path $cfg.LauncherDir 'XPiratezLauncher.exe'
    if (-not (Test-Path -LiteralPath $launcherExe)) { throw "нет $launcherExe - сборка «Обе» его не положила" }
    $lv = ((Get-Item -LiteralPath $launcherExe).VersionInfo.ProductVersion -split '\+')[0]
    $lid = if ($channel -eq 'stable') { "launcher-$lv" } else { "launcher-$lv-$channel" }
    $ptrFile = Join-Path $repo "channels\$launcherChannel.json"
    $current = if (Test-Path -LiteralPath $ptrFile) { (Get-Content -LiteralPath $ptrFile -Raw | ConvertFrom-Json).releaseId }
    if ($launcherOnly) { $id = $lid }
    $newLauncher = $current -ne $lid
    if ($current -eq $lid) {
        if ($launcherOnly) { throw "лаунчер $lv уже в канале $launcherChannel - поднимите <Version> в Xp.Launcher.csproj" }
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

    # ---- новый лаунчер в stable - установщик на страницу mod.io (tools/modio_publish.py); сбой выпуск не отменяет
    if ($newLauncher -and $channel -eq 'stable') {
        Step "Выкладываю лаунчер $lv на mod.io"
        $modioArgs = @((Join-Path $root 'tools\modio_publish.py'), '--repo', $repo, '--channel', $launcherChannel)
        $enNotes = @((Join-Path $notes "$id.en.txt"), (Join-Path $notes 'next.en.txt')) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if ($enNotes) { $modioArgs += @('--changelog', $enNotes) }
        if ($cfg.PSObject.Properties.Name -contains 'ModioMod' -and $cfg.ModioMod) { $modioArgs += @('--mod', [string]$cfg.ModioMod) }
        if (-not (Get-Command py -ErrorAction SilentlyContinue)) { Warn 'нет py - mod.io пропущен: py -3.13 tools\modio_publish.py' }
        else {
            & py -3.13 @modioArgs | Out-Host
            if ($LASTEXITCODE -eq 2) { Warn 'нет токена mod.io (%USERPROFILE%\.modio_token) - не выложено' }
            elseif ($LASTEXITCODE -ne 0) { Warn "mod.io: код $LASTEXITCODE - выпуск цел, повторить: py -3.13 tools\modio_publish.py" }
        }
    }

    # ---- исходники движка этого выпуска на GitHub (GPL): метка hd-<выпуск> на HEAD сборки и ветка hd-render; сбой выпуск не отменяет
    if (-not $launcherOnly -and $channel -eq 'stable') {
        Step "Исходники на GitHub: метка hd-$id"
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Warn "нет git - не выложено: git tag -a hd-$id; git push origin hd-render hd-$id" }
        else {
            $ea = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            $branch = (& git -C $root rev-parse --abbrev-ref HEAD 2>$null | Out-String).Trim()
            $dirty = @(& git -C $root status --porcelain -- src CMakeLists.txt cmake libs deps 2>$null)
            if ($branch -ne 'hd-render') { Warn "ветка $branch, а не hd-render - исходники не выложены" }
            else {
                if ($dirty.Count) { Warn "в src/CMake $($dirty.Count) незакоммиченных файлов - exe собран не ровно из метки (R-322)" }
                & git -C $root rev-parse -q --verify "refs/tags/hd-$id" *> $null
                # git пишет ход отправки в stderr - строками, иначе PowerShell 5 рисует его красным как NativeCommandError
                if ($LASTEXITCODE -ne 0) { & git -C $root tag -a "hd-$id" -m "OXCE-HD release $id (source of the binaries shipped to players)" 2>&1 | ForEach-Object { "    $_" } | Out-Host }
                & git -C $root push origin hd-render "hd-$id" 2>&1 | ForEach-Object { "    $_" } | Out-Host
                if ($LASTEXITCODE -eq 0) { Ok "https://github.com/vlourie/OpenXcom/tree/hd-$id" }
                else { Warn "git push: код $LASTEXITCODE - выпуск цел, повторить: git push origin hd-render hd-$id" }
            }
            $ErrorActionPreference = $ea
        }
    }

    Write-Host ''
    Write-Host ("ГОТОВО за {0:hh\:mm\:ss}: {1} в канале {2}" -f $clock.Elapsed, $id, $(if ($launcherOnly) { $launcherChannel } else { $channel })) -ForegroundColor Green
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
