# Слияние hd-render с MeridianOXC oxce-plus (OXCE 8.7.0, коммит cf59d42b2).
# Запуск:  powershell -ExecutionPolicy Bypass -File E:\OpenXCom\tools\merge\merge_upstream_87.ps1
# Отмена после запуска (пока слияние не закоммичено):  git merge --abort
# Полный откат после:  git reset --hard hd-render-before-8.7

$ErrorActionPreference = 'Stop'
$UpstreamUrl    = 'https://github.com/MeridianOXC/OpenXcom.git'
$UpstreamCommit = 'cf59d42b2e540bdffd127351ceba1641c1381a03'
$BackupBranch   = 'hd-render-before-8.7'
$ResolvedDir    = Join-Path $PSScriptRoot 'resolved_8.7'
$Repo           = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

# Конфликты, проверенные заранее: файл -> наша версия (blob), для которой готово решение
$Expected = @{
    'src/Basescape/CraftSoldiersState.cpp' = 'babdcfa0d756097c43a44906d88794cd566c382e'
    'src/Basescape/SoldiersState.cpp'      = 'c2acacb6f6dd7c3172ab30490ec84630d09e04d6'
    'src/Battlescape/Map.h'                = 'e051fcd7b9fdbc25a5f192d2b9fdfa81ee244823'
    'src/Engine/Screen.cpp'                = '4add5b3fa22d77dc8dbb6bb91e7c65931df2ac18'
    'src/version.h'                        = '5fc11b728a13b0d458c3f1b56de0130f958e6c1e'
    'src/OpenXcom.2010.vcxproj'            = '4c2a436d123cb7e15f40574980139028c20226d1'
}

function Gx {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $out = & $script:GitExe @args 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    return [pscustomobject]@{ Code = $code; Out = @($out) }
}
function Must($r, $what) { if ($r.Code -ne 0) { $r.Out | Write-Host; throw "$what (код $($r.Code))" } }
function Step($t) { Write-Host ''; Write-Host "== $t" -ForegroundColor Cyan }

try {
    Set-Location -LiteralPath $Repo
    $gc = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $gc) { throw 'git не найден в PATH' }
    $script:GitExe = $gc.Source

    $branch = (Gx rev-parse --abbrev-ref HEAD).Out[0]
    if ($branch -ne 'hd-render') { throw "Сейчас ветка '$branch', нужна hd-render" }
    if (Test-Path (Join-Path $Repo '.git\MERGE_HEAD')) { throw 'Уже идёт слияние. Закончи его или отмени: git merge --abort' }

    Step '1/4  Сохраняю текущую работу коммитом (src, tools, .gitignore, Выпуск + все изменённые файлы git)'
    $paths = @('src', 'tools', '.gitignore', 'Выпуск') | Where-Object { Test-Path (Join-Path $Repo $_) }
    Must (Gx add -A -- @paths) 'git add'
    # все уже отслеживаемые файлы с правками (например строки опций в bin\common\Language)
    Must (Gx add -u) 'git add -u'
    # крупные файлы (модели, картинки) в git не кладём
    $staged = (Gx diff --cached --name-only --diff-filter=AM).Out
    foreach ($f in $staged) {
        $p = Join-Path $Repo $f
        if ((Test-Path -LiteralPath $p) -and (Get-Item -LiteralPath $p).Length -gt 5MB) {
            Gx reset -q -- $f | Out-Null
            Write-Host "  пропущен (больше 5 МБ): $f" -ForegroundColor Yellow
        }
    }
    $count = @((Gx diff --cached --name-only).Out | Where-Object { $_ }).Count
    if ($count -gt 0) {
        Write-Host "  файлов в коммите: $count"
        Must (Gx commit -q -m 'HD render: local work before OXCE 8.7 merge') 'git commit'
    } else {
        Write-Host '  нечего коммитить'
    }

    Step "2/4  Резервная ветка $BackupBranch"
    Must (Gx branch -f $BackupBranch HEAD) 'git branch'
    Write-Host "  $((Gx rev-parse --short HEAD).Out[0])"

    Step '3/4  Скачиваю MeridianOXC oxce-plus'
    if ((Gx remote get-url upstream).Code -ne 0) { Must (Gx remote add upstream $UpstreamUrl) 'git remote add' }
    Must (Gx fetch upstream oxce-plus) 'git fetch upstream'
    Must (Gx cat-file -e "$UpstreamCommit^{commit}") 'нет коммита OXCE 8.7 после fetch'

    Step '4/4  Слияние'
    $m = Gx merge --no-edit -m 'Merge MeridianOXC oxce-plus (OXCE 8.7.0)' $UpstreamCommit
    if ($m.Code -eq 0) {
        Write-Host 'Слилось без конфликтов.' -ForegroundColor Green
    } else {
        $conflicts = @((Gx diff --name-only --diff-filter=U).Out | Where-Object { $_ })
        if ($conflicts.Count -eq 0) { $m.Out | Write-Host; throw 'git merge завершился с ошибкой' }
        $left = @()
        foreach ($c in $conflicts) {
            $ours = (Gx rev-parse ":2:$c").Out[0]
            $src = Join-Path $ResolvedDir ($c -replace '/', '\')
            if ($Expected.ContainsKey($c) -and $ours -eq $Expected[$c] -and (Test-Path -LiteralPath $src)) {
                Copy-Item -LiteralPath $src -Destination (Join-Path $Repo $c) -Force
                Must (Gx add -- $c) "git add $c"
                Write-Host "  решён: $c" -ForegroundColor Green
            } else {
                $left += $c
            }
        }
        if ($left.Count -gt 0) {
            Write-Host ''
            Write-Host 'Остались конфликты, которых не было в проверке:' -ForegroundColor Yellow
            $left | ForEach-Object { Write-Host "  $_" }
            Write-Host 'Слияние НЕ закоммичено. Напиши Claude — он посмотрит эти файлы.'
            Write-Host 'Отменить всё: git merge --abort'
            exit 2
        }
        Must (Gx commit -q --no-edit) 'git commit (слияние)'
        Write-Host 'Слияние закоммичено.' -ForegroundColor Green
    }

    Write-Host ''
    Write-Host "Готово: $((Gx log -1 --format='%h %s').Out[0])" -ForegroundColor Green
    Write-Host 'Дальше:  cd E:\OpenXCom\build-release ;  cmake .. ;  ninja'
    Write-Host "Откат при проблемах:  git reset --hard $BackupBranch"
    exit 0
}
catch {
    Write-Host ''
    Write-Host "ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
