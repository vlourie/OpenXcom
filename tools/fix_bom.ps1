<#
.SYNOPSIS
  Проверяет и чинит кодировку PowerShell-скриптов: UTF-8 с BOM, переводы строк CRLF.

.DESCRIPTION
  Windows PowerShell 5.1 читает файл БЕЗ BOM как ANSI (на русской локали cp1251).
  Скрипт, написанный в UTF-8 и содержащий кириллицу, при этом рассыпается:
  каждая буква превращается в два-три мусорных символа, рвутся кавычки и скобки,
  и разбор падает с ParserError вида "Missing '=' operator after key in hash literal".

  Лечится только спецификацией (BOM) в начале файла. Это не косметика и не вкус:
  без BOM скрипт с кириллицей физически не запускается.

  Без -Fix ничего не меняет, печатает список проблемных файлов и возвращает код 1 —
  годится для проверки в CI или в pre-commit.

.EXAMPLE
  .\fix_bom.ps1                      проверить текущий репозиторий
  .\fix_bom.ps1 -Fix                 починить
  .\fix_bom.ps1 -Path "E:\Mods\MyMod" -Fix
#>
[CmdletBinding()]
param(
    [string]$Path = $PSScriptRoot,
    [switch]$Fix,
    [switch]$ShowReads
)

$ErrorActionPreference = 'Stop'

