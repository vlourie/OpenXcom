<#
  OXCE HD — окно с тремя кнопками: EXE / Мод / Оба.
  Каждая кнопка запускает build.ps1 в отдельном окне консоли (там виден ход сборки;
  при ошибке окно не закрывается, пока не нажать клавишу).
  Запуск: двойной клик по OXCE_Build.cmd в корне E:\OpenXCom.
#>
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
try {
    Add-Type -Namespace OxceBuild -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
    [void][OxceBuild.Dpi]::SetProcessDPIAware()
} catch {}
[Windows.Forms.Application]::EnableVisualStyles()

# масштаб экрана (125%, 150% ...): все размеры ниже заданы для 100%
$k = 1.0
try { $g = [Drawing.Graphics]::FromHwnd([IntPtr]::Zero); $k = $g.DpiX / 96.0; $g.Dispose() } catch {}
function Px([double]$v) { return [int][Math]::Round($v * $k) }

$here        = $PSScriptRoot
$buildScript = Join-Path $here 'build.ps1'
$cfgPath     = Join-Path $here 'build_config.json'
$cfg         = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$repoDir     = if ($cfg.RepoDir) { $cfg.RepoDir } else { (Resolve-Path (Join-Path $here '..\..')).Path }
$distDir     = if ($cfg.DistDir) { $cfg.DistDir } else { Join-Path $repoDir 'dist' }
$resultFile  = Join-Path $distDir 'last_result.txt'
$patchFile   = Join-Path $distDir 'last_patch.txt'
$logFile     = Join-Path $env:TEMP 'oxce_build.log'
$errFile     = Join-Path $env:TEMP 'oxce_build_error.txt'

$script:proc       = $null
$script:lastResult = $null
$script:t0         = $null
$script:target     = ''

$green = [Drawing.Color]::FromArgb(0, 128, 0)
$red   = [Drawing.Color]::FromArgb(190, 0, 0)
$gray  = [Drawing.Color]::FromArgb(70, 70, 70)

# ---------------------------------------------------------------- окно

$form = New-Object Windows.Forms.Form
$form.AutoScaleMode   = [Windows.Forms.AutoScaleMode]::None
$form.Text            = 'OXCE HD — сборка'
$form.StartPosition   = 'CenterScreen'
$form.FormBorderStyle = 'FixedSingle'
$form.MaximizeBox     = $false
$form.Font            = New-Object Drawing.Font('Segoe UI', 9.5)
$form.ClientSize      = New-Object Drawing.Size((Px 512), (Px 236))

function Add-Control($ctrl, [double]$x, [double]$y, [double]$w, [double]$h) {
    $ctrl.Location = New-Object Drawing.Point((Px $x), (Px $y))
    $ctrl.Size = New-Object Drawing.Size((Px $w), (Px $h))
    $form.Controls.Add($ctrl)
    return $ctrl
}
function New-Button([string]$text, [double]$x, [double]$y, [double]$w, [double]$h) {
    $b = New-Object Windows.Forms.Button
    $b.Text = $text
    return (Add-Control $b $x $y $w $h)
}

$bigFont = New-Object Drawing.Font('Segoe UI', 14, [Drawing.FontStyle]::Bold)
$bExe  = New-Button 'EXE' 12  12 156 64
$bMod  = New-Button 'Мод' 178 12 156 64
$bBoth = New-Button 'Оба' 344 12 156 64
foreach ($b in $bExe, $bMod, $bBoth) { $b.Font = $bigFont }

$tip = New-Object Windows.Forms.ToolTip
$tip.SetToolTip($bExe,  'ninja → Enigma Virtual Box → dist\OpenXComEx_<дата>_<время>.exe')
$tip.SetToolTip($bMod,  'моды и данные движка → dist\OXCE-HD_…_mod.zip плюс патч изменений')
$tip.SetToolTip($bBoth, 'exe + моды + данные → dist\OXCE-HD_…_full.zip плюс патч изменений (распаковать в папку игры)')

$chk = New-Object Windows.Forms.CheckBox
$chk.Text = 'Пересобрать (ninja)'
$chk.Checked = $true
[void](Add-Control $chk 14 84 300 24)
$tip.SetToolTip($chk, 'Снять — упаковать уже собранный build-release\bin\openxcom.exe')

$lbl = New-Object Windows.Forms.Label
$lbl.AutoSize = $false
$lbl.AutoEllipsis = $true
$lbl.Text = 'Готово к сборке.'
[void](Add-Control $lbl 14 112 486 72)

$small = New-Object Drawing.Font('Segoe UI', 9)
$bOpen = New-Button 'Результат'  12  192 116 32
$bDist = New-Button 'Папка dist' 136 192 116 32
$bLog  = New-Button 'Журнал'     260 192 116 32
$bCfg  = New-Button 'Настройки'  384 192 116 32
foreach ($b in $bOpen, $bDist, $bLog, $bCfg) { $b.Font = $small }
$bOpen.Enabled = $false
$tip.SetToolTip($bOpen, 'Показать готовый файл в Проводнике')
$tip.SetToolTip($bLog,  "Журнал последнего запуска: $logFile")

# ---------------------------------------------------------------- логика

function Update-Title {
    $form.Text = 'OXCE HD — сборка'
    try {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return }
        $ErrorActionPreference = 'Continue'
        $br = @(& git -C $repoDir rev-parse --abbrev-ref HEAD 2>$null)[0]
        $h  = @(& git -C $repoDir rev-parse --short HEAD 2>$null)[0]
        if ($br) { $form.Text = "OXCE HD — сборка   ($br · $h)" }
    } catch {}
}

