# PreToolUse guard для команд оболочки: перенос, копирование, удаление и обмер папок с соединениями (R-047).
#
# Рабочие папки боя стенда ИИ (oxce_ai_probe/arena_<тег>_*) и BrutalAI (user_pzs_wNN) держат
# соединение (junction) mods на установку Пираток. mv между дисками копирует и идёт по нему
# (15.10: 7 копий установки по 6 ГБ), rm -rf может уйти в цель, du считает игру заново.
#
# Останавливается часть команды mv / cp -r / rm -r / du / robocopy / rsync / tar / zip /
# Move-Item / Copy-Item / Remove-Item -Recurse, если любой её аргумент-путь (шаблоны раскрываются)
# сам соединение или содержит соединение на глубине до 3.
# Пропускается: rmdir (снимает связь, не заходя), JUNCTION_OK=1 в команде.
#
# stdin: JSON события. Выход 0 = решение в stdout либо пропуск.
# Проверка: python tools/test_junction_guard.py

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}

$Movers = '(?i)^(mv|cp|rm|du|robocopy|rsync|tar|zip|7z|move-item|mi|move|copy-item|cpi|copy|remove-item|ri|del|rd)(\.exe)?$'
# этим опасна только рекурсия: без -r они папку не трогают
$NeedRec = '(?i)^(cp|rm|copy-item|cpi|copy|remove-item|ri|del)(\.exe)?$'
$MaxDirs = 4000
$MaxDepth = 3
$ReparseFlag = [IO.FileAttributes]::ReparsePoint

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

function Split-Words([string]$s) {
    $out = New-Object Collections.Generic.List[string]
    foreach ($m in [regex]::Matches($s, '"[^"]*"|''[^'']*''|\S+')) { $out.Add($m.Value.Trim('"', "'")) }
    return $out
}

function To-WinPath([string]$p, [string]$cwd) {
    if ($p -match '^/([a-zA-Z])(/|$)') { $p = $Matches[1] + ':' + $p.Substring(2) }
    if ($p -match '^~') { return $null }
    if (-not [IO.Path]::IsPathRooted($p) -and $cwd) { $p = Join-Path $cwd $p }
    return $p
}

# первое соединение в папке (сама папка или внутри на глубине до MaxDepth), иначе $null
function Find-Reparse([string]$dir) {
    $di = New-Object IO.DirectoryInfo $dir
    if (($di.Attributes -band $ReparseFlag) -ne 0) { return $dir }
    $queue = New-Object Collections.Generic.Queue[object]
    $queue.Enqueue(@($di, 0))
    $seen = 0
    while ($queue.Count -gt 0) {
        $item = $queue.Dequeue()
        $d = $item[0]; $depth = $item[1]
        $seen++
        if ($seen -gt $MaxDirs) { return $null }
        try { $subs = $d.GetDirectories() } catch { continue }
        foreach ($s in $subs) {
            if (($s.Attributes -band $ReparseFlag) -ne 0) { return $s.FullName }
            if ($depth + 1 -lt $MaxDepth) { $queue.Enqueue(@($s, $depth + 1)) }
        }
    }
    return $null
}

function Test-Command([string]$cmd, [string]$cwd) {
    if (-not $cmd) { return $null }
    if ($cmd -match 'JUNCTION_OK=1') { return $null }
    foreach ($seg in (Split-Command $cmd)) {
        $s = $seg.Trim()
        if (-not $s) { continue }
        $words = @(Split-Words $s | Where-Object { $_ -notmatch '^[A-Za-z_][A-Za-z0-9_]*=' })
        # слова оболочки перед командой
        while ($words.Count -gt 0 -and $words[0] -match '^(do|then|else|time|nohup|exec|sudo|\{|\(|!)$') { $words = @($words | Select-Object -Skip 1) }
        if ($words.Count -lt 2) { continue }
        $first = $words[0].Trim('(', '&')
        if ($first -notmatch $Movers) { continue }
        $args_ = @($words | Select-Object -Skip 1)
        if ($first -match $NeedRec) {
            $rec = $false
            foreach ($a in $args_) {
                if (($a -cmatch '^-[a-zA-Z]{1,5}$' -and $a -cmatch '[rR]' -and $a -notmatch '(?i)^-force$') -or $a -match '(?i)^--recursive$' -or $a -match '(?i)^-(Recurse|r)$' -or $a -match '(?i)^/s$' -or $a -match '^-a') { $rec = $true }
            }
            if (-not $rec) { continue }
        }
        foreach ($a in $args_) {
            if ($a -match '^-' -or $a -match '^/[a-zA-Z]{1,3}$' -or $a -match '^//') { continue }
            if ($a -match '^[<>|]' -or $a -match '^\d?>') { continue }
            $p = To-WinPath $a $cwd
            if (-not $p) { continue }
            $hits = @()
            try { $hits = @(Get-Item -Path $p -Force -ErrorAction SilentlyContinue | Select-Object -First 60) } catch { $hits = @() }
            foreach ($h in $hits) {
                if (-not $h.PSIsContainer) { continue }
                $j = Find-Reparse $h.FullName
                if ($j) { return "$first $a -> соединение $j" }
            }
        }
    }
    return $null
}

try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $ev = $raw | ConvertFrom-Json
    $cmd = $null
    if ($ev.tool_input -and ($ev.tool_input.PSObject.Properties.Name -contains 'command')) { $cmd = [string]$ev.tool_input.command }
    $cwd = if ($ev.cwd) { [string]$ev.cwd } else { (Get-Location).Path }
    $what = Test-Command $cmd $cwd
    if (-not $what) { exit 0 }

    @{ hookSpecificOutput = @{
        hookEventName            = 'PreToolUse'
        permissionDecision       = 'deny'
        permissionDecisionReason = "В папке соединение (R-047): $what. mv между дисками и cp -r скопируют цель соединения (установку игры), rm -r может уйти в неё, du посчитает её заново. Рабочие папки боя (arena_<тег>_*) не переносить - брать новый тег; соединение снимать только rmdir; переносить файлы, а не папки с соединением. Если точно понятно, что делаешь, - JUNCTION_OK=1 в начале команды."
    } } | ConvertTo-Json -Depth 5 -Compress
    exit 0
}
catch {
    exit 0
}
