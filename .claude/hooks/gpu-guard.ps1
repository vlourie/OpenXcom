# PreToolUse guard для команд оболочки: видеокарта только через очередь tools/gpuq.py.
#
# Скрипт из tools/gpu_scripts.txt, запущенный напрямую, делит карту с тем, что идёт из
# очереди (оба ползут, R-073), либо заставляет очередь ждать его. Поэтому прямой запуск
# останавливается, а агенту подсказывается та же команда через gpuq.py add.
#
# Что считается запуском: интерпретатор (python, py, pythonw, accelerate, powershell, pwsh,
# в том числе с путём и .exe) и дальше в той же команде имя скрипта из списка; либо .ps1 из
# списка первым словом команды (& .\train_lora.ps1). Чтение файла (cat, grep, git diff) -
# не запуск и не трогается.
#
# Пропускается: команда с gpuq.py (это и есть постановка в очередь); --help, -h, --dry-run,
# -DryRun (карту не трогают); GPUQ_BYPASS=1 в команде - для подкоманд без модели.
#
# stdin: JSON события. Выход 0 = решение в stdout либо пропуск.
# Проверка: python tools/test_gpu_guard.py

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}

function Get-Scripts {
    $list = Join-Path $PSScriptRoot '..\..\tools\gpu_scripts.txt'
    Get-Content -LiteralPath $list -Encoding UTF8 |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith('#') }
}

function Test-Command([string]$cmd, [string[]]$scripts) {
    if (-not $cmd) { return $null }
    if ($cmd -match '(?i)gpuq\.py') { return $null }
    if ($cmd -match 'GPUQ_BYPASS=1') { return $null }
    if ($cmd -match '(?i)(\s|^)(--help|-h|--dry-run|-DryRun)(\s|$)') { return $null }

    $names = ($scripts | ForEach-Object { [regex]::Escape($_) }) -join '|'
    # имя скрипта - отдельным словом: test_map_paint.py не совпадает с map_paint.py
    $script = "[^\s;&|]*?(?<![A-Za-z0-9_.-])(?<n>$names)(?![A-Za-z0-9_])"
    # интерпретатор - словом или концом пути, но не внутри кавычек: grep -n "py" gen_hd.py не запуск
    $interp = '(?i)(^|[\s(/\\])(python3?|pythonw|py|accelerate|powershell|pwsh)(\.exe)?[''"]?\s+(\S+\s+)*?' + $script
    $direct = '^\(?\s*(&\s*)?[''"]?' + $script
    # команду режем на части; часть, которая только читает файлы, не запуск
    $readers = '(?i)^(grep|rg|cat|git|sed|awk|head|tail|less|more|wc|ls|find|echo|printf|diff|type|code|notepad|get-content|gc|select-string|sls|get-item|test-path)$'
    foreach ($seg in [regex]::Split($cmd, '&&|\|\||[;|\r\n]')) {
        $s = $seg.Trim()
        if (-not $s) { continue }
        $first = ($s -split '\s+')[0].Trim('"', "'", '(')
        if ($first -match $readers) { continue }
        $m = [regex]::Match($s, $interp)
        if ($m.Success) { return $m.Groups['n'].Value }
        $m = [regex]::Match($s, $direct)
        if ($m.Success) { return $m.Groups['n'].Value }
    }
    return $null
}

try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $ev = $raw | ConvertFrom-Json
    $cmd = $null
    if ($ev.tool_input -and ($ev.tool_input.PSObject.Properties.Name -contains 'command')) { $cmd = [string]$ev.tool_input.command }
    $what = Test-Command $cmd @(Get-Scripts)
    if (-not $what) { exit 0 }

    @{ hookSpecificOutput = @{
        hookEventName            = 'PreToolUse'
        permissionDecision       = 'deny'
        permissionDecisionReason = "Видеокарта только через очередь: $what грузит модель на карту. Поставь ту же команду в очередь: py -3 tools/gpuq.py add --name <имя> -- <интерпретатор> <скрипт> <ключи> (без перенаправления вывода: лог будет в .gpuq/logs/<номер>.log, смотреть gpuq.py log <номер>). Место в очереди называет Vitali; без его слова - в конец. Если эта подкоманда модель не грузит - допиши в начало команды GPUQ_BYPASS=1."
    } } | ConvertTo-Json -Depth 5 -Compress
    exit 0
}
catch {
    exit 0
}
