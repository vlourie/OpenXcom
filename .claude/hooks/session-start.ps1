# SessionStart: подсовывает агенту грабли и карту проекта ДО первого действия.
# Это и есть защита от "захожу в комнату и наступаю на те же грабли".
# Вывод уходит в hookSpecificOutput.additionalContext -> попадает в контекст сессии.

$ErrorActionPreference = 'Stop'
# ответ хука читается как UTF-8; без этого PowerShell 5.1 пишет в кодировке консоли, и кириллица приходит знаками вопроса
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}
try {
    $root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
    Set-Location $root

    $lines = New-Object System.Collections.Generic.List[string]

    # --- 1. Индекс: пересобрать, если устарел -------------------------------
    # ?? недоступен в Windows PowerShell 5.1 — делаем совместимо
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
    if ($py -and (Test-Path 'tools/index_project.py')) {
        try {
            $out = & $py.Source tools/index_project.py --if-stale --quiet 2>&1 | Out-String
            if ($out.Trim()) { $lines.Add("КАРТА: " + $out.Trim()) }
        } catch { $lines.Add("КАРТА: индексатор не отработал — $_") }
    }

    if (Test-Path '.index/meta.json') {
        try {
            $meta = Get-Content '.index/meta.json' -Raw | ConvertFrom-Json
            $lines.Add("Карта проекта: .index/ — $($meta.files) файлов, $($meta.symbols) символов, собрана $($meta.built_human).")
            $lines.Add("Ищи символы грепом по .index/symbols.tsv, НЕ читай исходники целиком.")
            if (Test-Path '.index/files.md') { $lines.Add("Смысловые описания модулей: .index/files.md (черновик локальной модели, факты — только из symbols.tsv).") }
        } catch {}
    } else {
        $lines.Add("Карты проекта нет. Собрать: python tools/index_project.py")
    }

    # --- 2. Грабли ----------------------------------------------------------
    if ($py -and (Test-Path 'tools/rake.py')) {
        try {
            $rakes = & $py.Source tools/rake.py list 2>&1 | Out-String
            if ($rakes.Trim()) {
                $lines.Add("")
                $lines.Add("=== ГРАБЛИ ПРОЕКТА (docs/RAKES.md) ===")
                $lines.Add($rakes.Trim())
                $lines.Add("Наступил снова -> python tools/rake.py hit R-0NN. Новые -> python tools/rake.py add.")
                $lines.Add("Счётчик 2 и больше без защиты = обязан сделать тест или хук, а не ещё одну запись.")
            }
        } catch {}
    }

    if ($lines.Count -eq 0) { exit 0 }

    $payload = @{
        hookSpecificOutput = @{
            hookEventName     = 'SessionStart'
            additionalContext = ($lines -join "`n")
        }
    }
    $payload | ConvertTo-Json -Depth 5 -Compress
    exit 0
}
catch { exit 0 }   # хук никогда не роняет сессию
