# PostToolUse: после каждой записи в *.ps1 дописывает BOM и приводит к CRLF.
#
# Зачем: Windows PowerShell 5.1 читает файл без BOM как cp1251, и скрипт
# с кириллицей не запускается вообще (ParserError на разборе хеш-литералов).
# Грабли R-001. Текстового правила оказалось мало — здесь оно выполняется само.
#
# stdin: JSON события. Выход всегда 0 — хук не должен ронять сессию.

$ErrorActionPreference = 'Stop'
# ответ хука читается как UTF-8; без этого PowerShell 5.1 пишет в кодировке консоли, и кириллица приходит знаками вопроса
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}
try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $ev = $raw | ConvertFrom-Json

    $path = $null
    if ($ev.tool_input) {
        foreach ($k in 'file_path', 'path') {
            if ($ev.tool_input.PSObject.Properties.Name -contains $k) { $path = $ev.tool_input.$k; break }
        }
    }
    if (-not $path) { exit 0 }
    if ($path -notmatch '\.ps(m|d)?1$') { exit 0 }
    if (-not (Test-Path -LiteralPath $path)) { exit 0 }

    $bytes = [System.IO.File]::ReadAllBytes($path)
    if ($bytes.Length -eq 0) { exit 0 }

    $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    $body = if ($hasBom) { $bytes[3..($bytes.Length - 1)] } else { $bytes }

    $strict = New-Object System.Text.UTF8Encoding($false, $true)
    try { $text = $strict.GetString($body) } catch { exit 0 }

    $normalized = ($text -replace "`r`n", "`n") -replace "`n", "`r`n"
    if ($hasBom -and $normalized -eq $text) { exit 0 }

    [System.IO.File]::WriteAllText($path, $normalized, (New-Object System.Text.UTF8Encoding($true)))

    $out = @{
        hookSpecificOutput = @{
            hookEventName     = 'PostToolUse'
            additionalContext = "Файл '$path' пересохранён в UTF-8 с BOM и CRLF (грабли R-001). PowerShell 5.1 без BOM читает скрипт как cp1251 и падает на кириллице. Пиши .ps1 сразу с BOM."
        }
    }
    $out | ConvertTo-Json -Depth 5 -Compress
    exit 0
}
catch { exit 0 }
