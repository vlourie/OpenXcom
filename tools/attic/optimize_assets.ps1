<#
.SYNOPSIS
  Доводка сгенерированной графики до формата игры.
.DESCRIPTION
  assets/10_generated -> assets/20_optimized
  Ресайз, квантование палитры, сжатие PNG. Используется агентом asset-smith.
.EXAMPLE
  .\tools\optimize_assets.ps1 -Source assets\10_generated\raider -Size 32x40 -Colors 16
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Source,
    [string]$Dest = "assets\20_optimized",
    [string]$Size,                       # напр. 32x40
    [int]$Colors = 0,                    # 0 = не квантовать
    [ValidateSet('point','box','lanczos')][string]$Filter = 'point',
    [switch]$WhatIfOnly
)

$ErrorActionPreference = 'Stop'

function Test-Tool([string]$name) { $null -ne (Get-Command $name -ErrorAction SilentlyContinue) }

$magick  = Test-Tool 'magick'
$oxipng  = Test-Tool 'oxipng'
$pngquant= Test-Tool 'pngquant'

Write-Host "Инструменты: magick=$magick oxipng=$oxipng pngquant=$pngquant"
if (-not $magick) {
    Write-Warning "ImageMagick не найден. Установи: winget install ImageMagick.ImageMagick"
    Write-Warning "Без него ресайз и квантование недоступны."
}

if (-not (Test-Path $Source)) { throw "Нет папки: $Source" }
$leaf = Split-Path $Source -Leaf
$outDir = Join-Path $Dest $leaf
if (-not $WhatIfOnly) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }

$files = Get-ChildItem -Path $Source -Filter *.png -File
if ($files.Count -eq 0) { Write-Warning "PNG не найдены в $Source"; return }

$report = @()
foreach ($f in $files) {
    $out = Join-Path $outDir $f.Name
    $beforeKb = [math]::Round($f.Length / 1KB, 1)

    if ($WhatIfOnly) { Write-Host "[dry] $($f.Name) -> $out"; continue }

    if ($magick) {
        $mArgs = @($f.FullName)
        if ($Size)   { $mArgs += @('-filter', $Filter, '-resize', "${Size}!") }
        if ($Colors -gt 0) { $mArgs += @('-dither','None','-colors', $Colors) }
        $mArgs += $out
        & magick @mArgs
    } else {
        Copy-Item $f.FullName $out -Force
    }

    if ($pngquant -and $Colors -gt 0) {
        & pngquant --force --skip-if-larger --output $out -- $out 2>$null
    }
    if ($oxipng) { & oxipng -o 4 --strip safe -q $out 2>$null }

    $afterKb = [math]::Round((Get-Item $out).Length / 1KB, 1)
    $report += [pscustomobject]@{ Файл = $f.Name; 'До,КБ' = $beforeKb; 'После,КБ' = $afterKb }
}

if ($report.Count -gt 0) {
    $report | Format-Table -AutoSize
    $sumBefore = ($report | Measure-Object 'До,КБ' -Sum).Sum
    $sumAfter  = ($report | Measure-Object 'После,КБ' -Sum).Sum
    Write-Host ("Итого: {0} КБ -> {1} КБ" -f $sumBefore, $sumAfter)
    Write-Host "Результат: $outDir  (в 30_final переносит asset-smith после чек-листа)"
}
