# Карта проекта

Вынесено из `CLAUDE.md` 26.10.2026: в стартовом контексте только правила, справка — здесь.

| Путь | Что там |
|---|---|
| `src/` | исходники движка. Всё новое — в `src/Engine/Hd*` |
| `src/Engine/HdCanvas.*` | RGBA-холст мира: блиты, палитровая LUT, span-таблицы |
| `src/Engine/HdSprites.*` | реестр HD-кадров, загрузка паков `hd/<набор>/<кадр>.png` |
| `src/Engine/HdUi*.*` | HD-интерфейс: зеркала виджетов, TTF-шрифты, векторный скин |
| `src/Engine/HdWorkers.*` | список команд рисования, исполняемый полосами на всех ядрах |
| `src/Engine/HdSmooth.*`, `HdBlit.*` | xBRZ-откат и масштабирование классических элементов |
| `src/Engine/HdTest.*` | дампы кадров по Ctrl+F8 для сравнения сборок |
| `src/Interface/` | классические виджеты; у каждого своё HD-зеркало (`hdMirror`) |
| `bin/UFO` | оригинальные данные DOS-версии — **только чтение** |
| `bin/common`, `bin/standard` | строки, шрифты, ванильные рулсеты — см. «Святое правило» в `CLAUDE.md` |
| `user/mods/hd` | единый HD-мод: паки, картинки, глобус. В гит не идёт |
| `art/` | вся графика: листы наборов, обмен с моделью, отчёты сверки. См. `art/README.md`. В гит не идёт |
| `tools/hdart/` | генерация HD-арта: `gen_hd.py`, `gen_all.ps1`, `build_pack.py`, `photo_ui.py`, `upscale_ui.py` |
| `tools/merge/` | слияние с upstream MeridianOXC, готовые решения конфликтов |
| `tools/build/` | сборка «в три кнопки» + упаковка Enigma Virtual Box |
| `tools/hdtest_compare.py` | сравнение дампов: тот самый тест на IDENTICAL |
| `build-release/` | каталог сборки Ninja + MinGW. В гит не идёт |
| `Пиратки/Dioxine_XPiratez/` | установка X-Piratez — **только чтение**, в гит не идёт |
| `portal/` | раздача: сайт, лаунчер, сборщик выпусков, установщик; документы — `docs/portal/` |
| `docs/ART_STATUS.md` | **что рисовать следующим** — считается с диска `tools/art_status.py`, руками не править |
| `census/` | перепись всех PCK и очередь по охвату карт; скрипты — `tools/pck_census.py`, `tools/pck_roadmap.py`. В гит не идёт |
| `docs/RAKES.md` | **грабли** — целиком не читать: `python tools/rake.py match <файл>`, `find <слово>`, `show R-0NN` |
| `docs/DECISIONS.md` | журнал решений — грепом по теме, целиком не читать |
| `.index/` | **карта символов** — `symbols.tsv`, `files.tsv`. Грепать, не читать исходники целиком |
| `.index/mod/Piratez/rul/` | рулсеты Пираток после слияния: `values.tsv` (итог поля), `refs.tsv`, битые ссылки. Строит `tools/rul_map.py`, справка `docs/research/piratez-ruleset.md` |