$Path = (Resolve-Path -LiteralPath $Path).ProviderPath.TrimEnd('\')
$exts     = @('.ps1', '.psm1', '.psd1')
$skipDirs = @('\.git\', '\.index\', '\node_modules\', '\.venv\')

$bomBytes = [byte[]](0xEF, 0xBB, 0xBF)
$utf8Bom    = New-Object System.Text.UTF8Encoding($true)
$utf8Strict = New-Object System.Text.UTF8Encoding($false, $true)

$bad = @()
$broken = @()
$fixed = 0
$seen = 0

# -Include вместе с -Recurse ведёт себя непредсказуемо, поэтому фильтруем сами.
$files = Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue |
         Where-Object { $exts -contains $_.Extension } |
         Where-Object { $p = $_.FullName; -not ($skipDirs | Where-Object { $p -like "*$_*" }) }

foreach ($f in $files) {
    $seen++
    $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
    if ($bytes.Length -eq 0) { continue }

    $hasBom = $bytes.Length -ge 3 -and
              $bytes[0] -eq $bomBytes[0] -and $bytes[1] -eq $bomBytes[1] -and $bytes[2] -eq $bomBytes[2]

    # Голый ASCII без кириллицы не ломается и без BOM, но приводим к одному виду:
    # иначе следующая правка допишет русский комментарий и файл молча сломается.
    $body = if ($hasBom) { $bytes[3..($bytes.Length - 1)] } else { $bytes }

    try { $text = $utf8Strict.GetString($body) }
    catch {
        # Не UTF-8 — скорее всего файл уже сохранён в cp1251. Автоматом не трогаем:
        # угадывание кодировки здесь испортит текст молча.
        $broken += $f.FullName
        continue
    }

    $normalized = ($text -replace "`r`n", "`n") -replace "`n", "`r`n"
    $needsFix = (-not $hasBom) -or ($normalized -ne $text)
    if (-not $needsFix) { continue }

    $why = @()
    if (-not $hasBom)            { $why += 'нет BOM' }
    if ($normalized -ne $text)   { $why += 'не CRLF' }
    $rel = $f.FullName.Substring($Path.Length).TrimStart('\', '/')

    if ($Fix) {
        [System.IO.File]::WriteAllText($f.FullName, $normalized, $utf8Bom)
        Write-Host ("  [починил] {0,-48} {1}" -f $rel, ($why -join ', ')) -ForegroundColor Green
        $fixed++
    } else {
        Write-Host ("  [плохо]   {0,-48} {1}" -f $rel, ($why -join ', ')) -ForegroundColor Yellow
        $bad += $f.FullName
    }
}

Write-Host ""
if ($broken.Count -gt 0) {
    Write-Warning "Файлы не в UTF-8 — разбери руками, автоматом не чиню:"
    $broken | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
}

# Вторая сторона тех же граблей: python пишет UTF-8 БЕЗ спецификации, и потом
# `type INDEX.md` в PowerShell 5.1 печатает мусор. Лечится encoding="utf-8-sig".
$pyBad = @()
$pyFiles = Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue |
           Where-Object { $_.Extension -eq '.py' } |
           Where-Object { $p = $_.FullName; -not ($skipDirs | Where-Object { $p -like "*$_*" }) }
foreach ($f in $pyFiles) {
    $hits = Select-String -LiteralPath $f.FullName -Pattern 'encoding\s*=\s*"utf-8"' -ErrorAction SilentlyContinue
    foreach ($h in $hits) {
        $rel = $f.FullName.Substring($Path.Length).TrimStart('\', '/')
        $line = $h.Line.Trim()
        # Запись — это то, что потом читают в PowerShell: там спецификация обязательна.
        # Чтение без -sig тише: оно ломается только на файле, у которого спецификация есть.
        $mode = if ($line -match 'write_text|["'']w["'']|["'']wt["'']|["'']w\+["'']') { 'ЗАПИСЬ' } else { 'чтение' }

        # Главное различие не в режиме, а в том, КТО потом читает файл.
        # Рулсеты и metadata мода читает игра через yaml-cpp: спецификация там
        # в лучшем случае бесполезна, в худшем ломает загрузку мода. Не трогать.
        $what = switch -Regex ($line) {
            '\.rul|\.yml|\.yaml' { 'НЕ ТРОГАТЬ: читает игра' ; break }
            '\.csv'                { 'нужна: Excel без неё врёт'; break }
            '\.json'               { 'пара: чинить и чтение'   ; break }
            '\.txt|\.md'          { 'нужна: читает человек'   ; break }
            '\.cpp|\.h\b|\.xml' { 'не нужна: читает не PowerShell'; break }
            default                { 'посмотреть глазами'      }
        }
        if ($line.Length -gt 52) { $line = $line.Substring(0, 52) + '...' }
        $pyBad += [pscustomobject]@{ Режим = $mode; Что = $what; Файл = $rel; Строка = $h.LineNumber; Код = $line }
    }
}
if ($pyBad.Count -gt 0) {
    $w = @($pyBad | Where-Object { $_.Режим -eq 'ЗАПИСЬ' })
    Write-Host ""
    if ($w.Count -gt 0) {
        Write-Warning "python пишет UTF-8 без спецификации ($($w.Count) мест) — PowerShell прочтёт такой файл как cp1251."
    }
    Write-Host "         Смотри колонку 'Что', а не только режим: файлы, которые читает ИГРА" -ForegroundColor Yellow
    Write-Host "         (.rul, .yml), со спецификацией могут перестать грузиться. Грабли R-001." -ForegroundColor Yellow
    $pyBad | Where-Object { $_.Режим -eq 'ЗАПИСЬ' } | Sort-Object Что, Файл, Строка | Format-Table -AutoSize
    $r = @($pyBad | Where-Object { $_.Режим -eq 'чтение' })
    if ($r.Count -gt 0) {
        Write-Host "  Ещё $($r.Count) мест на чтение без -sig — тише, ломается только на файле со спецификацией." -ForegroundColor DarkGray
        Write-Host "  Показать: .\fix_bom.ps1 -ShowReads" -ForegroundColor DarkGray
    }
    if ($ShowReads) { $r | Sort-Object Файл, Строка | Format-Table -AutoSize }
}

if ($Fix) {
    Write-Host "Проверено: $seen, починено: $fixed" -ForegroundColor Cyan
    if ($broken.Count -gt 0) { exit 1 }
    exit 0
}

if ($bad.Count -gt 0 -or $broken.Count -gt 0) {
    Write-Host "Проверено: $seen, с проблемами: $($bad.Count + $broken.Count). Починить: .\fix_bom.ps1 -Fix" -ForegroundColor Yellow
    exit 1
}

Write-Host "Проверено: $seen, все в UTF-8 с BOM и CRLF." -ForegroundColor Green
exit 0
