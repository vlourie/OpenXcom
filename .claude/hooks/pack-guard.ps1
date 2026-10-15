# PreToolUse guard для команд оболочки: папка HD-пака - только выход сборщика (Pipeline v2, семья R-087).
#
# Что лежит в user/mods/hd/hd (и в установке Пираток, и в репозитории), решает манифест
# art/manifest/build_manifest.json, байты - хранилище art/store. Скопированный руками файл - это файл
# без происхождения: следующая установка из манифеста его молча откатит, а проверка на станции не
# отличит его от принятого. Ставить - через tools/hdart/build_hd_pack.py (stage + install, или adopt
# --by <инструмент> для того, что уже записал прежний скрипт).
#
# Останавливается часть команды, которая упоминает папку пака (mods/hd/hd) и пишет в неё: cp, mv, rm,
# rsync, robocopy, xcopy, copy, move, ln, tee, Copy-Item, Move-Item, Remove-Item, New-Item,
# Set-Content, Out-File, перенаправление > в эту папку.
# Пропускается: чтение (ls, find, du, grep, cat, sha256sum ...), сам build_hd_pack.py, и копирование
# ИЗ папки пака в другое место (путь пака - первый, назначение - не пак).
#
# stdin: JSON события. Выход 0 = решение в stdout либо пропуск.
# Проверка: python tools/test_pack_guard.py

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}

$Pack = '(?i)mods[\\/]+hd[\\/]+hd([\\/]|\b|$)'
$Writers = '(?i)^(cp|mv|rm|rsync|robocopy|xcopy|copy|move|ln|tee|install|copy-item|cpi|move-item|mi|remove-item|ri|del|new-item|ni|set-content|sc|add-content|ac|out-file)(\.exe)?$'
$Readers = '(?i)^(grep|rg|cat|git|sed|awk|head|tail|less|more|wc|ls|dir|find|du|df|echo|printf|diff|type|get-content|gc|get-childitem|gci|select-string|sls|get-item|test-path|sha256sum|md5sum|certutil|file|stat|measure-object)(\.exe)?$'

function Split-Command([string]$cmd) {
    $parts = New-Object Collections.Generic.List[string]
    $cur = New-Object Text.StringBuilder
    $quote = [char]0
    for ($i = 0; $i -lt $cmd.Length; $i++) {
        $c = $cmd[$i]
        if ($quote -ne [char]0) {
            if ($c -eq $quote) { $quote = [char]0 }
            [void]$cur.Append($c)
            continue
        }
        if ($c -eq '"' -or $c -eq "'") { $quote = $c; [void]$cur.Append($c); continue }
        if ($c -eq ';' -or $c -eq '|' -or $c -eq '&' -or $c -eq "`r" -or $c -eq "`n") {
            if ($c -eq '&' -and -not ($i + 1 -lt $cmd.Length -and $cmd[$i + 1] -eq '&')) { [void]$cur.Append($c); continue }
            $parts.Add($cur.ToString()); [void]$cur.Clear()
            if ($i + 1 -lt $cmd.Length -and $cmd[$i + 1] -eq $c) { $i++ }
            continue
        }
        [void]$cur.Append($c)
    }
    $parts.Add($cur.ToString())
    return $parts
}

function Test-Command([string]$cmd) {
    if (-not $cmd) { return $null }
    foreach ($seg in (Split-Command $cmd)) {
        $s = $seg.Trim()
        if (-not $s -or $s -notmatch $Pack) { continue }
        if ($s -match '(?i)build_hd_pack\.py') { continue }
        # перенаправление вывода в папку пака - запись, чем бы ни была команда
        if ($s -match ('(?i)>{1,2}\s*["'']?[^\s"'']*' + 'mods[\\/]+hd[\\/]+hd')) { return $s }
        $words = @($s -split '\s+' | Where-Object { $_ -notmatch '^[A-Za-z_][A-Za-z0-9_]*=' })
        if ($words.Count -eq 0) { continue }
        $first = $words[0].Trim('"', "'", '(', '&')
        if ($first -match '(?i)^(sudo|command|builtin|exec)$' -and $words.Count -gt 1) { $first = $words[1].Trim('"', "'") }
        if ($first -match $Readers) { continue }
        if ($first -notmatch $Writers) { continue }
        # копирование ИЗ пака наружу: последний путь (назначение) не в паке
        $args2 = @($words | Select-Object -Skip 1 | Where-Object { $_ -notmatch '^-' })
        if ($first -match '(?i)^(cp|copy|copy-item|cpi|robocopy|xcopy|rsync)(\.exe)?$' -and $args2.Count -ge 2) {
            $dest = $args2[$args2.Count - 1]
            if ($first -match '(?i)^robocopy' ) { $dest = $args2[1] }
            if ($dest -notmatch $Pack) { continue }
        }
        return $s
    }
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
    if ($what.Length -gt 160) { $what = $what.Substring(0, 160) + '...' }

    @{ hookSpecificOutput = @{
        hookEventName            = 'PreToolUse'
        permissionDecision       = 'deny'
        permissionDecisionReason = "Папка HD-пака (mods/hd/hd) - только выход сборщика (Pipeline v2): '$what' пишет в неё мимо манифеста. Ставить через py -3.13 tools/hdart/build_hd_pack.py: из скрипта - stage() + save() + install(target, only=[...]); то, что уже записал прежний инструмент, - adopt --changed --by <инструмент> --note <зачем>; откатить - install --yes (вернёт по манифесту)."
    } } | ConvertTo-Json -Depth 5 -Compress
    exit 0
}
catch {
    exit 0
}
