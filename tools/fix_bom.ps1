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
    [switch]$Fix
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
