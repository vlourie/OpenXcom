# PreToolUse guard для команд оболочки: игра для проверки запускается только невидимо (R-124).
#
# Vitali трижды видел окно игры поверх своей работы: SDL показывает окно сам, мимо
# -WindowStyle Hidden и SW_HIDE. Невидимо - это отдельный рабочий стол (ai_probe.Hidden) плюс
# SDL_VIDEODRIVER=dummy; готовый запускатель tools/game_hidden.py.
#
# Останавливается:
#  - часть команды, которая запускает openxcom.exe сама (путь, Start-Process, & "...exe"),
#    если в ней нет SDL_VIDEODRIVER=dummy;
#  - запуск скрипта (.py/.ps1/.sh/.cmd), в тексте которого есть openxcom.exe, а нет ни
#    ai_probe.Hidden, ни game_hidden, ни SDL_VIDEODRIVER.*dummy.
# Пропускается: чтение (grep, cat, git ...), taskkill/tasklist/Get-Process/Stop-Process,
# и GAME_VISIBLE=1 в команде - когда Vitali САМ попросил показать игру.
#
# stdin: JSON события. Выход 0 = решение в stdout либо пропуск.
# Проверка: python tools/test_game_guard.py

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}

# в команде: сам exe, а не папка репозитория E:/OpenXCom
$Exe = '(?i)openxcom\.exe'
# в тексте скрипта: exe по имени и чем его запустить
$ExeFile = '(?i)openxcom\.exe'
$Launch = '(?i)(Start-Process|Popen|subprocess\.(run|call|check_call|check_output)|CreateProcess|os\.system|os\.startfile)'
$Safe = '(?i)(ai_probe\.Hidden|game_hidden|SDL_VIDEODRIVER.{0,6}dummy)'
# сборка и упаковка называют exe, а Start-Process у них - проводник и блокнот
$NoLaunch = '(?i)^(build|BuildGUI)\.ps1$'

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

function Test-Command([string]$cmd, [string]$cwd) {
    if (-not $cmd) { return $null }
    if ($cmd -match 'GAME_VISIBLE=1') { return $null }
    $readers = '(?i)^(grep|rg|cat|git|sed|awk|head|tail|less|more|wc|ls|find|echo|printf|diff|type|code|notepad|get-content|gc|select-string|sls|get-item|test-path|taskkill|tasklist|get-process|stop-process|get-ciminstance|gdb|objdump|nm|strings)(\.exe)?$'
    foreach ($seg in (Split-Command $cmd)) {
        $s = $seg.Trim()
        if (-not $s) { continue }
        # окружение вида A=b C=d перед командой пропускаем, чтобы найти первое слово
        $words = @($s -split '\s+' | Where-Object { $_ -notmatch '^[A-Za-z_][A-Za-z0-9_]*=' })
        if ($words.Count -eq 0) { continue }
        $first = $words[0].Trim('"', "'", '(', '&')
        if (-not $first -and $words.Count -gt 1) { $first = $words[1].Trim('"', "'", '(') }
        if ($first -match $readers) { continue }
        if ($s -match $Exe -and $s -notmatch $Safe) { return 'openxcom.exe' }
        foreach ($t in $words) {
            $t = $t.Trim('"', "'", '(', ')', '&')
            if ($t -notmatch '(?i)\.(py|ps1|sh|cmd|bat)$') { continue }
            $p = $t
            if (-not [IO.Path]::IsPathRooted($p) -and $cwd) { $p = Join-Path $cwd $p }
            if ($p -match '^/([a-zA-Z])/') { $p = $Matches[1] + ':' + $p.Substring(2) }
            if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { continue }
            $leaf = Split-Path $p -Leaf
            if ($leaf -match $NoLaunch) { continue }
            $text = [IO.File]::ReadAllText($p)
            if ($text -match $ExeFile -and $text -match $Launch -and $text -notmatch $Safe) { return $leaf }
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
        permissionDecisionReason = "Игру проверять только невидимо (R-124): $what запускает openxcom.exe с окном, которое Vitali увидит. Запускать через py -3.13 tools/game_hidden.py --out <png> --after 100 --clicks ... (отдельный рабочий стол + SDL_VIDEODRIVER=dummy) или ai_probe.Hidden для боя. Показать игру на экране можно только по просьбе самого Vitali - тогда GAME_VISIBLE=1 в начале команды."
    } } | ConvertTo-Json -Depth 5 -Compress
    exit 0
}
catch {
    exit 0
}
