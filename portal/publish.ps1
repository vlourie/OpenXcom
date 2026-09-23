# Сборка лаунчера и bootstrapper'а (NativeAOT) в одну папку.
#   .\publish.ps1 -Out ..\dist\_launcher              - релиз, нужен prod-ключ в keys\release-keys.txt
#   .\publish.ps1 -Out ..\dist\_launcher -DevKeys     - локальная проверка на dev-ключе
# NativeAOT линкует через MSVC и ищет его vswhere'ом, а vswhere не в PATH (грабли R-002):
# скрипт находит оба инструмента сам и останавливается с понятной ошибкой, если чего-то нет.
param(
    [Parameter(Mandatory)] [string] $Out,
    [switch] $DevKeys
)
$ErrorActionPreference = 'Stop'

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw 'dotnet не найден: нужен .NET SDK 10 (global.json)' }
if (-not (Get-Command vswhere -ErrorAction SilentlyContinue)) {
    $installer = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer'
    if (-not (Test-Path (Join-Path $installer 'vswhere.exe'))) { throw "vswhere.exe не найден в $installer : нужна Visual Studio или Build Tools с C++" }
    $env:Path = "$installer;$env:Path"
}
$vs = vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'нет MSVC (VC.Tools.x86.x64): NativeAOT нечем линковать' }

$extra = @()
if ($DevKeys) { $extra += '-p:AllowDevKeys=true' }
$Out = [IO.Path]::GetFullPath([IO.Path]::Combine((Get-Location).Path, $Out))
foreach ($proj in 'src\Xp.Launcher', 'src\Xp.Bootstrapper') {
    dotnet publish (Join-Path $PSScriptRoot $proj) -c Release -r win-x64 -o $Out @extra
    if ($LASTEXITCODE -ne 0) { throw "сборка $proj упала" }
}
Get-ChildItem $Out -File | Where-Object { $_.Extension -in '.exe', '.dll' } |
    Format-Table Name, @{ n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } } -AutoSize
