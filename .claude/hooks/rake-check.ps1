# PreToolUse на Edit/Write: если по этому файлу уже есть грабли — показать их
# ПЕРЕД правкой. Режим предупреждения: не блокирует.
#
# Сделать жёстким: раскомментировать блок DENY ниже — тогда грабли со счётчиком
# 2 и больше запрещают правку, пока не будет написан тест.

$ErrorActionPreference = 'Stop'
# ответ хука читается как UTF-8; без этого PowerShell 5.1 пишет в кодировке консоли, и кириллица приходит знаками вопроса
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}
try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $ev = $raw | ConvertFrom-Json

    $path = $null
    if ($ev.tool_input) {
        foreach ($k in 'file_path','path','notebook_path') {
            if ($ev.tool_input.PSObject.Properties.Name -contains $k) { $path = $ev.tool_input.$k; break }
        }
    }
    if (-not $path) { exit 0 }

    $root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
    if (-not (Test-Path (Join-Path $root 'docs/RAKES.md'))) { exit 0 }
    Set-Location $root

    # ?? недоступен в Windows PowerShell 5.1 — делаем совместимо
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
    if (-not $py) { exit 0 }

    $rel = $path
    if ($rel.StartsWith($root)) { $rel = $rel.Substring($root.Length).TrimStart('\','/') }

    $hits = & $py.Source tools/rake.py match $rel 2>&1 | Out-String
    if (-not $hits.Trim()) { exit 0 }

    # журнал попаданий — видно, срабатывает ли система вообще
    $log = Join-Path $root '.index/rake-hits.log'
    if (Test-Path (Split-Path $log)) {
        Add-Content -LiteralPath $log -Value ("{0}`t{1}" -f (Get-Date -Format s), $rel) -Encoding UTF8
    }

    # --- DENY (жёсткий режим): раскомментировать при необходимости ---------
    # if ($hits -match '^\!\!') {
    #     @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'
    #        permissionDecision = 'deny'
    #        permissionDecisionReason = "На этом файле грабли со счётчиком 2+. Сначала тест.`n$hits" } } |
    #        ConvertTo-Json -Depth 5 -Compress
    #     exit 0
    # }

    @{ systemMessage = "ГРАБЛИ на $rel`n$($hits.Trim())" } | ConvertTo-Json -Depth 5 -Compress
    exit 0
}
catch { exit 0 }
