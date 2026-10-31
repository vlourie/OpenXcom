# Грабли запуска игры

<!-- ГРАБЛИ НИЖЕ. Новые добавляются скриптом: python tools/rake.py add --area startup ... -->

## R-368  Master из аргументов не различает первый запуск и reload
Статус:   активны
Файлы:    src/Menu/StartState.cpp, src/Engine/Options.cpp, src/Engine/Game.cpp, tools/test_intro_startup.py
Симптом:  При запуске лаунчером с -master интро пропускалось даже с playIntro=true.
Причина:  Аргумент задаёт master до StartState; сравнение старого и нового master ложно и на первом запуске.
Правило:  Для первого запуска проверять !Options::reload; отдельно сохранять смену master, pending и playIntro, проверять реальное C++-условие и отрицательный контроль прежнего условия.
Защита:   tools/test_intro_startup.py
Наступал: 1   Последний: 2026-10-17

## R-369  Вложенный Windows PowerShell 5 наследует смешанный PSModulePath и теряет Get-FileHash
Статус:   активны
Файлы:    Выпуск/release.ps1
Симптом:  Первый запуск release.ps1 во вложенном Windows PowerShell 5 из Codex остановился: Get-FileHash не найден.
Причина:  Дочерний Windows PowerShell 5 наследовал смешанный PSModulePath PowerShell 7 и Windows PowerShell; проблема была в окружении запуска, не в исправлении интро.
Правило:  Перед таким запуском задать стандартный PSModulePath из путей WindowsPowerShell Modules в Program Files и System32, затем проверить Get-Command Get-FileHash. С этим окружением повторный выпуск завершился; кодовый guard в этой задаче не добавлялся.
Защита:   нет
Наступал: 1   Последний: 2026-10-17
