<#
    Снимок окна своей программы в файл — для приёмки вёрстки лаунчера глазами.

    Окно рисует себя само (PrintWindow с PW_RENDERFULLCONTENT), поэтому в кадр не попадает
    ничего чужого, что лежит поверх, и окно не надо выводить на передний план.

    Грабли R-059: без объявления DPI-aware GetWindowRect отдаёт размер, поделённый на масштаб
    экрана, и в кадр влезает четверть окна. Поэтому скрипт печатает оба размера рядом.

    Пример:
        powershell -ExecutionPolicy Bypass -File tools\shot_window.ps1 `
            -Exe portal\src\Xp.Launcher\bin\Debug\net10.0\XPiratezLauncher.exe `
            -Arguments "--page","review" -Out shot.png
#>
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [string[]]$Arguments = @(),
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$WaitSeconds = 10,
    [double]$Scale = 0.5
)
$ErrorActionPreference = "Stop"
# powershell -File массивов не понимает: -Arguments "--page","review" приходит ОДНОЙ строкой
# "--page,review", программа получает один непонятный ключ и молча его не видит (грабли R-045)
$Arguments = @($Arguments | ForEach-Object { $_ -split '[,\s]+' } | Where-Object { $_ })
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct RECT { public int Left, Top, Right, Bottom; }
public static class ShotWin {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
}
"@
# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2; на старых системах — грубое SetProcessDPIAware
try { [void][ShotWin]::SetProcessDpiAwarenessContext([IntPtr](-4)) } catch { [void][ShotWin]::SetProcessDPIAware() }

if (-not (Test-Path $Exe)) { throw "нет программы: $Exe" }
$p = if ($Arguments.Count -gt 0) { Start-Process $Exe -ArgumentList $Arguments -PassThru }
     else { Start-Process $Exe -PassThru }
try {
    Start-Sleep -Seconds $WaitSeconds
    $p.Refresh()
    if ($p.HasExited) { throw "программа вышла с кодом $($p.ExitCode)" }
    $h = $p.MainWindowHandle
    if ($h -eq [IntPtr]::Zero) { throw "окна нет" }

    $r = New-Object RECT
    [void][ShotWin]::GetWindowRect($h, [ref]$r)
    $w = $r.Right - $r.Left
    $hh = $r.Bottom - $r.Top
    $bmp = New-Object System.Drawing.Bitmap $w, $hh
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $dc = $g.GetHdc()
    $ok = [ShotWin]::PrintWindow($h, $dc, 2)
    $g.ReleaseHdc($dc)
    $g.Dispose()
    if (-not $ok) { throw "PrintWindow отказал" }

    if ($Scale -ne 1.0) {
        $sw = [int]($w * $Scale)
        $sh = [int]($hh * $Scale)
        $small = New-Object System.Drawing.Bitmap $sw, $sh
        $sg = [System.Drawing.Graphics]::FromImage($small)
        $sg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $sg.DrawImage($bmp, 0, 0, $sw, $sh)
        $sg.Dispose()
        $small.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
        $small.Dispose()
        Write-Output "снято $Out ($sw x $sh из окна $w x $hh)"
    }
    else {
        $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
        Write-Output "снято $Out (окно $w x $hh)"
    }
    $bmp.Dispose()
}
finally {
    if (-not $p.HasExited) { $p.Kill(); $p.WaitForExit(3000) }
}
