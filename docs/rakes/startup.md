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