function Set-Busy([bool]$busy) {
    foreach ($b in $bExe, $bMod, $bBoth, $chk) { $b.Enabled = -not $busy }
    $form.UseWaitCursor = $busy
}

function Show-Error([string]$text) {
    $lbl.ForeColor = $red
    $lbl.Text = $text
    [Media.SystemSounds]::Hand.Play()
}

function Start-Build([string]$target) {
    if ($script:proc -and -not $script:proc.HasExited) { return }
    if (-not (Test-Path -LiteralPath $buildScript)) { Show-Error "Нет файла $buildScript"; return }

    # проверка синтаксиса build.ps1 этой же версией PowerShell
    $tok = $null; $perr = $null
    [void][Management.Automation.Language.Parser]::ParseFile($buildScript, [ref]$tok, [ref]$perr)
    if ($perr -and $perr.Count) {
        Show-Error ("build.ps1, строка {0}: {1}" -f $perr[0].Extent.StartLineNumber, $perr[0].Message)
        return
    }

    foreach ($f in $resultFile, $patchFile, $errFile) {
        try { Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue } catch {}
    }
    $ps = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$buildScript`" -Target $target -FromGui"
    if (-not $chk.Checked) { $ps += ' -NoNinja' }
    # через cmd: если сборка упала (или скрипт не запустился), окно ждёт клавишу
    $cmdLine = "/s /c `"$ps || (pause & exit 1)`""

    $script:proc = Start-Process -FilePath 'cmd.exe' -ArgumentList $cmdLine -WorkingDirectory $repoDir -PassThru
    $null = $script:proc.Handle          # без этого ExitCode после выхода бывает пустым
    $script:t0 = Get-Date
    $script:target = $target
    Set-Busy $true
    $bOpen.Enabled = $false
    $lbl.ForeColor = $gray
    $lbl.Text = "Идёт сборка «$target»… ход — в окне консоли."
    $timer.Start()
}

$timer = New-Object Windows.Forms.Timer
$timer.Interval = 500
$timer.Add_Tick({
    if (-not $script:proc) { $timer.Stop(); return }
    $sec = [int]((Get-Date) - $script:t0).TotalSeconds
    if (-not $script:proc.HasExited) {
        $lbl.Text = "Идёт сборка «$($script:target)»… $sec с`nход — в окне консоли."
        return
    }
    $timer.Stop()
    Set-Busy $false
    $code = $script:proc.ExitCode
    $res = $null
    if (Test-Path -LiteralPath $resultFile) {
        $res = Get-Content -LiteralPath $resultFile -Encoding UTF8 -TotalCount 1
    }
    if ($code -eq 0 -and $res -and (Test-Path -LiteralPath $res)) {
        $script:lastResult = $res
        $size = (Get-Item -LiteralPath $res).Length / 1MB
        $lbl.ForeColor = $green
        $lbl.Text = ("Готово за {0} с:`n{1}  ({2:N1} МБ)" -f $sec, (Split-Path $res -Leaf), $size)
        if (Test-Path -LiteralPath $patchFile) {
            $pz = Get-Content -LiteralPath $patchFile -Encoding UTF8 -TotalCount 1
            if ($pz -and (Test-Path -LiteralPath $pz)) {
                $psize = (Get-Item -LiteralPath $pz).Length / 1MB
                $lbl.Text += ("`nпатч: {0}  ({1:N1} МБ)" -f (Split-Path $pz -Leaf), $psize)
            }
        }
        $bOpen.Enabled = $true
        [Media.SystemSounds]::Asterisk.Play()
    } else {
        $why = $null
        if (Test-Path -LiteralPath $errFile) { $why = (Get-Content -LiteralPath $errFile -Raw -Encoding UTF8).Trim() }
        if (-not $why) { $why = 'скрипт не запустился — подробности в «Журнал» или в окне консоли' }
        Show-Error "Ошибка «$($script:target)» (код $code):`n$why"
    }
    Update-Title
})

$bExe.Add_Click({ Start-Build 'Exe' })
$bMod.Add_Click({ Start-Build 'Mod' })
$bBoth.Add_Click({ Start-Build 'Both' })

$bOpen.Add_Click({
    if ($script:lastResult -and (Test-Path -LiteralPath $script:lastResult)) {
        Start-Process explorer.exe "/select,`"$($script:lastResult)`""
    }
})
$bDist.Add_Click({
    if (-not (Test-Path -LiteralPath $distDir)) { New-Item -ItemType Directory -Force -Path $distDir | Out-Null }
    Start-Process explorer.exe "`"$distDir`""
})
$bLog.Add_Click({
    if (Test-Path -LiteralPath $logFile) { Start-Process notepad.exe "`"$logFile`"" }
    else { $lbl.ForeColor = $gray; $lbl.Text = "Журнала ещё нет ($logFile)." }
})
$bCfg.Add_Click({ Start-Process notepad.exe "`"$cfgPath`"" })

$form.Add_Shown({
    Update-Title
    if (Test-Path -LiteralPath $resultFile) {
        $prev = Get-Content -LiteralPath $resultFile -Encoding UTF8 -TotalCount 1
        if ($prev -and (Test-Path -LiteralPath $prev)) {
            $script:lastResult = $prev
            $bOpen.Enabled = $true
            $lbl.Text = "Готово к сборке.`nПрошлый результат: $(Split-Path $prev -Leaf)"
        }
    }
})
$form.Add_FormClosing({
    if ($script:proc -and -not $script:proc.HasExited) {
        $r = [Windows.Forms.MessageBox]::Show('Сборка ещё идёт (окно консоли продолжит работу). Закрыть это окно?', 'OXCE HD', 'YesNo', 'Question')
        if ($r -ne 'Yes') { $_.Cancel = $true }
    }
})

[void]$form.ShowDialog()
