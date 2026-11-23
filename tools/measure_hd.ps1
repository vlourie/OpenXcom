<#
    Замер HD-рендера: запускает свежесобранную игру против установки Пираток
    (ничего в неё не копируя) и раз в N секунд пишет память процесса в CSV.

    Игра пишет в лог строки "HD perf: ..." — размеры кэшей раз в 2 секунды
    и отдельную строку в момент обрыва кэша сглаживания.

    Использование:
        powershell -NoProfile -ExecutionPolicy Bypass -File tools\measure_hd.ps1
#>
[CmdletBinding()]
param(
    [int]$IntervalSec = 2,
    [string]$Exe  = "",
    [string]$Data = "",
    [string]$User = "",
    [string]$Out  = ""
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

# --- пути по умолчанию ---------------------------------------------------
if (-not $Exe)  { $Exe  = Join-Path $repo 'build-release\bin\openxcom.exe' }
if (-not $Data) { $Data = Join-Path $repo 'Пиратки\Dioxine_XPiratez' }
if (-not $User) { $User = Join-Path $Data 'user' }
if (-not $Out)  {
    $stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
    $Out = Join-Path $repo ("docs\QA\hd_mem_$stamp.csv")
}

# --- проверки (грабли R-002: ничего не считаем найденным заранее) --------
foreach ($pair in @(@{n='exe'; p=$Exe}, @{n='данные'; p=$Data}, @{n='папка user'; p=$User})) {
    if (-not (Test-Path -LiteralPath $pair.p)) {
        Write-Error ("Не найдено ({0}): {1}" -f $pair.n, $pair.p)
    }
}

# DLL тулчейна: свежий exe собран MinGW и без них не стартует
$cfgPath = Join-Path $PSScriptRoot 'build\build_config.json'
$msysBin = 'C:\msys64\mingw64\bin'
if (Test-Path -LiteralPath $cfgPath) {
    $cfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cfg.MsysBin) { $msysBin = $cfg.MsysBin }
}
if (Test-Path -LiteralPath $msysBin) {
    $env:Path = "$msysBin;$env:Path"
} else {
    Write-Warning "Папка тулчейна не найдена: $msysBin - exe может не запуститься"
}

$outDir = Split-Path -Parent $Out
if (-not (Test-Path -LiteralPath $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

$logPath = Join-Path $User 'openxcom.log'
$started = Get-Date

Write-Host ""
Write-Host "  exe   : $Exe"
Write-Host "  данные: $Data"
Write-Host "  user  : $User"
Write-Host "  CSV   : $Out"
Write-Host "  лог   : $logPath"
Write-Host ""
Write-Host "  Запускаю. Зайди в бой, поиграй до просадки, жми F8 в моменты тормозов." -ForegroundColor Cyan
Write-Host "  Замер остановится сам, когда закроешь игру." -ForegroundColor Cyan
Write-Host ""

$exeArgs = @('-data', $Data, '-user', $User)
$proc = Start-Process -FilePath $Exe -ArgumentList $exeArgs -WorkingDirectory $Data -PassThru

'sec,working_set_mb,private_mb,cpu_sec,threads,handles' |
    Out-File -LiteralPath $Out -Encoding UTF8

$peakWs = 0
$peakPriv = 0
while (-not $proc.HasExited) {
    Start-Sleep -Seconds $IntervalSec
    try {
        $p = Get-Process -Id $proc.Id -ErrorAction Stop
        $ws   = [int]($p.WorkingSet64 / 1MB)
        $priv = [int]($p.PrivateMemorySize64 / 1MB)
        if ($ws   -gt $peakWs)   { $peakWs   = $ws }
        if ($priv -gt $peakPriv) { $peakPriv = $priv }
        $sec = [int]((Get-Date) - $started).TotalSeconds
        ('{0},{1},{2},{3},{4},{5}' -f $sec, $ws, $priv, [int]$p.CPU, $p.Threads.Count, $p.HandleCount) |
            Out-File -LiteralPath $Out -Encoding UTF8 -Append
        Write-Host ("  {0,5} с   {1,6} МБ рабочий набор   {2,6} МБ приватной" -f $sec, $ws, $priv)
    } catch {
        break
    }
}

$dur = [int]((Get-Date) - $started).TotalSeconds
Write-Host ""
Write-Host "  Готово. $dur с, пик: $peakWs МБ рабочий набор / $peakPriv МБ приватной" -ForegroundColor Green
Write-Host "  CSV: $Out"
Write-Host ""

# строки HD perf из лога этого запуска
if (Test-Path -LiteralPath $logPath) {
    $perf = Get-Content -LiteralPath $logPath -Encoding UTF8 | Where-Object { $_ -match 'HD perf' }
    $drops = @($perf | Where-Object { $_ -match 'smooth cache dropped' })
    Write-Host ("  строк 'HD perf' в логе: {0}, из них обрывов кэша: {1}" -f $perf.Count, $drops.Count)
    $dumps = @(Get-ChildItem -LiteralPath (Join-Path $User 'piratez') -Filter 'hdtest*.json' -ErrorAction SilentlyContinue)
    Write-Host ("  дампов F8: {0}" -f $dumps.Count)
}
