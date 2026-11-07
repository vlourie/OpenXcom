# Сборка лаунчера и bootstrapper'а (NativeAOT) в одну папку.
#   .\publish.ps1 -Out ..\dist\_launcher              - релиз, нужен prod-ключ в keys\release-keys.txt
#   .\publish.ps1 -Out ..\dist\_launcher -DevKeys     - локальная проверка на dev-ключе
# Голос (раздел «Голос», docs/portal/VOICE_CHAT.md) входит всегда: рядом с exe ложатся livekit_ffi.dll
# и xpaudio.dll из third_party\voice (tools\voice_deps.py). Прототип с токеном из командной строки - только Debug.
# NativeAOT линкует через MSVC и ищет его vswhere'ом, а vswhere не в PATH (грабли R-002):
# скрипт находит оба инструмента сам и останавливается с понятной ошибкой, если чего-то нет.
param(
    [Parameter(Mandatory)] [string] $Out,
    [switch] $DevKeys
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw 'dotnet не найден: нужен .NET SDK 10 (global.json)' }
if (-not (Get-Command vswhere -ErrorAction SilentlyContinue)) {
    $installer = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer'
    if (-not (Test-Path (Join-Path $installer 'vswhere.exe'))) { throw "vswhere.exe не найден в $installer : нужна Visual Studio или Build Tools с C++" }
    $env:Path = "$installer;$env:Path"
}
$vs = vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'нет MSVC (VC.Tools.x86.x64): NativeAOT нечем линковать' }

# части голоса (third_party\voice) не в гите: до сборки - есть ли они и собраны ли из нынешних исходников,
# иначе в выпуск уйдёт xpaudio.dll без поздней заплатки miniaudio
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'py не найден: нужен Python 3 (py launcher) для проверки tools\voice_deps.py --check' }
& py -3.13 (Join-Path $PSScriptRoot '..\tools\voice_deps.py') --check
if ($LASTEXITCODE -ne 0) { throw 'части голоса не годятся для сборки лаунчера - выполните команду починки из строки выше' }

$extra = @()
if ($DevKeys) { $extra += '-p:AllowDevKeys=true' }
$Out = [IO.Path]::GetFullPath([IO.Path]::Combine((Get-Location).Path, $Out))
foreach ($proj in 'src\Xp.Launcher', 'src\Xp.Bootstrapper') {
    dotnet publish (Join-Path $PSScriptRoot $proj) -c Release -r win-x64 -o $Out @extra
    if ($LASTEXITCODE -ne 0) { throw "сборка $proj упала" }
}
# компилятор пишет в свойства исходное имя сборки: exe называет себя xp-bootstrap.dll (так его показывает VirusTotal).
# Строка той же длины меняется на месте; в UTF-16 это имя есть только в свойствах файла (InternalName и OriginalFilename)
function Set-ExeNameInVersionInfo([string] $Path) {
    $latin = [Text.Encoding]::GetEncoding(28591)
    $bytes = [IO.File]::ReadAllBytes($Path)
    $text = $latin.GetString($bytes)
    $name = [IO.Path]::GetFileNameWithoutExtension($Path)
    $dll = $latin.GetString([Text.Encoding]::Unicode.GetBytes("$name.dll"))
    $new = [Text.Encoding]::Unicode.GetBytes("$name.exe")
    $at = @(); $i = 0
    while (($i = $text.IndexOf($dll, $i, [StringComparison]::Ordinal)) -ge 0) { $at += $i; $i += $dll.Length }
    if ($at.Count -eq 0) { return }   # уже исправлен прошлым запуском, а dotnet publish файл не менял
    if ($at.Count -ne 2) { throw "$name.dll в $Path встречается $($at.Count) раз, ожидалось 2: свойства файла устроены иначе" }
    foreach ($p in $at) { [Array]::Copy($new, 0, $bytes, $p, $new.Length) }
    [IO.File]::WriteAllBytes($Path, $bytes)
}
# свойства файла видит игрок (Свойства - Подробно): название, компания и версия установщика = версии лаунчера
$lv = (Get-Item -LiteralPath (Join-Path $Out 'XPiratezLauncher.exe')).VersionInfo
foreach ($exe in 'XPiratezLauncher.exe', 'xp-bootstrap.exe') {
    Set-ExeNameInVersionInfo (Join-Path $Out $exe)
    $vi = (Get-Item -LiteralPath (Join-Path $Out $exe)).VersionInfo
    "{0}: {1} | {2} | {3} | {4}" -f $exe, $vi.FileDescription, $vi.CompanyName, $vi.FileVersion, $vi.OriginalFilename
    if ($vi.FileDescription -notlike 'X-Piratez HD*' -or $vi.CompanyName -ne 'X-Piratez HD' -or $vi.FileVersion -ne $lv.FileVersion -or $vi.OriginalFilename -ne $exe) {
        throw "у $exe чужие свойства файла: описание '$($vi.FileDescription)', компания '$($vi.CompanyName)', версия $($vi.FileVersion) (лаунчер $($lv.FileVersion)), имя $($vi.OriginalFilename)"
    }
}
if ((Get-Item -LiteralPath (Join-Path $Out 'xp-bootstrap.exe')).VersionInfo.Comments -notlike '*https://*') { throw 'в свойствах установщика нет ссылки на сайт' }
Get-ChildItem $Out -File | Where-Object { $_.Extension -in '.exe', '.dll' } |
    Format-Table Name, @{ n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } } -AutoSize
