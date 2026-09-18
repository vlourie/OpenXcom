# PreToolUse guard для OXCE-HD.
#
# deny  — установленная игра, оригинальные данные и вывод сборки: туда не пишем никогда.
# ask   — данные игры из bin/common и bin/standard: правка разрешена, но только осознанно,
#         потому что её придётся переносить в установку Пираток (грабли R-003).
#
# stdin: JSON события. Выход 0 = решение в stdout либо пропуск.

$ErrorActionPreference = 'Stop'
try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $ev = $raw | ConvertFrom-Json

    $path = $null
    if ($ev.tool_input) {
        foreach ($k in 'file_path', 'path', 'notebook_path') {
            if ($ev.tool_input.PSObject.Properties.Name -contains $k) { $path = $ev.tool_input.$k; break }
        }
    }
    if (-not $path) { exit 0 }

    $norm = ($path -replace '\\', '/')

    $denied = @(
        @{ pat = '(^|/)Пиратки/';        why = 'установка X-Piratez — только чтение' },
        @{ pat = '(^|/)bin/UFO/';        why = 'оригинальные данные UFO — только чтение' },
        @{ pat = '(^|/)bin/TFTD/';       why = 'оригинальные данные TFTD — только чтение' },
        @{ pat = '(^|/)build-release/';  why = 'каталог сборки, переписывается ninja' },
        @{ pat = '(^|/)dist/';           why = 'готовые сборки, собираются скриптом' },
        @{ pat = '(^|/)game/';           why = 'ссылка на установленную игру — только чтение' }
    )

    foreach ($b in $denied) {
        if ($norm -match $b.pat) {
            @{ hookSpecificOutput = @{
                hookEventName            = 'PreToolUse'
                permissionDecision       = 'deny'
                permissionDecisionReason = "Запись в '$path' запрещена: $($b.why). См. CLAUDE.md."
            } } | ConvertTo-Json -Depth 5 -Compress
            exit 0
        }
    }

    $asked = @('(^|/)bin/common/', '(^|/)bin/standard/')
    foreach ($a in $asked) {
        if ($norm -match $a) {
            @{ hookSpecificOutput = @{
                hookEventName            = 'PreToolUse'
                permissionDecision       = 'ask'
                permissionDecisionReason = "Это данные игры ($path). По святому правилу (грабли R-003): предупредить Vitali до правки, перенести изменение в Пиратки\Dioxine_XPiratez\common и \standard, отдельно написать ему, чтобы повторил на второй машине. Подтверди, что все три шага будут сделаны."
            } } | ConvertTo-Json -Depth 5 -Compress
            exit 0
        }
    }
    exit 0
}
catch {
    # Хук не должен ронять сессию: при ошибке просто пропускаем.
    exit 0
}
