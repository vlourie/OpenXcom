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
#   - sed -i и perl -i/-pi (правка файла на месте);
#   - подстановка sed ('s/../../') с косой и без -i - в конвейере или с > в файл.
# Там же R-037 (только для Bash): ключ windows-утилиты через одну косую (robocopy /E, taskkill /IM)
# Git Bash переводит в путь; просится //E или MSYS2_ARG_CONV_EXCL='*'.
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

    # подстановка sed с косой и без -i: в конвейере и с > в файл она так же пуста или портит (R-4 аудита);
    # адрес-регулярка на чтение (sed -n '/a\|b/p') не подстановка и не трогается
    foreach ($m in [regex]::Matches($cmd, '(^|[\s;&|(])sed\s+((?:[^|;&''"]|''[^'']*''|"[^"]*")*)')) {
        foreach ($q in [regex]::Matches($m.Groups[2].Value, '''([^'']*)''|"([^"]*)"')) {
            $s = $q.Groups[1].Value + $q.Groups[2].Value
            if ($s.Contains('\') -and $s -match '(^|[;{}\s\d$/])s([/|#,:@!])') { return 'sed s с косой' }
        }
    }
    return $null
}

# Грабли R-037 (семья R-090): Git Bash переводит ключ вида /E в путь E:/ ещё до запуска программы.
# Ключ windows-утилиты через одну косую - отдельным словом, не началом пути (/e/OpenXCom не ключ).
function Test-SlashFlags([string]$cmd) {
    if (-not $cmd -or $cmd -match 'MSYS2_ARG_CONV_EXCL') { return $null }
    # тело heredoc (сообщение коммита) и текст в кавычках - не команды
    $lines = New-Object Collections.Generic.List[string]
    $tag = $null
    foreach ($line in ($cmd -split "`n")) {
        if ($tag) { if ($line.Trim() -eq $tag) { $tag = $null }; continue }
        $lines.Add($line)
        $h = [regex]::Match($line, "<<-?[ \t]*(['""]?)([A-Za-z_][A-Za-z0-9_]*)\1")
        if ($h.Success) { $tag = $h.Groups[2].Value }
    }
    $bare = [regex]::Replace(($lines -join "`n"), '''[^'']*''|"[^"]*"', '""')
    $tools = 'robocopy|taskkill|tasklist|xcopy|reg|sc|schtasks|icacls|wmic|netsh|attrib|findstr|cmd|where|shutdown'
    foreach ($m in [regex]::Matches($bare, "(?i)(^|[\s;&|(])($tools)(\.exe)?\s+([^|;&\n]*)")) {
        $f = [regex]::Match($m.Groups[4].Value, '(?<![/\S])/[A-Za-z?][A-Za-z0-9]{0,11}(?=\s|:|$)')
        if ($f.Success) { return "$($m.Groups[2].Value) $($f.Value)" }
    }
    return $null
}

# Грабли R-184: питон без скрипта (python -, py -3.13 без аргументов) читает программу из stdin.
# Пустой heredoc или нет stdin вовсе - и у фоновой команды без консоли поднимается REPL, который
# печатает свою ошибку по кругу: гигабайты лога. Можно: конвейер в питон, < файл, непустой heredoc.
function Test-StdinPython([string]$cmd) {
    if (-not $cmd) { return $null }
    $lines = $cmd -split "`n"
    $rx = '(?i)(?:^|[;&|(])\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:\S*[/\\])?(python3?|py)(?:\.exe)?((?:\s+-(?:\d+(?:\.\d+)?|[uIBsSEOq]+))*)(\s+-)?(?=\s*(?:$|[;&|)<>]))'
    $tag = $null
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i].TrimEnd("`r")
        if ($tag) { if ($line.Trim() -eq $tag) { $tag = $null }; continue }
        foreach ($m in [regex]::Matches($line, $rx)) {
            $before = $line.Substring(0, $m.Index + 1).TrimEnd()
            $lead = $m.Value.TrimStart()
            if ($lead.StartsWith('|') -and -not $lead.StartsWith('||') -and -not $before.EndsWith('||')) { continue }   # конвейер в питон
            $rest = $line.Substring($m.Index + $m.Length)
            $h = [regex]::Match($rest, "^\s*<<-?[ \t]*(['""]?)([A-Za-z_][A-Za-z0-9_]*)\1")
            if ($h.Success) {
                $body = New-Object Collections.Generic.List[string]
                for ($j = $i + 1; $j -lt $lines.Count; $j++) {
                    if ($lines[$j].TrimEnd("`r").Trim() -eq $h.Groups[2].Value) { break }
                    $body.Add($lines[$j])
                }
                if ((($body -join '') -replace '\s', '') -eq '') { return "$($m.Groups[1].Value) с пустым heredoc" }
                continue
            }
            if ($rest -match '^\s*<') { continue }   # < файл, <<< строка
            return "$($m.Groups[1].Value)$($m.Groups[2].Value)$($m.Groups[3].Value) без stdin"
        }
        $hd = [regex]::Match($line, "<<-?[ \t]*(['""]?)([A-Za-z_][A-Za-z0-9_]*)\1")
        if ($hd.Success) { $tag = $hd.Groups[2].Value }
    }
    return $null
}

try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $ev = $raw | ConvertFrom-Json
    $cmd = $null
    if ($ev.tool_input -and ($ev.tool_input.PSObject.Properties.Name -contains 'command')) { $cmd = [string]$ev.tool_input.command }
    if ([string]$ev.tool_name -eq 'Bash') {
        $flag = Test-SlashFlags $cmd
        if ($flag) {
            @{ hookSpecificOutput = @{
                hookEventName            = 'PreToolUse'
                permissionDecision       = 'deny'
                permissionDecisionReason = "Грабли R-037: ключ '$flag' в Git Bash превратится в путь (/E -> E:/) ещё до запуска программы, и она получит испорченный аргумент. Пиши ключ через две косые (robocopy src dst //E, taskkill //IM x.exe //F) либо выстави MSYS2_ARG_CONV_EXCL='*' на эту команду."
            } } | ConvertTo-Json -Depth 5 -Compress
            exit 0
        }
    }
    $repl = Test-StdinPython $cmd
    if ($repl) {
        @{ hookSpecificOutput = @{
            hookEventName            = 'PreToolUse'
            permissionDecision       = 'deny'
            permissionDecisionReason = "Грабли R-184: $repl - питон возьмёт программу из stdin, а без неё поднимет REPL; у фоновой команды без консоли он пишет ошибку по кругу, гигабайты лога. Запиши скрипт инструментом Write и запусти по пути (py -3.13 путь)."
        } } | ConvertTo-Json -Depth 5 -Compress
        exit 0
    }
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
