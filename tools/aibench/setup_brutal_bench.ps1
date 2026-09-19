# Сборка Brutal-OXCE с замером времени ИИ.
# Запуск:  powershell -ExecutionPolicy Bypass -File E:\OpenXCom\tools\aibench\setup_brutal_bench.ps1
# Требует MSYS2 в C:\msys64 (тот же тулчейн, что и основная сборка).

$ErrorActionPreference = "Stop"

$Root      = "E:\OpenXCom\BrutalAI"
$Src       = Join-Path $Root "src-brutal"
$BuildDir  = Join-Path $Root "build-release"
$Patch     = "E:\OpenXCom\tools\aibench\aibench.patch"
$MsysBin   = "C:\msys64\mingw64\bin"

Write-Host "== 0. Проверка инструментов ==" -ForegroundColor Cyan
if (-not (Test-Path $MsysBin)) { throw "Не найден MSYS2: $MsysBin" }
$env:Path = "$MsysBin;$env:Path"
foreach ($t in @("git", "cmake", "ninja", "g++")) {
    $c = Get-Command $t -ErrorAction SilentlyContinue
    if (-not $c) { throw "Не найден инструмент: $t" }
    Write-Host ("  {0,-6} {1}" -f $t, $c.Source)
}

Write-Host "== 1. Исходники ==" -ForegroundColor Cyan
if (-not (Test-Path $Src)) {
    git clone --depth 1 -b oxce-plus https://github.com/pwwwa/OpenXcom-Brutal-AI.git $Src
} else {
    Write-Host "  уже склонировано, пропускаю"
}

Write-Host "== 2. Патч замера ==" -ForegroundColor Cyan
Push-Location $Src
$already = git diff --stat
if ($already) {
    Write-Host "  рабочее дерево уже изменено, патч не применяю повторно"
} else {
    git apply --verbose $Patch
    Write-Host "  патч применён" -ForegroundColor Green
}
Pop-Location

Write-Host "== 3. Сборка ==" -ForegroundColor Cyan
if (-not (Test-Path $BuildDir)) { New-Item -ItemType Directory -Path $BuildDir | Out-Null }
Push-Location $BuildDir
cmake -G Ninja -DCMAKE_BUILD_TYPE=Release $Src
ninja
Pop-Location

Write-Host ""
Write-Host "Готово. Бинарник:" -ForegroundColor Green
Write-Host "  $BuildDir\bin\openxcom.exe"
Write-Host ""
Write-Host "Дальше:"
Write-Host "  1. Скопировать в bin\ данные игры (UFO или установку Пираток)."
Write-Host "  2. Запустить, включить Options > AI > Autoplay (Ctrl+A в бою)."
Write-Host "  3. Отыграть/отсмотреть 5-10 ходов, выйти."
Write-Host "  4. python E:\OpenXCom\tools\aibench\parse_aibench.py <путь к openxcom.log>"
