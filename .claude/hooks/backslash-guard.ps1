# PreToolUse guard для команд оболочки: грабли R-035.
#
# Слой запуска команд схлопывает обратные косые ещё до оболочки, и встроенный скрипт
# получает не то, что написано: подстановка проходит с кодом 0 и ничего не меняет,
# либо портит файл (C#-литерал '\\' стал '\'). Поэтому встроенный скрипт с обратной
# косой не запускается вовсе: такой скрипт пишется файлом (Write) и запускается по пути.
#
# Что считается встроенным скриптом:
#   - тело heredoc (<<EOF ... EOF, <<'EOF', <<-EOF);
#   - код в -c / -e у python, py, perl, ruby, node;
#   - sed -i и perl -i/-pi (правка файла на месте).
# Косая в обычной команде (путь, регулярка grep) не трогается.
#
# stdin: JSON события. Выход 0 = решение в stdout либо пропуск.
# Проверка: python tools/test_backslash_guard.py

$ErrorActionPreference = 'Stop'
# ответ хука читается как UTF-8; без этого PowerShell 5.1 пишет в кодировке консоли, и кириллица приходит знаками вопроса
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}

function Test-Command([string]$cmd) {
    if (-not $cmd -or -not $cmd.Contains('\')) { return $null }

    # heredoc: всё от строки после маркера до строки с закрывающим маркером
    $hd = [regex]::Matches($cmd, "<<-?[ \t]*(['""]?)([A-Za-z_][A-Za-z0-9_]*)\1")
    foreach ($m in $hd) {
        $tag = $m.Groups[2].Value
        $start = $cmd.IndexOf("`n", $m.Index)
        if ($start -lt 0) { continue }
        $rest = $cmd.Substring($start + 1)
        $end = [regex]::Match($rest, "(?m)^[ \t]*$([regex]::Escape($tag))[ \t]*`r?$")
        $body = if ($end.Success) { $rest.Substring(0, $end.Index) } else { $rest }
        if ($body.Contains('\')) { return "heredoc <<$tag" }
    }

    # код прямо в командной строке интерпретатора
    if ($cmd -match '(?i)(^|[\s;&|(])(python3?|py|perl|ruby|node)(\.exe)?\s+(-[A-Za-z0-9.]+\s+)*-(c|e|E)\s') { return "$($Matches[2]) $($Matches[5])" }

    # правка файла на месте
    if ($cmd -match '(^|[\s;&|(])sed\s+(-[A-Za-z]*\s+)*-[A-Za-z]*i') { return 'sed -i' }
    if ($cmd -match '(^|[\s;&|(])perl\s+(-[A-Za-z]+\s+)*-[A-Za-z]*i') { return 'perl -i' }
    return $null
}

try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $ev = $raw | ConvertFrom-Json
    $cmd = $null
    if ($ev.tool_input -and ($ev.tool_input.PSObject.Properties.Name -contains 'command')) { $cmd = [string]$ev.tool_input.command }
    $what = Test-Command $cmd
    if (-not $what) { exit 0 }

    @{ hookSpecificOutput = @{
        hookEventName            = 'PreToolUse'
        permissionDecision       = 'deny'
        permissionDecisionReason = "Грабли R-035: обратная косая внутри встроенного скрипта ($what). Слой запуска схлопывает косые до оболочки, и замена молча становится пустой или портит файл. Запиши скрипт целиком инструментом Write в scratchpad и запусти по пути; правку исходника делай инструментом Edit."
    } } | ConvertTo-Json -Depth 5 -Compress
    exit 0
}
catch {
    # Хук не должен ронять сессию: при ошибке просто пропускаем.
    exit 0
}
