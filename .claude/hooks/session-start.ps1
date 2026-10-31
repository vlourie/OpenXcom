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

    # --- 2. Грабли: короткий индекс ------------------------------------------
    # Полный текст (docs/RAKES.md, 570+ КБ) в контекст не грузится (аудит кредитов 15.10.2026):
    # десять самых частых одной строкой плюс команды поиска по файлу и по теме.
    if ($py -and (Test-Path 'tools/rake.py')) {
        try {
            $rakes = & $py.Source tools/rake.py list --top 10 2>&1 | Out-String
            if ($rakes.Trim()) {
                $lines.Add("")
                $lines.Add("=== ГРАБЛИ ПРОЕКТА (docs/RAKES.md; целиком не читать) ===")
                $lines.Add($rakes.Trim())
                $lines.Add("Это только самые частые - они не заменяют относящиеся к задаче. Перед правкой файла: python tools/rake.py match <файл> (хук правки сам покажет до трёх правил). По теме: python tools/rake.py find <слово>. Запись целиком: python tools/rake.py show R-0NN.")
                $lines.Add("Наступил снова -> python tools/rake.py hit R-0NN. Новые -> python tools/rake.py add. Счётчик 2 и больше без защиты = тест или хук, а не ещё одна запись.")
            }
        } catch {}
    }

    # --- 3. Очередь правок игры: кто держит, что с выпуском ---------------------
    if (Test-Path 'tools/editq.py') {
        try {
            $q = & py -3 tools/editq.py brief 2>&1 | Out-String
            if ($q.Trim()) { $lines.Add(""); $lines.Add($q.Trim()) }
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
