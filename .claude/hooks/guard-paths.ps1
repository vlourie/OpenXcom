# PreToolUse guard: запрещает правки внутри game/ (оригинальные файлы игры)
# и в assets/00_raw (исходники правятся только человеком).
# stdin: JSON события. Выход 0 = разрешить, 2 = заблокировать.

$ErrorActionPreference = 'Stop'
try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $ev = $raw | ConvertFrom-Json

    $path = $null
    if ($ev.tool_input) {
        foreach ($k in 'file_path','path','notebook_path') {
            if ($ev.tool_input.PSObject.Properties.Name -contains $k) {
                $path = $ev.tool_input.$k; break
            }
        }
    }
    if (-not $path) { exit 0 }

    $norm = ($path -replace '\\', '/')

    $blocked = @(
        @{ pat = '(^|/)game/';            why = 'папка game/ — оригинальные файлы игры, только чтение' },
        @{ pat = '(^|/)assets/00_raw/';   why = 'assets/00_raw — исходники, правит только человек' }
    )

    foreach ($b in $blocked) {
        if ($norm -match $b.pat) {
            $out = @{
                hookSpecificOutput = @{
                    hookEventName          = 'PreToolUse'
                    permissionDecision     = 'deny'
                    permissionDecisionReason = "Запись в '$path' запрещена: $($b.why). См. CLAUDE.md."
                }
            }
            $out | ConvertTo-Json -Depth 5 -Compress
            exit 0
        }
    }
    exit 0
}
catch {
    # Хук не должен ронять сессию: при ошибке просто пропускаем.
    exit 0
}
