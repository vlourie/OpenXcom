<#
.SYNOPSIS
  Ставит локальный инструментарий для работы агентов: индексация, графика, LLM.
.DESCRIPTION
  Запускать один раз на машине. Ничего не ломает: что уже стоит — пропускает,
  что не встало — перечисляет в конце со ссылками.
.EXAMPLE
  .\tools\setup_workstation.ps1
  .\tools\setup_workstation.ps1 -SkipModel      # без скачивания 18 ГБ модели
  .\tools\setup_workstation.ps1 -WhatIfOnly     # только показать, что будет сделано
#>
[CmdletBinding()]
param(
    [switch]$SkipModel,
    [switch]$SkipGraphics,
    [switch]$WhatIfOnly
)

$ErrorActionPreference = 'Continue'

function Have([string]$exe) { $null -ne (Get-Command $exe -ErrorAction SilentlyContinue) }

$failed = @()

function Install-Pkg {
    param([string]$Id, [string]$Exe, [string]$Why, [string]$Manual)
    if ($Exe -and (Have $Exe)) {
        Write-Host ("  [есть]     {0,-28} {1}" -f $Exe, $Why) -ForegroundColor DarkGray
        return
    }
    Write-Host ("  [ставлю]   {0,-28} {1}" -f $Id, $Why) -ForegroundColor Cyan
    if ($WhatIfOnly) { return }
    winget install --id $Id --accept-package-agreements --accept-source-agreements --silent 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $script:failed += [pscustomobject]@{ Пакет = $Id; Зачем = $Why; Вручную = $Manual }
        Write-Warning "    не встало через winget: $Id"
    }
}

if (-not (Have 'winget')) {
    Write-Warning "winget не найден. Обнови App Installer из Microsoft Store, либо ставь всё вручную по docs/SETUP.md"
}

Write-Host "`n== Индексация кода (основа карты проекта) ==" -ForegroundColor Green
Install-Pkg -Id 'UniversalCtags.Ctags' -Exe 'ctags' -Why 'символы: где что объявлено' `
            -Manual 'https://github.com/universal-ctags/ctags-win32/releases'
Install-Pkg -Id 'LLVM.LLVM' -Exe 'clangd' -Why 'точный индекс C++ с типами' `
            -Manual 'https://github.com/llvm/llvm-project/releases'
Install-Pkg -Id 'DimitriVanHeesch.Doxygen' -Exe 'doxygen' -Why 'граф вызовов и наследования' `
            -Manual 'https://www.doxygen.nl/download.html'
Install-Pkg -Id 'Graphviz.Graphviz' -Exe 'dot' -Why 'рисует графы для doxygen' `
            -Manual 'https://graphviz.org/download/'

Write-Host "`n== База ==" -ForegroundColor Green
Install-Pkg -Id 'Python.Python.3.12' -Exe 'python' -Why 'скрипты индекса и граблей' `
            -Manual 'https://www.python.org/downloads/'
Install-Pkg -Id 'Git.Git' -Exe 'git' -Why 'версионирование' -Manual 'https://git-scm.com/download/win'

if (-not $SkipGraphics) {
    Write-Host "`n== Графика ==" -ForegroundColor Green
    Install-Pkg -Id 'ImageMagick.ImageMagick' -Exe 'magick' -Why 'ресайз, палитра, конвертация' `
                -Manual 'https://imagemagick.org/script/download.php#windows'
    Install-Pkg -Id 'Shssoichiro.Oxipng' -Exe 'oxipng' -Why 'сжатие PNG без потерь' `
                -Manual 'https://github.com/oxipng/oxipng/releases'
}

Write-Host "`n== Локальная модель ==" -ForegroundColor Green
Install-Pkg -Id 'Ollama.Ollama' -Exe 'ollama' -Why 'запуск LLM на 5090' -Manual 'https://ollama.com/download'

if (-not $SkipModel -and -not $WhatIfOnly) {
    if (Have 'ollama') {
        $model = if ($env:LOCAL_MODEL) { $env:LOCAL_MODEL } else { 'qwen3.8:27b' }
        $installed = (& ollama list 2>$null | Out-String)
        if ($installed -match [regex]::Escape($model.Split(':')[0])) {
            Write-Host "  [есть]     $model" -ForegroundColor DarkGray
        } else {
            Write-Host "  [качаю]    $model  (~18 ГБ, это надолго)" -ForegroundColor Cyan
            & ollama pull $model
        }
    } else {
        Write-Warning "ollama не установлен — модель не скачана"
    }
}

Write-Host "`n== Проверка ==" -ForegroundColor Green
$checks = @(
    @{ n = 'ctags';    why = 'символы' },
    @{ n = 'clangd';   why = 'C++ индекс' },
    @{ n = 'doxygen';  why = 'граф вызовов' },
    @{ n = 'dot';      why = 'graphviz' },
    @{ n = 'python';   why = 'скрипты' },
    @{ n = 'git';      why = 'гит' },
    @{ n = 'magick';   why = 'графика' },
    @{ n = 'oxipng';   why = 'сжатие PNG' },
    @{ n = 'ollama';   why = 'локальная модель' }
)
foreach ($c in $checks) {
    $ok = Have $c.n
    $mark = if ($ok) { 'OK ' } else { '-- ' }
    $color = if ($ok) { 'Green' } else { 'Yellow' }
    Write-Host ("  {0} {1,-12} {2}" -f $mark, $c.n, $c.why) -ForegroundColor $color
}

if ($failed.Count -gt 0) {
    Write-Host "`nНе встало через winget — поставь вручную:" -ForegroundColor Yellow
    $failed | Format-Table -AutoSize
}

Write-Host @"

Дальше:
  python tools/index_project.py              собрать карту проекта
  python tools/rake.py list                  посмотреть грабли
  python tools/describe_modules.py --check   проверить локальную модель
  python tools/gen_gpu.py --check            проверить бэкенд генерации картинок

Часть программ появляется в PATH только после перезапуска терминала.
"@ -ForegroundColor Cyan
